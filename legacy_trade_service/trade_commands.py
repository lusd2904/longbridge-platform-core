from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Request

from shared.bootstrap import bootstrap_runtime

bootstrap_runtime()

from legacy_trade_service.account_views import (  # noqa: E402
    _account_display_name,
    _get_broker_for_user,
    _load_account_row,
)
from legacy_trade_service.models import AuthUser, OrderCancelRequest, OrderSubmitRequest  # noqa: E402
from legacy_trade_service.outbox import (  # noqa: E402
    _create_saga,
    _record_outbox_event,
    _record_saga_step,
    _update_saga_status,
    _upsert_projection,
)


from legacy_trade_service.trade_support import (
    _audit_trade,
    _load_reference_price,
    _load_reference_price_snapshot,
    _normalize_action,
    _normalize_order_type,
    _quote_last_price,
    _reference_price_meta,
    _run_order_risk_check,
    _trade_error_detail,
)


logger = logging.getLogger("trade-service")


@dataclass(frozen=True)
class _TradeRequestContext:
    account_id: int
    account_row: Dict[str, Any]
    broker: Any
    request_id: Optional[str]
    client_ip: Optional[str]


def _build_trade_request_context(user: AuthUser, request: Request, account_id: int) -> _TradeRequestContext:
    account_row = _load_account_row(user.user_id, account_id)
    broker = _get_broker_for_user(user.user_id, account_id)
    request_id = request.headers.get("X-Request-ID")
    client_ip = request.client.host if request.client else None
    return _TradeRequestContext(
        account_id=account_id,
        account_row=account_row,
        broker=broker,
        request_id=request_id,
        client_ip=client_ip,
    )


def _validate_submit_payload(payload: OrderSubmitRequest) -> Tuple[str, str, str]:
    symbol = str(payload.symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol 不能为空")

    action = _normalize_action(payload.action)
    order_type = _normalize_order_type(payload.order_type)
    if order_type == "LIMIT" and payload.price is None:
        raise HTTPException(status_code=400, detail="限价单必须提供 price")
    return symbol, action, order_type

from legacy_trade_service.trade_submit_flow import (
    _build_submit_success_response,
    _complete_reference_price_step,
    _create_submit_order_saga,
    _handle_submit_persistence_failure,
    _persist_submitted_order,
    _raise_submit_reference_price_failure,
    _run_submit_risk_gate,
    _submit_order,
    _submit_to_broker,
)
from legacy_trade_service.trade_cancel_flow import (
    _build_cancel_success_response,
    _cancel_order,
    _create_cancel_order_saga,
    _raise_cancel_failure,
)
