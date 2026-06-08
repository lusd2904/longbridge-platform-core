from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


REFACTOR_ROOT = Path(__file__).resolve().parents[3]
if str(REFACTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(REFACTOR_ROOT))

from apps.trading.module_shared import (
    AccountAssetSnapshotService,
    DbUtil,
    LongbridgeAPI,
    PlatformAuditService,
    PositionSnapshotService,
    TigerBrokerAPI,
    TradeAuditService,
    bootstrap_runtime,
    build_alert,
    build_dependency_status,
    build_health_payload,
    build_masked_broker_config,
    decode_token,
    enrich_broker_account,
    ensure_default_selection,
    get_broker_manager,
    get_current_session,
    get_user_broker_account,
    kafka_bus,
    legacy_boundary_status,
    legacy_trade_service,
    mask_account_id,
    service_port,
    settings,
    summarize_status,
)

bootstrap_runtime()


PORT = service_port("REF_TRADE_SERVICE_PORT", 8105)


def _build_longbridge_connectivity_status(longbridge_status: Dict[str, Any]) -> Dict[str, Any]:
    configured = bool(longbridge_status.get("configured"))
    enabled = bool(longbridge_status.get("enabled"))
    last_error = str(longbridge_status.get("lastError") or "").strip()
    last_success_at = str(longbridge_status.get("lastSuccessAt") or "").strip()

    if configured or enabled or last_success_at:
        status = "degraded" if last_error else "healthy"
        status_text = "长桥观测存在最近错误" if last_error else "长桥观测已接入"
    else:
        status = "disabled"
        status_text = "长桥交易观测未启用；模拟账户保护仍由下单链路校验"

    return {
        "status": status,
        "status_text": status_text,
        "configured": configured,
        "enabled": enabled,
        **longbridge_status,
    }


def _serialize_datetime(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _ensure_admin_session(session: Dict[str, Any]) -> None:
    if str(session.get("role") or "").strip().lower() != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可执行该操作")


def _extract_event_ids(payload: Dict[str, Any]) -> List[str]:
    event_ids = payload.get("event_ids") or payload.get("eventIds") or []
    normalized_ids = [str(event_id or "").strip() for event_id in event_ids if str(event_id or "").strip()]
    if not normalized_ids:
        raise HTTPException(status_code=400, detail="event_ids 不能为空")
    return normalized_ids


def _extract_saga_ids(payload: Dict[str, Any]) -> List[str]:
    saga_ids = payload.get("saga_ids") or payload.get("sagaIds") or []
    normalized_ids = [str(saga_id or "").strip() for saga_id in saga_ids if str(saga_id or "").strip()]
    if not normalized_ids:
        raise HTTPException(status_code=400, detail="saga_ids 不能为空")
    return normalized_ids


def _mask_account_id(account_id: Any) -> str:
    raw = str(account_id or "").strip()
    if not raw:
        return ""
    if len(raw) <= 4:
        return "*" * len(raw)
    return f"{raw[:2]}{'*' * max(len(raw) - 4, 0)}{raw[-2:]}"


def _display_account_name(account: Dict[str, Any]) -> str:
    broker_name = account.get("broker_name") or account.get("broker_type") or "账户"
    masked_id = _mask_account_id(account.get("account_id"))
    return f"{broker_name} - {masked_id or account.get('id')}"


def _serialize_account(account: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(account)
    payload["account_id_masked"] = _mask_account_id(payload.get("account_id"))
    payload["display_name"] = _display_account_name(payload)
    payload["created_at"] = _serialize_datetime(payload.get("created_at"))
    return payload


def _build_account_runtime_hints(account: Dict[str, Any], row: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    broker_type = str((row or {}).get("broker_type") or account.get("broker_type") or "").strip().lower()
    display_name = " ".join(
        [
            str(account.get("display_name") or ""),
            str(account.get("name") or ""),
            str(account.get("broker_name") or ""),
            str(account.get("account_id") or ""),
        ]
    ).upper()

    trading_mode = "unknown"
    account_mode_label = "待确认"
    safety_level = "warning"
    safety_message = "请先确认当前券商环境与账户模式，再提交委托。"

    if broker_type == "tiger":
        env = str((row or {}).get("tiger_env") or "").strip().upper()
        if env and env != "PROD":
            trading_mode = "paper"
            account_mode_label = f"Tiger {env}"
            safety_level = "info"
            safety_message = "当前为 Tiger 模拟/非生产环境，下单仅用于演练，请勿将结果视为真实成交。"
        elif env == "PROD":
            trading_mode = "live"
            account_mode_label = "Tiger 实盘"
            safety_level = "danger"
            safety_message = "当前为 Tiger 实盘账户，请再次确认价格、数量与市场状态。"
    elif broker_type == "longbridge":
        config = build_masked_broker_config(row or {}, broker_type) if row else {}
        cli_channel = str(config.get("cli_account_channel") or "").strip().upper()
        if bool(config.get("has_cli_auth")) or any(keyword in cli_channel for keyword in ("SIM", "PAPER", "DEMO")):
            trading_mode = "paper"
            account_mode_label = "长桥模拟"
            safety_level = "info"
            safety_message = "当前为长桥模拟账户，页面中的委托与订单变化仅用于演练。"
        elif row:
            trading_mode = "live"
            account_mode_label = "长桥实盘"
            safety_level = "danger"
            safety_message = "当前为长桥实盘账户，请确认参考报价、数量与交易时段。"

    if trading_mode == "unknown":
        if any(keyword in display_name for keyword in ("PAPER", "SIM", "SIMULAT", "DEMO", "SANDBOX", "模拟")):
            trading_mode = "paper"
            account_mode_label = "模拟账户"
            safety_level = "info"
            safety_message = "当前账户看起来是模拟/演练环境，请勿将页面结果视为真实成交。"
        elif row:
            trading_mode = "live"
            account_mode_label = "实盘账户"
            safety_level = "danger"
            safety_message = "当前账户已接入可交易券商，请确认价格与数量后再提交。"

    return {
        "trading_mode": trading_mode,
        "tradingMode": trading_mode,
        "is_paper": trading_mode == "paper",
        "isPaper": trading_mode == "paper",
        "account_mode_label": account_mode_label,
        "accountModeLabel": account_mode_label,
        "safety_level": safety_level,
        "safetyLevel": safety_level,
        "safety_message": safety_message,
        "safetyMessage": safety_message,
    }


def _get_accounts(user_id: int) -> List[Dict[str, Any]]:
    manager = get_broker_manager()
    accounts: List[Dict[str, Any]] = []
    for item in (manager.list_accounts(user_id) or []):
        payload = _serialize_account(item)
        row = None
        account_row_id = int(payload.get("id") or 0)
        if account_row_id > 0:
            try:
                row = get_user_broker_account(account_row_id, user_id)
            except Exception:
                row = None
        payload.update(_build_account_runtime_hints(payload, row))
        accounts.append(payload)
    return accounts


def _get_account_or_404(user_id: int, account_id: int) -> Dict[str, Any]:
    account = next((item for item in _get_accounts(user_id) if int(item.get("id") or 0) == account_id), None)
    if not account:
        raise HTTPException(status_code=404, detail="券商账户不存在")
    return account


def _get_default_account(user_id: int) -> Optional[Dict[str, Any]]:
    accounts = _get_accounts(user_id)
    if not accounts:
        return None
    return next((item for item in accounts if item.get("is_default")), accounts[0])


def _build_account_state(
    *,
    user_id: int,
    account_id: int,
    status: Optional[str] = None,
    limit: int = 30,
) -> Dict[str, Any]:
    account = _get_account_or_404(user_id, account_id)
    trade_user = legacy_trade_service.AuthUser(user_id=user_id, username="", role="user")
    try:
        live_state = legacy_trade_service._load_account_state(
            trade_user,
            account_id,
            status=status,
            limit=limit,
        )
        positions = list(live_state.get("positions") or [])
        orders = list(live_state.get("orders") or [])
        position_count = int(live_state.get("positionCount") or len(positions))
        order_count = int(live_state.get("orderCount") or len(orders))
        upstream_meta = live_state.get("meta") if isinstance(live_state.get("meta"), dict) else {}

        state = {
            "account": account,
            "accountInfo": dict(live_state.get("accountInfo") or {}),
            "positions": positions,
            "orders": orders,
            "positionCount": position_count,
            "orderCount": order_count,
            "snapshotAt": live_state.get("snapshotAt"),
            "dataSource": "live",
            "meta": {
                "readModel": "trade-account-state",
                "defaultMode": "realtime",
                "dataSource": "live",
                "sources": {
                    "account": "broker",
                    "positions": "broker",
                    "orders": "broker",
                },
                "positionCount": position_count,
                "orderCount": order_count,
                "warnings": list(upstream_meta.get("warnings") or []),
                "realtimeOverlay": ["broker"],
            },
        }
        _persist_snapshot_state(user_id=user_id, account_id=account_id, account=account, state=state)
        return state
    except Exception as exc:
        snapshot_state = _build_snapshot_state(user_id=user_id, account_id=account_id)
        warning = str(exc)[:180]
        snapshot_state["warning"] = warning
        snapshot_state["meta"] = {
            **(snapshot_state.get("meta") if isinstance(snapshot_state.get("meta"), dict) else {}),
            "warnings": [warning],
            "degraded": True,
            "fallbackSource": "snapshot",
            "requestedMode": "live",
        }
        return snapshot_state


def _build_account_snapshot_summary(account_info: Dict[str, Any], positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_pnl = sum(float(item.get("unrealized_pnl") or 0) for item in positions)
    total_cost = sum(
        float(item.get("average_cost") or 0) * float(item.get("quantity") or 0)
        for item in positions
    )
    pnl_ratio = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0
    return {
        "currency": account_info.get("currency") or "USD",
        "total_assets": float(account_info.get("total_equity") or 0),
        "cash": float(account_info.get("cash") or 0),
        "market_value": float(account_info.get("market_value") or 0),
        "buying_power": float(account_info.get("buying_power") or account_info.get("cash") or 0),
        "maintenance_margin": float(account_info.get("maintenance_margin") or 0),
        "today_pnl": round(total_pnl, 4),
        "today_pnl_percent": round(pnl_ratio, 4),
    }


def _persist_snapshot_state(*, user_id: int, account_id: int, account: Dict[str, Any], state: Dict[str, Any]) -> None:
    try:
        account_info = state.get("accountInfo") or {}
        positions = state.get("positions") or []
        orders = list(state.get("orders") or [])[:5]
        summary = _build_account_snapshot_summary(account_info, positions)
        AccountAssetSnapshotService.save_summary(
            user_id=user_id,
            account_id=account_id,
            summary=summary,
            broker_type=str(account.get("broker_type") or ""),
            source="trade-service",
            payload={
                "account": account,
                "accountInfo": account_info,
                "orderCount": int(state.get("orderCount") or len(state.get("orders") or [])),
                "recentOrders": orders,
            },
        )
        PositionSnapshotService.replace_account_positions(
            user_id=user_id,
            account_id=account_id,
            positions=positions,
            source="trade-service",
        )
    except Exception:
        # 快照失败不影响实时交易主流程。
        pass


def _build_trade_snapshot_meta(
    *,
    account_snapshot: Dict[str, Any],
    positions_snapshot: List[Dict[str, Any]],
    order_count: int,
    snapshot_at: Optional[str],
    data_source: str = "snapshot",
    warnings: Optional[List[str]] = None,
    degraded: bool = False,
) -> Dict[str, Any]:
    account_snapshot_at = account_snapshot.get("snapshotAt") if isinstance(account_snapshot, dict) else None
    position_snapshot_at = positions_snapshot[0].get("snapshotAt") if positions_snapshot else None
    return {
        "readModel": "trade-snapshot-state",
        "defaultMode": "database",
        "dataSource": data_source,
        "snapshotAt": snapshot_at,
        "sources": {
            "account": "account_asset_snapshots",
            "positions": "position_snapshots",
            "orders": "account_asset_snapshots.payload.recentOrders",
        },
        "accountSnapshotAt": account_snapshot_at,
        "positionSnapshotAt": position_snapshot_at,
        "orderSnapshotAt": snapshot_at,
        "positionCount": len(positions_snapshot),
        "orderCount": int(order_count or 0),
        "realtimeOverlay": ["quotes", "order-stream"],
        "warnings": [str(item) for item in (warnings or []) if str(item or "").strip()],
        "degraded": bool(degraded),
    }


def _build_snapshot_state(*, user_id: int, account_id: int) -> Dict[str, Any]:
    account = _get_account_or_404(user_id, account_id)
    account_snapshot = AccountAssetSnapshotService.get_latest(user_id=user_id, account_id=account_id) or {}
    positions_snapshot = PositionSnapshotService.get_latest(user_id=user_id, account_id=account_id)
    snapshot_payload = account_snapshot.get("payload") if isinstance(account_snapshot.get("payload"), dict) else {}
    snapshot_orders = snapshot_payload.get("recentOrders") if isinstance(snapshot_payload.get("recentOrders"), list) else []
    snapshot_order_count = int(snapshot_payload.get("orderCount") or len(snapshot_orders) or 0)
    account_info = {
        "account_id": account.get("account_id") or "",
        "currency": account_snapshot.get("currency") or "USD",
        "cash": float(account_snapshot.get("cash") or 0),
        "market_value": float(account_snapshot.get("marketValue") or 0),
        "total_equity": float(account_snapshot.get("totalAssets") or 0),
        "buying_power": float(account_snapshot.get("buyingPower") or 0),
        "maintenance_margin": float(account_snapshot.get("maintenanceMargin") or 0),
    }
    snapshot_at = (
        account_snapshot.get("snapshotAt")
        or (positions_snapshot[0].get("snapshotAt") if positions_snapshot else None)
    )

    return {
        "account": account,
        "accountInfo": account_info,
        "positions": positions_snapshot,
        "orders": snapshot_orders,
        "positionCount": len(positions_snapshot),
        "orderCount": snapshot_order_count,
        "snapshotAt": snapshot_at,
        "dataSource": "snapshot",
        "meta": _build_trade_snapshot_meta(
            account_snapshot=account_snapshot,
            positions_snapshot=positions_snapshot,
            order_count=snapshot_order_count,
            snapshot_at=snapshot_at,
            data_source="snapshot",
            warnings=[],
            degraded=False,
        ),
    }


def _build_snapshot_summary_state(*, user_id: int, account_id: int) -> Dict[str, Any]:
    account = _get_account_or_404(user_id, account_id)
    account_snapshot = AccountAssetSnapshotService.get_latest(user_id=user_id, account_id=account_id) or {}
    snapshot_payload = account_snapshot.get("payload") if isinstance(account_snapshot.get("payload"), dict) else {}
    snapshot_orders = snapshot_payload.get("recentOrders") if isinstance(snapshot_payload.get("recentOrders"), list) else []
    snapshot_order_count = int(snapshot_payload.get("orderCount") or len(snapshot_orders) or 0)
    position_count = PositionSnapshotService.get_latest_count(user_id=user_id, account_id=account_id)
    snapshot_at = account_snapshot.get("snapshotAt")
    account_info = {
        "account_id": account.get("account_id") or "",
        "currency": account_snapshot.get("currency") or "USD",
        "cash": float(account_snapshot.get("cash") or 0),
        "market_value": float(account_snapshot.get("marketValue") or 0),
        "total_equity": float(account_snapshot.get("totalAssets") or 0),
        "buying_power": float(account_snapshot.get("buyingPower") or 0),
        "maintenance_margin": float(account_snapshot.get("maintenanceMargin") or 0),
        "today_pnl": float(account_snapshot.get("todayPnL") or 0),
        "today_pnl_percent": float(account_snapshot.get("todayPnLPercent") or 0),
    }
    return {
        "account": account,
        "accountInfo": account_info,
        "positions": [],
        "orders": snapshot_orders,
        "positionCount": position_count,
        "orderCount": snapshot_order_count,
        "snapshotAt": snapshot_at,
        "dataSource": "snapshot",
        "meta": _build_trade_snapshot_meta(
            account_snapshot=account_snapshot,
            positions_snapshot=[],
            order_count=snapshot_order_count,
            snapshot_at=snapshot_at,
            data_source="snapshot",
            warnings=[],
            degraded=False,
        ),
    }


def _build_positions_meta(
    *,
    state: Dict[str, Any],
    data_source: str,
    default_mode: str,
) -> Dict[str, Any]:
    is_live_source = str(data_source or "").startswith("live")
    state_meta = state.get("meta") if isinstance(state.get("meta"), dict) else {}
    sources = state_meta.get("sources") if isinstance(state_meta.get("sources"), dict) else {}
    snapshot_at = (
        state_meta.get("positionSnapshotAt")
        or state.get("snapshotAt")
        or state_meta.get("snapshotAt")
    )
    return {
        "readModel": "trade-positions",
        "defaultMode": default_mode,
        "dataSource": data_source,
        "snapshotAt": snapshot_at,
        "sources": {
            "positions": sources.get("positions") or ("broker" if is_live_source else "position_snapshots"),
            "account": sources.get("account") or ("broker" if is_live_source else "account_asset_snapshots"),
        },
        "positionCount": int(state.get("positionCount") or len(state.get("positions") or [])),
        "realtimeOverlay": ["quotes"] if not is_live_source else ["broker"],
    }


def _build_dashboard_summary_payload(
    *,
    state: Dict[str, Any],
    data_source: str,
    default_mode: str,
) -> Dict[str, Any]:
    is_live_source = str(data_source or "").startswith("live")
    account_info = state.get("accountInfo") if isinstance(state.get("accountInfo"), dict) else {}
    positions = state.get("positions") if isinstance(state.get("positions"), list) else []
    orders = state.get("orders") if isinstance(state.get("orders"), list) else []
    total_pnl = float(
        account_info.get("today_pnl")
        or account_info.get("todayPnL")
        or sum(float(item.get("pnl") or item.get("unrealized_pnl") or 0) for item in positions)
    )
    pnl_ratio = float(account_info.get("today_pnl_percent") or account_info.get("todayPnLPercent") or 0)
    if not pnl_ratio and positions:
        total_cost = sum(
            float(item.get("avgPrice") or item.get("avg_price") or item.get("average_cost") or 0) * float(item.get("quantity") or 0)
            for item in positions
        )
        pnl_ratio = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0
    state_meta = state.get("meta") if isinstance(state.get("meta"), dict) else {}
    sources = state_meta.get("sources") if isinstance(state_meta.get("sources"), dict) else {}
    snapshot_at = state.get("snapshotAt") or state_meta.get("snapshotAt")

    return {
        "account_id": state.get("account", {}).get("account_id") if isinstance(state.get("account"), dict) else "",
        "currency": account_info.get("currency") or "USD",
        "total_assets": float(account_info.get("total_equity") or account_info.get("totalAssets") or 0),
        "daily_pnl": round(total_pnl, 4),
        "today_pnl": round(total_pnl, 4),
        "today_pnl_percent": round(pnl_ratio, 4),
        "pnl_ratio": round(pnl_ratio, 4),
        "cash": float(account_info.get("cash") or 0),
        "market_value": float(account_info.get("market_value") or account_info.get("marketValue") or 0),
        "buying_power": float(account_info.get("buying_power") or account_info.get("buyingPower") or account_info.get("cash") or 0),
        "maintenance_margin": float(account_info.get("maintenance_margin") or account_info.get("maintenanceMargin") or 0),
        "source": data_source,
        "snapshot_at": snapshot_at,
        "meta": {
            "readModel": "trade-dashboard-summary",
            "defaultMode": default_mode,
            "dataSource": data_source,
            "snapshotAt": snapshot_at,
            "sources": {
                "account": sources.get("account") or ("broker" if is_live_source else "account_asset_snapshots"),
                "positions": sources.get("positions") or ("broker" if is_live_source else "position_snapshots"),
                "orders": sources.get("orders") or ("broker" if is_live_source else "account_asset_snapshots.payload.recentOrders"),
                "summary": "trade-dashboard-summary",
            },
            "accountSnapshotAt": state_meta.get("accountSnapshotAt") or snapshot_at,
            "positionSnapshotAt": state_meta.get("positionSnapshotAt") or snapshot_at,
            "orderSnapshotAt": state_meta.get("orderSnapshotAt") or snapshot_at,
            "positionCount": int(state.get("positionCount") or len(positions)),
            "orderCount": int(state.get("orderCount") or len(orders)),
            "realtimeOverlay": state_meta.get("realtimeOverlay") or (["broker"] if is_live_source else ["quotes", "order-stream"]),
            "warnings": list(state_meta.get("warnings") or []),
            "degraded": bool(state_meta.get("degraded") or str(data_source or "").endswith("fallback")),
        },
    }


def _extract_websocket_session(websocket: WebSocket) -> Dict[str, Any]:
    raw_token = (
        str(websocket.query_params.get("token") or "").strip()
        or str(websocket.headers.get("authorization") or "").strip()
    )
    if not raw_token:
        raise HTTPException(status_code=401, detail="未登录")
    if raw_token.startswith("Bearer "):
        raw_token = raw_token[7:].strip()
    return decode_token(raw_token)


def _normalize_projection_status(status: Optional[str]) -> Optional[str]:
    value = str(status or "").strip().lower()
    return value or None


def _normalize_projection_action(action: Any) -> str:
    raw = str(action or "").strip().upper()
    if raw in {"BUY", "买入"}:
        return "BUY"
    if raw in {"SELL", "卖出"}:
        return "SELL"
    return raw


def _normalize_projection_order_type(order_type: Any) -> str:
    return str(order_type or "").strip().upper()


def _positive_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _resolve_order_price_value(payload: Dict[str, Any]) -> Optional[float]:
    for key in (
        "price",
        "submitted_price",
        "submittedPrice",
        "request_price",
        "requestPrice",
        "reference_price",
        "referencePrice",
        "limit_price",
        "limitPrice",
        "order_price",
        "orderPrice",
        "trigger_price",
        "triggerPrice",
        "filled_price",
        "filledPrice",
        "avg_price",
        "avgPrice",
    ):
        resolved = _positive_float(payload.get(key))
        if resolved is not None:
            return resolved
    return None


def _upsert_order_projection(
    *,
    user_id: int,
    account_id: int,
    order_id: str,
    symbol: str,
    action: str,
    order_type: str,
    quantity: float,
    price: Optional[float],
    status: str,
) -> None:
    legacy_trade_service._upsert_projection(
        user_id=user_id,
        account_id=account_id,
        order_id=order_id,
        symbol=symbol,
        action=action,
        order_type=order_type,
        quantity=int(quantity or 0),
        price=price,
        status=status,
    )


def _serialize_projected_order(row: Dict[str, Any], account_map: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    account_id = int(row.get("account_id") or 0)
    account = account_map.get(account_id) or {}
    created_at = row.get("created_at")
    updated_at = row.get("updated_at")
    symbol = str(row.get("symbol") or "").strip().upper()
    action = _normalize_projection_action(row.get("action"))
    order_type = _normalize_projection_order_type(row.get("order_type"))
    price = _resolve_order_price_value(row)
    reference_price = _positive_float(row.get("reference_price"))
    request_price = _positive_float(row.get("request_price"))

    return {
        "orderId": str(row.get("order_id") or ""),
        "symbol": symbol,
        "name": symbol,
        "action": action,
        "orderType": order_type,
        "quantity": float(row.get("quantity") or 0),
        "filledQuantity": 0.0,
        "filledAmount": 0.0,
        "price": price if price is not None else None,
        "referencePrice": reference_price,
        "requestPrice": request_price,
        "hasPrice": price is not None,
        "status": str(row.get("status") or "").strip().lower(),
        "createTime": _serialize_datetime(created_at),
        "updateTime": _serialize_datetime(updated_at or created_at),
        "accountId": account_id or None,
        "accountName": account.get("display_name") or _display_account_name(account) if account else "",
        "dataSource": "order-projection",
    }


def _query_projected_orders(
    *,
    user_id: int,
    account_id: Optional[int],
    status: Optional[str],
    limit: int,
) -> List[Dict[str, Any]]:
    where_clauses = ["p.user_id = %s"]
    params: List[Any] = [user_id]

    if account_id is not None:
        where_clauses.append("p.account_id = %s")
        params.append(int(account_id))

    normalized_status = _normalize_projection_status(status)
    if normalized_status:
        where_clauses.append("LOWER(p.status) = %s")
        params.append(normalized_status)

    params.append(max(1, min(int(limit or 200), 500)))
    sql = f"""
        SELECT
            p.account_id,
            p.order_id,
            p.symbol,
            p.action,
            p.order_type,
            p.quantity,
            p.price,
            p.status,
            p.created_at,
            p.updated_at,
            s.request_price,
            s.reference_price
        FROM trade_order_projections p
        LEFT JOIN trade_sagas s
            ON s.user_id = p.user_id
           AND s.account_id = p.account_id
           AND s.order_id = p.order_id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY COALESCE(p.updated_at, p.created_at) DESC, p.order_id DESC
        LIMIT %s
        """
    query_params = tuple(params)
    rows = DbUtil.fetch_all(sql, query_params) or []
    if rows:
        return rows
    return DbUtil.fetch_all_primary(sql, query_params) or []


def _backfill_order_projections(
    *,
    user_id: int,
    account_id: Optional[int],
    status: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    warnings: List[str] = []
    live_rows: List[Dict[str, Any]] = []
    targets = [_get_account_or_404(user_id, int(account_id))] if account_id is not None else _get_accounts(user_id)

    for account in targets:
        current_account_id = int(account.get("id") or 0)
        if current_account_id <= 0:
            continue
        try:
            items = legacy_trade_service._load_orders_for_account(user_id, current_account_id, status)
            live_rows.extend(items)
            for item in items:
                _upsert_order_projection(
                    user_id=user_id,
                    account_id=current_account_id,
                    order_id=str(item.get("order_id") or ""),
                    symbol=str(item.get("symbol") or "").strip().upper(),
                    action=_normalize_projection_action(item.get("side")),
                    order_type=_normalize_projection_order_type(item.get("order_type")),
                    quantity=float(item.get("quantity") or 0),
                    price=_resolve_order_price_value(item),
                    status=str(item.get("status") or "").strip().lower(),
                )
        except Exception as exc:
            warnings.append(f"账户{current_account_id}订单回填失败: {exc}")

    live_rows.sort(key=lambda item: item.get("create_time") or "", reverse=True)
    if limit > 0:
        live_rows = live_rows[:limit]

    data = []
    for item in live_rows:
        data.append(
            {
                "orderId": str(item.get("order_id") or ""),
                "symbol": str(item.get("symbol") or "").strip().upper(),
                "name": str(item.get("symbol") or "").strip().upper(),
                "action": _normalize_projection_action(item.get("side")),
                "orderType": _normalize_projection_order_type(item.get("order_type")),
                "quantity": float(item.get("quantity") or 0),
                "filledQuantity": float(item.get("filled_quantity") or 0),
                "filledAmount": 0.0,
                "price": _resolve_order_price_value(item),
                "referencePrice": _positive_float(item.get("reference_price")),
                "requestPrice": _positive_float(item.get("request_price")),
                "hasPrice": _resolve_order_price_value(item) is not None,
                "status": str(item.get("status") or "").strip().lower(),
                "createTime": item.get("create_time"),
                "updateTime": item.get("create_time"),
                "accountId": item.get("account_id"),
                "accountName": item.get("account_name") or "",
                "dataSource": "live-backfill",
            }
        )

    return {"list": data, "warnings": warnings}


def _list_projected_orders(
    *,
    user_id: int,
    account_id: Optional[int],
    status: Optional[str],
    limit: int,
    allow_fallback: bool = True,
) -> Dict[str, Any]:
    accounts = _get_accounts(user_id)
    account_map = {int(item.get("id") or 0): item for item in accounts if int(item.get("id") or 0) > 0}
    rows = _query_projected_orders(
        user_id=user_id,
        account_id=account_id,
        status=status,
        limit=limit,
    )

    def build_projection_meta(data_source: str, snapshot_at: Optional[str], count: int, warnings: List[str]) -> Dict[str, Any]:
        return {
            "readModel": "order-projection",
            "defaultMode": "database",
            "dataSource": data_source,
            "snapshotAt": snapshot_at,
            "sources": {
                "orders": "trade_order_projections",
            },
            "query": {
                "accountId": account_id,
                "status": status,
                "limit": int(limit or 0),
            },
            "count": int(count or 0),
            "warnings": warnings,
            "realtimeOverlay": ["order-stream"],
        }

    if rows:
        items = [_serialize_projected_order(row, account_map) for row in rows]
        snapshot_at = max((item.get("updateTime") or item.get("createTime") or "") for item in items) if items else None
        warnings: List[str] = []
        return {
            "list": items,
            "count": len(items),
            "dataSource": "order-projection",
            "snapshotAt": snapshot_at,
            "warnings": warnings,
            "meta": build_projection_meta("order-projection", snapshot_at, len(items), warnings),
        }

    if not allow_fallback:
        warnings = []
        return {
            "list": [],
            "count": 0,
            "dataSource": "order-projection",
            "snapshotAt": None,
            "warnings": warnings,
            "meta": build_projection_meta("order-projection", None, 0, warnings),
        }

    fallback = _backfill_order_projections(
        user_id=user_id,
        account_id=account_id,
        status=status,
        limit=limit,
    )
    items = fallback.get("list") or []
    snapshot_at = max((item.get("updateTime") or item.get("createTime") or "") for item in items) if items else None
    warnings = fallback.get("warnings") or []
    data_source = "live-backfill" if items else "order-projection"
    return {
        "list": items,
        "count": len(items),
        "dataSource": data_source,
        "snapshotAt": snapshot_at,
        "warnings": warnings,
        "meta": build_projection_meta(data_source, snapshot_at, len(items), warnings),
    }
    positions = [
        {
            "symbol": item.get("symbol") or "",
            "name": item.get("name") or item.get("symbol") or "",
            "quantity": float(item.get("quantity") or 0),
            "average_cost": float(item.get("avgPrice") or 0),
            "market_price": float(item.get("currentPrice") or 0),
            "market_value": float(item.get("marketValue") or 0),
            "unrealized_pnl": float(item.get("pnl") or 0),
            "realized_pnl": 0.0,
        }
        for item in positions_snapshot
    ]
    return {
        "account": account,
        "accountInfo": account_info,
        "positions": positions,
        "orders": snapshot_orders,
        "positionCount": len(positions),
        "orderCount": snapshot_order_count,
        "dataSource": "snapshot",
        "snapshotAt": account_snapshot.get("snapshotAt") or (positions_snapshot[0].get("snapshotAt") if positions_snapshot else None),
    }


def _get_account_record(user_id: int, account_id: int) -> Dict[str, Any]:
    row = get_user_broker_account(account_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="券商账户不存在")
    return row


def _build_account_detail(user_id: int, account_id: int) -> Dict[str, Any]:
    row = _get_account_record(user_id, account_id)
    account = {
        "id": row.get("id"),
        "broker_type": row.get("broker_type"),
        "broker_name": row.get("broker_name"),
        "account_id": row.get("account_id"),
        "is_default": row.get("is_default"),
        "is_active": row.get("is_active"),
        "created_at": _serialize_datetime(row.get("created_at")),
        "updated_at": _serialize_datetime(row.get("updated_at")),
    }

    if account.get("account_id"):
        account["account_id"] = mask_account_id(account["account_id"])

    account["config"] = build_masked_broker_config(row, account["broker_type"])
    if account["broker_type"] == "longbridge":
        complete = bool(account["config"].get("has_cli_auth"))
    elif account["broker_type"] == "tiger":
        complete = all(
            [
                account["config"].get("has_tiger_id"),
                account["config"].get("has_account"),
                account["config"].get("has_license"),
                account["config"].get("has_private_key_pk1"),
            ]
        )
    else:
        complete = True

    account["credential_status"] = {
        "complete": complete,
        "fields": account["config"],
    }
    return enrich_broker_account(account)


def _save_longbridge_config(user_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    account_row_id = payload.get("account_id")
    existing = None
    if account_row_id not in (None, ""):
        account_row_id = int(account_row_id)
        existing = get_user_broker_account(account_row_id, user_id, "longbridge")
        if not existing:
            raise HTTPException(status_code=404, detail="券商账户不存在")

    config = {
        "account": str(payload.get("account", "")).strip(),
    }
    is_default = bool(payload.get("is_default", existing.get("is_default") if existing else False))
    saved_account_id = LongbridgeAPI.save_config(
        config,
        user_id=user_id,
        is_default=is_default,
        account_row_id=account_row_id,
    )
    ensure_default_selection(saved_account_id, user_id, is_default)
    return {
        "accountId": int(saved_account_id),
        "updated": bool(existing),
        "detail": _build_account_detail(user_id, int(saved_account_id)),
    }


def _save_tiger_config(user_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    account_row_id = payload.get("account_id")
    existing = None
    if account_row_id not in (None, ""):
        account_row_id = int(account_row_id)
        existing = get_user_broker_account(account_row_id, user_id, "tiger")
        if not existing:
            raise HTTPException(status_code=404, detail="券商账户不存在")

    required_fields = ["tiger_id", "account", "license", "private_key_pk1"]
    if not existing:
        for field in required_fields:
            if not str(payload.get(field, "")).strip():
                raise HTTPException(status_code=400, detail=f"缺少必填字段: {field}")

    config = {
        "tiger_id": str(payload.get("tiger_id", "")).strip(),
        "account": str(payload.get("account", "")).strip(),
        "license": str(payload.get("license", "")).strip(),
        "private_key_pk1": str(payload.get("private_key_pk1", "")).strip(),
        "private_key_pk8": str(payload.get("private_key_pk8", "")).strip(),
        "env": str(payload.get("env", existing.get("tiger_env") if existing else "PROD")).strip().upper(),
    }
    is_default = bool(payload.get("is_default", existing.get("is_default") if existing else False))
    saved_account_id = TigerBrokerAPI.save_config(
        config,
        user_id=user_id,
        is_default=is_default,
        account_row_id=account_row_id,
    )
    ensure_default_selection(saved_account_id, user_id, is_default)
    return {
        "accountId": int(saved_account_id),
        "updated": bool(existing),
        "detail": _build_account_detail(user_id, int(saved_account_id)),
    }


def _test_broker_connection(user_id: int, account_id: int) -> Dict[str, Any]:
    record = _get_account_record(user_id, account_id)
    broker_type = str(record.get("broker_type") or "").strip().lower()
    if broker_type == "longbridge":
        broker = LongbridgeAPI(account_id)
    elif broker_type == "tiger":
        broker = TigerBrokerAPI(account_id)
    else:
        raise HTTPException(status_code=400, detail=f"不支持的券商类型: {broker_type}")

    connected = broker.connect()
    if not connected:
        raise HTTPException(status_code=400, detail="连接失败")

    try:
        account_info = broker.get_account_info()
        return {
            "account_id": getattr(account_info, "account_id", ""),
            "currency": getattr(account_info, "currency", ""),
            "cash": float(getattr(account_info, "cash", 0) or 0),
            "market_value": float(getattr(account_info, "market_value", 0) or 0),
            "total_equity": float(getattr(account_info, "total_equity", 0) or 0),
            "buying_power": float(getattr(account_info, "buying_power", 0) or 0),
        }
    finally:
        disconnect = getattr(broker, "disconnect", None)
        if callable(disconnect):
            disconnect()


@asynccontextmanager
async def lifespan(_: FastAPI):
    legacy_trade_service._ensure_trade_schema()
    TradeAuditService.ensure_schema()
    PlatformAuditService.ensure_schema()
    AccountAssetSnapshotService.ensure_schema()
    PositionSnapshotService.ensure_schema()
    legacy_trade_service.outbox_relay.start()
    try:
        yield
    finally:
        legacy_trade_service.outbox_relay.stop()
        kafka_bus.close()


app = FastAPI(
    title="Refactor V2 Trade Service",
    version="0.2.0",
    description="Phase 1 live service for accounts, positions, orders and manual trade execution.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"success": False, "error": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.get("/health")
async def health():
    mysql_ok = bool(DbUtil.query_one("SELECT 1"))
    kafka_status = kafka_bus.get_status()
    outbox_status = legacy_trade_service.outbox_relay.get_status()
    longbridge_status = LongbridgeAPI.get_observability_snapshot()
    kafka_enabled = bool(kafka_status.get("enabled"))
    has_dead_letters = bool(outbox_status.get("deadLetterCount")) and kafka_enabled
    has_pending_backlog = bool(outbox_status.get("pendingCount")) and kafka_enabled
    has_failed_delivery = bool(outbox_status.get("failedCount")) and kafka_enabled
    event_stream_degraded = bool(has_dead_letters or has_pending_backlog or has_failed_delivery)
    if kafka_enabled:
        event_stream_status = "degraded" if (has_dead_letters or has_pending_backlog or has_failed_delivery) else "ok"
    else:
        event_stream_status = "disabled"
    deps = {
        "mysql": build_dependency_status("mysql", "healthy" if mysql_ok else "degraded", detail="订单、投影和审计读写数据库"),
        "kafka": build_dependency_status(
            "kafka",
            "healthy" if kafka_enabled and not has_failed_delivery else ("disabled" if not kafka_enabled else "degraded"),
            detail="订单事件发布总线",
            observed=kafka_status,
        ),
        "outbox": build_dependency_status(
            "outbox",
            event_stream_status,
            detail="订单事件投递与 saga 状态",
            observed=outbox_status,
        ),
    }
    alerts = []
    if has_pending_backlog:
        alerts.append(build_alert("trade-outbox-backlog", "warning", "交易 outbox 存在待发布积压", action="检查 outbox/requeue 或 outbox/repair"))
    if has_dead_letters:
        alerts.append(build_alert("trade-outbox-dead-letter", "critical", "交易事件已进入死信队列", action="检查 dead-letter 并决定 purge/requeue"))
    if has_failed_delivery:
        alerts.append(build_alert("trade-event-delivery-failed", "critical", "事件总线存在投递失败", action="检查 Kafka 连接与 outbox relay 日志"))
    broker_connectivity = {
        "longbridge": _build_longbridge_connectivity_status(longbridge_status)
    }
    return build_health_payload(
        service="trade-service",
        version=app.version,
        port=PORT,
        status=summarize_status(deps.values()),
        deps=deps,
        broker_connectivity=broker_connectivity,
        alerts=alerts,
        capabilities=["order-submit", "order-cancel", "outbox-repair", "position-projection"],
        legacy_compat=legacy_boundary_status("trade"),
        extra={
            "tradeServiceEnabled": bool(settings.TRADE_SERVICE_ENABLED),
            "kafka": kafka_status,
            "outbox": outbox_status,
            "eventStream": {
                "status": event_stream_status,
                "pendingCount": outbox_status.get("pendingCount"),
                "failedCount": outbox_status.get("failedCount"),
                "deadLetterCount": outbox_status.get("deadLetterCount"),
            },
            "longbridge": longbridge_status,
        },
    )


@app.post("/api/v1/trade/outbox/repair")
async def repair_trade_outbox(session: dict = Depends(get_current_session)):
    _ensure_admin_session(session)
    repair_summary = legacy_trade_service.outbox_relay.repair_state()
    outbox_status = legacy_trade_service.outbox_relay.get_status()
    return {
        "success": True,
        "message": "trade outbox 状态已修复",
        "data": {
            "repair": repair_summary,
            "outbox": outbox_status,
        },
    }


@app.get("/api/v1/trade/outbox/events")
async def list_trade_outbox_events(
    status: List[str] = Query(default=[]),
    saga_id: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    include_payload: bool = Query(default=False),
    session: dict = Depends(get_current_session),
):
    _ensure_admin_session(session)
    items = legacy_trade_service.outbox_relay.list_events(
        statuses=status,
        saga_id=saga_id,
        event_type=event_type,
        limit=limit,
        include_payload=include_payload,
    )
    return {
        "success": True,
        "data": items,
        "meta": {
            "count": len(items),
            "limit": limit,
            "status": status,
            "sagaId": saga_id,
            "eventType": event_type,
            "includePayload": include_payload,
        },
    }


@app.get("/api/v1/trade/outbox/sagas")
async def list_trade_outbox_sagas(
    status: List[str] = Query(default=[]),
    limit: int = Query(default=50, ge=1, le=200),
    session: dict = Depends(get_current_session),
):
    _ensure_admin_session(session)
    items = legacy_trade_service.outbox_relay.list_sagas(
        statuses=status,
        limit=limit,
    )
    return {
        "success": True,
        "data": items,
        "meta": {
            "count": len(items),
            "limit": limit,
            "status": status,
        },
    }


@app.post("/api/v1/trade/outbox/requeue")
async def requeue_trade_outbox_events(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    _ensure_admin_session(session)
    event_ids = _extract_event_ids(payload)
    updated = legacy_trade_service.outbox_relay.requeue_events(event_ids)
    return {
        "success": True,
        "message": f"已重放 {updated} 条 outbox 事件",
        "data": {
            "updatedCount": updated,
            "outbox": legacy_trade_service.outbox_relay.get_status(),
        },
    }


@app.post("/api/v1/trade/outbox/sagas/requeue")
async def requeue_trade_outbox_sagas(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    _ensure_admin_session(session)
    saga_ids = _extract_saga_ids(payload)
    updated = legacy_trade_service.outbox_relay.requeue_sagas(saga_ids)
    return {
        "success": True,
        "message": f"已按 saga 重放 {updated} 条 outbox 事件",
        "data": {
            "updatedCount": updated,
            "outbox": legacy_trade_service.outbox_relay.get_status(),
        },
    }


@app.post("/api/v1/trade/outbox/dead-letter/purge")
async def purge_trade_dead_letters(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    _ensure_admin_session(session)
    event_ids = _extract_event_ids(payload)
    deleted = legacy_trade_service.outbox_relay.purge_dead_letters(event_ids)
    return {
        "success": True,
        "message": f"已清理 {deleted} 条 dead-letter 事件",
        "data": {
            "deletedCount": deleted,
            "outbox": legacy_trade_service.outbox_relay.get_status(),
        },
    }


@app.post("/api/v1/trade/outbox/sagas/dead-letter/purge")
async def purge_trade_dead_letters_by_saga(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    _ensure_admin_session(session)
    saga_ids = _extract_saga_ids(payload)
    deleted = legacy_trade_service.outbox_relay.purge_dead_letters_by_saga(saga_ids)
    return {
        "success": True,
        "message": f"已按 saga 清理 {deleted} 条 dead-letter 事件",
        "data": {
            "deletedCount": deleted,
            "outbox": legacy_trade_service.outbox_relay.get_status(),
        },
    }


@app.get("/api/v1/trade/bootstrap")
async def bootstrap_trade(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=12, ge=1, le=60),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    accounts = _get_accounts(user_id)
    default_account = _get_default_account(user_id)
    default_state = None
    warnings: List[str] = []

    if default_account:
        try:
            default_state = _build_account_state(
                user_id=user_id,
                account_id=int(default_account["id"]),
                status=status,
                limit=limit,
            )
        except Exception as exc:
            warnings.append(f"默认账户状态加载失败: {exc}")

    return {
        "success": True,
        "data": {
            "service": "trade-service",
            "status": "live",
            "accounts": accounts,
            "defaultAccount": default_account,
            "defaultState": default_state,
            "relayStatus": legacy_trade_service.outbox_relay.get_status(),
            "kafka": kafka_bus.get_status(),
            "legacySources": [
                "refactor-v2/legacy_trade_service/main.py",
                "refactor-v2/backend-server/src/api/broker_routes.py",
                "refactor-v2/backend-server/src/core/broker/BrokerInterface.py",
            ],
            "warnings": warnings,
        },
    }


@app.get("/api/v1/trade/runtime")
async def runtime_summary(session: dict = Depends(get_current_session)):
    return {
        "success": True,
        "data": {
            "userId": int(session["user_id"]),
            "service": "trade-service",
            "phase": "phase-1-live",
            "port": PORT,
            "relayStatus": legacy_trade_service.outbox_relay.get_status(),
            "kafka": kafka_bus.get_status(),
        },
    }


@app.get("/api/v1/trade/accounts")
async def list_accounts(session: dict = Depends(get_current_session)):
    return {"success": True, "data": _get_accounts(int(session["user_id"]))}


@app.get("/api/v1/trade/brokers/bootstrap")
async def broker_bootstrap(session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    manager = get_broker_manager()
    accounts = _get_accounts(user_id)
    default_account = _get_default_account(user_id)
    return {
        "success": True,
        "data": {
            "accounts": accounts,
            "defaultAccount": default_account,
            "providers": manager.list_supported_brokers(),
        },
    }


@app.get("/api/v1/trade/brokers/providers")
async def broker_providers(session: dict = Depends(get_current_session)):
    _ = session
    return {"success": True, "data": get_broker_manager().list_supported_brokers()}


@app.get("/api/v1/trade/brokers/accounts/{account_id}")
async def broker_account_detail(account_id: int, session: dict = Depends(get_current_session)):
    return {"success": True, "data": _build_account_detail(int(session["user_id"]), account_id)}


@app.post("/api/v1/trade/brokers/accounts/{account_id}/default")
async def broker_account_set_default(account_id: int, session: dict = Depends(get_current_session)):
    success = get_broker_manager().set_default_account(account_id, int(session["user_id"]))
    if not success:
        raise HTTPException(status_code=400, detail="设置默认账户失败")
    return {"success": True, "message": "默认账户设置成功"}


@app.delete("/api/v1/trade/brokers/accounts/{account_id}")
async def broker_account_delete(account_id: int, session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    row = _get_account_record(user_id, account_id)
    DbUtil.execute(
        "UPDATE broker_accounts SET is_active = 0, is_default = 0 WHERE id = %s AND user_id = %s",
        (account_id, user_id),
    )
    if row.get("is_default"):
        next_account = DbUtil.fetch_one(
            """
            SELECT id
            FROM broker_accounts
            WHERE user_id = %s AND is_active = 1
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (user_id,),
        )
        if next_account:
            get_broker_manager().set_default_account(int(next_account.get("id")), user_id)
    return {"success": True, "message": "账户已删除"}


@app.post("/api/v1/trade/brokers/accounts/{account_id}/test")
async def broker_account_test(account_id: int, session: dict = Depends(get_current_session)):
    result = _test_broker_connection(int(session["user_id"]), account_id)
    return {"success": True, "message": "连接成功", "data": result}


@app.post("/api/v1/trade/brokers/longbridge")
async def save_longbridge_broker(
    payload: Dict[str, Any] = Body(default={}),
    session: dict = Depends(get_current_session),
):
    result = _save_longbridge_config(int(session["user_id"]), payload)
    return {"success": True, "message": "长桥配置保存成功", "data": result}


@app.post("/api/v1/trade/brokers/tiger")
async def save_tiger_broker(
    payload: Dict[str, Any] = Body(default={}),
    session: dict = Depends(get_current_session),
):
    result = _save_tiger_config(int(session["user_id"]), payload)
    return {"success": True, "message": "老虎配置保存成功", "data": result}


@app.get("/api/v1/trade/accounts/default")
async def get_default_account(session: dict = Depends(get_current_session)):
    account = _get_default_account(int(session["user_id"]))
    if not account:
        raise HTTPException(status_code=404, detail="暂无券商账户")
    return {"success": True, "data": account}


@app.get("/api/v1/trade/accounts/{account_id}/account")
async def get_account_summary(account_id: int, session: dict = Depends(get_current_session)):
    state = _build_account_state(user_id=int(session["user_id"]), account_id=account_id, limit=1)
    return {
        "success": True,
        "data": {
            "account": state["account"],
            "accountInfo": state["accountInfo"],
        },
    }


@app.get("/api/v1/trade/accounts/{account_id}/summary")
async def get_dashboard_summary(
    account_id: int,
    realtime: bool = Query(default=False),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    if realtime:
        state = _build_account_state(user_id=user_id, account_id=account_id, limit=1)
        return {
            "success": True,
            "data": _build_dashboard_summary_payload(
                state=state,
                data_source=state.get("dataSource") or "live",
                default_mode="realtime",
            ),
        }

    snapshot_summary_state = _build_snapshot_summary_state(user_id=user_id, account_id=account_id)
    snapshot_ready = bool(
        snapshot_summary_state.get("snapshotAt")
        or snapshot_summary_state.get("positionCount")
        or float(snapshot_summary_state.get("accountInfo", {}).get("total_equity") or 0)
    )
    if snapshot_ready:
        return {
            "success": True,
            "data": _build_dashboard_summary_payload(
                state=snapshot_summary_state,
                data_source=snapshot_summary_state.get("dataSource") or "snapshot",
                default_mode="database",
            ),
        }

    try:
        live_state = _build_account_state(user_id=user_id, account_id=account_id, limit=1)
        payload = _build_dashboard_summary_payload(
            state=live_state,
            data_source="live-fallback",
            default_mode="database",
        )
        payload["warning"] = "账户快照暂不可用，当前展示为实时回填结果。"
        return {"success": True, "data": payload}
    except Exception:
        return {
            "success": True,
            "data": _build_dashboard_summary_payload(
                state=snapshot_summary_state,
                data_source=snapshot_summary_state.get("dataSource") or "snapshot",
                default_mode="database",
            ),
        }


@app.get("/api/v1/trade/accounts/{account_id}/positions")
async def get_positions(
    account_id: int,
    realtime: bool = Query(default=False),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    state = _build_account_state(user_id=user_id, account_id=account_id, limit=1) if realtime else _build_snapshot_state(user_id=user_id, account_id=account_id)
    return {
        "success": True,
        "data": state["positions"],
        "meta": _build_positions_meta(
            state=state,
            data_source=state.get("dataSource") or ("live" if realtime else "snapshot"),
            default_mode="realtime" if realtime else "database",
        ),
    }


@app.get("/api/v1/trade/accounts/{account_id}/state")
async def get_account_state(
    account_id: int,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=200),
    realtime: bool = Query(default=False),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    if not realtime:
        snapshot_state = _build_snapshot_state(user_id=user_id, account_id=account_id)
        snapshot_ready = bool(
            snapshot_state.get("snapshotAt")
            or snapshot_state.get("positionCount")
            or float(snapshot_state.get("accountInfo", {}).get("total_equity") or 0)
        )
        if snapshot_ready:
            return {"success": True, "data": snapshot_state}

    return {
        "success": True,
        "data": _build_account_state(
            user_id=user_id,
            account_id=account_id,
            status=status,
            limit=limit,
        ),
    }


@app.get("/api/v1/trade/accounts/{account_id}/snapshot/state")
async def get_account_snapshot_state(account_id: int, session: dict = Depends(get_current_session)):
    return {
        "success": True,
        "data": _build_snapshot_state(
            user_id=int(session["user_id"]),
            account_id=account_id,
        ),
    }


@app.get("/api/v1/trade/orders")
async def get_orders(
    account_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    realtime: bool = Query(default=False),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    if realtime:
        trade_user = legacy_trade_service.AuthUser(user_id=user_id, username="", role=str(session.get("role") or "user"))
        return legacy_trade_service._list_orders(trade_user, account_id, status, limit)

    payload = _list_projected_orders(
        user_id=user_id,
        account_id=account_id,
        status=status,
        limit=limit,
        allow_fallback=False,
    )
    return {"success": True, "data": payload}


@app.get("/api/v1/trade/orders/projection")
async def get_order_projection(
    account_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    session: dict = Depends(get_current_session),
):
    payload = _list_projected_orders(
        user_id=int(session["user_id"]),
        account_id=account_id,
        status=status,
        limit=limit,
        allow_fallback=True,
    )
    return {"success": True, "data": payload}


@app.websocket("/ws/trade/orders")
async def order_projection_socket(websocket: WebSocket):
    try:
        session = _extract_websocket_session(websocket)
    except HTTPException:
        await websocket.close(code=4401)
        return

    user_id = int(session["user_id"])
    await websocket.accept()

    subscription: Dict[str, Any] = {
        "account_id": None,
        "status": None,
        "limit": 200,
    }
    last_serialized = ""

    async def push_orders() -> None:
        nonlocal last_serialized
        payload = _list_projected_orders(
            user_id=user_id,
            account_id=subscription["account_id"],
            status=subscription["status"],
            limit=int(subscription["limit"] or 200),
            allow_fallback=False,
        )
        body = payload.get("list") or []
        serialized = json.dumps(body, ensure_ascii=False, sort_keys=True)
        if serialized == last_serialized:
            return
        last_serialized = serialized
        await websocket.send_json(
            {
                "type": "orders",
                "payload": body,
                "count": payload.get("count") or len(body),
                "accountId": subscription["account_id"],
                "status": subscription["status"],
                "dataSource": payload.get("dataSource") or "order-projection",
                "snapshotAt": payload.get("snapshotAt"),
                "meta": payload.get("meta") or {},
                "receivedAt": datetime.now(timezone.utc).isoformat(),
            }
        )

    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
            except asyncio.TimeoutError:
                await push_orders()
                continue

            if not message:
                continue
            try:
                payload = json.loads(message)
            except Exception:
                payload = {"action": str(message).strip()}

            action = str(payload.get("action") or "").strip().lower()
            if action == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                        "channel": "trade.orders.system",
                        "receivedAt": datetime.now(timezone.utc).isoformat(),
                        "userId": user_id,
                    }
                )
                continue

            if action == "subscribe":
                next_account_id = payload.get("accountId")
                subscription["account_id"] = int(next_account_id) if next_account_id not in (None, "", 0, "0") else None
                subscription["status"] = _normalize_projection_status(payload.get("status"))
                subscription["limit"] = max(1, min(int(payload.get("limit") or 200), 500))
                last_serialized = ""
                await push_orders()
    except WebSocketDisconnect:
        pass


app.mount("/api/v1/trade", legacy_trade_service.app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
