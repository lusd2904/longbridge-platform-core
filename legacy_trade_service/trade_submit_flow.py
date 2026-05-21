from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException, Request

from . import trade_commands as command_support
from .models import AuthUser, OrderSubmitRequest


def _create_submit_order_saga(
    user: AuthUser,
    ctx: command_support._TradeRequestContext,
    payload: OrderSubmitRequest,
    *,
    symbol: str,
    action: str,
    order_type: str,
) -> str:
    saga_id = command_support._create_saga(
        user=user,
        account_id=ctx.account_id,
        saga_type="submit_order",
        symbol=symbol,
        action=action,
        quantity=int(payload.quantity),
        request_price=payload.price,
        order_type=order_type,
        request_id=ctx.request_id,
        initial_event_type="trade.order.requested",
    )
    if payload.source or payload.strategy_context:
        command_support._record_saga_step(
            saga_id,
            "strategy_context",
            "completed",
            "已记录策略下单上下文",
            {
                "source": payload.source,
                "strategyContext": payload.strategy_context,
            },
        )
    return saga_id


def _raise_submit_reference_price_failure(
    user: AuthUser,
    ctx: command_support._TradeRequestContext,
    payload: OrderSubmitRequest,
    *,
    saga_id: str,
    symbol: str,
    action: str,
    order_type: str,
    quote_snapshot: Dict[str, Any],
) -> None:
    message = "无法获取有效参考价格，请稍后再试"
    command_support._record_saga_step(saga_id, "reference_price", "failed", message, quote_snapshot)
    command_support._update_saga_status(saga_id=saga_id, status="failed", message=message)
    command_support._record_outbox_event(saga_id, "trade.order.failed", {"reason": message, "symbol": symbol})
    command_support._audit_trade(
        user=user,
        account_id=ctx.account_id,
        broker_type=ctx.account_row.get("broker_type") or "",
        symbol=symbol,
        action=action,
        order_type=order_type,
        quantity=int(payload.quantity),
        request_price=payload.price,
        reference_price=None,
        risk_level="unknown",
        risk_passed=False,
        status="submit_failed",
        message=message,
        order_id=None,
        request_id=ctx.request_id,
        client_ip=ctx.client_ip,
        extra={
            "quote": quote_snapshot,
            "sagaId": saga_id,
            "source": payload.source,
            "strategyContext": payload.strategy_context,
        },
    )
    raise HTTPException(
        status_code=502,
        detail=command_support._trade_error_detail(
            message,
            reference_price=None,
            quote_snapshot=quote_snapshot,
            extra={
                "sagaId": saga_id,
                "source": payload.source,
                "strategyContext": payload.strategy_context,
            },
        ),
    )


def _complete_reference_price_step(saga_id: str, reference_price: float, quote_snapshot: Dict[str, Any]) -> None:
    command_support._record_saga_step(
        saga_id,
        "reference_price",
        "completed",
        f"已获取参考价格 {reference_price:.4f}",
        {"quote": quote_snapshot, "referencePrice": reference_price},
    )


def _run_submit_risk_gate(
    user: AuthUser,
    ctx: command_support._TradeRequestContext,
    payload: OrderSubmitRequest,
    *,
    saga_id: str,
    symbol: str,
    action: str,
    order_type: str,
    reference_price: float,
    quote_snapshot: Dict[str, Any],
) -> str:
    risk_allowed, risk_message, risk_level = command_support._run_order_risk_check(
        ctx.broker,
        symbol=symbol,
        action=action,
        quantity=int(payload.quantity),
        reference_price=float(reference_price),
    )
    if not risk_allowed:
        command_support._record_saga_step(saga_id, "risk_check", "failed", risk_message, {"riskLevel": risk_level})
        command_support._update_saga_status(
            saga_id=saga_id,
            status="risk_rejected",
            message=risk_message,
            reference_price=reference_price,
        )
        command_support._record_outbox_event(
            saga_id,
            "trade.order.rejected",
            {
                "sagaId": saga_id,
                "reason": risk_message,
                "riskLevel": risk_level,
                "symbol": symbol,
                "source": payload.source,
                "strategyContext": payload.strategy_context,
            },
        )
        command_support._audit_trade(
            user=user,
            account_id=ctx.account_id,
            broker_type=ctx.account_row.get("broker_type") or "",
            symbol=symbol,
            action=action,
            order_type=order_type,
            quantity=int(payload.quantity),
            request_price=payload.price,
            reference_price=float(reference_price),
            risk_level=risk_level,
            risk_passed=False,
            status="risk_rejected",
            message=risk_message,
            order_id=None,
            request_id=ctx.request_id,
            client_ip=ctx.client_ip,
            extra={
                "quote": quote_snapshot,
                "sagaId": saga_id,
                "source": payload.source,
                "strategyContext": payload.strategy_context,
            },
        )
        raise HTTPException(
            status_code=422,
            detail=command_support._trade_error_detail(
                risk_message,
                reference_price=float(reference_price),
                quote_snapshot=quote_snapshot,
                extra={
                    "sagaId": saga_id,
                    "riskLevel": risk_level,
                    "source": payload.source,
                    "strategyContext": payload.strategy_context,
                },
            ),
        )

    command_support._record_saga_step(saga_id, "risk_check", "completed", "交易风控通过", {"riskLevel": risk_level})
    return risk_level


def _handle_broker_submission_failure(
    user: AuthUser,
    ctx: command_support._TradeRequestContext,
    payload: OrderSubmitRequest,
    *,
    saga_id: str,
    symbol: str,
    action: str,
    order_type: str,
    reference_price: float,
    risk_level: str,
    quote_snapshot: Dict[str, Any],
    message: str,
    status_code: int = 502,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    command_support._record_saga_step(saga_id, "broker_submit", "failed", message, extra)
    command_support._update_saga_status(
        saga_id=saga_id,
        status="failed",
        message=message,
        reference_price=reference_price,
    )
    command_support._record_outbox_event(
        saga_id,
        "trade.order.failed",
        {
            "sagaId": saga_id,
            "reason": message,
            "symbol": symbol,
            "source": payload.source,
            "strategyContext": payload.strategy_context,
        },
    )
    command_support._audit_trade(
        user=user,
        account_id=ctx.account_id,
        broker_type=ctx.account_row.get("broker_type") or "",
        symbol=symbol,
        action=action,
        order_type=order_type,
        quantity=int(payload.quantity),
        request_price=payload.price,
        reference_price=float(reference_price),
        risk_level=risk_level,
        risk_passed=True,
        status="submit_failed",
        message=message,
        order_id=None,
        request_id=ctx.request_id,
        client_ip=ctx.client_ip,
        extra={"sagaId": saga_id, **(extra or {})},
    )
    raise HTTPException(
        status_code=status_code,
        detail=command_support._trade_error_detail(
            message,
            reference_price=float(reference_price),
            quote_snapshot=quote_snapshot,
            extra={"sagaId": saga_id, **(extra or {})},
        ),
    )


def _submit_to_broker(
    user: AuthUser,
    ctx: command_support._TradeRequestContext,
    payload: OrderSubmitRequest,
    *,
    saga_id: str,
    symbol: str,
    action: str,
    order_type: str,
    reference_price: float,
    risk_level: str,
    quote_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        return ctx.broker.place_order(
            symbol=symbol,
            action=action,
            quantity=int(payload.quantity),
            order_type=order_type,
            price=float(payload.price) if payload.price is not None else None,
            time_in_force=str(payload.time_in_force or "DAY").strip().upper(),
        )
    except Exception as exc:
        _handle_broker_submission_failure(
            user,
            ctx,
            payload,
            saga_id=saga_id,
            symbol=symbol,
            action=action,
            order_type=order_type,
            reference_price=reference_price,
            risk_level=risk_level,
            quote_snapshot=quote_snapshot,
            message=f"券商下单失败: {exc}",
        )
        raise  # Should not reach here due to HTTPException


def _handle_submit_persistence_failure(
    user: AuthUser,
    ctx: command_support._TradeRequestContext,
    payload: OrderSubmitRequest,
    *,
    saga_id: str,
    symbol: str,
    action: str,
    order_type: str,
    reference_price: float,
    risk_level: str,
    order_id: str,
    quote_snapshot: Dict[str, Any],
    persistence_error: Exception,
) -> None:
    compensation_ok = False
    compensation_message = "下单结果持久化失败，已尝试补偿撤单"
    try:
        compensation_ok = bool(ctx.broker.cancel_order(order_id))
    except Exception:
        compensation_ok = False

    command_support._record_saga_step(
        saga_id,
        "compensation",
        "completed" if compensation_ok else "failed",
        "持久化失败后已执行补偿撤单" if compensation_ok else "持久化失败且补偿撤单失败",
        {"orderId": order_id},
    )
    command_support._update_saga_status(
        saga_id=saga_id,
        status="failed",
        message=compensation_message,
        reference_price=reference_price,
        order_id=order_id,
        compensation_status="cancelled" if compensation_ok else "cancel_failed",
    )
    command_support._record_outbox_event(
        saga_id,
        "trade.order.compensated",
        {
            "sagaId": saga_id,
            "orderId": order_id,
            "compensationStatus": "cancelled" if compensation_ok else "cancel_failed",
            "source": payload.source,
            "strategyContext": payload.strategy_context,
        },
    )
    command_support._audit_trade(
        user=user,
        account_id=ctx.account_id,
        broker_type=ctx.account_row.get("broker_type") or "",
        symbol=symbol,
        action=action,
        order_type=order_type,
        quantity=int(payload.quantity),
        request_price=payload.price,
        reference_price=float(reference_price),
        risk_level=risk_level,
        risk_passed=True,
        status="submit_failed",
        message=compensation_message,
        order_id=order_id,
        request_id=ctx.request_id,
        client_ip=ctx.client_ip,
        extra={
            "sagaId": saga_id,
            "compensationOk": compensation_ok,
            "source": payload.source,
            "strategyContext": payload.strategy_context,
        },
    )
    raise HTTPException(
        status_code=500,
        detail=command_support._trade_error_detail(
            compensation_message,
            reference_price=float(reference_price),
            quote_snapshot=quote_snapshot,
            extra={
                "sagaId": saga_id,
                "compensationOk": compensation_ok,
                "source": payload.source,
                "strategyContext": payload.strategy_context,
            },
        ),
    ) from persistence_error


def _persist_submitted_order(
    user: AuthUser,
    ctx: command_support._TradeRequestContext,
    payload: OrderSubmitRequest,
    *,
    saga_id: str,
    symbol: str,
    action: str,
    order_type: str,
    reference_price: float,
    risk_level: str,
    quote_snapshot: Dict[str, Any],
    broker_result: Dict[str, Any],
) -> str:
    order_id = str(broker_result.get("order_id") or "")
    if not order_id:
        _handle_broker_submission_failure(
            user,
            ctx,
            payload,
            saga_id=saga_id,
            symbol=symbol,
            action=action,
            order_type=order_type,
            reference_price=reference_price,
            risk_level=risk_level,
            quote_snapshot=quote_snapshot,
            message="券商下单结果缺少 order_id，无法确认订单状态",
            extra={
                "brokerResult": broker_result,
                "source": payload.source,
                "strategyContext": payload.strategy_context,
            },
        )

    try:
        command_support._record_saga_step(
            saga_id,
            "broker_submit",
            "completed",
            "券商订单已提交",
            {
                "orderId": order_id,
                "brokerResult": broker_result,
                "source": payload.source,
                "strategyContext": payload.strategy_context,
            },
        )
        command_support._upsert_projection(
            user_id=user.user_id,
            account_id=ctx.account_id,
            order_id=order_id,
            symbol=symbol,
            action=action,
            order_type=order_type,
            quantity=int(payload.quantity),
            price=float(payload.price) if payload.price is not None else float(reference_price),
            status=str(broker_result.get("status") or "submitted"),
        )
        command_support._record_outbox_event(
            saga_id,
            "trade.order.submitted",
            {
                "sagaId": saga_id,
                "orderId": order_id,
                "symbol": symbol,
                "action": action,
                "quantity": int(payload.quantity),
                "accountId": ctx.account_id,
                "referencePrice": float(reference_price),
                "source": payload.source,
                "strategyContext": payload.strategy_context,
            },
        )
        command_support._update_saga_status(
            saga_id=saga_id,
            status="completed",
            message="订单提交成功",
            reference_price=reference_price,
            order_id=order_id,
        )
    except Exception as exc:
        _handle_submit_persistence_failure(
            user,
            ctx,
            payload,
            saga_id=saga_id,
            symbol=symbol,
            action=action,
            order_type=order_type,
            reference_price=reference_price,
            risk_level=risk_level,
            order_id=order_id,
            quote_snapshot=quote_snapshot,
            persistence_error=exc,
        )

    return order_id


def _build_submit_success_response(
    ctx: command_support._TradeRequestContext,
    payload: OrderSubmitRequest,
    *,
    saga_id: str,
    symbol: str,
    action: str,
    order_id: str,
    reference_price: float,
    quote_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "success": True,
        "message": f"{'买入' if action == 'BUY' else '卖出'}订单提交成功: {symbol}",
        "order_id": order_id,
        "symbol": symbol,
        "side": action,
        "quantity": int(payload.quantity),
        "price": float(payload.price) if payload.price is not None else float(reference_price),
        "account_id": ctx.account_id,
        "account_name": command_support._account_display_name(ctx.account_row),
        "saga_id": saga_id,
        "status": "submitted",
        "source": payload.source,
        "strategyContext": payload.strategy_context,
        **command_support._reference_price_meta(float(reference_price), quote_snapshot),
    }


def _submit_order(user: AuthUser, request: Request, payload: OrderSubmitRequest) -> Dict[str, Any]:
    symbol, action, order_type = command_support._validate_submit_payload(payload)
    ctx = command_support._build_trade_request_context(user, request, int(payload.account_id))
    saga_id = _create_submit_order_saga(
        user,
        ctx,
        payload,
        symbol=symbol,
        action=action,
        order_type=order_type,
    )

    reference_price, quote_snapshot = command_support._load_reference_price(ctx.broker, symbol, payload.price)
    if reference_price is None or reference_price <= 0:
        _raise_submit_reference_price_failure(
            user,
            ctx,
            payload,
            saga_id=saga_id,
            symbol=symbol,
            action=action,
            order_type=order_type,
            quote_snapshot=quote_snapshot,
        )

    _complete_reference_price_step(saga_id, float(reference_price), quote_snapshot)
    risk_level = _run_submit_risk_gate(
        user,
        ctx,
        payload,
        saga_id=saga_id,
        symbol=symbol,
        action=action,
        order_type=order_type,
        reference_price=float(reference_price),
        quote_snapshot=quote_snapshot,
    )
    broker_result = _submit_to_broker(
        user,
        ctx,
        payload,
        saga_id=saga_id,
        symbol=symbol,
        action=action,
        order_type=order_type,
        reference_price=float(reference_price),
        risk_level=risk_level,
        quote_snapshot=quote_snapshot,
    )
    order_id = _persist_submitted_order(
        user,
        ctx,
        payload,
        saga_id=saga_id,
        symbol=symbol,
        action=action,
        order_type=order_type,
        reference_price=float(reference_price),
        risk_level=risk_level,
        quote_snapshot=quote_snapshot,
        broker_result=broker_result,
    )
    command_support._audit_trade(
        user=user,
        account_id=ctx.account_id,
        broker_type=ctx.account_row.get("broker_type") or "",
        symbol=symbol,
        action=action,
        order_type=order_type,
        quantity=int(payload.quantity),
        request_price=payload.price,
        reference_price=float(reference_price),
        risk_level=risk_level,
        risk_passed=True,
        status="submitted",
        message="订单提交成功",
        order_id=order_id,
        request_id=ctx.request_id,
        client_ip=ctx.client_ip,
        extra={
            "quote": quote_snapshot,
            "sagaId": saga_id,
            "source": payload.source,
            "strategyContext": payload.strategy_context,
        },
    )
    return _build_submit_success_response(
        ctx,
        payload,
        saga_id=saga_id,
        symbol=symbol,
        action=action,
        order_id=order_id,
        reference_price=float(reference_price),
        quote_snapshot=quote_snapshot,
    )
