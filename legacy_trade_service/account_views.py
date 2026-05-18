from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from shared.bootstrap import bootstrap_runtime

bootstrap_runtime()

from core.broker.BrokerInterface import get_broker_manager  # noqa: E402
from utils.DbUtil import DbUtil  # noqa: E402

from legacy_trade_service.models import AuthUser


def _positive_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _resolve_order_price(order: Any) -> Optional[float]:
    if isinstance(order, dict):
        values = (
            order.get("price"),
            order.get("submitted_price"),
            order.get("submittedPrice"),
            order.get("request_price"),
            order.get("requestPrice"),
            order.get("reference_price"),
            order.get("referencePrice"),
            order.get("limit_price"),
            order.get("limitPrice"),
        )
    else:
        values = (
            getattr(order, "price", None),
            getattr(order, "submitted_price", None),
            getattr(order, "submittedPrice", None),
            getattr(order, "request_price", None),
            getattr(order, "reference_price", None),
            getattr(order, "limit_price", None),
        )
    for value in values:
        number = _positive_float(value)
        if number is not None:
            return number
    return None


def _ensure_broker_connected(broker) -> bool:
    connection_state = getattr(broker, "is_connected", False)
    if connection_state() if callable(connection_state) else bool(connection_state):
        return True
    return bool(broker.connect())


def _load_account_row(user_id: int, account_id: int) -> Dict[str, Any]:
    row = DbUtil.fetch_one(
        """
        SELECT id, broker_type, broker_name, account_id
        FROM broker_accounts
        WHERE id = %s AND user_id = %s AND is_active = 1
        LIMIT 1
        """,
        (account_id, user_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="未找到券商账户")
    return row


def _get_broker_for_user(user_id: int, account_id: int):
    manager = get_broker_manager()
    broker = manager.get_broker(account_id, user_id=user_id)
    if not broker:
        raise HTTPException(status_code=404, detail="券商账户不存在或不属于当前用户")
    if not _ensure_broker_connected(broker):
        raise HTTPException(status_code=502, detail="券商连接失败")
    return broker


def _account_display_name(account_row: Dict[str, Any]) -> str:
    broker_name = account_row.get("broker_name") or account_row.get("broker_type") or "账户"
    return f"{broker_name} - {account_row.get('account_id')}"


def _serialize_order(order: Any, account_id: int, account_name: str) -> Dict[str, Any]:
    action = str(getattr(order, "action", getattr(order, "side", "")) or "").upper()
    create_time = getattr(order, "create_time", None)
    return {
        "order_id": getattr(order, "order_id", ""),
        "symbol": getattr(order, "symbol", ""),
        "side": "买入" if action == "BUY" else "卖出",
        "quantity": float(getattr(order, "quantity", 0) or 0),
        "price": _resolve_order_price(order),
        "submitted_price": _positive_float(getattr(order, "submitted_price", None)),
        "reference_price": _positive_float(getattr(order, "reference_price", None)),
        "status": getattr(order, "status", ""),
        "create_time": create_time.isoformat() if hasattr(create_time, "isoformat") else str(create_time or ""),
        "account_id": account_id,
        "account_name": account_name,
        "filled_quantity": float(getattr(order, "filled_quantity", 0) or 0),
        "order_type": getattr(order, "order_type", ""),
    }


def _load_orders_for_account(user_id: int, account_id: int, status: Optional[str]) -> List[Dict[str, Any]]:
    account_row = _load_account_row(user_id, account_id)
    broker = _get_broker_for_user(user_id, account_id)
    orders = broker.get_orders(status=status) or []
    account_name = _account_display_name(account_row)
    return [_serialize_order(item, account_id=account_id, account_name=account_name) for item in orders]


def _list_orders(user: AuthUser, account_id: Optional[int], status: Optional[str], limit: int) -> Dict[str, Any]:
    manager = get_broker_manager()
    order_items: List[Dict[str, Any]] = []
    warnings: List[str] = []

    if account_id is not None:
        order_items.extend(_load_orders_for_account(user.user_id, int(account_id), status))
    else:
        accounts = manager.list_accounts(user.user_id) or []
        for account in accounts:
            current_account_id = int(account.get("id") or 0)
            if current_account_id <= 0:
                continue
            try:
                order_items.extend(_load_orders_for_account(user.user_id, current_account_id, status))
            except HTTPException as exc:
                warnings.append(f"账户{current_account_id}订单加载失败: {exc.detail}")
            except Exception as exc:
                warnings.append(f"账户{current_account_id}订单加载失败: {exc}")

    order_items.sort(key=lambda item: item.get("create_time") or "", reverse=True)
    if limit > 0:
        order_items = order_items[:limit]

    payload = {
        "success": True,
        "orders": order_items,
        "count": len(order_items),
    }
    if warnings:
        payload["warnings"] = warnings
    return payload


def _serialize_account_summary(account: Dict[str, Any]) -> Dict[str, Any]:
    broker_name = account.get("broker_name") or account.get("broker_type") or "账户"
    account_id = account.get("account_id") or account.get("id")
    return {
        **account,
        "name": f"{broker_name} - {account_id}",
        "display_name": f"{broker_name} - {account_id}",
        "brokerType": account.get("broker_type") or "",
        "brokerName": broker_name,
        "accountId": account.get("account_id") or "",
        "isDefault": bool(account.get("is_default")),
        "isActive": bool(account.get("is_active", True)),
    }


def _serialize_position(position: Any, account_id: int) -> Dict[str, Any]:
    return {
        "symbol": getattr(position, "symbol", ""),
        "name": getattr(position, "name", "") or getattr(position, "symbol", ""),
        "quantity": int(getattr(position, "quantity", 0) or 0),
        "average_cost": float(getattr(position, "average_cost", 0) or 0),
        "avgPrice": float(getattr(position, "average_cost", 0) or 0),
        "market_price": float(getattr(position, "market_price", 0) or 0),
        "currentPrice": float(getattr(position, "market_price", 0) or 0),
        "market_value": float(getattr(position, "market_value", 0) or 0),
        "marketValue": float(getattr(position, "market_value", 0) or 0),
        "unrealized_pnl": float(getattr(position, "unrealized_pnl", 0) or 0),
        "pnl": float(getattr(position, "unrealized_pnl", 0) or 0),
        "realized_pnl": float(getattr(position, "realized_pnl", 0) or 0),
        "account_id": account_id,
        "accountId": account_id,
    }


def _list_accounts(user: AuthUser) -> List[Dict[str, Any]]:
    manager = get_broker_manager()
    accounts = manager.list_accounts(user.user_id) or []
    return [_serialize_account_summary(item) for item in accounts if bool(item.get("is_active", True))]


def _get_default_account(user: AuthUser) -> Optional[Dict[str, Any]]:
    accounts = _list_accounts(user)
    if not accounts:
        return None
    return next((item for item in accounts if item.get("is_default")), accounts[0])


def _load_account_positions(user: AuthUser, account_id: int) -> List[Dict[str, Any]]:
    broker = _get_broker_for_user(user.user_id, account_id)
    positions = broker.get_positions() or []
    return [_serialize_position(item, account_id) for item in positions]


def _load_account_state(user: AuthUser, account_id: int, status: Optional[str] = None, limit: int = 30) -> Dict[str, Any]:
    account_row = _load_account_row(user.user_id, account_id)
    broker = _get_broker_for_user(user.user_id, account_id)
    account_name = _account_display_name(account_row)
    account_info = broker.get_account_info()
    positions = [_serialize_position(item, account_id) for item in (broker.get_positions() or [])]
    orders_payload = _list_orders(user, account_id, status, limit)
    snapshot_at = datetime.now().isoformat()

    return {
        "account": {
            "id": account_id,
            "broker_type": account_row.get("broker_type") or "",
            "broker_name": account_row.get("broker_name") or account_row.get("broker_type") or "",
            "account_id": account_row.get("account_id") or "",
            "name": account_name,
            "display_name": account_name,
            "is_default": bool(account_row.get("is_default")),
            "is_active": bool(account_row.get("is_active", True)),
        },
        "accountInfo": {
            "account_id": getattr(account_info, "account_id", "") or account_row.get("account_id") or "",
            "currency": getattr(account_info, "currency", "USD"),
            "cash": float(getattr(account_info, "cash", 0) or 0),
            "market_value": float(getattr(account_info, "market_value", 0) or 0),
            "total_equity": float(getattr(account_info, "total_equity", 0) or 0),
            "buying_power": float(getattr(account_info, "buying_power", 0) or 0),
            "maintenance_margin": float(getattr(account_info, "maintenance_margin", 0) or 0),
        },
        "positions": positions,
        "orders": orders_payload.get("orders", []),
        "positionCount": len(positions),
        "orderCount": int(orders_payload.get("count") or 0),
        "snapshotAt": snapshot_at,
        "dataSource": "broker-live",
        "meta": {
            "snapshotAt": snapshot_at,
            "sources": {
                "account": "broker-live",
                "positions": "broker-live",
                "orders": "broker-live",
            },
            "positionSnapshotAt": snapshot_at,
            "orderSnapshotAt": snapshot_at,
            "warnings": orders_payload.get("warnings", []),
            "realtimeOverlay": ["quotes", "orders"],
        },
    }


def _build_account_summary_payload(
    user: AuthUser,
    account_id: int,
    *,
    realtime: bool = False,
) -> Dict[str, Any]:
    state = _load_account_state(user, account_id, limit=30)
    account_info = state.get("accountInfo") or {}
    positions = state.get("positions") or []

    cash = float(account_info.get("cash") or 0)
    aggregate_market_value = 0.0

    pnl = 0.0
    cost = 0.0
    for item in positions:
        quantity = float(item.get("quantity") or 0)
        avg_price = float(item.get("average_cost") or item.get("avgPrice") or 0)
        current_price = float(item.get("market_price") or item.get("currentPrice") or 0)
        position_market_value = float(item.get("market_value") or item.get("marketValue") or (quantity * current_price))
        item_pnl = float(item.get("unrealized_pnl") or item.get("pnl") or ((current_price - avg_price) * quantity))
        pnl += item_pnl
        aggregate_market_value += position_market_value
        cost += max(avg_price * quantity, 0)

    market_value = float(account_info.get("market_value") or account_info.get("marketValue") or aggregate_market_value)
    total_assets = float(account_info.get("total_equity") or account_info.get("totalAssets") or (cash + market_value))
    pnl_ratio = (pnl / cost * 100) if cost > 0 else 0.0
    snapshot_at = state.get("snapshotAt") or datetime.now().isoformat()
    upstream_meta = state.get("meta") if isinstance(state.get("meta"), dict) else {}

    return {
        "account_id": state.get("account", {}).get("account_id") or "",
        "currency": account_info.get("currency") or "USD",
        "total_assets": total_assets,
        "daily_pnl": pnl,
        "today_pnl": pnl,
        "today_pnl_percent": pnl_ratio,
        "pnl_ratio": pnl_ratio,
        "cash": cash,
        "market_value": float(account_info.get("market_value") or account_info.get("marketValue") or market_value),
        "buying_power": float(account_info.get("buying_power") or cash),
        "maintenance_margin": float(account_info.get("maintenance_margin") or 0),
        "source": "realtime" if realtime else (state.get("dataSource") or state.get("source") or "live"),
        "snapshot_at": snapshot_at,
        "meta": {
            **upstream_meta,
            "snapshotAt": snapshot_at,
            "readModel": "trade-dashboard-summary",
            "defaultMode": "realtime" if realtime else "database",
            "sources": {
                **(upstream_meta.get("sources") or {}),
                "summary": "trade-dashboard-summary",
            },
        },
    }


def _build_order_stream_event(
    *,
    user: AuthUser,
    account_id: Optional[int],
    status: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    payload = _list_orders(user, account_id, status, limit)
    snapshot_at = datetime.now().isoformat()
    normalized_status = str(status or "").strip()
    warnings = payload.get("warnings", [])
    return {
        "type": "orders",
        "payload": payload.get("orders", []),
        "accountId": account_id,
        "status": normalized_status,
        "snapshotAt": snapshot_at,
        "receivedAt": snapshot_at,
        "dataSource": "broker-live",
        "meta": {
            "snapshotAt": snapshot_at,
            "dataSource": "broker-live",
            "query": {
                "accountId": account_id,
                "status": normalized_status,
                "limit": limit,
            },
            "sources": {
                "orders": "broker-live",
            },
            "warnings": warnings,
            "realtimeOverlay": ["order-stream"],
        },
    }
