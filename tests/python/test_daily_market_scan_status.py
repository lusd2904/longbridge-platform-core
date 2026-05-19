from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = ROOT / "backend-server/src/core/analysis/DailyMarketScanService.py"


def _dependency_stub(module_name: str, attr_name: str) -> ModuleType:
    module = ModuleType(module_name)
    setattr(module, attr_name, type(attr_name, (), {}))
    return module


def _load_service_module():
    stub_names = {
        "core.analysis.IndicatorSnapshotService": _dependency_stub(
            "core.analysis.IndicatorSnapshotService",
            "IndicatorSnapshotService",
        ),
        "core.analysis.MarketInsightService": _dependency_stub(
            "core.analysis.MarketInsightService",
            "MarketInsightService",
        ),
        "core.analysis.ai_analyst": _dependency_stub("core.analysis.ai_analyst", "AIAnalyst"),
        "utils.DbUtil": _dependency_stub("utils.DbUtil", "DbUtil"),
    }
    previous = {name: sys.modules.get(name) for name in stub_names}
    sys.modules.update(stub_names)
    try:
        spec = importlib.util.spec_from_file_location("_daily_market_scan_service_under_test", SERVICE_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, previous_module in previous.items():
            if previous_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous_module


market_scan_module = _load_service_module()
DailyMarketScanService = market_scan_module.DailyMarketScanService


def test_market_scan_status_is_short_display_value() -> None:
    status = DailyMarketScanService._normalize_status(
        status_text="风险偏好回升但内部结构明显分化，需要观察半导体和科技权重能否继续放量",
        regime="balanced",
        technical_score=63,
        breadth_ratio=58,
    )

    assert status == "偏强"
    assert len(status) <= 32


def test_market_scan_status_falls_back_to_metrics_when_text_is_unclear() -> None:
    assert DailyMarketScanService._normalize_status(
        status_text="AI 返回了一段没有明确状态关键词的长句子",
        regime="",
        technical_score=32,
        breadth_ratio=30,
    ) == "偏弱"

    assert DailyMarketScanService._normalize_status(
        status_text="",
        regime="balanced",
        technical_score=50,
        breadth_ratio=50,
    ) == "中性"


def test_save_result_coerces_long_status_before_sql(monkeypatch) -> None:
    captured = {}

    def fake_execute_sql(sql, params):
        captured["params"] = params

    monkeypatch.setattr(market_scan_module.DbUtil, "execute_sql", fake_execute_sql, raising=False)

    DailyMarketScanService._save_result({
        "market": "US",
        "tradeDate": "2026-05-19",
        "technicalScore": 65,
        "breadthRatio": 60,
        "status": "风险偏好回升但内部结构明显分化，需要观察科技权重能否继续放量",
        "modelId": "gpt-5.5",
        "modelAlias": "最高质量",
        "headline": "美股技术扫描",
        "summary": "测试摘要",
        "insights": {"statusText": "长状态"},
        "benchmarks": [],
    })

    assert captured["params"][4] == "偏强"
    assert len(captured["params"][4]) <= 32
