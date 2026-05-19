from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, Depends, HTTPException, Query


REFACTOR_ROOT = Path(__file__).resolve().parents[3]
if str(REFACTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(REFACTOR_ROOT))

from apps.governance.module_shared import (
    DbUtil,
    PositionSnapshotService,
    QuoteSnapshotService,
    RiskOverviewSnapshotService,
    bootstrap_runtime,
    build_dependency_status,
    build_health_payload,
    build_risk_overview,
    collect_notifications,
    create_service_app,
    ensure_risk_control_tables,
    get_current_session,
    legacy_boundary_status,
    load_risk_limits,
    load_risk_orders,
    normalize_market_symbol,
    service_port,
    summarize_status,
    upsert_notification_states,
)
from apps.intelligence.module_shared import StrategyMonitorService

bootstrap_runtime()


app = create_service_app(
    title="Refactor V2 Risk Service",
    version="0.2.0",
    description="Phase 1 live service for risk overview, protection orders and notification center.",
)
PORT = service_port("REF_RISK_SERVICE_PORT", 8108)
RISK_STRATEGY_EXACT_TYPES = {
    "stop_loss",
    "take_profit",
    "overweight_trim",
    "market_guard",
    "drawdown",
    "drawdown_guard",
    "max_drawdown",
    "position_control",
    "risk_control",
}
RISK_STRATEGY_TYPE_KEYWORDS = (
    "risk",
    "stop",
    "loss",
    "profit",
    "drawdown",
    "position",
    "guard",
    "take",
)
RISK_STRATEGY_TEXT_KEYWORDS = (
    "风控",
    "止损",
    "止盈",
    "仓位",
    "回撤",
    "防守",
    "risk",
    "stop",
    "profit",
    "drawdown",
    "position",
    "guard",
)
RECENT_ALERTS_PER_STRATEGY = 5


def _coerce_account_id(account_id: Optional[int]) -> Optional[int]:
    if account_id in (None, ""):
        return None
    try:
        return int(account_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="account_id 必须是整数") from exc


def _parse_order_payload(payload: dict, price_field: str) -> Dict[str, Any]:
    symbol = normalize_market_symbol(payload.get("symbol"))
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol 不能为空")

    trigger_price = float(payload.get("price") or payload.get(price_field) or 0)
    if trigger_price <= 0:
        raise HTTPException(status_code=400, detail="触发价格必须大于0")

    quantity = payload.get("quantity")
    if quantity not in (None, ""):
        quantity = float(quantity)
        if quantity <= 0:
            raise HTTPException(status_code=400, detail="quantity 必须大于0")

    account_id = payload.get("account_id")
    if account_id not in (None, ""):
        account_id = int(account_id)

    return {
        "symbol": symbol,
        "triggerPrice": trigger_price,
        "quantity": quantity,
        "accountId": account_id,
        "note": payload.get("note"),
    }


def _parse_notification_keys(payload: dict) -> List[str]:
    raw_keys = payload.get("keys") if isinstance(payload.get("keys"), list) else [
        payload.get("notification_key") or payload.get("id")
    ]
    return [str(item).strip() for item in raw_keys if str(item or "").strip()]


def _notification_summary(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    type_counts = {"trade": 0, "risk": 0, "system": 0}
    unread_count = 0
    for item in items:
        item_type = str(item.get("type") or "system").strip().lower()
        if item_type not in type_counts:
            type_counts[item_type] = 0
        type_counts[item_type] += 1
        if not item.get("read"):
            unread_count += 1
    return {
        "totalCount": len(items),
        "unreadCount": unread_count,
        "typeCounts": type_counts,
    }


def _normalize_notification_route(route: Any) -> str:
    raw = str(route or "").strip()
    if raw == "/orders":
        return "/trade"
    if raw == "/profile":
        return "/profile"
    return raw or "/notifications"


def _normalize_notifications(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            **item,
            "route": _normalize_notification_route(item.get("route")),
        }
        for item in items
    ]


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_enabled_risk_strategy(strategy: Dict[str, Any]) -> bool:
    if _normalize_text(strategy.get("status")) != "active":
        return False

    strategy_type = _normalize_text(strategy.get("type"))
    if strategy_type in RISK_STRATEGY_EXACT_TYPES:
        return True
    if any(keyword in strategy_type for keyword in RISK_STRATEGY_TYPE_KEYWORDS):
        return True

    search_text = " ".join(
        str(strategy.get(field) or "")
        for field in ("name", "description")
    ).lower()
    return any(keyword in search_text for keyword in RISK_STRATEGY_TEXT_KEYWORDS)


def _filter_orders_for_account(orders: List[Dict[str, Any]], account_id: Optional[int]) -> List[Dict[str, Any]]:
    if account_id in (None, ""):
        return list(orders)
    safe_account_id = int(account_id)
    return [
        item for item in orders
        if item.get("accountId") in (None, safe_account_id)
    ]


def _group_alerts_by_strategy(alerts: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for alert in alerts:
        strategy_id = int(alert.get("strategyId") or 0)
        if strategy_id <= 0:
            continue
        grouped.setdefault(strategy_id, []).append(alert)
    return grouped


def _build_strategy_order_records(
    strategy: Dict[str, Any],
    *,
    stop_loss_orders: List[Dict[str, Any]],
    take_profit_orders: List[Dict[str, Any]],
) -> Dict[str, Any]:
    strategy_type = _normalize_text(strategy.get("type"))
    stop_loss_records = stop_loss_orders if strategy_type == "stop_loss" else []
    take_profit_records = take_profit_orders if strategy_type == "take_profit" else []

    notes = ["当前保护单记录按用户/账户维护，未与策略 ID 建立直接关联。"]
    if not stop_loss_records and not take_profit_records:
        if strategy_type in {"stop_loss", "take_profit"}:
            notes.append("当前没有可直接复用的同类型保护单记录。")
        else:
            notes.append("当前策略类型没有专属保护单表，仅返回告警/触发记录。")

    return {
        "autoOrderRecords": [],
        "stopLossOrders": stop_loss_records,
        "takeProfitOrders": take_profit_records,
        "orderLinkMode": "unlinked-by-user-account",
        "notes": notes,
    }


def _build_enabled_risk_strategy_payload(user_id: int, account_id: Optional[int]) -> Dict[str, Any]:
    strategies = StrategyMonitorService.list_strategies(user_id=user_id)
    enabled_strategies = [item for item in strategies if _is_enabled_risk_strategy(item)]

    alerts = StrategyMonitorService.get_alerts(user_id=user_id, limit=200)
    alerts_by_strategy = _group_alerts_by_strategy(alerts)
    stop_loss_orders = _filter_orders_for_account(
        _load_risk_orders(user_id, "stop_loss", account_id),
        account_id,
    )
    take_profit_orders = _filter_orders_for_account(
        _load_risk_orders(user_id, "take_profit", account_id),
        account_id,
    )

    items = []
    for strategy in enabled_strategies:
        strategy_id = int(strategy.get("id") or 0)
        strategy_alerts = list(alerts_by_strategy.get(strategy_id, []))
        last_alert_at = strategy_alerts[0].get("createdAt") if strategy_alerts else None

        items.append(
            {
                "id": strategy.get("id"),
                "name": strategy.get("name"),
                "type": strategy.get("type"),
                "status": strategy.get("status"),
                "description": strategy.get("description") or "",
                "ruleParams": strategy.get("params") or {},
                "execution": {
                    "mode": strategy.get("executionMode"),
                    "autoExecute": strategy.get("executionMode") == "auto",
                    "scheduleFrequency": strategy.get("scheduleFrequency"),
                    "schedulePeriod": strategy.get("schedulePeriod"),
                    "lastExecutedAt": strategy.get("lastExecutedAt"),
                },
                "trigger": {
                    "count": int(strategy.get("triggerCount") or 0),
                    "lastTriggeredAt": strategy.get("lastTriggeredAt"),
                },
                "riskRecords": {
                    "alertCount": len(strategy_alerts),
                    "lastAlertAt": last_alert_at,
                    "recentAlerts": strategy_alerts[:RECENT_ALERTS_PER_STRATEGY],
                },
                "orderRecords": _build_strategy_order_records(
                    strategy,
                    stop_loss_orders=stop_loss_orders,
                    take_profit_orders=take_profit_orders,
                ),
            }
        )

    notes = []
    if not items:
        notes.append("当前没有已启用且归类为风控/止损/止盈/仓位/回撤的策略。")
    if not alerts:
        notes.append("当前没有自动风控触发记录，riskRecords.recentAlerts 返回空数组。")
    if not stop_loss_orders and not take_profit_orders:
        notes.append("当前没有可读取的止损/止盈保护单记录，orderRecords 返回空数组。")

    return {
        "enabledStrategies": items,
        "records": {
            "strategyAlerts": alerts,
            "stopLossOrders": stop_loss_orders,
            "takeProfitOrders": take_profit_orders,
            "autoOrderRecords": [],
        },
        "meta": {
            "dataSource": "live-aggregate",
            "accountId": account_id,
            "filters": {
                "status": "active",
                "riskStrategyTypeMode": "exact-and-keyword-match",
            },
            "sources": {
                "strategies": "strategies",
                "strategyAlerts": "strategy_alerts",
                "stopLossOrders": "user_risk_orders",
                "takeProfitOrders": "user_risk_orders",
                "autoOrderRecords": None,
            },
            "counts": {
                "enabledStrategyCount": len(items),
                "strategyAlertCount": len(alerts),
                "stopLossOrderCount": len(stop_loss_orders),
                "takeProfitOrderCount": len(take_profit_orders),
                "autoOrderRecordCount": 0,
            },
            "emptyStates": {
                "autoOrderRecords": "当前服务未落地独立自动挂单执行记录表。",
            },
            "notes": notes,
        },
    }


def _build_risk_bootstrap(user_id: int, account_id: Optional[int]) -> Dict[str, Any]:
    risk_payload = build_risk_overview(user_id=user_id, account_id=account_id)
    recent_notifications = _normalize_notifications(collect_notifications(
        user_id=user_id,
        limit=12,
        notification_type="risk",
    ))
    return {
        "service": "risk-service",
        "status": "live",
        "overview": risk_payload.get("overview") or {},
        "limits": risk_payload.get("config") or {},
        "events": risk_payload.get("events") or [],
        "stopLossOrders": risk_payload.get("stopLossOrders") or [],
        "takeProfitOrders": risk_payload.get("takeProfitOrders") or [],
        "notifications": recent_notifications,
        "notificationSummary": _notification_summary(recent_notifications),
        "legacySources": [
            "refactor-v2/backend-server/src/api/data_routes.py",
            "refactor-v2/backend-server/src/core/analysis/StrategyMonitorService.py",
            "refactor-v2/backend-server/src/core/platform/TradeAuditService.py",
        ],
    }


def _build_risk_snapshot_meta(
    *,
    user_id: int,
    account_id: Optional[int],
    snapshot: Optional[Dict[str, Any]],
    event_count: int,
    stop_loss_count: int,
    take_profit_count: int,
    data_source: str = "snapshot",
) -> Dict[str, Any]:
    position_snapshot_at = None
    if account_id not in (None, ""):
        position_rows = PositionSnapshotService.get_latest(
            user_id=user_id,
            account_id=int(account_id),
        )
        position_snapshot_at = position_rows[0].get("snapshotAt") if position_rows else None

    return {
        "readModel": "risk-overview-snapshot",
        "defaultMode": "database",
        "dataSource": data_source,
        "snapshotAt": snapshot.get("snapshotAt") if snapshot else None,
        "sources": {
            "overview": "risk_overview_snapshots",
            "positions": "position_snapshots",
            "stopLossOrders": "risk_control_orders",
            "takeProfitOrders": "risk_control_orders",
        },
        "positionSnapshotAt": position_snapshot_at,
        "eventCount": int(event_count or 0),
        "stopLossCount": int(stop_loss_count or 0),
        "takeProfitCount": int(take_profit_count or 0),
        "realtimeOverlay": ["quotes", "protection-order-status"],
    }


def _load_cached_risk_orders(user_id: int, order_type: str, account_id: Optional[int]) -> List[Dict[str, Any]]:
    ensure_risk_control_tables()
    where_clauses = ["user_id = %s", "order_type = %s", "status = 'active'"]
    params: List[Any] = [user_id, order_type]
    if account_id not in (None, ""):
        where_clauses.append("(account_id = %s OR account_id IS NULL)")
        params.append(int(account_id))

    rows = DbUtil.fetch_all(
        f"""
        SELECT id, account_id, symbol, trigger_price, quantity, status, note, created_at, updated_at
        FROM user_risk_orders
        WHERE {' AND '.join(where_clauses)}
        ORDER BY updated_at DESC, id DESC
        LIMIT 100
        """,
        tuple(params),
    ) or []
    symbols = [normalize_market_symbol(row.get("symbol")) for row in rows if row.get("symbol")]
    try:
        quote_map = QuoteSnapshotService.get_latest_map(symbols, max_age_minutes=60) if symbols else {}
    except Exception:
        quote_map = {}

    results: List[Dict[str, Any]] = []
    for row in rows:
        symbol = normalize_market_symbol(row.get("symbol"))
        quote = quote_map.get(symbol) or {}
        current_price = float(quote.get("last_price") or quote.get("lastPrice") or quote.get("price") or 0)
        trigger_price = float(row.get("trigger_price") or 0)
        if current_price:
            if order_type == "stop_loss":
                distance = ((current_price - trigger_price) / current_price) * 100
            else:
                distance = ((trigger_price - current_price) / current_price) * 100
        else:
            distance = 0.0
        return_item = {
            "id": int(row.get("id") or 0),
            "accountId": row.get("account_id"),
            "symbol": symbol,
            "price": trigger_price,
            "stopPrice": trigger_price if order_type == "stop_loss" else None,
            "profitPrice": trigger_price if order_type == "take_profit" else None,
            "quantity": float(row.get("quantity") or 0),
            "currentPrice": round(current_price, 4),
            "distance": round(distance, 2),
            "status": row.get("status") or "active",
            "note": row.get("note") or "",
            "updatedAt": row.get("updated_at").strftime("%Y-%m-%d %H:%M:%S") if row.get("updated_at") else None,
            "createdAt": row.get("created_at").strftime("%Y-%m-%d %H:%M:%S") if row.get("created_at") else None,
            "dataSource": "risk-order-snapshot",
        }
        results.append(return_item)
    return results


def _build_risk_snapshot_payload(
    *,
    user_id: int,
    account_id: Optional[int],
    snapshot: Optional[Dict[str, Any]] = None,
    warning: Optional[str] = None,
) -> Dict[str, Any]:
    snapshot_payload = snapshot if snapshot is not None else RiskOverviewSnapshotService.get_latest(
        user_id=user_id,
        account_id=account_id,
    )
    snapshot_events = (snapshot_payload.get("events") or []) if snapshot_payload else []
    stop_loss_orders = _load_cached_risk_orders(user_id, "stop_loss", account_id)
    take_profit_orders = _load_cached_risk_orders(user_id, "take_profit", account_id)
    payload = {
        "config": load_risk_limits(user_id),
        "overview": snapshot_payload.get("overview") or {} if snapshot_payload else {},
        "events": snapshot_events,
        "stopLossOrders": stop_loss_orders,
        "takeProfitOrders": take_profit_orders,
        "dataSource": "snapshot",
        "snapshotAt": snapshot_payload.get("snapshotAt") if snapshot_payload else None,
        "meta": _build_risk_snapshot_meta(
            user_id=user_id,
            account_id=account_id,
            snapshot=snapshot_payload,
            event_count=len(snapshot_events),
            stop_loss_count=len(stop_loss_orders),
            take_profit_count=len(take_profit_orders),
            data_source="snapshot",
        ),
    }
    if warning:
        payload["warning"] = warning[:180]
    return payload


def _build_notifications_bootstrap(
    user_id: int,
    *,
    limit: int,
    notification_type: str,
) -> Dict[str, Any]:
    if notification_type:
        items = _normalize_notifications(collect_notifications(
            user_id=user_id,
            limit=limit,
            notification_type=notification_type,
        ))
        summary_items = items
    else:
        all_items = _normalize_notifications(collect_notifications(
            user_id=user_id,
            limit=max(100, limit),
            notification_type="",
        ))
        items = all_items[:limit]
        summary_items = all_items
    return {
        "service": "risk-service",
        "status": "live",
        "type": notification_type or "all",
        "items": items,
        "summary": _notification_summary(summary_items),
    }


def _load_risk_limits(user_id: int) -> Dict[str, Any]:
    return load_risk_limits(user_id)


def _load_risk_orders(user_id: int, order_type: str, account_id: Optional[int]) -> List[Dict[str, Any]]:
    return load_risk_orders(
        user_id=user_id,
        order_type=order_type,
        account_id=account_id,
    )


@app.get("/health")
async def health():
    mysql_ok = bool(DbUtil.query_one("SELECT 1"))
    deps = {
        "mysql": build_dependency_status("mysql", "healthy" if mysql_ok else "degraded", detail="风控总览、保护单与通知读写数据库"),
    }
    return build_health_payload(
        service="risk-service",
        version=app.version,
        port=PORT,
        status=summarize_status(deps.values()),
        deps=deps,
        capabilities=["risk-overview", "stoploss", "notifications"],
        legacy_compat=legacy_boundary_status("risk"),
    )


@app.get("/api/v1/risk/bootstrap")
async def risk_bootstrap(
    account_id: Optional[int] = Query(default=None),
    session: dict = Depends(get_current_session),
):
    return {
        "success": True,
        "data": _build_risk_bootstrap(
            int(session["user_id"]),
            _coerce_account_id(account_id),
        ),
    }


@app.get("/api/v1/risk/overview")
async def risk_overview(
    account_id: Optional[int] = Query(default=None),
    realtime: bool = Query(default=False),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    safe_account_id = _coerce_account_id(account_id)
    if not realtime:
        snapshot = RiskOverviewSnapshotService.get_latest(
            user_id=user_id,
            account_id=safe_account_id,
        )
        return {
            "success": True,
            "data": _build_risk_snapshot_payload(
                user_id=user_id,
                account_id=safe_account_id,
                snapshot=snapshot,
            ),
        }

    try:
        payload = build_risk_overview(
            user_id=user_id,
            account_id=safe_account_id,
        )
        payload["meta"] = _build_risk_snapshot_meta(
            user_id=user_id,
            account_id=safe_account_id,
            snapshot={"snapshotAt": payload.get("snapshotAt")},
            event_count=len(payload.get("events") or []),
            stop_loss_count=len(payload.get("stopLossOrders") or []),
            take_profit_count=len(payload.get("takeProfitOrders") or []),
            data_source=payload.get("dataSource") or "live",
        )
        RiskOverviewSnapshotService.save_snapshot(
            user_id=user_id,
            account_id=safe_account_id,
            payload=payload,
            source="risk-service",
        )
        return {"success": True, "data": payload}
    except Exception as exc:
        snapshot = RiskOverviewSnapshotService.get_latest(
            user_id=user_id,
            account_id=safe_account_id,
        )
        if snapshot:
            return {
                "success": True,
                "data": _build_risk_snapshot_payload(
                    user_id=user_id,
                    account_id=safe_account_id,
                    snapshot=snapshot,
                    warning=str(exc),
                ),
            }
        raise


@app.get("/api/v1/risk/overview/snapshot")
async def risk_overview_snapshot(
    account_id: Optional[int] = Query(default=None),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    safe_account_id = _coerce_account_id(account_id)
    snapshot = RiskOverviewSnapshotService.get_latest(
        user_id=user_id,
        account_id=safe_account_id,
    )
    return {
        "success": True,
        "data": _build_risk_snapshot_payload(
            user_id=user_id,
            account_id=safe_account_id,
            snapshot=snapshot,
        ),
    }


@app.get("/api/v1/risk/limits")
async def risk_limits(session: dict = Depends(get_current_session)):
    return {"success": True, "data": _load_risk_limits(int(session["user_id"]))}


@app.put("/api/v1/risk/limits")
async def update_risk_limits(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    ensure_risk_control_tables()
    max_position_size = float(payload.get("maxPositionSize", payload.get("max_position_size", 35)) or 35)
    max_loss_per_trade = float(payload.get("maxLossPerTrade", payload.get("max_loss_per_trade", 1000)) or 1000)
    max_daily_loss = float(payload.get("maxDailyLoss", payload.get("max_daily_loss", 5000)) or 5000)
    max_drawdown = float(payload.get("maxDrawdown", payload.get("max_drawdown", 20)) or 20)
    volatility_limit = float(payload.get("volatilityLimit", payload.get("volatility_limit", 50)) or 50)

    DbUtil.execute_sql(
        """
        INSERT INTO user_risk_limits (
            user_id, max_position_size, max_loss_per_trade, max_daily_loss, max_drawdown, volatility_limit
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            max_position_size = VALUES(max_position_size),
            max_loss_per_trade = VALUES(max_loss_per_trade),
            max_daily_loss = VALUES(max_daily_loss),
            max_drawdown = VALUES(max_drawdown),
            volatility_limit = VALUES(volatility_limit),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            max_position_size,
            max_loss_per_trade,
            max_daily_loss,
            max_drawdown,
            volatility_limit,
        ),
    )
    return {"success": True, "data": _load_risk_limits(user_id), "message": "风控设置已保存"}


@app.get("/api/v1/risk/events")
async def risk_events(
    account_id: Optional[int] = Query(default=None),
    session: dict = Depends(get_current_session),
):
    payload = build_risk_overview(
        user_id=int(session["user_id"]),
        account_id=_coerce_account_id(account_id),
    )
    return {"success": True, "data": payload.get("events") or []}


@app.get("/api/v1/risk/strategies/enabled")
async def enabled_risk_strategies(
    account_id: Optional[int] = Query(default=None),
    session: dict = Depends(get_current_session),
):
    return {
        "success": True,
        "data": _build_enabled_risk_strategy_payload(
            user_id=int(session["user_id"]),
            account_id=_coerce_account_id(account_id),
        ),
    }


@app.get("/api/v1/risk/stoploss")
async def risk_stoploss_orders(
    account_id: Optional[int] = Query(default=None),
    session: dict = Depends(get_current_session),
):
    return {
        "success": True,
        "data": _load_risk_orders(int(session["user_id"]), "stop_loss", _coerce_account_id(account_id)),
    }


@app.post("/api/v1/risk/stoploss")
async def create_stoploss_order(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    ensure_risk_control_tables()
    parsed = _parse_order_payload(payload, "stopPrice")
    DbUtil.execute_sql(
        """
        INSERT INTO user_risk_orders (user_id, account_id, symbol, order_type, trigger_price, quantity, status, note)
        VALUES (%s, %s, %s, 'stop_loss', %s, %s, 'active', %s)
        ON DUPLICATE KEY UPDATE
            account_id = VALUES(account_id),
            trigger_price = VALUES(trigger_price),
            quantity = VALUES(quantity),
            status = 'active',
            note = VALUES(note),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            parsed["accountId"],
            parsed["symbol"],
            parsed["triggerPrice"],
            parsed["quantity"],
            parsed["note"],
        ),
    )
    return {"success": True, "message": "止损规则已保存"}


@app.post("/api/v1/risk/stoploss/cancel")
async def cancel_stoploss_order(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    order_id = int(payload.get("order_id") or 0)
    if order_id <= 0:
        raise HTTPException(status_code=400, detail="order_id 无效")
    DbUtil.execute_sql(
        """
        UPDATE user_risk_orders
        SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
        WHERE id = %s AND user_id = %s AND order_type = 'stop_loss'
        """,
        (order_id, int(session["user_id"])),
    )
    return {"success": True, "message": "止损规则已取消"}


@app.get("/api/v1/risk/takeprofit")
async def risk_takeprofit_orders(
    account_id: Optional[int] = Query(default=None),
    session: dict = Depends(get_current_session),
):
    return {
        "success": True,
        "data": _load_risk_orders(int(session["user_id"]), "take_profit", _coerce_account_id(account_id)),
    }


@app.post("/api/v1/risk/takeprofit")
async def create_takeprofit_order(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    ensure_risk_control_tables()
    parsed = _parse_order_payload(payload, "profitPrice")
    DbUtil.execute_sql(
        """
        INSERT INTO user_risk_orders (user_id, account_id, symbol, order_type, trigger_price, quantity, status, note)
        VALUES (%s, %s, %s, 'take_profit', %s, %s, 'active', %s)
        ON DUPLICATE KEY UPDATE
            account_id = VALUES(account_id),
            trigger_price = VALUES(trigger_price),
            quantity = VALUES(quantity),
            status = 'active',
            note = VALUES(note),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            parsed["accountId"],
            parsed["symbol"],
            parsed["triggerPrice"],
            parsed["quantity"],
            parsed["note"],
        ),
    )
    return {"success": True, "message": "止盈规则已保存"}


@app.post("/api/v1/risk/takeprofit/cancel")
async def cancel_takeprofit_order(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    order_id = int(payload.get("order_id") or 0)
    if order_id <= 0:
        raise HTTPException(status_code=400, detail="order_id 无效")
    DbUtil.execute_sql(
        """
        UPDATE user_risk_orders
        SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
        WHERE id = %s AND user_id = %s AND order_type = 'take_profit'
        """,
        (order_id, int(session["user_id"])),
    )
    return {"success": True, "message": "止盈规则已取消"}


@app.get("/api/v1/notifications/bootstrap")
async def notifications_bootstrap(
    limit: int = Query(default=60, ge=10, le=100),
    notification_type: str = Query(default="", alias="type"),
    session: dict = Depends(get_current_session),
):
    payload = _build_notifications_bootstrap(
        int(session["user_id"]),
        limit=limit,
        notification_type=str(notification_type or "").strip().lower(),
    )
    return {"success": True, "data": payload}


@app.get("/api/v1/notifications")
async def notifications(
    limit: int = Query(default=60, ge=10, le=100),
    notification_type: str = Query(default="", alias="type"),
    session: dict = Depends(get_current_session),
):
    items = _normalize_notifications(collect_notifications(
        user_id=int(session["user_id"]),
        limit=limit,
        notification_type=str(notification_type or "").strip().lower(),
    ))
    return {"success": True, "data": items}


@app.post("/api/v1/notifications/read")
async def read_notification(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    updated = upsert_notification_states(
        int(session["user_id"]),
        _parse_notification_keys(payload),
        is_read=True,
    )
    return {"success": True, "data": {"updated": updated}}


@app.post("/api/v1/notifications/read-all")
async def read_all_notifications(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    items = collect_notifications(
        user_id=int(session["user_id"]),
        limit=100,
        notification_type=str(payload.get("type", "") or "").strip().lower(),
    )
    updated = upsert_notification_states(
        int(session["user_id"]),
        [item.get("notificationKey") for item in items],
        is_read=True,
    )
    return {"success": True, "data": {"updated": updated}}


@app.post("/api/v1/notifications/delete")
async def delete_notification(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    updated = upsert_notification_states(
        int(session["user_id"]),
        _parse_notification_keys(payload),
        is_hidden=True,
    )
    return {"success": True, "data": {"updated": updated}}


@app.post("/api/v1/notifications/clear")
async def clear_notifications(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    items = collect_notifications(
        user_id=int(session["user_id"]),
        limit=100,
        notification_type=str(payload.get("type", "") or "").strip().lower(),
    )
    updated = upsert_notification_states(
        int(session["user_id"]),
        [item.get("notificationKey") for item in items],
        is_hidden=True,
    )
    return {"success": True, "data": {"updated": updated}}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
