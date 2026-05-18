from __future__ import annotations

from pathlib import Path

from apps.intelligence.intelligence_shared import boundary as analysis_boundary


ROOT = Path(__file__).resolve().parents[2]


def test_analysis_boundary_real_indicator_context_uses_strict_live_loader(monkeypatch) -> None:
    class FakeRoutes:
        def _build_real_indicator_context(self, symbol, current_price, volume, user_id=1):
            return {"symbol": symbol, "price": current_price}, {"volume": volume, "user_id": user_id}

    monkeypatch.setattr(analysis_boundary, "ai_routes", lambda: FakeRoutes())

    ai_payload, indicator_payload = analysis_boundary.build_real_indicator_context(
        "AAPL.US",
        123.45,
        1000,
        user_id=7,
    )

    assert ai_payload == {"symbol": "AAPL.US", "price": 123.45}
    assert indicator_payload == {"volume": 1000, "user_id": 7}


def test_analysis_service_source_stops_using_fake_analysis_fallbacks() -> None:
    source = (ROOT / "apps/analysis-service/src/main.py").read_text(encoding="utf-8")
    boundary_source = (ROOT / "apps/intelligence/intelligence_shared/boundary.py").read_text(encoding="utf-8")

    assert "build_real_indicator_context" in source
    assert "build_indicator_context_with_fallback" not in source
    assert "build_degraded_analysis_result" not in source
    assert "_build_manual_scan_error_result(" in source
    assert "def build_indicator_context_with_fallback" not in boundary_source
    assert "def build_degraded_analysis_result" not in boundary_source


def test_legacy_ai_routes_and_consultant_stop_faking_analysis_results() -> None:
    ai_routes_source = (ROOT / "backend-server/src/api/ai_routes.py").read_text(encoding="utf-8")
    consultant_source = (ROOT / "backend-server/src/core/analysis/AiConsultant.py").read_text(encoding="utf-8")

    assert "def _build_synthetic_indicator_context" not in ai_routes_source
    assert "def _build_indicator_context_with_fallback" not in ai_routes_source
    assert "def _build_degraded_analysis_result" not in ai_routes_source
    assert "def _get_batch_fallback_analysis" not in ai_routes_source
    assert "_fallback_pulse_text(" in consultant_source
    assert "pulse_text = AiConsultant._fallback_pulse_text" not in consultant_source
    assert "risk_text = AiConsultant._fallback_risk_text" not in consultant_source
    assert "decision_text = AiConsultant._fallback_decision_text" not in consultant_source


def test_scan_routes_and_trade_engine_stop_using_random_market_fallbacks() -> None:
    scan_routes_source = (ROOT / "backend-server/src/api/scan_routes.py").read_text(encoding="utf-8")
    trade_engine_source = (ROOT / "backend-server/src/core/trade/TradeEngine.py").read_text(encoding="utf-8")

    assert "import random" not in scan_routes_source
    assert "随机游走模拟历史价格" not in scan_routes_source
    assert "volume * random.uniform" not in scan_routes_source
    assert "HistoricalMarketDataService.get_history" in scan_routes_source
    assert "_get_mock_stock_data" not in trade_engine_source
    assert "使用模拟数据" not in trade_engine_source


def test_recommendation_and_batch_analysis_stop_fabricating_ai_text_or_prices() -> None:
    recommendation_source = (ROOT / "backend-server/src/core/analysis/RecommendationService.py").read_text(encoding="utf-8")
    ai_routes_source = (ROOT / "backend-server/src/api/ai_routes.py").read_text(encoding="utf-8")
    frontend_api_source = (ROOT / "apps/web-portal/src/utils/api.js").read_text(encoding="utf-8")

    assert "_fallback_catalysts" not in recommendation_source
    assert "_fallback_risks" not in recommendation_source
    assert "AI 组合摘要当前不可用" in recommendation_source
    assert "price = random.uniform(10, 1000)" not in ai_routes_source
    assert "random.randint" not in ai_routes_source
    assert "random.uniform" not in ai_routes_source
    assert "HistoricalMarketDataService.get_history(symbol, timeframe='daily', limit=90)" in ai_routes_source
    assert "AI 推荐摘要当前不可用" in frontend_api_source
