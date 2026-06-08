from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend-server" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from core.analysis.StrategyMonitorService import StrategyMonitorService  # noqa: E402


def _position(symbol: str, quantity: int, average_cost: float, market_price: float, market_value: float | None = None):
    return SimpleNamespace(
        symbol=symbol,
        quantity=quantity,
        average_cost=average_cost,
        market_price=market_price,
        market_value=market_value if market_value is not None else quantity * market_price,
    )


def _strategy(strategy_id: int, *, action: str = "SELL", execution_mode: str = "auto") -> dict:
    return {
        "id": strategy_id,
        "name": f"Strategy {strategy_id}",
        "type": "stop_loss" if action == "SELL" else "take_profit",
        "status": "active",
        "executionMode": execution_mode,
        "scheduleFrequency": 1,
        "schedulePeriod": "minute",
        "params": {"threshold": 5 if action == "SELL" else 10, "action": action},
    }


class _Broker:
    def __init__(self, positions):
        self.account_id = 11
        self.is_connected = True
        self._positions = positions

    def connect(self):
        return True

    def get_positions(self):
        return list(self._positions)


class _Manager:
    def __init__(self, positions):
        self._positions = positions

    def get_broker(self, account_id, user_id=1):
        return _Broker(self._positions)


def _install_common_monkeypatches(monkeypatch, *, strategies, positions):
    monkeypatch.setattr(StrategyMonitorService, "ensure_schema", classmethod(lambda cls, user_id=1: None))
    monkeypatch.setattr(StrategyMonitorService, "list_strategies", classmethod(lambda cls, user_id=1: list(strategies)))
    monkeypatch.setattr(StrategyMonitorService, "_mark_strategies_executed", classmethod(lambda cls, user_id, strategy_ids: None))
    monkeypatch.setattr(StrategyMonitorService, "_is_strategy_due", classmethod(lambda cls, strategy: True))
    monkeypatch.setattr(
        "core.analysis.StrategyMonitorService.get_broker_manager",
        lambda: _Manager(positions),
    )
    monkeypatch.setattr(
        "core.analysis.StrategyMonitorService.MarketInsightService.get_latest_snapshots",
        staticmethod(lambda user_id=1: []),
    )
    monkeypatch.setattr(
        "core.analysis.StrategyMonitorService.DbUtil.query_one",
        staticmethod(lambda *args, **kwargs: None),
    )
    monkeypatch.setattr(
        "core.analysis.StrategyMonitorService.DbUtil.execute_sql",
        staticmethod(lambda *args, **kwargs: None),
    )


def test_run_monitor_manual_source_only_records_alert(monkeypatch) -> None:
    _install_common_monkeypatches(
        monkeypatch,
        strategies=[_strategy(1, action="SELL", execution_mode="auto")],
        positions=[_position("AAPL.US", quantity=8, average_cost=100, market_price=90)],
    )
    called = {"submit": 0, "load_orders": 0}
    monkeypatch.setattr(
        StrategyMonitorService,
        "_load_trade_service_orders",
        classmethod(lambda cls, account_id, user_id: called.__setitem__("load_orders", called["load_orders"] + 1) or ([], "")),
    )
    monkeypatch.setattr(
        StrategyMonitorService,
        "_submit_order_intent_via_trade_service",
        classmethod(lambda cls, **kwargs: called.__setitem__("submit", called["submit"] + 1) or {}),
    )

    result = StrategyMonitorService.run_monitor(user_id=1, source="manual")

    assert result["alertCount"] == 1
    assert result["alerts"][0]["execution"]["status"] == "alert_only"
    assert called == {"submit": 0, "load_orders": 0}


def test_delete_strategy_unlinks_risk_orders_before_deleting_strategy(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(StrategyMonitorService, "ensure_schema", classmethod(lambda cls, user_id=1: None))
    monkeypatch.setattr(
        "core.analysis.StrategyMonitorService.DbUtil.execute_sql",
        staticmethod(lambda sql, params=None: calls.append((sql, params)) or 1),
    )

    StrategyMonitorService.delete_strategy(user_id=7, strategy_id=42)

    assert "UPDATE user_risk_orders" in calls[0][0]
    assert "SET strategy_id = 0" in calls[0][0]
    assert "protection order retained as global" in calls[0][1][0]
    assert calls[0][1][-2:] == (7, 42)
    assert "DELETE FROM strategy_alerts" in calls[1][0]
    assert calls[1][1] == (42, 7)
    assert "DELETE FROM strategies" in calls[2][0]
    assert calls[2][1] == (42, 7)


def test_run_monitor_scheduler_auto_sell_submits_full_position(monkeypatch) -> None:
    _install_common_monkeypatches(
        monkeypatch,
        strategies=[_strategy(2, action="SELL", execution_mode="auto")],
        positions=[_position("AAPL.US", quantity=8, average_cost=100, market_price=90)],
    )
    captured = {}
    monkeypatch.setattr(
        StrategyMonitorService,
        "_load_trade_service_orders",
        classmethod(lambda cls, account_id, user_id: ([], "")),
    )
    monkeypatch.setattr(
        StrategyMonitorService,
        "_assert_paper_trading_account",
        classmethod(lambda cls, account_id, user_id: {"id": account_id, "trading_mode": "paper"}),
    )

    def _submit(cls, *, account_id, user_id, order_intent):
        captured.update({"account_id": account_id, "user_id": user_id, "order_intent": order_intent})
        return {
            "status": "executed",
            "order_id": "order-sell-1",
            "standardStatus": "submitted",
            "boundary": "trade-service",
        }

    monkeypatch.setattr(StrategyMonitorService, "_submit_order_intent_via_trade_service", classmethod(_submit))

    result = StrategyMonitorService.run_monitor(user_id=3, source="scheduler")

    execution = result["alerts"][0]["execution"]
    assert captured["order_intent"]["action"] == "SELL"
    assert captured["order_intent"]["quantity"] == 8
    assert execution["status"] == "executed"
    assert execution["orderId"] == "order-sell-1"
    assert execution["boundary"] == "trade-service"


def test_run_monitor_scheduler_reduce_submits_half_position_with_minimum_one_share(monkeypatch) -> None:
    _install_common_monkeypatches(
        monkeypatch,
        strategies=[_strategy(3, action="REDUCE", execution_mode="auto")],
        positions=[_position("TSLA.US", quantity=1, average_cost=100, market_price=112)],
    )
    captured = {}
    monkeypatch.setattr(
        StrategyMonitorService,
        "_load_trade_service_orders",
        classmethod(lambda cls, account_id, user_id: ([], "")),
    )
    monkeypatch.setattr(
        StrategyMonitorService,
        "_assert_paper_trading_account",
        classmethod(lambda cls, account_id, user_id: {"id": account_id, "trading_mode": "paper"}),
    )

    def _submit(cls, *, account_id, user_id, order_intent):
        captured["order_intent"] = order_intent
        return {
            "status": "executed",
            "order_id": "order-reduce-1",
            "standardStatus": "submitted",
            "boundary": "trade-service",
        }

    monkeypatch.setattr(StrategyMonitorService, "_submit_order_intent_via_trade_service", classmethod(_submit))

    result = StrategyMonitorService.run_monitor(user_id=1, source="scheduler")

    execution = result["alerts"][0]["execution"]
    assert captured["order_intent"]["action"] == "SELL"
    assert captured["order_intent"]["quantity"] == 1
    assert execution["action"] == "REDUCE"
    assert execution["orderAction"] == "SELL"
    assert execution["quantity"] == 1


def test_run_monitor_scheduler_auto_order_requires_paper_account(monkeypatch) -> None:
    _install_common_monkeypatches(
        monkeypatch,
        strategies=[_strategy(31, action="SELL", execution_mode="auto")],
        positions=[_position("AAPL.US", quantity=8, average_cost=100, market_price=90)],
    )
    monkeypatch.setattr(
        StrategyMonitorService,
        "_load_trade_service_orders",
        classmethod(lambda cls, account_id, user_id: ([], "")),
    )
    monkeypatch.setattr(
        StrategyMonitorService,
        "_assert_paper_trading_account",
        classmethod(lambda cls, account_id, user_id: (_ for _ in ()).throw(PermissionError("非模拟账户"))),
    )
    monkeypatch.setattr(
        StrategyMonitorService,
        "_submit_order_intent_via_trade_service",
        classmethod(lambda cls, **kwargs: (_ for _ in ()).throw(AssertionError("non-paper auto order must not submit"))),
    )

    result = StrategyMonitorService.run_monitor(user_id=1, source="scheduler")

    execution = result["alerts"][0]["execution"]
    assert execution["status"] == "failed"
    assert execution["reason"] == "非模拟账户"
    assert execution["action"] == "SELL"


def test_run_monitor_scheduler_skips_when_active_same_side_order_exists(monkeypatch) -> None:
    _install_common_monkeypatches(
        monkeypatch,
        strategies=[_strategy(4, action="SELL", execution_mode="auto")],
        positions=[_position("NVDA.US", quantity=5, average_cost=100, market_price=92)],
    )
    monkeypatch.setattr(
        StrategyMonitorService,
        "_load_trade_service_orders",
        classmethod(
            lambda cls, account_id, user_id: (
                [{"symbol": "NVDA.US", "side": "SELL", "status": "Partial-Filled", "order_id": "pending-1"}],
                "",
            )
        ),
    )
    monkeypatch.setattr(
        StrategyMonitorService,
        "_submit_order_intent_via_trade_service",
        classmethod(lambda cls, **kwargs: (_ for _ in ()).throw(AssertionError("duplicate active order must skip submit"))),
    )

    result = StrategyMonitorService.run_monitor(user_id=1, source="scheduler")

    execution = result["alerts"][0]["execution"]
    assert execution["status"] == "skipped"
    assert execution["duplicateOrderId"] == "pending-1"
    assert execution["duplicateStatus"] == "partially_filled"


def test_trade_service_account_lookup_does_not_fall_back_when_strategy_account_id_is_missing(monkeypatch) -> None:
    calls = []

    def _request(cls, *, method, path, user_id, **kwargs):
        calls.append(path)
        if path == "/api/v1/trade/accounts":
            return {"success": True, "data": [{"id": 12, "trading_mode": "paper", "account_id": "LBPT100"}]}
        if path == "/api/v1/trade/accounts/default":
            raise AssertionError("must not fall back to the default account when an explicit account id is missing")
        return {}

    monkeypatch.setattr(StrategyMonitorService, "_request_trade_service", classmethod(_request))

    try:
        StrategyMonitorService._load_trade_service_account(account_id=11, user_id=1)
    except PermissionError as exc:
        assert "指定账户不存在或不可用" in str(exc)
    else:
        raise AssertionError("missing explicit account id must fail")

    assert calls == ["/api/v1/trade/accounts"]


def test_monitor_summary_counts_positions_via_trade_service_without_legacy_broker(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(StrategyMonitorService, "ensure_schema", classmethod(lambda cls, user_id=1: None))
    monkeypatch.setattr(StrategyMonitorService, "list_strategies", classmethod(lambda cls, user_id=1: []))
    monkeypatch.setattr(StrategyMonitorService, "get_alerts", classmethod(lambda cls, user_id=1, limit=20: []))
    monkeypatch.setattr(
        "core.analysis.StrategyMonitorService.DbUtil.fetch_one",
        staticmethod(lambda *args, **kwargs: None),
    )
    monkeypatch.setattr(
        "core.analysis.StrategyMonitorService.get_broker_manager",
        lambda: (_ for _ in ()).throw(AssertionError("summary must not open legacy broker sessions")),
    )

    def _request(cls, *, method, path, user_id, **kwargs):
        calls.append((method, path, user_id))
        if path == "/api/v1/trade/accounts/default":
            return {"success": True, "data": {"id": 22, "tradingMode": "paper"}}
        if path == "/api/v1/trade/accounts/22/positions":
            return {"success": True, "data": [{"symbol": "AAPL.US"}, {"symbol": "MSFT.US"}]}
        raise AssertionError(f"unexpected trade-service path: {path}")

    monkeypatch.setattr(StrategyMonitorService, "_request_trade_service", classmethod(_request))

    result = StrategyMonitorService.get_monitor_summary(user_id=7)

    assert result["overview"]["positionCount"] == 2
    assert calls == [
        ("GET", "/api/v1/trade/accounts/default", 7),
        ("GET", "/api/v1/trade/accounts/22/positions", 7),
    ]
