from __future__ import annotations

from typing import Any, Dict, List, Optional

from .legacy_loader import data_routes


def normalize_market_symbol(symbol: str) -> str:
    return data_routes()._normalize_market_symbol(symbol)  # noqa: SLF001


def build_risk_overview(user_id: int, account_id: Optional[int] = None) -> Dict[str, Any]:
    return data_routes()._build_risk_overview(user_id=user_id, account_id=account_id)  # noqa: SLF001


def collect_notifications(
    user_id: int,
    *,
    limit: int = 50,
    notification_type: str = "",
) -> List[Dict[str, Any]]:
    return data_routes()._collect_notifications(  # noqa: SLF001
        user_id=user_id,
        limit=limit,
        notification_type=notification_type,
    )


def collect_agent_risk_events(user_id: int, *, limit: int = 20) -> List[Dict[str, Any]]:
    return data_routes()._collect_agent_risk_events(  # noqa: SLF001
        user_id=user_id,
        limit=limit,
    )


def upsert_notification_states(
    user_id: int,
    keys: List[str],
    *,
    is_read: Optional[bool] = None,
    is_hidden: Optional[bool] = None,
) -> int:
    return int(data_routes()._upsert_notification_states(  # noqa: SLF001
        user_id,
        keys,
        is_read=is_read,
        is_hidden=is_hidden,
    ) or 0)


def load_risk_limits(user_id: int) -> Dict[str, Any]:
    return data_routes()._load_risk_limits(user_id)  # noqa: SLF001


def ensure_risk_control_tables() -> None:
    data_routes()._ensure_risk_control_tables()  # noqa: SLF001


def load_risk_orders(
    user_id: int,
    order_type: str,
    account_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    return data_routes()._load_risk_orders(  # noqa: SLF001
        user_id=user_id,
        order_type=order_type,
        account_id=account_id,
    )
