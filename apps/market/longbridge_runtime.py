from __future__ import annotations

import math
import os
import threading
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from apps.market.longbridge_cli_runtime import (
    CliConfig,
    CliContentContext,
    CliQuoteContext,
    CliTradeContext,
    account_channel as cli_account_channel,
    account_no as cli_account_no,
    auth_status as cli_auth_status,
    ensure_paper_trading,
    run_longbridge_cli,
    use_cli_runtime,
)


class _EnumValue:
    def __init__(self, name: str, value: Optional[str] = None):
        self.name = name
        self.value = value or name

    def __str__(self) -> str:
        return self.name


class _EnumNamespace:
    def __getattr__(self, name: str) -> _EnumValue:
        value = _EnumValue(name)
        setattr(self, name, value)
        return value


Config = CliConfig
QuoteContext = CliQuoteContext
TradeContext = CliTradeContext
ContentContext = CliContentContext
SDK_PACKAGE = "longbridge-cli"

AdjustType = _EnumNamespace()
CalcIndex = _EnumNamespace()
Market = _EnumNamespace()
OrderSide = _EnumNamespace()
OrderStatus = _EnumNamespace()
OrderType = _EnumNamespace()
Period = _EnumNamespace()
PushBrokers = _EnumNamespace()
PushCandlestick = _EnumNamespace()
PushCandlestickMode = _EnumNamespace()
PushDepth = _EnumNamespace()
PushQuote = _EnumNamespace()
PushTrades = _EnumNamespace()
FilterWarrantExpiryDate = _EnumNamespace()
FilterWarrantInOutBoundsType = _EnumNamespace()
SecurityListCategory = _EnumNamespace()
SortOrderType = _EnumNamespace()
SubType = _EnumNamespace()
TimeInForceType = _EnumNamespace()
TradeSessions = _EnumNamespace()
WarrantSortBy = _EnumNamespace()
WarrantStatus = _EnumNamespace()
WarrantType = _EnumNamespace()

_QUOTE_CONTEXTS: Dict[Tuple[str, int, str, str], QuoteContext] = {}
_TRADE_CONTEXTS: Dict[Tuple[str, int, str, str], TradeContext] = {}
_CONTENT_CONTEXTS: Dict[Tuple[str, int, str, str], ContentContext] = {}
_CONTEXT_LOCK = threading.RLock()


def resolve_region() -> str:
    region = (
        os.getenv("LONGBRIDGE_REGION")
        or os.getenv("LONGPORT_REGION")
        or os.getenv("REF_LONGBRIDGE_REGION")
        or "cn"
    )
    return str(region).strip().lower() or "cn"


def resolve_endpoints(region: Optional[str] = None) -> Dict[str, str]:
    resolved = str(region or resolve_region()).strip().lower() or "cn"
    if resolved == "cn":
        return {
            "region": "cn",
            "http_url": "https://openapi.longbridge.cn",
            "quote_ws_url": "wss://openapi-quote.longbridge.cn/v2",
            "trade_ws_url": "wss://openapi-trade.longbridge.cn/v2",
        }
    return {
        "region": resolved,
        "http_url": "https://openapi.longbridge.com",
        "quote_ws_url": "wss://openapi-quote.longbridge.com/v2",
        "trade_ws_url": "wss://openapi-trade.longbridge.com/v2",
    }


def apply_region_env(region: Optional[str] = None) -> str:
    resolved = str(region or resolve_region()).strip().lower() or "cn"
    os.environ["LONGBRIDGE_REGION"] = resolved
    os.environ["LONGPORT_REGION"] = resolved
    os.environ.setdefault("LONGPORT_PRINT_QUOTE_PACKAGES", "false")
    return resolved


def cleared_proxy_env():
    class _NoopProxyContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    return _NoopProxyContext()


def build_sdk_config(*_legacy_args: Any, region: Optional[str] = None, push_candlestick_mode: Any = None, **_: Any) -> Config:
    return CliConfig(region=str(region or resolve_region()).strip().lower() or "cn")


def load_longbridge_credentials(user_id: int = 1) -> Optional[Dict[str, str]]:
    return {}


def _cache_mode_token(value: Any = None) -> str:
    if value is None:
        return ""
    raw = getattr(value, "value", None)
    if raw not in (None, ""):
        return str(raw)
    raw = getattr(value, "name", None)
    if raw not in (None, ""):
        return str(raw)
    return str(value)


def _cache_key(kind: str, user_id: int, region: Optional[str], mode: Any = None) -> Tuple[str, int, str, str]:
    resolved_region = str(region or resolve_region()).strip().lower() or "cn"
    return (kind, int(user_id), resolved_region, _cache_mode_token(mode))


def _build_cached_context(
    cache: Dict[Tuple[str, int, str, str], Any],
    key: Tuple[str, int, str, str],
    factory: Callable[[], Any],
):
    with _CONTEXT_LOCK:
        cached = cache.get(key)
        if cached is not None:
            return cached

        context = factory()
        cache[key] = context
        return context


def _invalidate_cached_context(cache: Dict[Tuple[str, int, str, str], Any], key: Tuple[str, int, str, str]) -> bool:
    with _CONTEXT_LOCK:
        return cache.pop(key, None) is not None


def _build_quote_context_from_cli(
    *,
    region: Optional[str] = None,
    push_candlestick_mode: Any = None,
) -> QuoteContext:
    key = _cache_key("quote", 0, region, push_candlestick_mode)

    def _factory() -> QuoteContext:
        return CliQuoteContext(CliConfig(region=str(region or resolve_region()).strip().lower() or "cn"))

    return _build_cached_context(_QUOTE_CONTEXTS, key, _factory)


def _build_trade_context_from_cli(*, region: Optional[str] = None) -> TradeContext:
    key = _cache_key("trade", 0, region)

    def _factory() -> TradeContext:
        return CliTradeContext(CliConfig(region=str(region or resolve_region()).strip().lower() or "cn"))

    return _build_cached_context(_TRADE_CONTEXTS, key, _factory)


def invalidate_quote_context(
    *,
    user_id: Optional[int] = None,
    region: Optional[str] = None,
    push_candlestick_mode: Any = None,
    **_: Any,
) -> bool:
    cache_identity = user_id
    if cache_identity is None:
        cache_identity = 0
    key = _cache_key("quote", int(cache_identity), region, push_candlestick_mode)
    return _invalidate_cached_context(_QUOTE_CONTEXTS, key)


def invalidate_trade_context(
    *,
    user_id: Optional[int] = None,
    region: Optional[str] = None,
    **_: Any,
) -> bool:
    cache_identity = user_id
    if cache_identity is None:
        cache_identity = 0
    key = _cache_key("trade", int(cache_identity), region)
    return _invalidate_cached_context(_TRADE_CONTEXTS, key)


def build_quote_context(
    user_id: int = 1,
    *,
    region: Optional[str] = None,
    push_candlestick_mode: Any = None,
) -> QuoteContext:
    return _build_cached_context(
        _QUOTE_CONTEXTS,
        _cache_key("quote", user_id, region, push_candlestick_mode),
        lambda: CliQuoteContext(CliConfig(region=str(region or resolve_region()).strip().lower() or "cn")),
    )


def build_trade_context(user_id: int = 1, *, region: Optional[str] = None) -> TradeContext:
    return _build_cached_context(
        _TRADE_CONTEXTS,
        _cache_key("trade", user_id, region),
        lambda: CliTradeContext(CliConfig(region=str(region or resolve_region()).strip().lower() or "cn")),
    )


def build_trade_context_from_cli(*, region: Optional[str] = None) -> TradeContext:
    return _build_trade_context_from_cli(region=region)


def build_quote_context_from_cli(
    *,
    region: Optional[str] = None,
    push_candlestick_mode: Any = None,
) -> QuoteContext:
    return _build_quote_context_from_cli(
        region=region,
        push_candlestick_mode=push_candlestick_mode,
    )


def build_trade_context_from_credentials(*_legacy_args: Any, region: Optional[str] = None, **_: Any) -> TradeContext:
    return build_trade_context_from_cli(region=region)


def build_quote_context_from_credentials(
    *_legacy_args: Any,
    region: Optional[str] = None,
    push_candlestick_mode: Any = None,
    **_: Any,
) -> QuoteContext:
    return build_quote_context_from_cli(region=region, push_candlestick_mode=push_candlestick_mode)


def build_content_context(user_id: int = 1, *, region: Optional[str] = None) -> ContentContext:
    return _build_cached_context(
        _CONTENT_CONTEXTS,
        _cache_key("content", user_id, region),
        lambda: CliContentContext(CliConfig(region=str(region or resolve_region()).strip().lower() or "cn")),
    )


def _enum_from_attr(enum_cls: Any, attr: str, fallback: Any = None) -> Any:
    if enum_cls is None:
        return fallback
    return getattr(enum_cls, attr, fallback)


def parse_market(value: Any) -> Any:
    if value is None or value == "":
        return _enum_from_attr(Market, "US", "US")
    if isinstance(Market, type) and isinstance(value, Market):  # type: ignore[arg-type]
        return value
    token = str(value).strip().upper()
    mapping = {
        "US": "US",
        "HK": "HK",
        "CN": "CN",
        "SG": "SG",
        "CRYPTO": "Crypto",
    }
    return _enum_from_attr(Market, mapping.get(token, token), token)


def parse_period(value: Any) -> Any:
    if value is None or value == "":
        return _enum_from_attr(Period, "Day", "Day")
    if isinstance(Period, type) and isinstance(value, Period):  # type: ignore[arg-type]
        return value
    token = str(value).strip().lower()
    mapping = {
        "1m": "Min_1",
        "1min": "Min_1",
        "2m": "Min_2",
        "3m": "Min_3",
        "5m": "Min_5",
        "10m": "Min_10",
        "15m": "Min_15",
        "20m": "Min_20",
        "30m": "Min_30",
        "45m": "Min_45",
        "60m": "Min_60",
        "120m": "Min_120",
        "180m": "Min_180",
        "240m": "Min_240",
        "d": "Day",
        "day": "Day",
        "daily": "Day",
        "w": "Week",
        "week": "Week",
        "weekly": "Week",
        "month": "Month",
        "monthly": "Month",
        "quarter": "Quarter",
        "quarterly": "Quarter",
        "year": "Year",
        "yearly": "Year",
    }
    return _enum_from_attr(Period, mapping.get(token, token), token)


def parse_adjust_type(value: Any) -> Any:
    if value is None or value == "":
        return _enum_from_attr(AdjustType, "NoAdjust", "NoAdjust")
    if isinstance(AdjustType, type) and isinstance(value, AdjustType):  # type: ignore[arg-type]
        return value
    token = str(value).strip().lower()
    mapping = {
        "none": "NoAdjust",
        "no_adjust": "NoAdjust",
        "noadjust": "NoAdjust",
        "forward": "ForwardAdjust",
        "forward_adjust": "ForwardAdjust",
        "forwardadjust": "ForwardAdjust",
    }
    return _enum_from_attr(AdjustType, mapping.get(token, token), token)


def parse_trade_sessions(value: Any) -> Any:
    if TradeSessions is None or value in (None, "", "all"):
        return _enum_from_attr(TradeSessions, "All", None)
    if isinstance(TradeSessions, type) and isinstance(value, TradeSessions):  # type: ignore[arg-type]
        return value
    token = str(value).strip().lower()
    mapping = {
        "all": "All",
        "intraday": "Intraday",
    }
    return _enum_from_attr(TradeSessions, mapping.get(token, token), None)


def parse_sub_types(values: Iterable[str]) -> List[Any]:
    parsed: List[Any] = []
    for raw in values or []:
        token = str(raw or "").strip()
        if not token:
            continue
        for chunk in token.split(","):
            name = chunk.strip().lower()
            if not name:
                continue
            mapping = {
                "quote": "Quote",
                "depth": "Depth",
                "brokers": "Brokers",
                "broker": "Brokers",
                "trade": "Trade",
                "trades": "Trade",
            }
            value = getattr(SubType, mapping.get(name, name[:1].upper() + name[1:]), None)
            if value is not None and value not in parsed:
                parsed.append(value)
    return parsed


def parse_calc_indexes(values: Iterable[str]) -> List[Any]:
    if CalcIndex is None:
        return []
    indexes: List[Any] = []
    for raw in values or []:
        token = str(raw or "").strip()
        if not token:
            continue
        for chunk in token.split(","):
            name = chunk.strip()
            if not name:
                continue
            attr = name[:1].upper() + name[1:]
            value = getattr(CalcIndex, attr, None)
            if value is None:
                compact = name.replace("_", "").replace("-", "").lower()
                for candidate in dir(CalcIndex):
                    if candidate.startswith("_"):
                        continue
                    if candidate.replace("_", "").replace("-", "").lower() == compact:
                        value = getattr(CalcIndex, candidate)
                        break
            if value is not None and value not in indexes:
                indexes.append(value)
    return indexes


def parse_security_list_category(value: Any) -> Any:
    if SecurityListCategory is None or value in (None, ""):
        return None
    token = str(value).strip()
    return getattr(SecurityListCategory, token[:1].upper() + token[1:], None)


def parse_warrant_sort_by(value: Any) -> Any:
    if WarrantSortBy is None or value in (None, ""):
        return None
    token = str(value).strip()
    normalized = token[:1].upper() + token[1:]
    return getattr(WarrantSortBy, normalized, None)


def parse_sort_order(value: Any) -> Any:
    if SortOrderType is None or value in (None, ""):
        return _enum_from_attr(SortOrderType, "Descending", None)
    token = str(value).strip().lower()
    return _enum_from_attr(
        SortOrderType,
        "Ascending" if token in {"asc", "ascending"} else "Descending",
        None,
    )


def parse_warrant_type(value: Any) -> Any:
    if WarrantType is None or value in (None, ""):
        return None
    token = str(value).strip()
    return getattr(WarrantType, token[:1].upper() + token[1:], None)


def parse_warrant_expiry_filter(value: Any) -> Any:
    if FilterWarrantExpiryDate is None or value in (None, ""):
        return None
    token = str(value).strip()
    return getattr(FilterWarrantExpiryDate, token, None)


def parse_warrant_price_type(value: Any) -> Any:
    if FilterWarrantInOutBoundsType is None or value in (None, ""):
        return None
    token = str(value).strip()
    return getattr(FilterWarrantInOutBoundsType, token[:1].upper() + token[1:], None)


def parse_warrant_status(value: Any) -> Any:
    if WarrantStatus is None or value in (None, ""):
        return None
    token = str(value).strip()
    return getattr(WarrantStatus, token[:1].upper() + token[1:], None)


def to_plain(value: Any, _seen: Optional[set] = None, _depth: int = 0) -> Any:
    if _seen is None:
        _seen = set()

    if value is None or isinstance(value, (bool, int, str)):
        return value

    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return None

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, dict):
        return {str(key): to_plain(item, _seen, _depth + 1) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [to_plain(item, _seen, _depth + 1) for item in value]

    enum_name = getattr(value, "name", None)
    enum_value = getattr(value, "value", None)
    if isinstance(enum_name, str) and not callable(enum_name):
        if isinstance(enum_value, (str, int, float, bool)):
            return enum_value
        return enum_name

    if isinstance(enum_value, (str, int, float, bool)):
        return enum_value

    if hasattr(value, "timestamp") and callable(getattr(value, "timestamp")):
        try:
            return value.timestamp()
        except Exception:
            pass

    if _depth >= 4:
        return str(value)

    identity = id(value)
    if identity in _seen:
        return str(value)
    _seen.add(identity)

    public_attrs: Dict[str, Any] = {}
    for attr in dir(value):
        if attr.startswith("_"):
            continue
        try:
            attr_value = getattr(value, attr)
        except Exception:
            continue
        if callable(attr_value):
            continue
        public_attrs[attr] = to_plain(attr_value, _seen, _depth + 1)

    if public_attrs:
        _seen.discard(identity)
        return public_attrs

    _seen.discard(identity)
    return str(value)
