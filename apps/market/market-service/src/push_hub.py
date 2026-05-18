from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Iterable, List, Optional, Set

from fastapi import WebSocket

from apps.market.longbridge_shared import (
    PushCandlestickMode,
    QuoteContext,
    SubType,
    build_quote_context,
    parse_period,
    parse_sub_types,
    parse_trade_sessions,
    resolve_region,
    to_plain,
)

LOGGER = logging.getLogger(__name__)
HEARTBEAT_INTERVAL_SECONDS = 10.0
CLI_QUOTE_POLL_INTERVAL_SECONDS = 4.0
CLI_DEPTH_POLL_INTERVAL_SECONDS = 5.0
CLI_BROKERS_POLL_INTERVAL_SECONDS = 5.0
CLI_TRADES_POLL_INTERVAL_SECONDS = 5.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_symbols(values: Iterable[str]) -> List[str]:
    if isinstance(values, str):
        values = [values]
    items: List[str] = []
    for raw in values or []:
        for chunk in str(raw or "").split(","):
            symbol = _normalize_symbol(chunk)
            if symbol and symbol not in items:
                items.append(symbol)
    return items


def _normalize_subtypes(values: Iterable[str]) -> List[Any]:
    if isinstance(values, str):
        values = [values]
    parsed = parse_sub_types(values)
    return parsed or [SubType.Quote]


def _sub_type_name(value: Any) -> str:
    raw = str(getattr(value, "name", value) or "").strip().lower()
    if raw == "trade":
        return "trades"
    if raw == "broker":
        return "brokers"
    return raw


class LongbridgePushSession:
    def __init__(self, user_id: int, loop: asyncio.AbstractEventLoop):
        self.user_id = int(user_id)
        self.loop = loop
        self.region = resolve_region()
        self._op_lock = threading.RLock()
        self._connections: Set[WebSocket] = set()
        self._latest_events: Deque[Dict[str, Any]] = deque(maxlen=160)
        self._quote_subscriptions: Dict[str, Set[str]] = {}
        self._candlestick_subscriptions: Dict[str, Dict[str, str]] = {}
        self._ctx = build_quote_context(
            user_id=self.user_id,
            region=self.region,
            push_candlestick_mode=getattr(PushCandlestickMode, "Realtime", None),
        )
        self._cli_trade_count = 50
        self._cli_poller_thread: Optional[threading.Thread] = None
        self._cli_poller_stop = threading.Event()
        self._cli_poller_wakeup = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop = threading.Event()
        self._bind_callbacks()

    def _bind_callbacks(self) -> None:
        self._ctx.set_on_quote(lambda *args: self._handle_push("quote", *args))
        self._ctx.set_on_depth(lambda *args: self._handle_push("depth", *args))
        self._ctx.set_on_brokers(lambda *args: self._handle_push("brokers", *args))
        self._ctx.set_on_trades(lambda *args: self._handle_push("trades", *args))
        self._ctx.set_on_candlestick(lambda *args: self._handle_push("candlestick", *args))

    def _cli_polling_mode(self) -> bool:
        return str(self._ctx.__class__.__name__) == "CliQuoteContext"

    def _split_callback_args(self, args: tuple[Any, ...]) -> tuple[Optional[str], Any, Dict[str, Any]]:
        if not args:
            return None, None, {}

        if isinstance(args[0], str):
            symbol = _normalize_symbol(args[0])
            if len(args) == 2:
                return symbol, args[1], {}
            return symbol, list(args[1:]), {}

        payload = args[0] if len(args) == 1 else list(args)
        plain_payload = to_plain(payload)
        symbol = None
        meta: Dict[str, Any] = {}

        if isinstance(plain_payload, dict):
            candidate = plain_payload.get("symbol") or plain_payload.get("security")
            if candidate:
                symbol = _normalize_symbol(candidate)
        elif (
            isinstance(plain_payload, list)
            and plain_payload
            and isinstance(plain_payload[0], dict)
        ):
            candidate = plain_payload[0].get("symbol") or plain_payload[0].get("security")
            if candidate:
                symbol = _normalize_symbol(candidate)

        return symbol, payload, meta

    def _handle_push(self, event_type: str, *args: Any) -> None:
        symbol, payload, meta = self._split_callback_args(args)
        envelope = {
            "type": event_type,
            "channel": f"longbridge.push.{event_type}",
            "symbol": symbol,
            "receivedAt": _utc_now(),
            "userId": self.user_id,
            "payload": to_plain(payload),
            "meta": meta,
            "dataSource": "longbridge-push",
        }
        self._latest_events.appendleft(envelope)
        self._schedule_broadcast(envelope)

    def _has_cli_polling_targets(self) -> bool:
        return bool(self._quote_subscriptions)

    def _ensure_cli_poller(self) -> None:
        if not self._cli_polling_mode():
            return
        if not self._has_cli_polling_targets():
            self._stop_cli_poller()
            return
        thread = self._cli_poller_thread
        if thread is not None and thread.is_alive():
            self._cli_poller_wakeup.set()
            return
        self._cli_poller_stop.clear()
        self._cli_poller_wakeup.set()
        self._cli_poller_thread = threading.Thread(
            target=self._run_cli_poller,
            name=f"longbridge-cli-poller-{self.user_id}",
            daemon=True,
        )
        self._cli_poller_thread.start()
        LOGGER.info("Started Longbridge CLI poller: user_id=%s", self.user_id)

    def _stop_cli_poller(self) -> None:
        thread = self._cli_poller_thread
        if thread is None:
            return
        self._cli_poller_stop.set()
        self._cli_poller_wakeup.set()

    def _active_cli_targets(self) -> Dict[str, List[str]]:
        with self._op_lock:
            return {
                symbol: sorted(sub_types)
                for symbol, sub_types in self._quote_subscriptions.items()
                if sub_types
            }

    def _run_cli_poller(self) -> None:
        last_run: Dict[str, float] = {}
        interval_map = {
            "quote": CLI_QUOTE_POLL_INTERVAL_SECONDS,
            "depth": CLI_DEPTH_POLL_INTERVAL_SECONDS,
            "brokers": CLI_BROKERS_POLL_INTERVAL_SECONDS,
            "trades": CLI_TRADES_POLL_INTERVAL_SECONDS,
        }
        while not self._cli_poller_stop.is_set():
            targets = self._active_cli_targets()
            if not targets:
                break
            now = time.monotonic()
            target_symbols: Dict[str, List[str]] = {
                event_type: sorted({symbol for symbol, sub_types in targets.items() if event_type in sub_types})
                for event_type in interval_map
            }
            for event_type, symbols in target_symbols.items():
                if not symbols:
                    continue
                interval = interval_map[event_type]
                due_at = last_run.get(event_type, 0.0)
                if now - due_at < interval:
                    continue
                self._poll_cli_event_type(event_type, symbols)
                last_run[event_type] = time.monotonic()
            self._cli_poller_wakeup.wait(timeout=1.0)
            self._cli_poller_wakeup.clear()
        self._cli_poller_thread = None
        self._cli_poller_stop.clear()
        self._cli_poller_wakeup.clear()
        LOGGER.info("Stopped Longbridge CLI poller: user_id=%s", self.user_id)

    def _poll_cli_event_type(self, event_type: str, symbols: List[str]) -> None:
        try:
            if event_type == "quote":
                rows = self._ctx.realtime_quote(symbols) if hasattr(self._ctx, "realtime_quote") else self._ctx.quote(symbols)
                for row in rows or []:
                    symbol = _normalize_symbol(getattr(row, "symbol", None) or getattr(row, "security", None))
                    self._ctx.emit_push_event("quote", symbol, row)
                return
            for symbol in symbols:
                if event_type == "depth":
                    payload = self._ctx.realtime_depth(symbol) if hasattr(self._ctx, "realtime_depth") else self._ctx.depth(symbol)
                elif event_type == "brokers":
                    payload = self._ctx.realtime_brokers(symbol) if hasattr(self._ctx, "realtime_brokers") else self._ctx.brokers(symbol)
                elif event_type == "trades":
                    payload = self._ctx.realtime_trades(symbol, self._cli_trade_count) if hasattr(self._ctx, "realtime_trades") else self._ctx.trades(symbol, self._cli_trade_count)
                else:
                    continue
                self._ctx.emit_push_event(event_type, symbol, payload)
        except Exception as exc:
            LOGGER.warning(
                "Longbridge CLI polling failed: user_id=%s event_type=%s symbols=%s error=%s",
                self.user_id,
                event_type,
                symbols,
                exc,
            )

    def _emit_snapshot_events(self, snapshots: Dict[str, Any]) -> None:
        quote_rows = snapshots.get("quote")
        if isinstance(quote_rows, list):
            for row in quote_rows:
                symbol = _normalize_symbol(row.get("symbol") if isinstance(row, dict) else getattr(row, "symbol", None))
                if symbol:
                    self._handle_push("quote", symbol, row)
        for event_type in ("depth", "brokers", "trades"):
            event_map = snapshots.get(event_type)
            if not isinstance(event_map, dict):
                continue
            for symbol, payload in event_map.items():
                normalized_symbol = _normalize_symbol(symbol)
                if normalized_symbol:
                    self._handle_push(event_type, normalized_symbol, payload)

    def _build_snapshots(
        self,
        parsed_symbols: List[str],
        parsed_sub_types: List[Any],
        *,
        trade_count: int,
    ) -> Dict[str, Any]:
        snapshots: Dict[str, Any] = {}
        if SubType.Quote in parsed_sub_types and hasattr(self._ctx, "realtime_quote"):
            try:
                snapshots["quote"] = to_plain(self._ctx.realtime_quote(parsed_symbols))
            except Exception as exc:
                LOGGER.warning("Longbridge quote snapshot failed: user_id=%s symbols=%s error=%s", self.user_id, parsed_symbols, exc)
        if SubType.Depth in parsed_sub_types and hasattr(self._ctx, "realtime_depth"):
            depth_snapshots: Dict[str, Any] = {}
            for symbol in parsed_symbols:
                try:
                    depth_snapshots[symbol] = to_plain(self._ctx.realtime_depth(symbol))
                except Exception as exc:
                    LOGGER.warning("Longbridge depth snapshot failed: user_id=%s symbol=%s error=%s", self.user_id, symbol, exc)
            if depth_snapshots:
                snapshots["depth"] = depth_snapshots
        if SubType.Brokers in parsed_sub_types and hasattr(self._ctx, "realtime_brokers"):
            broker_snapshots: Dict[str, Any] = {}
            for symbol in parsed_symbols:
                try:
                    broker_snapshots[symbol] = to_plain(self._ctx.realtime_brokers(symbol))
                except Exception as exc:
                    LOGGER.warning("Longbridge brokers snapshot failed: user_id=%s symbol=%s error=%s", self.user_id, symbol, exc)
            if broker_snapshots:
                snapshots["brokers"] = broker_snapshots
        if SubType.Trade in parsed_sub_types and hasattr(self._ctx, "realtime_trades"):
            trade_snapshots: Dict[str, Any] = {}
            bounded_trade_count = max(1, min(int(trade_count or 50), 500))
            for symbol in parsed_symbols:
                try:
                    trade_snapshots[symbol] = to_plain(self._ctx.realtime_trades(symbol, bounded_trade_count))
                except Exception as exc:
                    LOGGER.warning("Longbridge trades snapshot failed: user_id=%s symbol=%s error=%s", self.user_id, symbol, exc)
            if trade_snapshots:
                snapshots["trades"] = trade_snapshots
        return snapshots

    def _schedule_broadcast(self, payload: Dict[str, Any]) -> None:
        if not self._connections:
            return
        future = asyncio.run_coroutine_threadsafe(self._broadcast(payload), self.loop)
        future.add_done_callback(lambda _: None)

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        stale: List[WebSocket] = []
        for websocket in list(self._connections):
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self._connections.discard(websocket)

    async def register_connection(self, websocket: WebSocket) -> None:
        self._connections.add(websocket)
        self._ensure_heartbeat()
        await websocket.send_json(
            {
                "type": "system",
                "channel": "longbridge.push.system",
                "receivedAt": _utc_now(),
                "userId": self.user_id,
                "payload": self.runtime(),
                "dataSource": "market-service",
            }
        )

    def unregister_connection(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)
        if not self._connections:
            self._stop_heartbeat()

    def _heartbeat_payload(self) -> Dict[str, Any]:
        return {
            "type": "system",
            "channel": "longbridge.push.system.heartbeat",
            "receivedAt": _utc_now(),
            "userId": self.user_id,
            "payload": {
                "kind": "heartbeat",
                "connectionCount": len(self._connections),
            },
            "dataSource": "market-service",
        }

    def _ensure_heartbeat(self) -> None:
        thread = self._heartbeat_thread
        if thread is not None and thread.is_alive():
            return
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._run_heartbeat,
            name=f"longbridge-heartbeat-{self.user_id}",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()

    def _run_heartbeat(self) -> None:
        while not self._heartbeat_stop.wait(timeout=HEARTBEAT_INTERVAL_SECONDS):
            if not self._connections:
                break
            self._schedule_broadcast(self._heartbeat_payload())
        self._heartbeat_thread = None
        self._heartbeat_stop.clear()

    def runtime(self) -> Dict[str, Any]:
        with self._op_lock:
            try:
                subscriptions = to_plain(self._ctx.subscriptions())
            except Exception as exc:
                subscriptions = {"error": str(exc)}
            return {
                "userId": self.user_id,
                "region": self.region,
                "connectionCount": len(self._connections),
                "quoteSubscriptions": {
                    symbol: sorted(sub_types)
                    for symbol, sub_types in self._quote_subscriptions.items()
                },
                "candlestickSubscriptions": self._candlestick_subscriptions,
                "subscriptions": subscriptions,
                "latestEvents": list(self._latest_events)[:20],
            }

    def subscribe(
        self,
        symbols: Iterable[str],
        sub_types: Iterable[str],
        *,
        trade_count: int = 50,
    ) -> Dict[str, Any]:
        parsed_symbols = _normalize_symbols(symbols)
        if not parsed_symbols:
            raise ValueError("至少需要一个 symbol")
        parsed_sub_types = _normalize_subtypes(sub_types)
        parsed_sub_type_names = sorted({_sub_type_name(item) for item in parsed_sub_types if _sub_type_name(item)})
        bounded_trade_count = max(1, min(int(trade_count or 50), 500))

        with self._op_lock:
            self._cli_trade_count = bounded_trade_count
            if not self._cli_polling_mode():
                self._ctx.subscribe(parsed_symbols, parsed_sub_types)
            else:
                self._ctx.subscribe(parsed_symbols, parsed_sub_types)
            for symbol in parsed_symbols:
                current = self._quote_subscriptions.setdefault(symbol, set())
                current.update(parsed_sub_type_names)

            snapshots = self._build_snapshots(
                parsed_symbols,
                parsed_sub_types,
                trade_count=bounded_trade_count,
            )
            if self._cli_polling_mode():
                self._ensure_cli_poller()
        if self._cli_polling_mode() and snapshots:
            self._emit_snapshot_events(snapshots)

        return {
            "symbols": parsed_symbols,
            "subTypes": parsed_sub_type_names,
            "snapshots": snapshots,
            "runtime": self.runtime(),
        }

    def unsubscribe(self, symbols: Iterable[str], sub_types: Iterable[str]) -> Dict[str, Any]:
        parsed_symbols = _normalize_symbols(symbols)
        if not parsed_symbols:
            raise ValueError("至少需要一个 symbol")
        parsed_sub_types = _normalize_subtypes(sub_types)
        parsed_sub_type_names = sorted({_sub_type_name(item) for item in parsed_sub_types if _sub_type_name(item)})

        with self._op_lock:
            if not self._cli_polling_mode():
                self._ctx.unsubscribe(parsed_symbols, parsed_sub_types)
            else:
                self._ctx.unsubscribe(parsed_symbols, parsed_sub_types)
            for symbol in parsed_symbols:
                current = self._quote_subscriptions.get(symbol, set())
                current.difference_update(parsed_sub_type_names)
                if current:
                    self._quote_subscriptions[symbol] = current
                else:
                    self._quote_subscriptions.pop(symbol, None)
            if self._cli_polling_mode() and not self._has_cli_polling_targets():
                self._stop_cli_poller()
        return {
            "symbols": parsed_symbols,
            "subTypes": parsed_sub_type_names,
            "runtime": self.runtime(),
        }

    def subscribe_candlesticks(
        self,
        symbol: str,
        period: str,
        *,
        trade_session: str = "all",
        snapshot_count: int = 60,
    ) -> Dict[str, Any]:
        normalized_symbol = _normalize_symbol(symbol)
        if not normalized_symbol:
            raise ValueError("symbol 不能为空")
        parsed_period = parse_period(period)
        parsed_trade_session = parse_trade_sessions(trade_session)

        kwargs: Dict[str, Any] = {}
        if parsed_trade_session is not None:
            kwargs["trade_sessions"] = parsed_trade_session

        with self._op_lock:
            self._ctx.subscribe_candlesticks(normalized_symbol, parsed_period, **kwargs)
            subscription_key = f"{normalized_symbol}:{period}"
            self._candlestick_subscriptions[subscription_key] = {
                "symbol": normalized_symbol,
                "period": str(period),
                "tradeSession": str(trade_session),
            }
            snapshots = []
            if hasattr(self._ctx, "realtime_candlesticks"):
                snapshots = to_plain(
                    self._ctx.realtime_candlesticks(
                        normalized_symbol,
                        parsed_period,
                        max(1, min(int(snapshot_count or 60), 500)),
                    )
                )
            return {
                "symbol": normalized_symbol,
                "period": period,
                "tradeSession": trade_session,
                "snapshots": snapshots,
                "runtime": self.runtime(),
            }

    def unsubscribe_candlesticks(self, symbol: str, period: str) -> Dict[str, Any]:
        normalized_symbol = _normalize_symbol(symbol)
        if not normalized_symbol:
            raise ValueError("symbol 不能为空")
        parsed_period = parse_period(period)

        with self._op_lock:
            self._ctx.unsubscribe_candlesticks(normalized_symbol, parsed_period)
            self._candlestick_subscriptions.pop(f"{normalized_symbol}:{period}", None)
            return {
                "symbol": normalized_symbol,
                "period": period,
                "runtime": self.runtime(),
            }


class LongbridgePushHub:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[int, LongbridgePushSession] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None:
            return self._loop
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise RuntimeError("Longbridge push loop 尚未初始化") from exc
        return self._loop

    def get_session(self, user_id: int) -> LongbridgePushSession:
        normalized_user_id = int(user_id)
        with self._lock:
            session = self._sessions.get(normalized_user_id)
            if session is None:
                session = LongbridgePushSession(normalized_user_id, self._get_loop())
                self._sessions[normalized_user_id] = session
            return session

    async def connect(self, user_id: int, websocket: WebSocket) -> LongbridgePushSession:
        session = self.get_session(user_id)
        await session.register_connection(websocket)
        return session

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        session = self._sessions.get(int(user_id))
        if session is None:
            return
        session.unregister_connection(websocket)

    def runtime(self, user_id: int) -> Dict[str, Any]:
        return self.get_session(user_id).runtime()

    def subscribe(
        self,
        user_id: int,
        symbols: Iterable[str],
        sub_types: Iterable[str],
        *,
        trade_count: int = 50,
    ) -> Dict[str, Any]:
        return self.get_session(user_id).subscribe(symbols, sub_types, trade_count=trade_count)

    def unsubscribe(self, user_id: int, symbols: Iterable[str], sub_types: Iterable[str]) -> Dict[str, Any]:
        return self.get_session(user_id).unsubscribe(symbols, sub_types)

    def subscribe_candlesticks(
        self,
        user_id: int,
        symbol: str,
        period: str,
        *,
        trade_session: str = "all",
        snapshot_count: int = 60,
    ) -> Dict[str, Any]:
        return self.get_session(user_id).subscribe_candlesticks(
            symbol,
            period,
            trade_session=trade_session,
            snapshot_count=snapshot_count,
        )

    def unsubscribe_candlesticks(self, user_id: int, symbol: str, period: str) -> Dict[str, Any]:
        return self.get_session(user_id).unsubscribe_candlesticks(symbol, period)


push_hub = LongbridgePushHub()
