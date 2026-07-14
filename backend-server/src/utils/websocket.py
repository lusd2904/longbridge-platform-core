"""
WebSocket实时数据推送模块
支持股票行情实时订阅与后台推送
"""

import json
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime

from flask import Flask

try:
    from flask_sock import Sock
except Exception:  # pragma: no cover - 兼容未安装 Flask-Sock 的环境
    Sock = None

from config.settings import settings
from core.broker.BrokerInterface import get_broker_manager
from utils.redis_client import redis_client

logger = logging.getLogger(__name__)


class WebSocketManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.connections: dict[str, set] = {}
        self.user_connections: dict[str, set] = {}
        self.subscriptions: dict[object, dict[str, object]] = {}
        self.lock = threading.Lock()

    @staticmethod
    def _normalize_symbols(symbols: list | None) -> list:
        normalized = []
        for symbol in symbols or []:
            value = str(symbol or "").strip().upper()
            if value and value not in normalized:
                normalized.append(value)
        return normalized

    def register(self, ws, symbols: list = None, user_id: str = None):
        """注册 WebSocket 连接。"""
        normalized_symbols = self._normalize_symbols(symbols)
        normalized_user_id = str(user_id) if user_id not in (None, "") else None

        with self.lock:
            self.subscriptions[ws] = {"symbols": normalized_symbols, "user_id": normalized_user_id}

            for symbol in normalized_symbols:
                self.connections.setdefault(symbol, set()).add(ws)

            if normalized_user_id:
                self.user_connections.setdefault(normalized_user_id, set()).add(ws)

        logger.info("WebSocket连接注册: user=%s, symbols=%s", normalized_user_id, normalized_symbols)

    def unregister(self, ws, symbols: list = None, user_id: str = None):
        """注销 WebSocket 连接。"""
        with self.lock:
            subscription = self.subscriptions.get(ws, {})
            normalized_symbols = self._normalize_symbols(symbols) or subscription.get("symbols", [])
            normalized_user_id = str(user_id) if user_id not in (None, "") else subscription.get("user_id")

            for symbol in normalized_symbols:
                if symbol in self.connections:
                    self.connections[symbol].discard(ws)
                    if not self.connections[symbol]:
                        del self.connections[symbol]

            if normalized_user_id and normalized_user_id in self.user_connections:
                self.user_connections[normalized_user_id].discard(ws)
                if not self.user_connections[normalized_user_id]:
                    del self.user_connections[normalized_user_id]

            self.subscriptions.pop(ws, None)

        logger.info("WebSocket连接注销: user=%s", normalized_user_id)

    def get_subscribed_symbols(self) -> list:
        with self.lock:
            return sorted(self.connections.keys())

    def get_user_symbol_map(self) -> dict[str | None, set[str]]:
        """按用户聚合当前订阅的股票代码。"""
        aggregated: dict[str | None, set[str]] = defaultdict(set)
        with self.lock:
            subscriptions = list(self.subscriptions.values())

        for item in subscriptions:
            user_id = item.get("user_id")
            symbols = item.get("symbols") or []
            aggregated[user_id].update(symbols)
        return aggregated

    def broadcast_to_symbol(self, symbol: str, data: dict):
        """向订阅某个股票的所有连接广播消息。"""
        with self.lock:
            connections = self.connections.get(symbol, set()).copy()

        message = json.dumps({"type": "quote", "symbol": symbol, "data": data, "timestamp": datetime.now().isoformat()})

        dead_connections = set()
        for ws in connections:
            try:
                ws.send(message)
            except Exception as exc:
                logger.error("发送消息失败: %s", exc)
                dead_connections.add(ws)

        for ws in dead_connections:
            self.unregister(ws)

    def broadcast_to_user(self, user_id: str, data: dict):
        """向特定用户的所有连接发送消息。"""
        with self.lock:
            connections = self.user_connections.get(str(user_id), set()).copy()

        message = json.dumps({"type": "notification", "data": data, "timestamp": datetime.now().isoformat()})

        dead_connections = set()
        for ws in connections:
            try:
                ws.send(message)
            except Exception as exc:
                logger.error("发送消息失败: %s", exc)
                dead_connections.add(ws)

        for ws in dead_connections:
            self.unregister(ws)

    def broadcast_all(self, data: dict):
        """向所有连接广播消息。"""
        with self.lock:
            all_connections = set()
            for conns in self.connections.values():
                all_connections.update(conns)

        message = json.dumps({"type": "broadcast", "data": data, "timestamp": datetime.now().isoformat()})

        for ws in all_connections:
            try:
                ws.send(message)
            except Exception as exc:
                logger.error("广播消息失败: %s", exc)

    def get_stats(self) -> dict:
        """获取 WebSocket 统计信息。"""
        with self.lock:
            return {
                "total_symbol_subscriptions": len(self.connections),
                "total_user_connections": len(self.user_connections),
                "symbols": list(self.connections.keys()),
                "connection_counts": {symbol: len(conns) for symbol, conns in self.connections.items()},
            }


ws_manager = WebSocketManager()


def init_websocket(app: Flask):
    """
    初始化 WebSocket。
    未安装 Flask-Sock 或关闭开关时自动跳过。
    """
    if not settings.WEBSOCKET_ENABLED:
        logger.info("WebSocket 已关闭")
        return None

    if Sock is None:
        logger.warning("未安装 Flask-Sock，WebSocket 路由将跳过初始化")
        return None

    sock = Sock(app)

    @sock.route("/ws")
    def websocket_handler(ws):
        logger.info("新的WebSocket连接")
        subscribed_symbols = []
        user_id = None

        try:
            while True:
                message = ws.receive()
                if message is None:
                    break

                try:
                    data = json.loads(message)
                    action = data.get("action")

                    if action == "subscribe":
                        symbols = data.get("symbols", [])
                        next_user_id = data.get("user_id")

                        if subscribed_symbols:
                            ws_manager.unregister(ws, subscribed_symbols, user_id)

                        subscribed_symbols = WebSocketManager._normalize_symbols(symbols)
                        user_id = next_user_id
                        ws_manager.register(ws, subscribed_symbols, user_id)

                        ws.send(
                            json.dumps(
                                {
                                    "type": "subscribed",
                                    "symbols": subscribed_symbols,
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )
                        )

                    elif action == "unsubscribe":
                        symbols = WebSocketManager._normalize_symbols(data.get("symbols", []))
                        ws_manager.unregister(ws, symbols, user_id)
                        subscribed_symbols = [s for s in subscribed_symbols if s not in symbols]
                        if subscribed_symbols:
                            ws_manager.register(ws, subscribed_symbols, user_id)

                        ws.send(
                            json.dumps(
                                {"type": "unsubscribed", "symbols": symbols, "timestamp": datetime.now().isoformat()}
                            )
                        )

                    elif action == "ping":
                        ws.send(json.dumps({"type": "pong", "timestamp": datetime.now().isoformat()}))

                    elif action == "get_stats":
                        ws.send(json.dumps({"type": "stats", "data": ws_manager.get_stats()}))
                except json.JSONDecodeError:
                    ws.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
        except Exception as exc:
            logger.error("WebSocket错误: %s", exc)
        finally:
            ws_manager.unregister(ws, subscribed_symbols, user_id)
            logger.info("WebSocket连接关闭")

    return sock


class QuotePusher:
    """行情推送器"""

    def __init__(self, ws_manager: WebSocketManager, interval_seconds: int | None = None):
        self.ws_manager = ws_manager
        self.running = False
        self.thread = None
        self.interval_seconds = max(1, int(interval_seconds or settings.WEBSOCKET_QUOTE_INTERVAL or 2))
        self.batch_size = 120
        self.last_push_at: str | None = None
        self.last_error: str = ""
        self._user_cursors: dict[str, int] = {}

    @staticmethod
    def _task_policy():
        from core.platform.SystemTaskService import SystemTaskService

        return SystemTaskService.get_policy("websocket_quote_stream")

    def _refresh_runtime_config(self) -> bool:
        from core.platform.SystemTaskService import SystemTaskService

        self.interval_seconds = max(
            1, SystemTaskService.get_interval("websocket_quote_stream", settings.WEBSOCKET_QUOTE_INTERVAL)
        )
        self.batch_size = max(20, SystemTaskService.get_batch_size("websocket_quote_stream", 120) or 120)
        return SystemTaskService.is_enabled("websocket_quote_stream", settings.WEBSOCKET_ENABLED)

    def get_runtime_status(self) -> dict:
        return {
            "running": bool(self.running),
            "intervalSeconds": int(self.interval_seconds),
            "batchSize": int(self.batch_size),
            "lastPushAt": self.last_push_at,
            "lastError": self.last_error or "",
            "taskPolicy": self._task_policy(),
        }

    def _slice_symbols(self, user_key: str, symbols: set[str]) -> list:
        ordered = sorted(symbols)
        if len(ordered) <= self.batch_size:
            return ordered

        cursor = self._user_cursors.get(user_key, 0) % len(ordered)
        batch = ordered[cursor : cursor + self.batch_size]
        if len(batch) < self.batch_size:
            batch.extend(ordered[: self.batch_size - len(batch)])
        self._user_cursors[user_key] = (cursor + self.batch_size) % len(ordered)
        return batch

    @staticmethod
    def _load_cached_quotes(symbols: list) -> dict[str, dict]:
        cached: dict[str, dict] = {}
        for symbol in symbols:
            value = redis_client.get_hot_json(f"quote:{symbol}")
            if isinstance(value, dict):
                cached[symbol] = value
        return cached

    @staticmethod
    def _normalize_quote(symbol: str, quote) -> dict | None:
        if quote is None:
            return None

        if isinstance(quote, dict):
            last_price = float(quote.get("last_price", 0) or 0)
            prev_close = float(quote.get("prev_close", 0) or 0)
            volume = int(quote.get("volume", 0) or 0)
            change_percent = quote.get("change_percent")
        else:
            last_price = float(getattr(quote, "last_price", 0) or 0)
            prev_close = float(getattr(quote, "prev_close", 0) or 0)
            volume = int(getattr(quote, "volume", 0) or 0)
            change_percent = getattr(quote, "change_percent", None)

        if change_percent is None:
            change_percent = ((last_price - prev_close) / prev_close * 100) if prev_close else 0

        return {
            "symbol": symbol,
            "last_price": last_price,
            "prev_close": prev_close,
            "volume": volume,
            "change_percent": float(change_percent or 0),
        }

    @staticmethod
    def _is_broker_connected(broker) -> bool:
        value = getattr(broker, "is_connected", False)
        return value() if callable(value) else bool(value)

    def start(self):
        """启动推送服务。"""
        if self.running or not settings.WEBSOCKET_ENABLED:
            return

        self.running = True
        self.thread = threading.Thread(target=self._push_loop, name="quote-pusher", daemon=True)
        self.thread.start()
        logger.info("行情推送服务启动")

    def stop(self):
        """停止推送服务。"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("行情推送服务停止")

    def _push_loop(self):
        while self.running:
            try:
                if not self._refresh_runtime_config():
                    time.sleep(2)
                    continue
                quotes = self._fetch_quotes()
                for symbol, data in quotes.items():
                    self.ws_manager.broadcast_to_symbol(symbol, data)
                self.last_push_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.last_error = ""
                time.sleep(self.interval_seconds)
            except Exception as exc:
                logger.error("推送循环错误: %s", exc)
                self.last_error = str(exc)
                time.sleep(max(2, self.interval_seconds))

    def _fetch_quotes(self) -> dict:
        user_symbol_map = self.ws_manager.get_user_symbol_map()
        if not user_symbol_map:
            return {}

        aggregated_quotes: dict[str, dict] = {}
        manager = get_broker_manager()

        for raw_user_id, symbols in user_symbol_map.items():
            if not symbols:
                continue

            user_id = int(raw_user_id) if raw_user_id and str(raw_user_id).isdigit() else None
            user_key = str(user_id or "anonymous")
            batch_symbols = self._slice_symbols(user_key, symbols)
            broker = manager.get_broker(user_id=user_id) if user_id is not None else manager.get_broker()
            if not broker:
                aggregated_quotes.update(self._load_cached_quotes(batch_symbols))
                continue

            try:
                if not self._is_broker_connected(broker) and not broker.connect():
                    aggregated_quotes.update(self._load_cached_quotes(batch_symbols))
                    continue
                quotes = broker.get_quote(batch_symbols) or {}
            except Exception as exc:
                logger.error("获取实时行情失败 user=%s symbols=%s error=%s", user_id, batch_symbols, exc)
                aggregated_quotes.update(self._load_cached_quotes(batch_symbols))
                continue

            for symbol in batch_symbols:
                quote = self._normalize_quote(symbol, quotes.get(symbol))
                if not quote:
                    continue
                aggregated_quotes[symbol] = quote
                redis_client.set_hot(f"quote:{symbol}", quote, expire=max(5, self.interval_seconds * 3))

        return aggregated_quotes

    def push_quote(self, symbol: str, data: dict):
        self.ws_manager.broadcast_to_symbol(symbol, data)


quote_pusher = QuotePusher(ws_manager)
