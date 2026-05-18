from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from .legacy_loader import ai_routes


def get_quote_from_broker(symbol: str, account_id: Optional[int] = None, *, user_id: Optional[int] = None):
    return ai_routes()._get_quote_from_broker(symbol, account_id, user_id=user_id)  # noqa: SLF001


def get_quotes_from_broker(
    symbols: Iterable[str],
    account_id: Optional[int] = None,
    *,
    user_id: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    return ai_routes()._get_quotes_from_broker(list(symbols), account_id, user_id=user_id)  # noqa: SLF001


def build_market_snapshot(
    account_id: Optional[int] = None,
    focus_symbol: Optional[str] = None,
    *,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    return ai_routes()._build_market_snapshot(account_id, focus_symbol, user_id=user_id)  # noqa: SLF001


def build_real_indicator_context(symbol: str, current_price: float, volume: int, *, user_id: int = 1):
    return ai_routes()._build_real_indicator_context(  # noqa: SLF001
        symbol,
        current_price,
        volume,
        user_id=user_id,
    )


def detect_market(symbol: str) -> str:
    return ai_routes()._detect_market(symbol)  # noqa: SLF001


def extract_position_quote_fallback(position: Dict[str, Any]):
    return ai_routes()._extract_position_quote_fallback(position)  # noqa: SLF001
