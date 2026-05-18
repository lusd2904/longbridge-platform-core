from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from legacy_trade_service import trade_commands as commands
from legacy_trade_service.models import AuthUser, OrderCancelRequest, OrderSubmitRequest


class BrokerDouble:
    def __init__(
        self,
        *,
        place_result=None,
        place_exception: Exception | None = None,
        cancel_result: bool = True,
        cancel_exception: Exception | None = None,
    ) -> None:
        self.place_result = place_result or {}
        self.place_exception = place_exception
        self.cancel_result = cancel_result
        self.cancel_exception = cancel_exception
        self.cancel_calls: list[str] = []

    def place_order(self, **_: object):
        if self.place_exception is not None:
            raise self.place_exception
        return self.place_result

    def cancel_order(self, order_id: str) -> bool:
        self.cancel_calls.append(order_id)
        if self.cancel_exception is not None:
            raise self.cancel_exception
        return self.cancel_result


def _user() -> AuthUser:
    return AuthUser(user_id=1, username="tester", role="admin")


def _request():
    return SimpleNamespace(headers={"X-Request-ID": "req-1"}, client=SimpleNamespace(host="127.0.0.1"))


def _submit_payload() -> OrderSubmitRequest:
    return OrderSubmitRequest(
        symbol="AAPL",
        action="BUY",
        quantity=10,
        account_id=7,
        price=100.0,
        order_type="LIMIT",
        time_in_force="DAY",
    )


def _cancel_payload() -> OrderCancelRequest:
    return OrderCancelRequest(order_id="ord-1", account_id=7)


def _context(broker: BrokerDouble) -> commands._TradeRequestContext:
    return commands._TradeRequestContext(
        account_id=7,
        account_row={"broker_type": "demo", "broker_name": "Demo", "account_id": "ACC-7"},
        broker=broker,
        request_id="req-1",
        client_ip="127.0.0.1",
    )


def _stub_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(commands, "_record_saga_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(commands, "_update_saga_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(commands, "_record_outbox_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(commands, "_audit_trade", lambda *args, **kwargs: None)


def _stub_submit_context(
    monkeypatch: pytest.MonkeyPatch,
    *,
    broker: BrokerDouble,
    saga_id: str = "saga-submit-1",
) -> None:
    monkeypatch.setattr(commands, "_build_trade_request_context", lambda *args, **kwargs: _context(broker))
    monkeypatch.setattr(commands, "_create_submit_order_saga", lambda *args, **kwargs: saga_id)


def _stub_cancel_context(
    monkeypatch: pytest.MonkeyPatch,
    *,
    broker: BrokerDouble,
    saga_id: str = "saga-cancel-1",
) -> None:
    monkeypatch.setattr(commands, "_build_trade_request_context", lambda *args, **kwargs: _context(broker))
    monkeypatch.setattr(commands, "_create_cancel_order_saga", lambda *args, **kwargs: saga_id)


def test_persist_submitted_order_rejects_missing_order_id_without_projection_or_compensation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = BrokerDouble(place_result={"status": "submitted"})
    projection_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    _stub_side_effects(monkeypatch)
    monkeypatch.setattr(
        commands,
        "_upsert_projection",
        lambda *args, **kwargs: projection_calls.append((args, kwargs)),
    )

    with pytest.raises(HTTPException) as exc_info:
        commands._persist_submitted_order(
            _user(),
            _context(broker),
            _submit_payload(),
            saga_id="saga-submit-1",
            symbol="AAPL",
            action="BUY",
            order_type="LIMIT",
            reference_price=100.0,
            risk_level="low",
            quote_snapshot={"source": "request"},
            broker_result={"status": "submitted"},
        )

    assert exc_info.value.status_code == 502
    assert "order_id" in exc_info.value.detail["error"]
    assert not projection_calls
    assert broker.cancel_calls == []


def test_submit_order_returns_502_when_reference_price_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_side_effects(monkeypatch)
    _stub_submit_context(monkeypatch, broker=BrokerDouble())
    monkeypatch.setattr(commands, "_load_reference_price", lambda *args, **kwargs: (None, {"source": "quote_snapshot"}))

    with pytest.raises(HTTPException) as exc_info:
        commands._submit_order(_user(), _request(), _submit_payload())

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["error"] == "无法获取有效参考价格，请稍后再试"


def test_submit_order_returns_422_when_risk_check_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_side_effects(monkeypatch)
    _stub_submit_context(monkeypatch, broker=BrokerDouble())
    monkeypatch.setattr(commands, "_load_reference_price", lambda *args, **kwargs: (100.0, {"source": "request"}))
    monkeypatch.setattr(commands, "_run_order_risk_check", lambda *args, **kwargs: (False, "risk rejected", "high"))

    with pytest.raises(HTTPException) as exc_info:
        commands._submit_order(_user(), _request(), _submit_payload())

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "risk rejected"


def test_submit_order_returns_502_when_broker_submit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_side_effects(monkeypatch)
    _stub_submit_context(monkeypatch, broker=BrokerDouble(place_exception=RuntimeError("broker down")))
    monkeypatch.setattr(commands, "_load_reference_price", lambda *args, **kwargs: (100.0, {"source": "request"}))
    monkeypatch.setattr(commands, "_run_order_risk_check", lambda *args, **kwargs: (True, "ok", "low"))

    with pytest.raises(HTTPException) as exc_info:
        commands._submit_order(_user(), _request(), _submit_payload())

    assert exc_info.value.status_code == 502
    assert "券商下单失败" in exc_info.value.detail["error"]


def test_submit_order_returns_500_and_attempts_compensation_when_projection_write_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = BrokerDouble(place_result={"order_id": "ord-1", "status": "submitted"}, cancel_result=True)
    saga_statuses: list[str] = []

    monkeypatch.setattr(commands, "_record_saga_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(commands, "_update_saga_status", lambda *args, **kwargs: saga_statuses.append(kwargs["status"]))
    monkeypatch.setattr(commands, "_record_outbox_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(commands, "_audit_trade", lambda *args, **kwargs: None)
    _stub_submit_context(monkeypatch, broker=broker)
    monkeypatch.setattr(commands, "_load_reference_price", lambda *args, **kwargs: (100.0, {"source": "request"}))
    monkeypatch.setattr(commands, "_run_order_risk_check", lambda *args, **kwargs: (True, "ok", "low"))
    monkeypatch.setattr(commands, "_upsert_projection", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db fail")))

    with pytest.raises(HTTPException) as exc_info:
        commands._submit_order(_user(), _request(), _submit_payload())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["error"] == "下单结果持久化失败，已尝试补偿撤单"
    assert broker.cancel_calls == ["ord-1"]
    assert saga_statuses == ["failed"]


def test_submit_order_does_not_mark_saga_completed_before_submitted_event_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = BrokerDouble(place_result={"order_id": "ord-1", "status": "submitted"}, cancel_result=True)
    saga_statuses: list[str] = []
    submitted_event_calls = 0

    monkeypatch.setattr(commands, "_record_saga_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(commands, "_update_saga_status", lambda *args, **kwargs: saga_statuses.append(kwargs["status"]))
    monkeypatch.setattr(commands, "_audit_trade", lambda *args, **kwargs: None)

    def _record_outbox_event(*args, **kwargs):
        nonlocal submitted_event_calls
        event_type = args[1]
        if event_type == "trade.order.submitted":
            submitted_event_calls += 1
            raise RuntimeError("outbox fail")
        return None

    monkeypatch.setattr(commands, "_record_outbox_event", _record_outbox_event)
    _stub_submit_context(monkeypatch, broker=broker)
    monkeypatch.setattr(commands, "_load_reference_price", lambda *args, **kwargs: (100.0, {"source": "request"}))
    monkeypatch.setattr(commands, "_run_order_risk_check", lambda *args, **kwargs: (True, "ok", "low"))
    monkeypatch.setattr(commands, "_upsert_projection", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        commands._submit_order(_user(), _request(), _submit_payload())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["error"] == "下单结果持久化失败，已尝试补偿撤单"
    assert broker.cancel_calls == ["ord-1"]
    assert submitted_event_calls == 1
    assert saga_statuses == ["failed"]


def test_cancel_order_returns_502_when_broker_cancel_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_side_effects(monkeypatch)
    _stub_cancel_context(monkeypatch, broker=BrokerDouble(cancel_result=False))

    with pytest.raises(HTTPException) as exc_info:
        commands._cancel_order(_user(), _request(), _cancel_payload())

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "撤单失败: 券商未返回成功状态"
