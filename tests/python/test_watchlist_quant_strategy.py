from __future__ import annotations

import importlib
import sys
from pathlib import Path


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
    assert "QuantTradingService.run_watchlist_strategy_backtest(" in source
    assert "QuantTradingService.run_cycle(" not in source
