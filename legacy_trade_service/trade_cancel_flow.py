from __future__ import annotations

from typing import Dict

from fastapi import HTTPException, Request

from . import trade_commands as command_support
from .models import AuthUser, OrderCancelRequest


def _create_cancel_order_saga(user: AuthUser, ctx: command_support._TradeRequestContext) -> str:
    return command_support._create_saga(
        user=user,
        account_id=ctx.account_id,
        saga_type="cancel_order",
        symbol="",
        action="CANCEL",
        quantity=0,
        request_price=None,
        order_type="CANCEL",
        request_id=ctx.request_id,
        initial_event_type="trade.order.cancel_requested",
    )


def _raise_cancel_failure(
    user: AuthUser,
    ctx: command_support._TradeRequestContext,
    payload: OrderCancelRequest,
    *,
    saga_id: str,
    message: str,
) -> None:
    command_support._record_saga_step(saga_id, "broker_cancel", "failed", message, {"orderId": payload.order_id})
    command_support._update_saga_status(saga_id=saga_id, status="failed", message=message, order_id=payload.order_id)
    command_support._record_outbox_event(
        saga_id,
        "trade.order.cancel_failed",
        {"sagaId": saga_id, "orderId": payload.order_id},
    )
    command_support._audit_trade(
        user=user,
        account_id=ctx.account_id,
        broker_type=ctx.account_row.get("broker_type") or "",
        symbol="",
        action="CANCEL",
        order_type="CANCEL",
        quantity=0,
        request_price=None,
        reference_price=None,
        risk_level="none",
        risk_passed=True,
        status="cancel_failed",
        message=message,
        order_id=payload.order_id,
        request_id=ctx.request_id,
        client_ip=ctx.client_ip,
        extra={"sagaId": saga_id},
    )
    raise HTTPException(status_code=502, detail=message)


def _build_cancel_success_response(
    ctx: command_support._TradeRequestContext,
    payload: OrderCancelRequest,
    *,
    saga_id: str,
) -> Dict[str, object]:
    return {
        "success": True,
        "message": f"订单 {payload.order_id} 已撤销",
        "order_id": payload.order_id,
        "account_id": ctx.account_id,
        "account_name": command_support._account_display_name(ctx.account_row),
        "saga_id": saga_id,
    }


def _cancel_order(user: AuthUser, request: Request, payload: OrderCancelRequest) -> Dict[str, object]:
    ctx = command_support._build_trade_request_context(user, request, int(payload.account_id))
    saga_id = command_support._create_cancel_order_saga(user, ctx)

    command_support._record_saga_step(saga_id, "cancel_validate", "completed", "已进入撤单流程", {"orderId": payload.order_id})

    try:
        success = bool(ctx.broker.cancel_order(payload.order_id))
    except Exception as exc:
        success = False
        cancel_error = str(exc)
    else:
        cancel_error = ""

    if not success:
        command_support._raise_cancel_failure(
            user,
            ctx,
            payload,
            saga_id=saga_id,
            message=f"撤单失败: {cancel_error or '券商未返回成功状态'}",
        )

    command_support._record_saga_step(saga_id, "broker_cancel", "completed", "券商已接受撤单请求", {"orderId": payload.order_id})
    command_support._update_saga_status(saga_id=saga_id, status="completed", message="订单已撤销", order_id=payload.order_id)
    command_support._record_outbox_event(
        saga_id,
        "trade.order.cancelled",
        {"sagaId": saga_id, "orderId": payload.order_id},
    )
    command_support._upsert_projection(
        user_id=user.user_id,
        account_id=ctx.account_id,
        order_id=payload.order_id,
        symbol="",
        action="CANCEL",
        order_type="CANCEL",
        quantity=0,
        price=None,
        status="cancelled",
    )
    command_support._audit_trade(
        user=user,
        account_id=ctx.account_id,
        broker_type=ctx.account_row.get("broker_type") or "",
        symbol="",
        action="CANCEL",
        order_type="CANCEL",
        quantity=0,
        request_price=None,
        reference_price=None,
        risk_level="none",
        risk_passed=True,
        status="cancelled",
        message="订单已撤销",
        order_id=payload.order_id,
        request_id=ctx.request_id,
        client_ip=ctx.client_ip,
        extra={"sagaId": saga_id},
    )
    return command_support._build_cancel_success_response(ctx, payload, saga_id=saga_id)
