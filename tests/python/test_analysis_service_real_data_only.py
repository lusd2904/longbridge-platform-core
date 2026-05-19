from __future__ import annotations

from pathlib import Path

from apps.intelligence.intelligence_shared import boundary as analysis_boundary
from core.analysis.AiConsultant import AiConsultant
from core.analysis import ai_analyst


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


def test_ai_consultant_uses_one_model_call_on_normal_path(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(AiConsultant, "_lookup_stock_name", staticmethod(lambda symbol: symbol))

    def fake_get_decision(cls, model, prompt, task="general", user_id=1):
        calls.append(task)
        return (
            "市场脉冲层:\n"
            "趋势判断: 上升\n"
            "指标共振: OK\n"
            "大盘联动: OK\n"
            "机会窗口: OK\n"
            "一句结论: pulse\n"
            "建议标签: BUY\n\n"
            "风险筛查层:\n"
            "情绪温度: 中性\n"
            "资金流与波动: OK\n"
            "主要风险: 低\n"
            "仓位建议: 轻仓\n"
            "市场环境: 稳定\n"
            "一句结论: risk\n"
            "建议标签: HOLD\n\n"
            "决策终审层:\n"
            "趋势判断: 上升\n"
            "关键指标: OK\n"
            "市场扫描: OK\n"
            "操作策略: 观察\n"
            "目标价位: $1\n"
            "止损价位: $0.9\n"
            "基本面评分: 7/10\n"
            "技术面评分: 7/10\n"
            "资金面评分: 7/10\n"
            "大盘共振评分: 7/10\n"
            "综合置信度: 80%\n"
            "最终决策: BUY\n"
            "详细理由: final"
        )

    monkeypatch.setattr(ai_analyst.AIAnalyst, "get_decision", classmethod(fake_get_decision))

    verdict, reason, pulse, risk, decision = AiConsultant.get_final_decision_with_details(
        "AAPL.US",
        "HOLD",
        {
            "user_id": 1,
            "price": 10,
            "rsi": 55,
            "macd": 0.1,
            "atr": 1.2,
            "roc": 2.0,
            "support": 9.5,
            "resistance": 10.5,
        },
    )

    assert calls == ["scan_final"]
    assert verdict == "BUY"
    assert "终审层给出BUY" in reason
    assert pulse["role"] == "市场脉冲层"
    assert risk["role"] == "风险筛查层"
    assert decision["role"] == "决策终审层"


def test_ai_consultant_falls_back_to_legacy_chain_when_combined_format_breaks(monkeypatch) -> None:
    calls = []
    first_scan_final = {"seen": False}

    monkeypatch.setattr(AiConsultant, "_lookup_stock_name", staticmethod(lambda symbol: symbol))
    monkeypatch.setattr(AiConsultant, "_extract_combined_sections", staticmethod(lambda text: None))

    def fake_get_decision(cls, model, prompt, task="general", user_id=1):
        calls.append(task)
        if task == "scan_final" and not first_scan_final["seen"]:
            first_scan_final["seen"] = True
            return "格式不完整"
        if task == "scan_pulse":
            return (
                "趋势判断: 上升\n"
                "指标共振: OK\n"
                "大盘联动: OK\n"
                "机会窗口: OK\n"
                "一句结论: pulse\n"
                "建议标签: BUY"
            )
        if task == "scan_risk":
            return (
                "情绪温度: 中性\n"
                "资金流与波动: OK\n"
                "主要风险: 低\n"
                "仓位建议: 轻仓\n"
                "市场环境: 稳定\n"
                "一句结论: risk\n"
                "建议标签: HOLD"
            )
        return (
            "趋势判断: 上升\n"
            "关键指标: OK\n"
            "市场扫描: OK\n"
            "操作策略: 观察\n"
            "目标价位: $1\n"
            "止损价位: $0.9\n"
            "基本面评分: 7/10\n"
            "技术面评分: 7/10\n"
            "资金面评分: 7/10\n"
            "大盘共振评分: 7/10\n"
            "综合置信度: 80%\n"
            "最终决策: BUY\n"
            "详细理由: final"
        )

    monkeypatch.setattr(ai_analyst.AIAnalyst, "get_decision", classmethod(fake_get_decision))

    verdict, reason, pulse, risk, decision = AiConsultant.get_final_decision_with_details(
        "AAPL.US",
        "HOLD",
        {
            "user_id": 1,
            "price": 10,
            "rsi": 55,
            "macd": 0.1,
            "atr": 1.2,
            "roc": 2.0,
            "support": 9.5,
            "resistance": 10.5,
        },
    )

    assert calls == ["scan_final", "scan_pulse", "scan_risk", "scan_final"]
    assert verdict == "BUY"
    assert "终审层给出BUY" in reason
    assert pulse["role"] == "市场脉冲层"
    assert risk["role"] == "风险筛查层"
    assert decision["role"] == "决策终审层"


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
