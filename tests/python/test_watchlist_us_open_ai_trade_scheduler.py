from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_scheduler_main():
    module_path = ROOT / "apps" / "operations" / "scheduler-service" / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("scheduler_service_main_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_system_task_service_exposes_watchlist_us_open_ai_trade_defaults() -> None:
    from core.platform.SystemTaskService import SystemTaskService

    policy = SystemTaskService.DEFAULT_POLICIES["watchlist_us_open_ai_trade"]

    assert policy["taskName"] == "美股开盘 AI 自动交易"
    assert policy["category"] == "trade"
    assert policy["scheduleType"] == "interval"
    assert policy["enabled"] is True
    assert policy["intervalSeconds"] == 900
    assert policy["settings"] == {
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
    }
    assert "纸账户" in policy["description"]
    assert "交易边界保护" in policy["description"]


def test_scheduler_runtime_and_manual_runner_register_watchlist_us_open_ai_trade(monkeypatch) -> None:
    scheduler_main = _load_scheduler_main()

    calls = []

    monkeypatch.setattr(
        scheduler_main.QuantTradingService,
        "run_us_open_watchlist_ai_trade",
        lambda *, user_id, source: calls.append((user_id, source)) or {"success": True, "userId": user_id},
        raising=False,
    )
    monkeypatch.setattr(
        scheduler_main,
        "_list_us_open_ai_trade_users",
        lambda: [{"userId": 11, "username": "alice"}, {"userId": 17, "username": "bob"}],
    )
    monkeypatch.setattr(
        scheduler_main,
        "_write_job_status",
        lambda *args, **kwargs: None,
    )

    settings = scheduler_main._us_open_ai_trade_settings()
    assert settings["autoTradeEnabled"] is True
    assert settings["maxSymbols"] == 5
    assert settings["targetPortfolioRatio"] == 0.70
    assert settings["strategyProfile"] == "balanced"
    assert settings["market"] == "US"
    assert settings["regularSessionOnly"] is True
    assert settings["refreshRealtimePrice"] is True
    assert settings["requireRealtimePrice"] is True
    assert settings["maxDailySubmittedOrders"] == 10
    assert settings["maxDailyNotionalRatio"] == 0.70

    assert "watchlist_us_open_ai_trade" in scheduler_main.TASK_RUNNERS

    result = scheduler_main.TASK_RUNNERS["watchlist_us_open_ai_trade"](999)

    assert calls == [(11, "scheduler"), (17, "scheduler")]
    assert result["userCount"] == 2
    assert result["successCount"] == 2
    assert result["failureCount"] == 0
    managed = scheduler_main.scheduler_runtime.snapshot()["threads"]
    assert any(item["taskKey"] == "watchlist_us_open_ai_trade" for item in managed)
