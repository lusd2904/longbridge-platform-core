from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException

from shared.bootstrap import bootstrap_runtime

bootstrap_runtime()

from core.account.RiskManager import get_risk_manager  # noqa: E402
from core.platform.PlatformAuditService import PlatformAuditService  # noqa: E402
from core.platform.TradeAuditService import TradeAuditService  # noqa: E402
from core.readmodel.QuoteSnapshotService import QuoteSnapshotService  # noqa: E402

from legacy_trade_service.models import AuthUser  # noqa: E402

logger = logging.getLogger("trade-service")


def _normalize_action(value: Any) -> str:
    action = str(value or "").strip().upper()
    if action in {"BUY", "B"}:
        return "BUY"
    if action in {"SELL", "S"}:
        return "SELL"
    raise HTTPException(status_code=400, detail="action 只支持 BUY 或 SELL")


def _normalize_order_type(value: Any) -> str:
    order_type = str(value or "LIMIT").strip().upper()
    if order_type not in {"LIMIT", "MARKET"}:
        raise HTTPException(status_code=400, detail="order_type 只支持 LIMIT 或 MARKET")
    return order_type


def _quote_last_price(quote: Any) -> Optional[float]:
    value = getattr(quote, "last_price", None)
    if isinstance(quote, dict):
        value = quote.get("last_price")
    try:
        return float(value) if value is not None else None
    except Exception:
        return None


def _load_reference_price_snapshot(symbol: str) -> Tuple[Optional[float], Dict[str, Any]]:
    snapshot = QuoteSnapshotService.get_latest(symbol, max_age_minutes=240) or {}
    if not snapshot:
        return None, {}

    last_price = _quote_last_price(snapshot)
    if last_price is None or last_price <= 0:
        return None, {}

    return last_price, {
        "symbol": str(snapshot.get("symbol") or symbol).strip().upper(),
        "last_price": float(snapshot.get("last_price") or snapshot.get("price") or 0),
        "prev_close": float(snapshot.get("prev_close") or snapshot.get("prevClose") or 0),
        "open": float(snapshot.get("open") or 0),
        "high": float(snapshot.get("high") or 0),
        "low": float(snapshot.get("low") or 0),
        "volume": int(snapshot.get("volume") or 0),
        "change": float(snapshot.get("change") or snapshot.get("changeAmount") or 0),
        "change_percent": float(snapshot.get("change_percent") or snapshot.get("changePercent") or 0),
        "snapshot_at": snapshot.get("snapshot_at") or snapshot.get("snapshotAt"),
        "source": snapshot.get("source") or "snapshot",
        "fallback": "quote_snapshot",
        "degraded": True,
    }


def _load_reference_price(broker, symbol: str, request_price: Optional[float]) -> Tuple[Optional[float], Dict[str, Any]]:
    if request_price is not None:
        return float(request_price), {
            "symbol": symbol,
            "last_price": float(request_price),
            "snapshot_at": None,
            "source": "request",
            "degraded": False,
        }
    try:
        quotes = broker.get_quote([symbol]) or {}
    except Exception as exc:
        logger.warning("获取实时行情失败，准备回退快照参考价: symbol=%s error=%s", symbol, exc)
        return _load_reference_price_snapshot(symbol)

    quote = quotes.get(symbol)
    last_price = _quote_last_price(quote)
    if last_price is not None and last_price > 0 and quote is not None:
        return last_price, {
            "symbol": symbol,
            "last_price": float(getattr(quote, "last_price", 0) or 0),
            "prev_close": float(getattr(quote, "prev_close", 0) or 0),
            "open": float(getattr(quote, "open", 0) or 0),
            "high": float(getattr(quote, "high", 0) or 0),
            "low": float(getattr(quote, "low", 0) or 0),
            "volume": int(getattr(quote, "volume", 0) or 0),
            "change": float(getattr(quote, "change", 0) or 0),
            "change_percent": float(getattr(quote, "change_percent", 0) or 0),
            "source": "broker",
            "snapshot_at": datetime.now().isoformat(),
            "degraded": False,
        }

    return _load_reference_price_snapshot(symbol)


def _reference_price_meta(reference_price: Optional[float], quote_snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    snapshot = quote_snapshot or {}
    source = str(snapshot.get("source") or "unknown")
    if source == "snapshot" and snapshot.get("fallback") == "quote_snapshot":
        source = "quote_snapshot"

    snapshot_at = snapshot.get("snapshot_at") or snapshot.get("snapshotAt") or None
    degraded = bool(snapshot.get("degraded") or source == "quote_snapshot")

    return {
        "referencePrice": float(reference_price) if reference_price is not None else None,
        "referencePriceSource": source,
        "referencePriceSnapshotAt": snapshot_at,
        "degraded": degraded,
        "quoteSnapshot": snapshot if snapshot else None,
    }


def _trade_error_detail(
    message: str,
    *,
    reference_price: Optional[float] = None,
    quote_snapshot: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "error": message,
        "data": {
            **_reference_price_meta(reference_price, quote_snapshot),
            **(extra or {}),
        },
    }


def _run_order_risk_check(
    broker,
    symbol: str,
    action: str,
    quantity: int,
    reference_price: float,
) -> Tuple[bool, str, str]:
    account_info = broker.get_account_info()
    positions = broker.get_positions()
    passed, message, level = get_risk_manager().check_order_risk(
        symbol=symbol,
        side=action,
        quantity=quantity,
        price=reference_price,
        account_info={"total_equity": float(getattr(account_info, "total_equity", 0) or 0)},
        positions=[
            {
                "symbol": getattr(item, "symbol", ""),
                "market_value": float(getattr(item, "market_value", 0) or 0),
            }
            for item in positions
        ],
    )
    return passed, message, level.value


def _audit_trade(
    *,
    user: AuthUser,
    account_id: int,
    broker_type: str,
    symbol: str,
    action: str,
    order_type: str,
    quantity: int,
    request_price: Optional[float],
    reference_price: Optional[float],
    risk_level: str,
    risk_passed: bool,
    status: str,
    message: str,
    order_id: Optional[str],
    request_id: Optional[str],
    client_ip: Optional[str],
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    TradeAuditService.log(
        user_id=user.user_id,
        username=user.username,
        account_id=account_id,
        broker_type=broker_type,
        symbol=symbol,
        action=action,
        order_type=order_type,
        quantity=quantity,
        request_price=request_price,
        reference_price=reference_price,
        risk_level=risk_level,
        risk_passed=risk_passed,
        status=status,
        message=message,
        order_id=order_id,
        request_id=request_id,
        client_ip=client_ip,
        extra=extra,
    )
    PlatformAuditService.log(
        user_id=user.user_id,
        username=user.username,
        module="trade-service",
        operation=status,
        level="warning" if not risk_passed or status.endswith("failed") else "info",
        description=message,
        extra={
            "accountId": account_id,
            "brokerType": broker_type,
            "symbol": symbol,
            "action": action,
            "orderType": order_type,
            "quantity": quantity,
            "orderId": order_id,
            **(extra or {}),
        },
    )
