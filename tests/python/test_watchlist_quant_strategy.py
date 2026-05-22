from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend-server" / "src"
STRATEGY_MAIN = ROOT / "apps" / "intelligence" / "strategy-service" / "src" / "main.py"
QUANT_SERVICE = ROOT / "backend-server" / "src" / "core" / "analysis" / "QuantTradingService.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))


def _load_module():
    return importlib.import_module("core.analysis.QuantTradingService")


def _trend_series(days: int = 100):
    rows = []
    for index in range(days):
        close = 100 + index * 0.8
        rows.append(
            {
                "date": f"2026-01-{(index % 28) + 1:02d}",
                "open": close - 0.3,
                "high": close + 1.0,
                "low": close - 1.2,
                "close": close,
                "volume": 1_000_000 + index * 10_000,
            }
        )
    return rows


def _patch_strategy_inputs(monkeypatch, module, *, enabled: bool = False):
    service = module.QuantTradingService
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(
        service,
        "_save_watchlist_strategy_run",
        classmethod(lambda cls, **kwargs: {"saved": True, "runId": 1}),
    )
    monkeypatch.setattr(
        service,
        "_load_watchlist_scan_targets",
        classmethod(
            lambda cls, *, user_id, session_filter="all": [
                {"symbol": "AAPL.US", "name": "Apple", "market": "US"}
            ]
        ),
    )
    monkeypatch.setattr(
        module.HistoricalMarketDataService,
        "get_daily_series_until",
        staticmethod(lambda symbol, limit=260: _trend_series()),
    )
    monkeypatch.setattr(
        module.IndicatorSnapshotService,
        "get_snapshot",
        staticmethod(
            lambda symbol, timeframe="daily", user_id=1: {
                "rsi": 62,
                "macdHist": 0.18,
                "roc": 6,
                "momentumScore": 72,
                "atr": 2,
                "supportPrice": 158,
            }
        ),
    )
    monkeypatch.setattr(
        module.DailySymbolTrendScanService,
        "get_latest_for_symbol",
        staticmethod(
            lambda symbol: {
                "trendDirection": "up",
                "trendStrength": 78,
                "riskLevel": "low",
                "technicalScore": 82,
                "summary": "趋势偏多",
            }
        ),
    )

    def fake_config_get(key, *args, **kwargs):
        values = {
            "AI_QUANT_TRADING_ENABLED": enabled,
            "AI_QUANT_AUTO_EXECUTE": False,
        }
        return values.get(key, kwargs.get("default"))

    monkeypatch.setattr(module.AppConfig, "get", staticmethod(fake_config_get))


def test_watchlist_strategy_scans_only_watchlist_targets_without_execution(monkeypatch) -> None:
    module = _load_module()
    _patch_strategy_inputs(monkeypatch, module, enabled=False)
    monkeypatch.setattr(
        module.QuantTradingService,
        "execute_watchlist_opportunities",
        classmethod(lambda cls, **kwargs: (_ for _ in ()).throw(AssertionError("preview must not execute orders"))),
    )

    result = module.QuantTradingService.run_watchlist_strategy_cycle(user_id=1, execute=False)

    assert result["targetCount"] == 1
    assert result["evaluatedCount"] == 1
    assert result["opportunityCount"] == 1
    assert result["opportunities"][0]["symbol"] == "AAPL.US"
    assert result["executed"] is False
    assert result["autoTrade"]["reason"] == "not-requested"
    assert "RecommendationService.refresh(" not in QUANT_SERVICE.read_text(encoding="utf-8")


def test_watchlist_strategy_execute_is_blocked_when_global_quant_disabled(monkeypatch) -> None:
    module = _load_module()
    _patch_strategy_inputs(monkeypatch, module, enabled=False)
    monkeypatch.setattr(
        module.QuantTradingService,
        "execute_watchlist_opportunities",
        classmethod(lambda cls, **kwargs: (_ for _ in ()).throw(AssertionError("disabled quant must not execute"))),
    )

    result = module.QuantTradingService.run_watchlist_strategy_cycle(user_id=1, execute=True)

    assert result["opportunityCount"] == 1
    assert result["executed"] is False
    assert result["autoTrade"]["reason"] == "quant-disabled"


def test_watchlist_strategy_execute_delegates_position_controls_when_enabled(monkeypatch) -> None:
    module = _load_module()
    _patch_strategy_inputs(monkeypatch, module, enabled=True)
    captured = {}

    def fake_execute(cls, **kwargs):
        captured.update(kwargs)
        return {
            "executed": True,
            "submittedCount": 1,
            "signals": [{"symbol": "AAPL.US", "status": "executed"}],
        }

    monkeypatch.setattr(module.QuantTradingService, "execute_watchlist_opportunities", classmethod(fake_execute))

    result = module.QuantTradingService.run_watchlist_strategy_cycle(
        user_id=1,
        execute=True,
        max_symbols=3,
        max_amount=5000,
        max_position_ratio=0.12,
        min_confidence=75,
    )

    assert result["executed"] is True
    assert captured["opportunities"][0]["symbol"] == "AAPL.US"
    assert captured["max_symbols"] == 3
    assert captured["max_amount"] == 5000
    assert captured["max_position_ratio"] == 0.12
    assert captured["min_confidence"] == 75


def test_execute_watchlist_opportunities_rejects_symbols_outside_watchlist(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(service, "_load_watchlist_symbols", classmethod(lambda cls, *, user_id: {"AAPL.US"}))
    monkeypatch.setattr(service, "_has_recent_duplicate", classmethod(lambda cls, user_id, symbol, side: False))
    monkeypatch.setattr(service, "_load_broker_today_orders", classmethod(lambda cls, account_id, user_id: ([], "")))

    class AccountInfo:
        cash = 10_000
        buying_power = 10_000
        total_equity = 50_000

    class FakeBroker:
        is_connected = True
        account_id = 7

        def connect(self):
            return True

        def get_account_info(self):
            return AccountInfo()

        def get_positions(self):
            return []

    executed = []
    monkeypatch.setattr(
        module.PlatformAccessService,
        "get_user_capabilities",
        staticmethod(
            lambda user_id: {
                "hasBoundAccount": True,
                "quantApiEnabled": True,
                "canUseQuantTrading": True,
            }
        ),
    )
    monkeypatch.setattr(service, "_get_broker", staticmethod(lambda account_id=None, user_id=1: FakeBroker()))
    monkeypatch.setattr(
        service,
        "_execute_decision",
        classmethod(lambda cls, account_id, decision, user_id=1: executed.append(decision) or {"status": "executed", "order_id": "order-1"}),
    )
    monkeypatch.setattr(
        service,
        "_save_decision",
        classmethod(lambda cls, **kwargs: {**kwargs["decision"], "status": kwargs["status"], "orderId": kwargs["order_id"]}),
    )

    result = service.execute_watchlist_opportunities(
        user_id=1,
        opportunities=[
            {"symbol": "MSFT.US", "price": 100, "confidence": 90, "reason": "非自选机会"},
            {"symbol": "AAPL.US", "price": 100, "confidence": 90, "reason": "自选机会"},
        ],
        max_symbols=2,
        max_amount=2000,
        min_confidence=72,
    )

    assert result["submittedCount"] == 1
    assert executed[0]["symbol"] == "AAPL.US"
    assert result["skipped"][0]["symbol"] == "MSFT.US"
    assert "不在当前用户自选股池" in result["skipped"][0]["reason"]


def test_execute_watchlist_opportunities_blocks_existing_broker_order(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(service, "_load_watchlist_symbols", classmethod(lambda cls, *, user_id: {"AAPL.US"}))
    monkeypatch.setattr(service, "_has_recent_duplicate", classmethod(lambda cls, user_id, symbol, side: False))
    monkeypatch.setattr(
        service,
        "_load_broker_today_orders",
        classmethod(
            lambda cls, account_id, user_id: (
                [{"symbol": "AAPL.US", "side": "Buy", "status": "New", "order_id": "paper-existing"}],
                "",
            )
        ),
    )

    class AccountInfo:
        cash = 10_000
        buying_power = 10_000
        total_equity = 50_000

    class FakeBroker:
        is_connected = True
        account_id = 7

        def connect(self):
            return True

        def get_account_info(self):
            return AccountInfo()

        def get_positions(self):
            return []

    monkeypatch.setattr(
        module.PlatformAccessService,
        "get_user_capabilities",
        staticmethod(
            lambda user_id: {
                "hasBoundAccount": True,
                "quantApiEnabled": True,
                "canUseQuantTrading": True,
            }
        ),
    )
    monkeypatch.setattr(service, "_get_broker", staticmethod(lambda account_id=None, user_id=1: FakeBroker()))
    monkeypatch.setattr(
        service,
        "_execute_decision",
        classmethod(lambda cls, account_id, decision, user_id=1: (_ for _ in ()).throw(AssertionError("active broker order must block execution"))),
    )

    result = service.execute_watchlist_opportunities(
        user_id=1,
        opportunities=[{"symbol": "AAPL.US", "price": 100, "confidence": 90, "reason": "自选机会"}],
        max_symbols=2,
        max_amount=2000,
        min_confidence=72,
    )

    assert result["submittedCount"] == 0
    assert result["skipped"][0]["orderId"] == "paper-existing"
    assert "已有未完成同向委托" in result["skipped"][0]["reason"]


def test_execute_watchlist_opportunities_blocks_when_broker_order_check_fails(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(service, "_load_watchlist_symbols", classmethod(lambda cls, *, user_id: {"AAPL.US"}))
    monkeypatch.setattr(service, "_has_recent_duplicate", classmethod(lambda cls, user_id, symbol, side: False))
    monkeypatch.setattr(
        service,
        "_load_broker_today_orders",
        classmethod(lambda cls, account_id, user_id: ([], "network timeout")),
    )

    class AccountInfo:
        cash = 10_000
        buying_power = 10_000
        total_equity = 50_000

    class FakeBroker:
        is_connected = True
        account_id = 7

        def connect(self):
            return True

        def get_account_info(self):
            return AccountInfo()

        def get_positions(self):
            return []

    monkeypatch.setattr(
        module.PlatformAccessService,
        "get_user_capabilities",
        staticmethod(
            lambda user_id: {
                "hasBoundAccount": True,
                "quantApiEnabled": True,
                "canUseQuantTrading": True,
            }
        ),
    )
    monkeypatch.setattr(service, "_get_broker", staticmethod(lambda account_id=None, user_id=1: FakeBroker()))
    monkeypatch.setattr(
        service,
        "_execute_decision",
        classmethod(lambda cls, account_id, decision, user_id=1: (_ for _ in ()).throw(AssertionError("failed broker order check must block execution"))),
    )

    result = service.execute_watchlist_opportunities(
        user_id=1,
        opportunities=[{"symbol": "AAPL.US", "price": 100, "confidence": 90, "reason": "自选机会"}],
        max_symbols=2,
        max_amount=2000,
        min_confidence=72,
    )

    assert result["submittedCount"] == 0
    assert "券商当日委托核验失败" in result["skipped"][0]["reason"]


def test_execute_watchlist_opportunities_blocks_recent_local_decision_first(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(service, "_load_watchlist_symbols", classmethod(lambda cls, *, user_id: {"AAPL.US"}))
    monkeypatch.setattr(service, "_has_recent_duplicate", classmethod(lambda cls, user_id, symbol, side: True))
    monkeypatch.setattr(
        service,
        "_load_broker_today_orders",
        classmethod(lambda cls, account_id, user_id: ([{"symbol": "AAPL.US", "side": "Buy", "status": "New"}], "")),
    )

    class AccountInfo:
        cash = 10_000
        buying_power = 10_000
        total_equity = 50_000

    class FakeBroker:
        is_connected = True
        account_id = 7

        def connect(self):
            return True

        def get_account_info(self):
            return AccountInfo()

        def get_positions(self):
            return []

    monkeypatch.setattr(
        module.PlatformAccessService,
        "get_user_capabilities",
        staticmethod(
            lambda user_id: {
                "hasBoundAccount": True,
                "quantApiEnabled": True,
                "canUseQuantTrading": True,
            }
        ),
    )
    monkeypatch.setattr(service, "_get_broker", staticmethod(lambda account_id=None, user_id=1: FakeBroker()))
    monkeypatch.setattr(
        service,
        "_execute_decision",
        classmethod(lambda cls, account_id, decision, user_id=1: (_ for _ in ()).throw(AssertionError("recent duplicate must block execution"))),
    )

    result = service.execute_watchlist_opportunities(
        user_id=1,
        opportunities=[{"symbol": "AAPL.US", "price": 100, "confidence": 90, "reason": "自选机会"}],
        max_symbols=2,
        max_amount=2000,
        min_confidence=72,
    )

    assert result["submittedCount"] == 0
    assert result["skipped"][0]["reason"] == "60 分钟内已有同向决策"


def test_execute_watchlist_opportunities_uses_smallest_budget_and_decrements_cash(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(service, "_load_watchlist_symbols", classmethod(lambda cls, *, user_id: {"AAPL.US", "MSFT.US"}))
    monkeypatch.setattr(service, "_has_recent_duplicate", classmethod(lambda cls, user_id, symbol, side: False))
    monkeypatch.setattr(service, "_load_broker_today_orders", classmethod(lambda cls, account_id, user_id: ([], "")))

    class AccountInfo:
        cash = 1_500
        buying_power = 1_500
        total_equity = 10_000

    class FakeBroker:
        is_connected = True
        account_id = 7

        def connect(self):
            return True

        def get_account_info(self):
            return AccountInfo()

        def get_positions(self):
            return []

    executed = []
    monkeypatch.setattr(
        module.PlatformAccessService,
        "get_user_capabilities",
        staticmethod(
            lambda user_id: {
                "hasBoundAccount": True,
                "quantApiEnabled": True,
                "canUseQuantTrading": True,
            }
        ),
    )
    monkeypatch.setattr(service, "_get_broker", staticmethod(lambda account_id=None, user_id=1: FakeBroker()))
    monkeypatch.setattr(
        service,
        "_execute_decision",
        classmethod(lambda cls, account_id, decision, user_id=1: executed.append(decision) or {"status": "executed", "order_id": f"order-{len(executed)}"}),
    )
    monkeypatch.setattr(
        service,
        "_save_decision",
        classmethod(lambda cls, **kwargs: {**kwargs["decision"], "status": kwargs["status"], "orderId": kwargs["order_id"]}),
    )

    result = service.execute_watchlist_opportunities(
        user_id=1,
        opportunities=[
            {"symbol": "AAPL.US", "price": 100, "confidence": 95, "reason": "第一笔"},
            {"symbol": "MSFT.US", "price": 100, "confidence": 94, "reason": "第二笔"},
        ],
        max_symbols=2,
        max_amount=900,
        max_position_ratio=0.12,
        min_confidence=72,
    )

    assert result["submittedCount"] == 2
    assert [item["quantity"] for item in executed] == [9, 6]
    assert executed[0]["budget"]["budget"] == 900
    assert executed[1]["budget"]["availableCashBefore"] == 600
    assert executed[1]["budget"]["budget"] == 600
    assert result["positionControl"]["budgetRule"] == "min(maxAmount, availableCash, totalEquity * maxPositionRatio)"


def test_execute_watchlist_opportunities_skips_existing_position_and_invalid_price(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(service, "_load_watchlist_symbols", classmethod(lambda cls, *, user_id: {"AAPL.US", "MSFT.US"}))
    monkeypatch.setattr(service, "_has_recent_duplicate", classmethod(lambda cls, user_id, symbol, side: False))
    monkeypatch.setattr(service, "_load_broker_today_orders", classmethod(lambda cls, account_id, user_id: ([], "")))

    class AccountInfo:
        cash = 10_000
        buying_power = 10_000
        total_equity = 50_000

    class Position:
        symbol = "AAPL.US"
        market_value = 2_000

    class FakeBroker:
        is_connected = True
        account_id = 7

        def connect(self):
            return True

        def get_account_info(self):
            return AccountInfo()

        def get_positions(self):
            return [Position()]

    monkeypatch.setattr(
        module.PlatformAccessService,
        "get_user_capabilities",
        staticmethod(
            lambda user_id: {
                "hasBoundAccount": True,
                "quantApiEnabled": True,
                "canUseQuantTrading": True,
            }
        ),
    )
    monkeypatch.setattr(service, "_get_broker", staticmethod(lambda account_id=None, user_id=1: FakeBroker()))
    monkeypatch.setattr(
        service,
        "_execute_decision",
        classmethod(lambda cls, account_id, decision, user_id=1: (_ for _ in ()).throw(AssertionError("skipped candidates must not execute"))),
    )

    result = service.execute_watchlist_opportunities(
        user_id=1,
        opportunities=[
            {"symbol": "AAPL.US", "price": 100, "confidence": 90, "reason": "已有持仓"},
            {"symbol": "MSFT.US", "price": 0, "confidence": 90, "reason": "无价格"},
        ],
        max_symbols=2,
        max_amount=2000,
        min_confidence=72,
    )

    assert result["submittedCount"] == 0
    reasons = {item["symbol"]: item["reason"] for item in result["skipped"]}
    assert reasons["AAPL.US"] == "已有持仓"
    assert reasons["MSFT.US"] == "缺少有效价格"


def test_find_active_broker_order_ignores_terminal_statuses_and_standardizes_active_status() -> None:
    module = _load_module()
    service = module.QuantTradingService

    assert service._find_active_broker_order(
        [{"symbol": "AAPL.US", "side": "Buy", "status": "Filled", "order_id": "done"}],
        "AAPL.US",
        "BUY",
    ) is None
    assert service._find_active_broker_order(
        [{"symbol": "AAPL.US", "side": "Buy", "status": "Cancelled", "order_id": "cancelled"}],
        "AAPL.US",
        "BUY",
    ) is None

    active = service._find_active_broker_order(
        [{"symbol": "AAPL.US", "side": "Buy", "status": "Partial-Filled", "order_id": "active"}],
        "AAPL.US",
        "BUY",
    )

    assert active["orderId"] == "active"
    assert active["status"] == "partially_filled"


def test_quant_execution_submits_order_intent_to_trade_service(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    captured = {}

    def fake_request(cls, **kwargs):
        captured.update(kwargs)
        return {"success": True, "order_id": "trade-order-1", "status": "submitted"}

    monkeypatch.setattr(service, "_request_trade_service", classmethod(fake_request))

    result = service._execute_decision(
        7,
        {
            "symbol": "AAPL.US",
            "side": "BUY",
            "quantity": 1,
            "price": 100,
            "confidence": 88,
            "reason": "测试",
            "budget": {"budget": 100},
            "scoreBreakdown": {"total": 88},
            "factorInputs": {"rsi14": 60},
        },
        user_id=3,
    )

    assert captured["path"] == "/api/v1/trade/orders/submit"
    assert captured["payload"]["strategy_context"]["budget"] == {"budget": 100}
    assert captured["payload"]["strategy_context"]["scoreBreakdown"] == {"total": 88}
    assert result["status"] == "executed"
    assert result["order_id"] == "trade-order-1"
    assert result["boundary"] == "trade-service"


def test_execute_watchlist_opportunities_dedupes_normalized_symbol_variants(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(service, "_load_watchlist_symbols", classmethod(lambda cls, *, user_id: {"AAPL.US"}))
    monkeypatch.setattr(service, "_has_recent_duplicate", classmethod(lambda cls, user_id, symbol, side: False))
    monkeypatch.setattr(service, "_load_broker_today_orders", classmethod(lambda cls, account_id, user_id: ([], "")))

    class AccountInfo:
        cash = 10_000
        buying_power = 10_000
        total_equity = 50_000

    class FakeBroker:
        is_connected = True
        account_id = 7

        def connect(self):
            return True

        def get_account_info(self):
            return AccountInfo()

        def get_positions(self):
            return []

    executed = []
    monkeypatch.setattr(
        module.PlatformAccessService,
        "get_user_capabilities",
        staticmethod(
            lambda user_id: {
                "hasBoundAccount": True,
                "quantApiEnabled": True,
                "canUseQuantTrading": True,
            }
        ),
    )
    monkeypatch.setattr(service, "_get_broker", staticmethod(lambda account_id=None, user_id=1: FakeBroker()))
    monkeypatch.setattr(
        service,
        "_execute_decision",
        classmethod(lambda cls, account_id, decision, user_id=1: executed.append(decision) or {"status": "executed", "order_id": f"order-{len(executed)}"}),
    )
    monkeypatch.setattr(
        service,
        "_save_decision",
        classmethod(lambda cls, **kwargs: {**kwargs["decision"], "status": kwargs["status"], "orderId": kwargs["order_id"]}),
    )

    result = service.execute_watchlist_opportunities(
        user_id=1,
        opportunities=[
            {"symbol": "AAPL", "market": "US", "price": 100, "confidence": 90, "reason": "raw symbol"},
            {"symbol": "AAPL.US", "price": 101, "confidence": 91, "reason": "normalized symbol"},
        ],
        max_symbols=2,
        max_amount=2000,
        min_confidence=72,
    )

    assert result["submittedCount"] == 1
    assert [item["symbol"] for item in executed] == ["AAPL.US"]
    assert any(item["symbol"] == "AAPL.US" and "重复机会标的" in item["reason"] for item in result["skipped"])


def test_execute_watchlist_opportunities_allows_one_share_under_1000_with_portfolio_budget(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(service, "_load_watchlist_symbols", classmethod(lambda cls, *, user_id: {"AAPL.US", "MSFT.US"}))
    monkeypatch.setattr(service, "_has_recent_duplicate", classmethod(lambda cls, user_id, symbol, side: False))
    monkeypatch.setattr(service, "_load_broker_today_orders", classmethod(lambda cls, account_id, user_id: ([], "")))
    monkeypatch.setattr(service, "_assert_paper_trading_account", classmethod(lambda cls, account_id, user_id: {"isPaper": True}))

    class AccountInfo:
        cash = 450
        buying_power = 450
        market_value = 0
        total_equity = 1000

    class FakeBroker:
        is_connected = True
        account_id = 7

        def connect(self):
            return True

        def get_account_info(self):
            return AccountInfo()

        def get_positions(self):
            return []

    executed = []
    monkeypatch.setattr(
        module.PlatformAccessService,
        "get_user_capabilities",
        staticmethod(lambda user_id: {"hasBoundAccount": True, "quantApiEnabled": True, "canUseQuantTrading": True}),
    )
    monkeypatch.setattr(service, "_get_broker", staticmethod(lambda account_id=None, user_id=1: FakeBroker()))
    monkeypatch.setattr(
        service,
        "_execute_decision",
        classmethod(lambda cls, account_id, decision, user_id=1: executed.append(decision) or {"status": "executed", "order_id": f"order-{len(executed)}"}),
    )
    monkeypatch.setattr(
        service,
        "_save_decision",
        classmethod(lambda cls, **kwargs: {**kwargs["decision"], "status": kwargs["status"], "orderId": kwargs["order_id"]}),
    )

    result = service.execute_watchlist_opportunities(
        user_id=1,
        opportunities=[
            {"symbol": "AAPL.US", "price": 180, "confidence": 91, "reason": "一股也可买"},
            {"symbol": "MSFT.US", "price": 260, "confidence": 90, "reason": "继续分配"},
        ],
        max_symbols=5,
        max_amount=0,
        max_position_ratio=1,
        min_confidence=72,
        target_portfolio_ratio=0.70,
        require_paper=True,
    )

    assert result["submittedCount"] == 2
    assert [item["quantity"] for item in executed] == [1, 1]
    assert executed[0]["budget"]["budget"] < 1000
    assert result["positionControl"]["targetPortfolioRatio"] == 0.70
    assert "US min 1 share" in result["positionControl"]["budgetRule"]


def test_execute_watchlist_opportunities_sells_existing_position_when_allowed(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(service, "_load_watchlist_symbols", classmethod(lambda cls, *, user_id: {"AAPL.US"}))
    monkeypatch.setattr(service, "_has_recent_duplicate", classmethod(lambda cls, user_id, symbol, side: False))
    monkeypatch.setattr(service, "_load_broker_today_orders", classmethod(lambda cls, account_id, user_id: ([], "")))
    monkeypatch.setattr(service, "_assert_paper_trading_account", classmethod(lambda cls, account_id, user_id: {"isPaper": True}))

    class AccountInfo:
        cash = 5000
        buying_power = 5000
        market_value = 900
        total_equity = 5900

    class Position:
        symbol = "AAPL.US"
        quantity = 3
        market_price = 180
        average_cost = 200
        market_value = 540

    class FakeBroker:
        is_connected = True
        account_id = 7

        def connect(self):
            return True

        def get_account_info(self):
            return AccountInfo()

        def get_positions(self):
            return [Position()]

    executed = []
    monkeypatch.setattr(
        module.PlatformAccessService,
        "get_user_capabilities",
        staticmethod(lambda user_id: {"hasBoundAccount": True, "quantApiEnabled": True, "canUseQuantTrading": True}),
    )
    monkeypatch.setattr(service, "_get_broker", staticmethod(lambda account_id=None, user_id=1: FakeBroker()))
    monkeypatch.setattr(
        service,
        "_execute_decision",
        classmethod(lambda cls, account_id, decision, user_id=1: executed.append(decision) or {"status": "executed", "order_id": "sell-1"}),
    )
    monkeypatch.setattr(
        service,
        "_save_decision",
        classmethod(lambda cls, **kwargs: {**kwargs["decision"], "status": kwargs["status"], "orderId": kwargs["order_id"]}),
    )

    result = service.execute_watchlist_opportunities(
        user_id=1,
        opportunities=[{"symbol": "AAPL.US", "side": "SELL", "price": 180, "confidence": 38, "reason": "趋势转弱"}],
        allow_sells=True,
        require_paper=True,
    )

    assert result["submittedCount"] == 1
    assert executed[0]["side"] == "SELL"
    assert executed[0]["quantity"] == 3
    assert executed[0]["budget"]["budgetRule"] == "sell full available holding"


def test_run_us_open_watchlist_ai_trade_skips_outside_regular_session(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    started = []
    finished = []
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(service, "_cycle_id", staticmethod(lambda: "qt-test-skip"))
    monkeypatch.setattr(
        service,
        "_start_us_open_ai_trade_run",
        classmethod(lambda cls, **kwargs: started.append(kwargs) or {"saved": True, "runId": 1}),
    )
    monkeypatch.setattr(
        service,
        "_finish_us_open_ai_trade_run",
        classmethod(lambda cls, **kwargs: finished.append(kwargs) or {"saved": True}),
    )
    monkeypatch.setattr(
        service,
        "_load_us_open_ai_trade_settings",
        classmethod(lambda cls, overrides=None: {
            "autoTradeEnabled": True,
            "maxSymbols": 5,
            "targetPortfolioRatio": 0.70,
            "minConfidence": 72,
            "strategyProfile": "balanced",
            "market": "US",
            "regularSessionOnly": True,
        }),
    )
    monkeypatch.setattr(service, "_is_us_regular_session_now", staticmethod(lambda now=None: False))
    monkeypatch.setattr(
        service,
        "_load_watchlist_scan_targets",
        classmethod(lambda cls, **kwargs: (_ for _ in ()).throw(AssertionError("outside session must not scan"))),
    )

    result = service.run_us_open_watchlist_ai_trade(user_id=1, source="scheduler")

    assert result["skippedRun"] is True
    assert result["reason"] == "outside-us-regular-session"
    assert started[0]["cycle_id"] == "qt-test-skip"
    assert finished[0]["status"] == "skipped"
    assert finished[0]["result"]["cycleId"] == "qt-test-skip"
    assert finished[0]["result"]["targetCount"] == 0


def test_run_us_open_watchlist_ai_trade_builds_buy_and_sell_orders(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    finished = []
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(service, "_start_us_open_ai_trade_run", classmethod(lambda cls, **kwargs: {"saved": True, "runId": 1}))
    monkeypatch.setattr(
        service,
        "_finish_us_open_ai_trade_run",
        classmethod(lambda cls, **kwargs: finished.append(kwargs) or {"saved": True}),
    )
    monkeypatch.setattr(service, "_save_watchlist_strategy_run", classmethod(lambda cls, **kwargs: {"saved": True, "runId": 99}))
    monkeypatch.setattr(service, "_is_us_regular_session_now", staticmethod(lambda now=None: True))
    monkeypatch.setattr(service, "_assert_paper_trading_account", classmethod(lambda cls, account_id, user_id: {"isPaper": True}))
    monkeypatch.setattr(service, "_load_watchlist_symbols", classmethod(lambda cls, *, user_id: {"AAPL.US", "MSFT.US"}))
    monkeypatch.setattr(service, "_has_recent_duplicate", classmethod(lambda cls, user_id, symbol, side: False))
    monkeypatch.setattr(service, "_load_broker_today_orders", classmethod(lambda cls, account_id, user_id: ([], "")))
    monkeypatch.setattr(
        service,
        "_load_watchlist_scan_targets",
        classmethod(lambda cls, *, user_id, session_filter="all": [
            {"symbol": "AAPL.US", "name": "Apple", "market": "US"},
            {"symbol": "MSFT.US", "name": "Microsoft", "market": "US"},
        ]),
    )

    class AccountInfo:
        cash = 1000
        buying_power = 1000
        market_value = 200
        total_equity = 1200

    class Position:
        symbol = "AAPL.US"
        quantity = 2
        market_price = 100
        average_cost = 150
        market_value = 200

    class FakeBroker:
        is_connected = True
        account_id = 7

        def connect(self):
            return True

        def get_account_info(self):
            return AccountInfo()

        def get_positions(self):
            return [Position()]

    def fake_evaluate(cls, *, target, symbol, user_id, strategy_profile):
        if symbol == "AAPL.US":
            return {
                "symbol": symbol,
                "name": "Apple",
                "market": "US",
                "side": "HOLD",
                "status": "observed",
                "isOpportunity": False,
                "price": 100,
                "confidence": 35,
                "riskLevel": "high",
                "trendDirection": "down",
                "reason": "高风险转弱",
                "scoreBreakdown": {"total": 35, "trendDirection": "down"},
                "metrics": {"latestClose": 100, "return20": -8, "trendScanDirection": "down"},
            }
        return {
            "symbol": symbol,
            "name": "Microsoft",
            "market": "US",
            "side": "BUY",
            "status": "candidate",
            "isOpportunity": True,
            "price": 300,
            "confidence": 90,
            "riskLevel": "low",
            "trendDirection": "up",
            "reason": "强势机会",
            "scoreBreakdown": {"total": 90, "trendDirection": "up"},
            "metrics": {"latestClose": 300, "return20": 6, "trendScanDirection": "up"},
        }

    executed = []
    monkeypatch.setattr(
        module.PlatformAccessService,
        "get_user_capabilities",
        staticmethod(lambda user_id: {"hasBoundAccount": True, "quantApiEnabled": True, "canUseQuantTrading": True}),
    )
    monkeypatch.setattr(service, "_get_broker", staticmethod(lambda account_id=None, user_id=1: FakeBroker()))
    monkeypatch.setattr(service, "_evaluate_watchlist_quant_target", classmethod(fake_evaluate))
    monkeypatch.setattr(
        service,
        "_execute_decision",
        classmethod(lambda cls, account_id, decision, user_id=1: executed.append(decision) or {"status": "executed", "order_id": f"order-{len(executed)}"}),
    )
    monkeypatch.setattr(
        service,
        "_save_decision",
        classmethod(lambda cls, **kwargs: {**kwargs["decision"], "status": kwargs["status"], "orderId": kwargs["order_id"]}),
    )

    result = service.run_us_open_watchlist_ai_trade(user_id=1, source="scheduler")

    assert result["executed"] is True
    assert result["autoTrade"]["submittedCount"] == 2
    assert [item["side"] for item in executed] == ["SELL", "BUY"]
    assert executed[0]["symbol"] == "AAPL.US"
    assert executed[0]["quantity"] == 2
    assert executed[1]["symbol"] == "MSFT.US"
    assert executed[1]["quantity"] == 1
    assert finished[0]["status"] == "completed"
    assert finished[0]["result"]["opportunityCount"] == 2
    assert finished[0]["result"]["autoTrade"]["submittedCount"] == 2


def test_trade_service_account_lookup_does_not_fall_back_when_account_id_is_missing(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    calls = []

    def _request(cls, *, method, path, user_id, **kwargs):
        calls.append(path)
        if path == "/api/v1/trade/accounts":
            return {"success": True, "data": [{"id": 8, "trading_mode": "paper", "account_id": "LBPT100"}]}
        if path == "/api/v1/trade/accounts/default":
            raise AssertionError("must not fall back to the default account when an explicit account id is missing")
        return {}

    monkeypatch.setattr(service, "_request_trade_service", classmethod(_request))

    with pytest.raises(PermissionError, match="指定账户不存在或不可用"):
        service._load_trade_service_account(account_id=7, user_id=1)

    assert calls == ["/api/v1/trade/accounts"]


def test_list_us_open_ai_trade_runs_parses_dedicated_run_table(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))

    def fake_fetch_all(sql, params=None):
        assert "watchlist_us_open_ai_trade_runs" in sql
        assert params == (1, 50)
        return [
            {
                "id": 12,
                "cycle_id": "qt-202605220930000000",
                "source": "scheduler",
                "status": "completed",
                "reason": "executed",
                "message": "美股开盘 AI 自动交易已完成",
                "settings_json": '{"autoTradeEnabled": true, "maxSymbols": 5}',
                "target_count": 8,
                "evaluated_count": 8,
                "opportunity_count": 2,
                "submitted_count": 1,
                "skipped_count": 1,
                "executed": 1,
                "auto_trade_json": '{"enabled": true, "submittedCount": 1}',
                "position_control_json": '{"targetPortfolioRatio": 0.7}',
                "candidates_json": '[{"symbol": "MSFT.US", "confidence": 90}]',
                "opportunities_json": '[{"symbol": "MSFT.US", "side": "BUY"}]',
                "skipped_json": '[{"symbol": "AAPL.US", "reason": "已有持仓"}]',
                "error": "",
                "started_at": "2026-05-22 21:30:00",
                "finished_at": "2026-05-22 21:30:08",
            }
        ]

    monkeypatch.setattr(module.DbUtil, "fetch_all", staticmethod(fake_fetch_all))

    result = service.list_us_open_ai_trade_runs(user_id=1, limit=50)

    assert result["total"] == 1
    assert result["items"][0]["cycleId"] == "qt-202605220930000000"
    assert result["items"][0]["status"] == "completed"
    assert result["items"][0]["settings"]["maxSymbols"] == 5
    assert result["items"][0]["autoTrade"]["submittedCount"] == 1
    assert result["items"][0]["positionControl"]["targetPortfolioRatio"] == 0.7
    assert result["items"][0]["opportunities"][0]["symbol"] == "MSFT.US"


def test_watchlist_strategy_backtest_replays_historical_scores(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    monkeypatch.setattr(
        module.HistoricalMarketDataService,
        "get_daily_series_until",
        staticmethod(lambda symbol, end_date=None, limit=350: _trend_series(150)),
    )

    result = service.run_watchlist_strategy_backtest(
        user_id=1,
        symbol="AAPL",
        market="US",
        lookback_days=40,
        min_confidence=60,
    )

    assert result["status"] == "completed"
    assert result["symbol"] == "AAPL.US"
    assert result["summary"]["pointCount"] == 40
    assert result["points"][-1]["tradeDate"]


def test_watchlist_symbol_normalization_uses_declared_market() -> None:
    module = _load_module()
    service = module.QuantTradingService

    assert service._normalize_watchlist_symbol("00700", market="HK") == "00700.HK"
    assert service._normalize_watchlist_symbol("600519", market="CN") == "600519.SH"
    assert service._normalize_watchlist_symbol("000001", market="CN") == "000001.SZ"
    assert service._normalize_watchlist_symbol("AAPL", market="US") == "AAPL.US"


def test_strategy_service_quant_run_uses_watchlist_strategy_entrypoint() -> None:
    source = STRATEGY_MAIN.read_text(encoding="utf-8")

    assert "QuantTradingService.run_watchlist_strategy_cycle(" in source
    assert "QuantTradingService.list_watchlist_strategy_history(" in source
    assert "QuantTradingService.list_us_open_ai_trade_runs(" in source
    assert "QuantTradingService.run_watchlist_strategy_backtest(" in source
    assert "QuantTradingService.run_cycle(" not in source
