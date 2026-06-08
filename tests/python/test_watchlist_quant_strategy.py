from __future__ import annotations

import importlib
import json
import math
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


def _synthetic_factor_set(count: int = 1500):
    return {
        "version": "watchlist-alpha-factor-v1",
        "count": count,
        "families": {"lag": count},
        "values": {f"lag.close_l{index}": float(index) for index in range(count)},
    }


def _assert_factor_set_contract(metrics, *, min_count: int = 1500):
    factor_set = metrics["factorSet"]
    assert factor_set["version"] == "watchlist-alpha-factor-v1"
    assert factor_set["count"] >= min_count
    assert metrics["factorSetVersion"] == factor_set["version"]
    assert metrics["factorCount"] == factor_set["count"]
    assert metrics["factorFamilies"] == factor_set["families"]
    assert isinstance(factor_set["values"], dict)
    assert len(factor_set["values"]) == factor_set["count"]
    assert len(factor_set["values"]) == len(set(factor_set["values"].keys()))
    assert all(isinstance(value, (int, float)) for value in factor_set["values"].values())
    assert all(math.isfinite(float(value)) for value in factor_set["values"].values())


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


def test_watchlist_strategy_returns_extended_factor_inputs_and_scores(monkeypatch) -> None:
    module = _load_module()
    _patch_strategy_inputs(monkeypatch, module, enabled=False)

    result = module.QuantTradingService.run_watchlist_strategy_cycle(user_id=1, execute=False)
    candidate = result["candidates"][0]
    metrics = candidate["metrics"]
    score = candidate["scoreBreakdown"]

    assert metrics["historyCount"] >= 60
    for key in (
        "kMid",
        "bollPercentB20",
        "adx14",
        "obvSlope20",
        "mfi14",
        "cmf20",
        "avgDollarVolume20",
        "maxDrawdown20",
        "trendStrength",
        "technicalScore",
        "factorSet",
    ):
        assert key in metrics
    _assert_factor_set_contract(metrics)
    for key in (
        "factorVersion",
        "trend",
        "priceAction",
        "momentum",
        "breakout",
        "volumeFlow",
        "reversion",
        "volatility",
        "liquidity",
        "aiTrend",
        "riskPenalty",
    ):
        assert key in score
    assert score["factorVersion"] == "watchlist-factor-v2"
    assert result["factorSchema"]
    assert {item["key"] for item in result["factorSchema"]} >= {
        "trend",
        "priceAction",
        "momentum",
        "volumeFlow",
        "volatility",
        "liquidity",
        "riskPenalty",
        "factorSet",
    }
    metric_keys = set(metrics.keys())
    score_keys = set(score.keys())
    for schema in result["factorSchema"]:
        missing = [key for key in schema.get("inputs", []) if key not in metric_keys and key not in score_keys]
        assert missing == []


def test_build_watchlist_quant_metrics_returns_deterministic_large_factor_set() -> None:
    module = _load_module()
    service = module.QuantTradingService

    first = service._build_watchlist_quant_metrics(
        series=_trend_series(160),
        snapshot={"rsi": 62, "macdHist": 0.18, "roc": 6, "momentumScore": 72, "atr": 2},
        trend_scan={"trendDirection": "up", "trendStrength": 78, "riskLevel": "low", "technicalScore": 82},
    )
    second = service._build_watchlist_quant_metrics(
        series=_trend_series(160),
        snapshot={"rsi": 62, "macdHist": 0.18, "roc": 6, "momentumScore": 72, "atr": 2},
        trend_scan={"trendDirection": "up", "trendStrength": 78, "riskLevel": "low", "technicalScore": 82},
    )

    _assert_factor_set_contract(first)
    assert first["factorSet"] == second["factorSet"]


def test_factor_set_covers_expected_family_distribution() -> None:
    module = _load_module()
    service = module.QuantTradingService

    metrics = service._build_watchlist_quant_metrics(series=_trend_series(160), snapshot={}, trend_scan=None)
    families = metrics["factorSet"]["families"]

    assert families["lag"] >= 100
    assert families["trend"] >= 300
    assert families["momentum"] >= 350
    assert families["volatility"] >= 300
    assert families["volume_flow"] >= 400
    assert families["price_action"] >= 450
    assert families["range_drawdown"] >= 300
    assert families["liquidity"] >= 200
    assert families["correlation"] >= 120


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
    assert captured["require_paper"] is True


def test_execute_watchlist_opportunities_rejects_live_account_when_paper_required(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(service, "_load_watchlist_symbols", classmethod(lambda cls, *, user_id: {"AAPL.US"}))
    monkeypatch.setattr(
        module.PlatformAccessService,
        "get_user_capabilities",
        staticmethod(lambda user_id: {"hasBoundAccount": True, "quantApiEnabled": True, "canUseQuantTrading": True}),
    )

    class FakeBroker:
        is_connected = True
        account_id = 7

        def connect(self):
            return True

    monkeypatch.setattr(service, "_get_broker", staticmethod(lambda account_id=None, user_id=1: FakeBroker()))
    monkeypatch.setattr(
        service,
        "_assert_paper_trading_account",
        classmethod(lambda cls, account_id, user_id: (_ for _ in ()).throw(PermissionError("live account blocked"))),
    )

    with pytest.raises(PermissionError, match="live account blocked"):
        service.execute_watchlist_opportunities(
            user_id=1,
            opportunities=[{"symbol": "AAPL.US", "price": 180, "confidence": 91, "reason": "live account"}],
            require_paper=True,
        )


def test_score_watchlist_quant_metrics_applies_extended_risk_penalty() -> None:
    module = _load_module()
    service = module.QuantTradingService
    base_metrics = service._build_watchlist_quant_metrics(
        series=_trend_series(120),
        snapshot={"rsi": 62, "macdHist": 0.18, "roc": 6, "momentumScore": 72, "atr": 2},
        trend_scan={"trendDirection": "up", "trendStrength": 78, "riskLevel": "low", "technicalScore": 82},
    )
    high_risk_metrics = {
        **base_metrics,
        "trendScanRisk": "high",
        "volatility20": 6.2,
        "atrPercent": 7.0,
        "atr14Percent": 7.0,
        "maxDrawdown20": -16,
        "downsideVol20": 5.0,
    }

    base_score = service._score_watchlist_quant_metrics(metrics=base_metrics, strategy_profile="balanced")
    high_risk_score = service._score_watchlist_quant_metrics(metrics=high_risk_metrics, strategy_profile="balanced")

    assert high_risk_score["riskLevel"] == "high"
    assert high_risk_score["riskPenalty"] > base_score["riskPenalty"]
    assert high_risk_score["total"] < base_score["total"]


def test_extended_factor_helpers_handle_flat_zero_volume_series() -> None:
    module = _load_module()
    service = module.QuantTradingService
    series = [
        {
            "date": f"2026-02-{(index % 28) + 1:02d}",
            "open": 100,
            "high": 100,
            "low": 100,
            "close": 100,
            "volume": 0,
        }
        for index in range(80)
    ]

    metrics = service._build_watchlist_quant_metrics(series=series, snapshot={}, trend_scan=None)
    score = service._score_watchlist_quant_metrics(metrics=metrics, strategy_profile="balanced")

    assert metrics["adx14"] == 0
    assert metrics["cci20"] == 0
    assert metrics["mfi14"] == 50
    assert metrics["cmf20"] == 0
    assert metrics["bollPercentB20"] == 50
    assert metrics["maxDrawdown20"] == 0
    _assert_factor_set_contract(metrics)
    assert score["factorVersion"] == "watchlist-factor-v2"
    assert 0 <= score["total"] <= 100


def test_extended_factor_helpers_sanitize_non_finite_inputs() -> None:
    module = _load_module()
    service = module.QuantTradingService

    metrics = service._build_watchlist_quant_metrics(
        series=_trend_series(100),
        snapshot={
            "rsi": float("nan"),
            "macdHist": float("inf"),
            "roc": float("-inf"),
            "momentumScore": float("nan"),
            "atr": float("inf"),
            "supportPrice": float("-inf"),
        },
        trend_scan={
            "trendDirection": "up",
            "trendStrength": float("inf"),
            "riskLevel": "low",
            "technicalScore": float("nan"),
        },
    )
    score = service._score_watchlist_quant_metrics(metrics=metrics, strategy_profile="balanced")

    numeric_values = [
        value for value in metrics.values()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    assert numeric_values
    assert all(math.isfinite(float(value)) for value in numeric_values)
    _assert_factor_set_contract(metrics)
    assert math.isfinite(float(score["total"]))
    encoded = service._to_json(metrics)
    assert "NaN" not in encoded
    assert "Infinity" not in encoded
    json.loads(encoded)


def test_opportunity_candidate_schema_documents_extended_factor_contract() -> None:
    module = _load_module()
    schema = module.QuantTradingService._opportunity_candidate_schema()

    assert "scoreBreakdown" in schema["required"]
    score_contract = schema["fields"]["scoreBreakdown"]
    metrics_contract = schema["fields"]["metrics"]
    for key in ("priceAction", "momentum", "volumeFlow", "volatility", "liquidity", "riskPenalty"):
        assert key in score_contract
    assert "factorInputs" in metrics_contract
    assert "1500+" in metrics_contract


def test_evaluate_watchlist_quant_target_skips_when_history_shorter_than_60(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    monkeypatch.setattr(
        module.HistoricalMarketDataService,
        "get_daily_series_until",
        staticmethod(lambda symbol, limit=260: _trend_series(59)),
    )

    result = service._evaluate_watchlist_quant_target(
        target={"symbol": "AAPL.US", "name": "Apple", "market": "US"},
        symbol="AAPL.US",
        user_id=1,
        strategy_profile="balanced",
    )

    assert result["status"] == "skipped"
    assert result["historyCount"] == 59
    assert result["reason"] == "历史行情少于 60 条，暂不参与自选池量化评分"


def test_evaluate_watchlist_quant_target_skips_when_history_load_fails(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService

    def raise_history_error(symbol, limit=260):
        raise RuntimeError("market data unavailable")

    monkeypatch.setattr(
        module.HistoricalMarketDataService,
        "get_daily_series_until",
        staticmethod(raise_history_error),
    )

    result = service._evaluate_watchlist_quant_target(
        target={"symbol": "AAPL.US", "name": "Apple", "market": "US"},
        symbol="AAPL.US",
        user_id=1,
        strategy_profile="balanced",
    )

    assert result["status"] == "skipped"
    assert result["symbol"] == "AAPL.US"
    assert result["reason"].startswith("历史行情读取失败:")


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
            "scoreBreakdown": {
                "factorVersion": "watchlist-factor-v2",
                "total": 88,
                "trend": 22,
                "priceAction": 6,
                "momentum": 9,
                "volumeFlow": 5,
                "riskPenalty": 6,
            },
            "factorInputs": {"rsi14": 60, "return20": 5.2, "mfi14": 58, "cmf20": 0.12},
        },
        user_id=3,
    )

    assert captured["path"] == "/api/v1/trade/orders/submit"
    assert captured["payload"]["strategy_context"]["budget"] == {"budget": 100}
    assert captured["payload"]["strategy_context"]["scoreBreakdown"]["riskPenalty"] == 6
    assert captured["payload"]["strategy_context"]["scoreBreakdown"]["factorVersion"] == "watchlist-factor-v2"
    assert captured["payload"]["strategy_context"]["factorInputs"]["mfi14"] == 58
    assert result["status"] == "executed"
    assert result["order_id"] == "trade-order-1"
    assert result["boundary"] == "trade-service"


def test_quant_execution_summarizes_large_factor_set_for_order_intent(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    captured = {}
    factor_set = _synthetic_factor_set(1500)

    def fake_request(cls, **kwargs):
        captured.update(kwargs)
        return {"success": True, "order_id": "trade-order-2", "status": "submitted"}

    monkeypatch.setattr(service, "_request_trade_service", classmethod(fake_request))

    service._execute_decision(
        7,
        {
            "symbol": "AAPL.US",
            "side": "BUY",
            "quantity": 1,
            "price": 100,
            "confidence": 88,
            "reason": "测试大因子集摘要",
            "budget": {"budget": 100},
            "scoreBreakdown": {"factorVersion": "watchlist-factor-v2", "total": 88},
            "factorInputs": {
                "rsi14": 60,
                "mfi14": 58,
                "factorSet": factor_set,
            },
        },
        user_id=3,
    )

    factor_inputs = captured["payload"]["strategy_context"]["factorInputs"]
    assert factor_inputs["mfi14"] == 58
    assert factor_inputs["factorSetVersion"] == "watchlist-alpha-factor-v1"
    assert factor_inputs["factorCount"] == 1500
    assert factor_inputs["factorFamilies"] == {"lag": 1500}
    assert "factorSet" not in factor_inputs


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


def test_execute_watchlist_opportunities_blocks_daily_guardrail(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(service, "_load_watchlist_symbols", classmethod(lambda cls, *, user_id: {"AAPL.US"}))
    monkeypatch.setattr(service, "_has_recent_duplicate", classmethod(lambda cls, user_id, symbol, side: False))
    monkeypatch.setattr(service, "_load_broker_today_orders", classmethod(lambda cls, account_id, user_id: ([], "")))
    monkeypatch.setattr(
        module.DbUtil,
        "fetch_one_primary",
        staticmethod(lambda sql, params=None: {"submitted_count": 1, "submitted_notional": 250}),
    )

    class AccountInfo:
        cash = 5000
        buying_power = 5000
        market_value = 0
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
        staticmethod(lambda user_id: {"hasBoundAccount": True, "quantApiEnabled": True, "canUseQuantTrading": True}),
    )
    monkeypatch.setattr(service, "_get_broker", staticmethod(lambda account_id=None, user_id=1: FakeBroker()))
    monkeypatch.setattr(
        service,
        "_execute_decision",
        classmethod(lambda cls, account_id, decision, user_id=1: executed.append(decision) or {"status": "executed", "order_id": "order-1"}),
    )

    result = service.execute_watchlist_opportunities(
        user_id=1,
        opportunities=[{"symbol": "AAPL.US", "price": 100, "confidence": 90, "reason": "超过日内护栏"}],
        max_symbols=1,
        max_amount=1000,
        min_confidence=72,
        max_daily_submitted_orders=1,
        max_daily_notional_ratio=0.20,
    )

    assert result["submittedCount"] == 0
    assert executed == []
    assert "今日自动交易最多提交" in result["skipped"][0]["reason"]
    assert result["positionControl"]["dailySubmittedCount"] == 1
    assert result["positionControl"]["maxDailySubmittedOrders"] == 1
    assert result["positionControl"]["maxDailyNotional"] == 2000


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
            "refreshRealtimePrice": True,
            "requireRealtimePrice": True,
            "maxDailySubmittedOrders": 10,
            "maxDailyNotionalRatio": 0.70,
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
            "refreshRealtimePrice": True,
            "requireRealtimePrice": True,
            "maxDailySubmittedOrders": 10,
            "maxDailyNotionalRatio": 0.70,
        }),
    )
    monkeypatch.setattr(service, "_save_watchlist_strategy_run", classmethod(lambda cls, **kwargs: {"saved": True, "runId": 99}))
    monkeypatch.setattr(service, "_is_us_regular_session_now", staticmethod(lambda now=None: True))
    monkeypatch.setattr(service, "_assert_paper_trading_account", classmethod(lambda cls, account_id, user_id: {"isPaper": True}))
    monkeypatch.setattr(service, "_load_watchlist_symbols", classmethod(lambda cls, *, user_id: {"AAPL.US", "MSFT.US"}))
    monkeypatch.setattr(service, "_has_recent_duplicate", classmethod(lambda cls, user_id, symbol, side: False))
    monkeypatch.setattr(service, "_load_broker_today_orders", classmethod(lambda cls, account_id, user_id: ([], "")))
    monkeypatch.setattr(
        module.DbUtil,
        "fetch_one_primary",
        staticmethod(lambda sql, params=None: {"submitted_count": 0, "submitted_notional": 0}),
    )
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

        def get_quote(self, symbols):
            return {
                "AAPL.US": {"last_price": 101, "timestamp": "2026-05-22 09:31:00"},
                "MSFT.US": {"last_price": 310, "timestamp": "2026-05-22 09:31:01"},
            }

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
    assert executed[0]["price"] == 101
    assert executed[0]["priceSource"] == "broker-realtime"
    assert executed[1]["symbol"] == "MSFT.US"
    assert executed[1]["quantity"] == 1
    assert executed[1]["price"] == 310
    assert finished[0]["status"] == "completed"
    assert finished[0]["result"]["opportunityCount"] == 2
    assert finished[0]["result"]["autoTrade"]["submittedCount"] == 2
    assert finished[0]["result"]["autoTrade"]["priceRefresh"]["refreshedCount"] == 2
    assert finished[0]["result"]["positionControl"]["maxDailySubmittedOrders"] == 10


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


def test_list_watchlist_strategy_history_loads_run_items_in_one_query(monkeypatch) -> None:
    module = _load_module()
    service = module.QuantTradingService
    monkeypatch.setattr(service, "ensure_schema", classmethod(lambda cls: None))
    calls = []
    large_factor_set = _synthetic_factor_set(1500)
    large_metrics_json = json.dumps(
        {
            "mfi14": 62,
            "cmf20": 0.13,
            "factorSetVersion": large_factor_set["version"],
            "factorCount": large_factor_set["count"],
            "factorFamilies": large_factor_set["families"],
            "factorSet": large_factor_set,
        }
    )

    def fake_fetch_all(sql, params=None):
        normalized_sql = " ".join(str(sql).split())
        calls.append((normalized_sql, params))
        if "FROM watchlist_quant_strategy_runs" in normalized_sql:
            return [
                {
                    "id": 12,
                    "cycle_id": "cycle-b",
                    "source": "manual",
                    "strategy_profile": "balanced",
                    "enabled": 1,
                    "auto_execute": 0,
                    "executed": 0,
                    "target_count": 4,
                    "evaluated_count": 4,
                    "opportunity_count": 1,
                    "auto_trade_json": '{"enabled": false}',
                    "position_control_json": '{"maxSymbols": 2}',
                    "skipped_json": "[]",
                    "created_at": "2026-05-22 21:30:00",
                },
                {
                    "id": 11,
                    "cycle_id": "cycle-a",
                    "source": "manual",
                    "strategy_profile": "momentum",
                    "enabled": 1,
                    "auto_execute": 1,
                    "executed": 1,
                    "target_count": 3,
                    "evaluated_count": 3,
                    "opportunity_count": 2,
                    "auto_trade_json": '{"enabled": true}',
                    "position_control_json": '{"maxSymbols": 1}',
                    "skipped_json": '[{"symbol": "TSLA.US"}]',
                    "created_at": "2026-05-22 21:20:00",
                },
            ]
        if "FROM watchlist_quant_strategy_run_items" in normalized_sql:
            assert "cycle_id IN (%s, %s)" in normalized_sql
            assert params == (1, "cycle-b", "cycle-a")
            return [
                {
                    "cycle_id": "cycle-a",
                    "symbol": "MSFT.US",
                    "name": "Microsoft",
                    "market": "US",
                    "side": "BUY",
                    "status": "candidate",
                    "is_opportunity": 1,
                    "price": 420,
                    "confidence": 91,
                    "risk_level": "low",
                    "reason": "strong",
                    "tags_json": '["站上20日线"]',
                    "metrics_json": large_metrics_json,
                    "score_json": '{"total": 91, "factorVersion": "watchlist-factor-v2", "riskPenalty": 3, "volumeFlow": 6}',
                    "created_at": "2026-05-22 21:21:00",
                },
                {
                    "cycle_id": "cycle-b",
                    "symbol": "AAPL.US",
                    "name": "Apple",
                    "market": "US",
                    "side": "HOLD",
                    "status": "observed",
                    "is_opportunity": 0,
                    "price": 190,
                    "confidence": 61,
                    "risk_level": "medium",
                    "reason": "watch",
                    "tags_json": "[]",
                    "metrics_json": '{"adx14": 18, "bollPercentB20": 44}',
                    "score_json": '{"total": 61, "factorVersion": "watchlist-factor-v2", "priceAction": 2}',
                    "created_at": "2026-05-22 21:31:00",
                },
            ]
        raise AssertionError(normalized_sql)

    monkeypatch.setattr(module.DbUtil, "fetch_all", staticmethod(fake_fetch_all))

    result = service.list_watchlist_strategy_history(user_id=1, limit=20)

    item_queries = [sql for sql, _params in calls if "FROM watchlist_quant_strategy_run_items" in sql]
    assert len(item_queries) == 1
    assert result["total"] == 2
    assert result["items"][0]["cycleId"] == "cycle-b"
    assert result["items"][0]["items"][0]["symbol"] == "AAPL.US"
    assert result["items"][0]["items"][0]["metrics"]["adx14"] == 18
    assert "factorSet" not in result["items"][0]["items"][0]["metrics"]
    assert result["items"][0]["items"][0]["scoreBreakdown"]["priceAction"] == 2
    assert result["items"][1]["cycleId"] == "cycle-a"
    assert result["items"][1]["items"][0]["symbol"] == "MSFT.US"
    history_metrics = result["items"][1]["items"][0]["metrics"]
    assert history_metrics["mfi14"] == 62
    assert history_metrics["factorSetVersion"] == "watchlist-alpha-factor-v1"
    assert history_metrics["factorCount"] == 1500
    assert history_metrics["factorFamilies"] == {"lag": 1500}
    assert "factorSet" not in history_metrics
    assert len(json.dumps(history_metrics)) < 1000
    assert result["items"][1]["items"][0]["scoreBreakdown"]["volumeFlow"] == 6


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
