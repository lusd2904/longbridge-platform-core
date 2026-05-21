from __future__ import annotations

import json
import logging
import math
import os
import re
import subprocess
import threading
import time
import copy
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional, Sequence


class LongbridgeCliError(RuntimeError):
    pass


@dataclass(frozen=True)
class CliConfig:
    region: str = "cn"


PAPER_ACCOUNT_CHANNEL = "lb_papertrading"
PAPER_ACCOUNT_NO_PREFIX = "LBPT"
LOGGER = logging.getLogger(__name__)
_AUTH_STATUS_CACHE_TTL_SECONDS = max(1, int(os.getenv("LONGBRIDGE_CLI_AUTH_CACHE_TTL_SECONDS", "60") or "60"))
_AUTH_STATUS_CACHE_LOCK = threading.RLock()
_AUTH_STATUS_CACHE: Dict[str, Any] = {"expires_at": 0.0, "payload": None}


def use_cli_runtime() -> bool:
    return True


def cli_binary() -> str:
    return str(os.getenv("LONGBRIDGE_CLI_BIN", "longbridge") or "longbridge").strip()


def _clean_env() -> Dict[str, str]:
    env = os.environ.copy()
    region = str(
        env.get("LONGBRIDGE_REGION")
        or env.get("LONGPORT_REGION")
        or env.get("REF_LONGBRIDGE_REGION")
        or "cn"
    ).strip().lower() or "cn"
    env["LONGBRIDGE_REGION"] = region
    env["LONGPORT_REGION"] = region
    env.setdefault("LONGPORT_PRINT_QUOTE_PACKAGES", "false")
    for key in (
        "LONGBRIDGE_APP_KEY",
        "LONGBRIDGE_APP_SECRET",
        "LONGBRIDGE_ACCESS_TOKEN",
        "LONGPORT_APP_KEY",
        "LONGPORT_APP_SECRET",
        "LONGPORT_ACCESS_TOKEN",
    ):
        env.pop(key, None)
    for key in ("all_proxy", "ALL_PROXY", "http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        env.pop(key, None)
    return env


def _extract_json(raw: str) -> Any:
    text = str(raw or "").strip()
    if not text:
        return None
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    starts = [idx for idx in (text.find("{"), text.find("[")) if idx >= 0]
    if not starts:
        raise LongbridgeCliError(f"长桥 CLI 未返回 JSON: {text[:300]}")
    start = min(starts)
    decoder = json.JSONDecoder()
    try:
        payload, _ = decoder.raw_decode(text[start:])
        return payload
    except json.JSONDecodeError as exc:
        raise LongbridgeCliError(f"长桥 CLI JSON 解析失败: {text[:300]}") from exc


def run_longbridge_cli(
    args: Sequence[Any],
    *,
    timeout: Optional[int] = None,
    expect_json: bool = True,
    require_paper_account: bool = True,
) -> Any:
    normalized_args = [str(item) for item in args if item not in (None, "")]
    if "--format" not in normalized_args:
        normalized_args.extend(["--format", "json"])

    if require_paper_account:
        ensure_paper_trading()

    completed = subprocess.run(
        [cli_binary(), *normalized_args],
        env=_clean_env(),
        text=True,
        capture_output=True,
        timeout=timeout or int(os.getenv("LONGBRIDGE_CLI_TIMEOUT", "45") or "45"),
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise LongbridgeCliError(f"长桥 CLI 调用失败: {' '.join(normalized_args)}: {detail}")
    if not expect_json:
        return completed.stdout
    return _extract_json(completed.stdout)


def auth_status() -> Dict[str, Any]:
    now = time.time()
    with _AUTH_STATUS_CACHE_LOCK:
        cached_payload = _AUTH_STATUS_CACHE.get("payload")
        if isinstance(cached_payload, dict) and float(_AUTH_STATUS_CACHE.get("expires_at") or 0.0) > now:
            return copy.deepcopy(cached_payload)

        payload = run_longbridge_cli(["auth", "status"], timeout=15, require_paper_account=False)
        normalized_payload = payload if isinstance(payload, dict) else {}
        _AUTH_STATUS_CACHE["payload"] = copy.deepcopy(normalized_payload)
        _AUTH_STATUS_CACHE["expires_at"] = time.time() + _AUTH_STATUS_CACHE_TTL_SECONDS
        return copy.deepcopy(normalized_payload)


def account_channel() -> str:
    payload = auth_status()
    account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
    return str(account.get("account_channel") or "").strip()


def account_no() -> str:
    payload = auth_status()
    account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
    return str(account.get("account_no") or "").strip()


def is_paper_account() -> bool:
    channel = account_channel()
    if channel == PAPER_ACCOUNT_CHANNEL:
        return True
    return account_no().upper().startswith(PAPER_ACCOUNT_NO_PREFIX)


def ensure_paper_trading() -> None:
    channel = account_channel()
    no = account_no()
    if not is_paper_account():
        raise LongbridgeCliError(
            f"当前长桥 CLI 账户不是模拟账户({PAPER_ACCOUNT_CHANNEL}/{PAPER_ACCOUNT_NO_PREFIX})，"
            f"已阻止长桥操作。当前通道: {channel or 'unknown'}，账户: {no or 'unknown'}"
        )


def _value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


class AttrObject(SimpleNamespace):
    def __iter__(self):
        return iter(vars(self).items())

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


def _to_attr(value: Any) -> Any:
    if isinstance(value, dict):
        return AttrObject(**{str(key): _to_attr(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_to_attr(item) for item in value]
    return value


def _number(value: Any) -> float:
    raw = getattr(value, "value", value)
    if raw in (None, ""):
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _name(value: Any) -> str:
    if value is None:
        return ""
    raw = getattr(value, "name", None)
    if raw not in (None, ""):
        return str(raw)
    raw = getattr(value, "value", None)
    if raw not in (None, ""):
        return str(raw)
    text = str(value)
    if "." in text:
        text = text.split(".")[-1]
    return text


def _period_arg(period: Any) -> str:
    token = _name(period).strip().lower().replace("-", "_")
    mapping = {
        "min_1": "1m",
        "min_5": "5m",
        "min_15": "15m",
        "min_30": "30m",
        "min_60": "1h",
        "60m": "1h",
        "hour": "1h",
        "day": "day",
        "d": "day",
        "week": "week",
        "w": "week",
        "month": "month",
        "m": "month",
        "year": "year",
        "y": "year",
    }
    return mapping.get(token, token or "day")


def _adjust_arg(adjust_type: Any) -> str:
    token = _name(adjust_type).strip().lower().replace("_", "")
    if token in {"forward", "forwardadjust"}:
        return "forward"
    return "none"


def _session_arg(trade_sessions: Any) -> str:
    token = _name(trade_sessions).strip().lower()
    return "intraday" if token == "intraday" else "all"


def _date_arg(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return datetime.now()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if "%H" in fmt else text[:10], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.now()


def _normalize_quote_item(item: Dict[str, Any]) -> AttrObject:
    data = dict(item)
    if "last_done" not in data and "last" in data:
        data["last_done"] = data.get("last")
    for nested_key in ("pre_market_quote", "post_market_quote", "overnight_quote"):
        nested = data.get(nested_key)
        if isinstance(nested, dict) and "last_done" not in nested and "last" in nested:
            nested["last_done"] = nested.get("last")
    last = _number(data.get("last_done"))
    prev_close = _number(data.get("prev_close"))
    if "change" not in data:
        data["change"] = last - prev_close if prev_close else 0
    if "change_percent" not in data:
        data["change_percent"] = ((last - prev_close) / prev_close * 100) if prev_close else 0
    return _to_attr(data)


def _normalize_candle_item(item: Dict[str, Any]) -> AttrObject:
    data = dict(item)
    timestamp = _parse_datetime(data.get("timestamp") or data.get("time") or data.get("date"))
    data.setdefault("timestamp", timestamp)
    data.setdefault("time", timestamp)
    return _to_attr(data)


def _fields_arg(indexes: Iterable[Any]) -> str:
    fields: List[str] = []
    for value in indexes or []:
        name = _name(value).strip()
        if not name:
            continue
        fields.append(name.replace("total_market_value", "mktcap"))
    return ",".join(fields or ["pe", "pb", "dps_rate", "turnover_rate", "mktcap"])


class CliQuoteContext:
    def __init__(self, config: Optional[CliConfig] = None, *args: Any, **kwargs: Any):
        self.config = config or CliConfig()
        self._callback_lock = threading.RLock()
        self._callbacks: Dict[str, Optional[Any]] = {
            "quote": None,
            "depth": None,
            "brokers": None,
            "trades": None,
            "candlestick": None,
        }
        self._subscriptions: Dict[str, set[str]] = {}
        self._candlestick_subscriptions: Dict[str, Dict[str, Any]] = {}

    def _set_callback(self, event_type: str, callback: Any = None, *args: Any, **kwargs: Any) -> None:
        handler = callback
        if handler is None and args:
            handler = args[0]
        if handler is None:
            handler = kwargs.get("callback") or kwargs.get("handler")
        with self._callback_lock:
            self._callbacks[event_type] = handler if callable(handler) else None

    def emit_push_event(self, event_type: str, *args: Any) -> None:
        with self._callback_lock:
            callback = self._callbacks.get(event_type)
        if not callable(callback):
            return
        try:
            callback(*args)
        except Exception:
            LOGGER.exception("CLI push callback failed: event_type=%s", event_type)

    @staticmethod
    def _normalize_symbol(symbol: Any) -> str:
        return str(symbol or "").strip().upper()

    @staticmethod
    def _normalize_sub_type(sub_type: Any) -> str:
        token = _name(sub_type).strip().lower()
        if token == "trade":
            return "trades"
        return token

    def quote(self, symbols: Iterable[str]) -> List[AttrObject]:
        payload = run_longbridge_cli(["quote", *list(symbols)])
        return [_normalize_quote_item(item) for item in payload or [] if isinstance(item, dict)]

    realtime_quote = quote

    def static_info(self, symbols: Iterable[str]) -> List[AttrObject]:
        return _to_attr(run_longbridge_cli(["static", *list(symbols)]) or [])

    def option_quote(self, symbols: Iterable[str]) -> List[AttrObject]:
        return _to_attr(run_longbridge_cli(["option", "quote", *list(symbols)]) or [])

    def warrant_quote(self, symbols: Iterable[str]) -> List[AttrObject]:
        return _to_attr(run_longbridge_cli(["warrant", "quote", *list(symbols)]) or [])

    def depth(self, symbol: str) -> Any:
        return _to_attr(run_longbridge_cli(["depth", symbol]))

    realtime_depth = depth

    def brokers(self, symbol: str) -> Any:
        return _to_attr(run_longbridge_cli(["brokers", symbol]))

    realtime_brokers = brokers

    def trades(self, symbol: str, count: int = 50) -> Any:
        return _to_attr(run_longbridge_cli(["trades", symbol, "--count", max(1, int(count or 50))]))

    realtime_trades = trades

    def intraday(self, symbol: str, **kwargs: Any) -> Any:
        args: List[Any] = ["intraday", symbol]
        trade_sessions = kwargs.get("trade_sessions")
        if trade_sessions is not None:
            args.extend(["--session", _session_arg(trade_sessions)])
        return _to_attr(run_longbridge_cli(args))

    def candlesticks(self, symbol: str, period: Any, count: int = 100, adjust_type: Any = None, **kwargs: Any) -> List[AttrObject]:
        args: List[Any] = [
            "kline",
            symbol,
            "--period",
            _period_arg(period),
            "--count",
            max(1, int(count or 100)),
            "--adjust",
            _adjust_arg(adjust_type),
        ]
        if kwargs.get("trade_sessions") is not None:
            args.extend(["--session", _session_arg(kwargs.get("trade_sessions"))])
        payload = run_longbridge_cli(args)
        return [_normalize_candle_item(item) for item in payload or [] if isinstance(item, dict)]

    realtime_candlesticks = candlesticks

    def history_candlesticks_by_date(
        self,
        symbol: str,
        period: Any,
        adjust_type: Any = None,
        start: Any = None,
        end: Any = None,
        **kwargs: Any,
    ) -> List[AttrObject]:
        args: List[Any] = ["kline", "history", symbol, "--period", _period_arg(period), "--adjust", _adjust_arg(adjust_type)]
        start_arg = _date_arg(start)
        end_arg = _date_arg(end)
        if start_arg:
            args.extend(["--start", start_arg])
        if end_arg:
            args.extend(["--end", end_arg])
        payload = run_longbridge_cli(args)
        return [_normalize_candle_item(item) for item in payload or [] if isinstance(item, dict)]

    def history_candlesticks_by_offset(
        self,
        symbol: str,
        period: Any,
        count: int = 100,
        adjust_type: Any = None,
        **kwargs: Any,
    ) -> List[AttrObject]:
        return self.candlesticks(symbol, period, count=count, adjust_type=adjust_type, **kwargs)

    def trading_session(self) -> Any:
        return _to_attr(run_longbridge_cli(["trading", "session"]))

    def trading_days(self, market: Any, start: Any, end: Any) -> Any:
        return _to_attr(run_longbridge_cli(["trading", "days", _name(market) or "US", "--start", _date_arg(start), "--end", _date_arg(end)]))

    def capital_flow(self, symbol: str) -> Any:
        return _to_attr(run_longbridge_cli(["capital", symbol, "--flow"]))

    def capital_distribution(self, symbol: str) -> Any:
        return _to_attr(run_longbridge_cli(["capital", symbol]))

    def calc_indexes(self, symbols: Iterable[str], indexes: Iterable[Any]) -> Any:
        return _to_attr(run_longbridge_cli(["calc-index", *list(symbols), "--fields", _fields_arg(indexes)]))

    def security_list(self, market: Any, **kwargs: Any) -> Any:
        return _to_attr(run_longbridge_cli(["security-list", _name(market) or "US"]))

    def market_temperature(self, market: Any) -> Any:
        return _to_attr(run_longbridge_cli(["market-temp", _name(market) or "HK"]))

    def history_market_temperature(self, market: Any, start: Any, end: Any) -> Any:
        return _to_attr(run_longbridge_cli(["market-temp", _name(market) or "HK", "--history", "--start", _date_arg(start), "--end", _date_arg(end)]))

    def option_chain_expiry_date_list(self, symbol: str) -> Any:
        return _to_attr(run_longbridge_cli(["option", "chain", symbol]))

    def option_chain_info_by_date(self, symbol: str, expiry_date: Any) -> Any:
        return _to_attr(run_longbridge_cli(["option", "chain", symbol, "--date", _date_arg(expiry_date)]))

    def warrant_issuers(self) -> Any:
        return _to_attr(run_longbridge_cli(["warrant", "issuers"]))

    def warrant_list(self, symbol: str, **kwargs: Any) -> Any:
        return _to_attr(run_longbridge_cli(["warrant", symbol]))

    def filings(self, symbol: str) -> Any:
        return _to_attr(run_longbridge_cli(["filing", symbol]))

    def participants(self) -> Any:
        return _to_attr(run_longbridge_cli(["participants"]))

    def set_on_quote(self, callback: Any = None, *args: Any, **kwargs: Any) -> None:
        self._set_callback("quote", callback, *args, **kwargs)

    def set_on_depth(self, callback: Any = None, *args: Any, **kwargs: Any) -> None:
        self._set_callback("depth", callback, *args, **kwargs)

    def set_on_brokers(self, callback: Any = None, *args: Any, **kwargs: Any) -> None:
        self._set_callback("brokers", callback, *args, **kwargs)

    def set_on_trades(self, callback: Any = None, *args: Any, **kwargs: Any) -> None:
        self._set_callback("trades", callback, *args, **kwargs)

    def set_on_candlestick(self, callback: Any = None, *args: Any, **kwargs: Any) -> None:
        self._set_callback("candlestick", callback, *args, **kwargs)

    def subscribe(self, symbols: Iterable[str], sub_types: Iterable[Any], *args: Any, **kwargs: Any) -> Any:
        normalized_symbols = [self._normalize_symbol(symbol) for symbol in symbols or [] if self._normalize_symbol(symbol)]
        normalized_sub_types = [self._normalize_sub_type(sub_type) for sub_type in sub_types or [] if self._normalize_sub_type(sub_type)]
        for symbol in normalized_symbols:
            current = self._subscriptions.setdefault(symbol, set())
            current.update(normalized_sub_types)
        return _to_attr(
            {
                "success": True,
                "mode": "cli-polling",
                "symbols": normalized_symbols,
                "sub_types": sorted(normalized_sub_types),
            }
        )

    def unsubscribe(self, symbols: Iterable[str], sub_types: Iterable[Any], *args: Any, **kwargs: Any) -> Any:
        normalized_symbols = [self._normalize_symbol(symbol) for symbol in symbols or [] if self._normalize_symbol(symbol)]
        normalized_sub_types = [self._normalize_sub_type(sub_type) for sub_type in sub_types or [] if self._normalize_sub_type(sub_type)]
        for symbol in normalized_symbols:
            current = self._subscriptions.get(symbol, set())
            current.difference_update(normalized_sub_types)
            if current:
                self._subscriptions[symbol] = current
            else:
                self._subscriptions.pop(symbol, None)
        return _to_attr(
            {
                "success": True,
                "mode": "cli-polling",
                "symbols": normalized_symbols,
                "sub_types": sorted(normalized_sub_types),
            }
        )

    def subscribe_candlesticks(self, symbol: str, period: Any, *args: Any, **kwargs: Any) -> Any:
        normalized_symbol = self._normalize_symbol(symbol)
        subscription_key = f"{normalized_symbol}:{_period_arg(period)}"
        self._candlestick_subscriptions[subscription_key] = {
            "symbol": normalized_symbol,
            "period": _period_arg(period),
            "trade_session": _session_arg(kwargs.get("trade_sessions")),
        }
        return _to_attr({"success": True, "mode": "cli-polling", "symbol": normalized_symbol, "period": _period_arg(period)})

    def unsubscribe_candlesticks(self, symbol: str, period: Any, *args: Any, **kwargs: Any) -> Any:
        normalized_symbol = self._normalize_symbol(symbol)
        self._candlestick_subscriptions.pop(f"{normalized_symbol}:{_period_arg(period)}", None)
        return _to_attr({"success": True, "mode": "cli-polling", "symbol": normalized_symbol, "period": _period_arg(period)})

    def subscriptions(self) -> List[Any]:
        payload: List[Dict[str, Any]] = []
        for symbol, sub_types in sorted(self._subscriptions.items()):
            payload.append({"symbol": symbol, "sub_types": sorted(sub_types)})
        return [_to_attr(item) for item in payload]


class CliContentContext:
    def __init__(self, config: Optional[CliConfig] = None, *args: Any, **kwargs: Any):
        self.config = config or CliConfig()

    def news(self, symbol: str) -> Any:
        return _to_attr(run_longbridge_cli(["news", symbol]))

    def topics(self, symbol: str) -> Any:
        return _to_attr(run_longbridge_cli(["topic", symbol]))


class PositionsResponse(AttrObject):
    def __iter__(self):
        return iter(self.positions)

    def __len__(self) -> int:
        return len(self.positions)


def _normalize_position(item: Dict[str, Any]) -> AttrObject:
    data = dict(item)
    data.setdefault("symbol_name", data.get("name") or data.get("symbol"))
    data.setdefault("available_quantity", data.get("available") or data.get("available_quantity"))
    data.setdefault("market_price", data.get("market_price") or data.get("cost_price") or 0)
    return _to_attr(data)


def _positions_response(items: List[Dict[str, Any]]) -> PositionsResponse:
    positions = [_normalize_position(item) for item in items if isinstance(item, dict)]
    channel = AttrObject(positions=positions)
    return PositionsResponse(channels=[channel], positions=positions)


def _normalize_asset(item: Dict[str, Any]) -> AttrObject:
    data = dict(item)
    data.setdefault("total_equity", data.get("net_assets"))
    data.setdefault("buying_power", data.get("buy_power"))
    data["cash_infos"] = [_to_attr(cash) for cash in data.get("cash_infos") or []]
    data["balances"] = [_to_attr(data)]
    return _to_attr(data)


def _normalize_order(item: Dict[str, Any]) -> AttrObject:
    data = dict(item)
    data.setdefault("quantity", data.get("submitted_quantity") or data.get("qty") or data.get("submitted_qty") or 0)
    data.setdefault("submitted_quantity", data.get("quantity"))
    data.setdefault("price", data.get("submitted_price") or data.get("price") or 0)
    data.setdefault("submitted_price", data.get("price"))
    data.setdefault("executed_quantity", data.get("filled_quantity") or data.get("executed_quantity") or 0)
    data.setdefault("filled_quantity", data.get("executed_quantity"))
    return _to_attr(data)


def _side_arg(side: Any) -> str:
    token = _name(side).strip().lower()
    if token in {"buy", "b"}:
        return "buy"
    if token in {"sell", "s"}:
        return "sell"
    return "buy" if "buy" in token else "sell"


def _order_type_arg(order_type: Any) -> str:
    token = _name(order_type).strip().upper()
    if token in {"MARKET", "MO"}:
        return "MO"
    if token in {"LIMIT", "LO", ""}:
        return "LO"
    return token


def _tif_arg(time_in_force: Any) -> str:
    token = _name(time_in_force).strip().lower()
    if token in {"goodtilcanceled", "gtc"}:
        return "gtc"
    if token in {"goodtildate", "gtd"}:
        return "gtd"
    return "day"


class CliTradeContext:
    def __init__(self, config: Optional[CliConfig] = None, *args: Any, **kwargs: Any):
        self.config = config or CliConfig()

    def stock_positions(self) -> PositionsResponse:
        payload = run_longbridge_cli(["positions"])
        return _positions_response(payload or [])

    def account_balance(self) -> List[AttrObject]:
        payload = run_longbridge_cli(["assets"])
        return [_normalize_asset(item) for item in payload or [] if isinstance(item, dict)]

    def today_orders(self) -> List[AttrObject]:
        payload = run_longbridge_cli(["order"])
        return [_normalize_order(item) for item in payload or [] if isinstance(item, dict)]

    def submit_order(
        self,
        *,
        symbol: str,
        order_type: Any,
        side: Any,
        submitted_quantity: Any,
        submitted_price: Any = None,
        time_in_force: Any = None,
        **kwargs: Any,
    ) -> AttrObject:
        ensure_paper_trading()
        side_arg = _side_arg(side)
        order_type_arg = _order_type_arg(order_type)
        args: List[Any] = [
            "order",
            side_arg,
            symbol,
            int(float(str(submitted_quantity))),
            "--order-type",
            order_type_arg,
            "--tif",
            _tif_arg(time_in_force),
            "--yes",
        ]
        if order_type_arg != "MO" and submitted_price not in (None, ""):
            args.extend(["--price", submitted_price])
        payload = run_longbridge_cli(args, timeout=60)
        return _to_attr(payload if isinstance(payload, dict) else {"order_id": str(payload), "status": "SUBMITTED"})

    def cancel_order(self, order_id: str, **kwargs: Any) -> Any:
        ensure_paper_trading()
        message = str(
            run_longbridge_cli(
                ["order", "cancel", order_id, "--yes"],
                timeout=60,
                expect_json=False,
            )
            or ""
        ).strip()
        return _to_attr(
            {
                "success": True,
                "order_id": order_id,
                "message": message or f"Order {order_id} cancel request accepted.",
            }
        )
