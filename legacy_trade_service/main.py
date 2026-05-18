"""
FastAPI 交易执行服务。

职责：
1. 承接 Flask 网关转发过来的交易请求
2. 复用现有券商适配器、风控和审计能力
3. 使用 Saga + Outbox 记录交易状态，支持本地 Kafka 事件流
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import jwt
import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env", override=False)
load_dotenv(ROOT_DIR / "backend-server" / ".env", override=False)

from shared.bootstrap import bootstrap_runtime  # noqa: E402

bootstrap_runtime()

from config.settings import settings  # noqa: E402
from core.broker.LongbridgeAPI import LongbridgeAPI  # noqa: E402
from core.platform.PlatformAuditService import PlatformAuditService  # noqa: E402
from core.platform.TradeAuditService import TradeAuditService  # noqa: E402
from utils.DbUtil import DbUtil  # noqa: E402
from utils.kafka_bus import kafka_bus  # noqa: E402

from legacy_trade_service.models import (
    AuthUser,
    OrderCancelRequest,
    OrderSubmitRequest,
)
from legacy_trade_service.outbox import (
    OutboxRelay,
    _create_saga,
    _ensure_trade_outbox_columns,
    _ensure_trade_schema,
    _insert_outbox,
    _insert_step,
    _record_outbox_event,
    _record_saga_step,
    _serialize_datetime,
    _serialize_payload,
    _update_saga_status,
    _upsert_projection,
    outbox_relay,
)
from legacy_trade_service.account_views import (
    _account_display_name,
    _build_account_summary_payload,
    _build_order_stream_event,
    _ensure_broker_connected,
    _get_broker_for_user,
    _get_default_account,
    _list_accounts,
    _list_orders,
    _load_account_positions,
    _load_account_row,
    _load_account_state,
    _load_orders_for_account,
    _serialize_account_summary,
    _serialize_order,
    _serialize_position,
)
from legacy_trade_service.trade_commands import (
    _audit_trade,
    _cancel_order,
    _load_reference_price,
    _load_reference_price_snapshot,
    _normalize_action,
    _normalize_order_type,
    _quote_last_price,
    _reference_price_meta,
    _run_order_risk_check,
    _submit_order,
    _trade_error_detail,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [trade-service] %(levelname)s %(message)s"
)
logger = logging.getLogger("trade-service")


def _decode_jwt_token(authorization: Optional[str]) -> AuthUser:
    if not authorization:
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization[7:] if authorization.startswith("Bearer ") else authorization
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        return AuthUser(
            user_id=int(payload.get("user_id") or 0),
            username=str(payload.get("username") or ""),
            role=str(payload.get("role") or "user")
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="登录已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="登录令牌无效") from exc


def get_current_user(authorization: Optional[str] = Header(default=None)) -> AuthUser:
    return _decode_jwt_token(authorization)


def _decode_ws_user(websocket: WebSocket) -> AuthUser:
    authorization = websocket.headers.get("authorization")
    if not authorization:
        token = str(websocket.query_params.get("token") or "").strip()
        if token:
            authorization = f"Bearer {token}"
    return _decode_jwt_token(authorization)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _ensure_trade_schema()
    TradeAuditService.ensure_schema()
    PlatformAuditService.ensure_schema()
    outbox_relay.start()
    try:
        yield
    finally:
        outbox_relay.stop()
        kafka_bus.close()


app = FastAPI(
    title="Trade Service",
    description="本地可运行的 FastAPI 交易执行服务",
    version="2.0.0",
    lifespan=lifespan
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
    if isinstance(exc.detail, dict):
        content = {"success": False, **exc.detail}
        content.setdefault("error", "请求失败")
        return JSONResponse(status_code=exc.status_code, content=content)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail
        }
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    logger.exception("trade-service.unhandled", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "trade-service 内部错误",
            "detail": str(exc) if settings.APP_DEBUG else None
        }
    )


@app.get("/health")
def health_check():
    mysql_ok = bool(DbUtil.query_one("SELECT 1"))
    return {
        "status": "healthy" if mysql_ok else "degraded",
        "service": "trade-service",
        "timestamp": datetime.now().isoformat(),
        "tradeServiceEnabled": bool(settings.TRADE_SERVICE_ENABLED),
        "kafka": kafka_bus.get_status(),
        "outbox": outbox_relay.get_status(),
        "longbridge": LongbridgeAPI.get_observability_snapshot()
    }


@app.get("/api/v1/trade/accounts")
def list_trade_accounts(user: AuthUser = Depends(get_current_user)):
    return {
        "success": True,
        "data": _list_accounts(user)
    }


@app.get("/api/v1/trade/accounts/default")
def get_default_trade_account(user: AuthUser = Depends(get_current_user)):
    account = _get_default_account(user)
    if not account:
        raise HTTPException(status_code=404, detail="暂无券商账户")
    return {
        "success": True,
        "data": account
    }


@app.get("/api/v1/trade/accounts/{account_id}/positions")
def get_trade_positions(account_id: int, user: AuthUser = Depends(get_current_user)):
    return {
        "success": True,
        "data": _load_account_positions(user, account_id)
    }


@app.get("/api/v1/trade/accounts/{account_id}/state")
def get_trade_account_state(
    account_id: int,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=200),
    user: AuthUser = Depends(get_current_user)
):
    return {
        "success": True,
        "data": _load_account_state(user, account_id, status=status, limit=limit)
    }


@app.get("/api/v1/trade/accounts/{account_id}/snapshot/state")
def get_trade_account_snapshot_state(account_id: int, user: AuthUser = Depends(get_current_user)):
    return {
        "success": True,
        "data": _load_account_state(user, account_id, limit=30)
    }


@app.get("/api/v1/trade/accounts/{account_id}/summary")
def get_trade_account_summary(
    account_id: int,
    realtime: bool = Query(default=False),
    user: AuthUser = Depends(get_current_user)
):
    return {
        "success": True,
        "data": _build_account_summary_payload(user, account_id, realtime=realtime)
    }


@app.get("/orders")
@app.get("/api/v1/trade/orders")
def list_orders(
    account_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    user: AuthUser = Depends(get_current_user)
):
    return _list_orders(user, account_id, status, limit)


@app.get("/api/v1/trade/orders/projection")
def list_projected_orders(
    account_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    user: AuthUser = Depends(get_current_user)
):
    payload = _list_orders(user, account_id, status, limit)
    snapshot_at = datetime.now().isoformat()
    return {
        "success": True,
        "data": {
            "list": payload.get("orders", []),
            "count": int(payload.get("count") or 0),
            "snapshotAt": snapshot_at,
            "dataSource": "broker-live",
            "warnings": payload.get("warnings", []),
            "meta": {
                "snapshotAt": snapshot_at,
                "sources": {
                    "orders": "broker-live"
                },
                "realtimeOverlay": ["order-stream"]
            }
        }
    }


@app.post("/orders/submit")
@app.post("/api/v1/trade/orders/submit")
def submit_order(payload: OrderSubmitRequest, request: Request, user: AuthUser = Depends(get_current_user)):
    return _submit_order(user, request, payload)


@app.post("/orders/cancel")
@app.post("/api/v1/trade/orders/cancel")
def cancel_order(payload: OrderCancelRequest, request: Request, user: AuthUser = Depends(get_current_user)):
    return _cancel_order(user, request, payload)


@app.get("/sagas/{saga_id}")
@app.get("/api/v1/trade/sagas/{saga_id}")
def get_saga(saga_id: str, user: AuthUser = Depends(get_current_user)):
    saga = DbUtil.fetch_one(
        """
        SELECT saga_id, user_id, account_id, saga_type, status, symbol, action, quantity,
               request_price, reference_price, order_type, order_id, message,
               compensation_status, request_id, created_at, updated_at
        FROM trade_sagas
        WHERE saga_id = %s AND user_id = %s
        LIMIT 1
        """,
        (saga_id, user.user_id)
    )
    if not saga:
        raise HTTPException(status_code=404, detail="未找到 Saga")

    steps = DbUtil.fetch_all(
        """
        SELECT step_name, status, detail, payload_json, created_at
        FROM trade_saga_steps
        WHERE saga_id = %s
        ORDER BY id ASC
        """,
        (saga_id,)
    ) or []
    return {
        "success": True,
        "data": {
            "saga": saga,
            "steps": steps
        }
    }


@app.websocket("/ws/trade/orders")
async def websocket_trade_orders(websocket: WebSocket):
    try:
        user = _decode_ws_user(websocket)
    except HTTPException:
        await websocket.close(code=4401)
        return

    await websocket.accept()

    interval_seconds = max(2, int(os.getenv("REF_TRADE_ORDER_STREAM_INTERVAL_SECONDS", "4")))
    subscription = {
        "account_id": None,
        "status": "",
        "limit": 200,
    }
    last_signature = ""

    async def send_snapshot(force: bool = False) -> None:
        nonlocal last_signature
        event = _build_order_stream_event(
            user=user,
            account_id=subscription["account_id"],
            status=subscription["status"],
            limit=subscription["limit"],
        )
        signature = json.dumps(
            {
                "payload": event.get("payload", []),
                "accountId": event.get("accountId"),
                "status": event.get("status"),
                "warnings": event.get("meta", {}).get("warnings", []),
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        if force or signature != last_signature:
            await websocket.send_json(event)
            last_signature = signature

    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                await send_snapshot(force=False)
                continue
            except WebSocketDisconnect:
                break

            action = str((message or {}).get("action") or "").strip().lower()
            if action == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now().isoformat(),
                })
                continue

            if action != "subscribe":
                await websocket.send_json({
                    "type": "error",
                    "message": "unsupported action",
                    "timestamp": datetime.now().isoformat(),
                })
                continue

            raw_account_id = message.get("accountId")
            subscription["account_id"] = int(raw_account_id) if raw_account_id not in (None, "", 0, "0") else None
            subscription["status"] = str(message.get("status") or "").strip()
            subscription["limit"] = max(1, min(int(message.get("limit") or 200), 500))

            await websocket.send_json({
                "type": "subscribed",
                "accountId": subscription["account_id"],
                "status": subscription["status"],
                "limit": subscription["limit"],
                "timestamp": datetime.now().isoformat(),
            })
            await send_snapshot(force=True)
    except Exception as exc:
        logger.warning("trade.order_stream.error: %s", exc)
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(exc),
                "timestamp": datetime.now().isoformat(),
            })
        except Exception:
            pass
        try:
            await websocket.close(code=1011)
        except Exception:
            pass


@app.post("/outbox/flush")
def flush_outbox(user: AuthUser = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可手动刷新 Outbox")
    count = outbox_relay.flush_pending(limit=120)
    return {
        "success": True,
        "message": f"已尝试推送 {count} 条待处理事件",
        "data": outbox_relay.get_status()
    }


if __name__ == "__main__":
    host = os.getenv("TRADE_SERVICE_HOST", "127.0.0.1")
    port = int(os.getenv("TRADE_SERVICE_PORT", "8002"))
    uvicorn.run(app, host=host, port=port)
