from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[2]
LEGACY_SRC = ROOT / "backend-server" / "src"
RISK_SERVICE_MAIN = ROOT / "apps/governance/risk-service/src/main.py"
if str(LEGACY_SRC) not in sys.path:
    sys.path.insert(0, str(LEGACY_SRC))

from api import data_routes


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_notifications_fall_back_to_live_trade_orders_when_projection_empty(monkeypatch) -> None:
    monkeypatch.setattr(data_routes.StrategyMonitorService, "get_alerts", lambda *args, **kwargs: [])
    monkeypatch.setattr(data_routes.AgentRunService, "list_recent_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr(data_routes.DbUtil, "fetch_all", lambda *args, **kwargs: [])
    monkeypatch.setattr(data_routes, "_get_notification_states", lambda *args, **kwargs: {})
    monkeypatch.setattr(data_routes, "_list_recent_order_projection_notifications", lambda *args, **kwargs: [])

    live_order = {
        "notificationKey": "trade:1:order-1:2026-05-19 09:30:00",
        "type": "trade",
        "title": "AAPL.US 买入",
        "message": "状态 已提交，数量 1.00，价格 190.00",
        "time": datetime(2026, 5, 19, 9, 30, 0),
        "route": "/orders",
    }
    monkeypatch.setattr(data_routes, "_list_recent_live_orders", lambda *args, **kwargs: [live_order])

    items = data_routes._collect_notifications(user_id=1, limit=10, notification_type="")

    assert len(items) == 1
    assert items[0]["type"] == "trade"
    assert items[0]["title"] == "AAPL.US 买入"
    assert items[0]["id"] == live_order["notificationKey"]


def test_agent_review_notifications_link_to_specific_run(monkeypatch) -> None:
    monkeypatch.setattr(
        data_routes.AgentRunService,
        "list_recent_runs",
        lambda *args, **kwargs: [
            {
                "runId": "run-20260520-001",
                "scene": "watchlist_pre_open_review",
                "status": "succeeded",
                "resultSummary": {
                    "summary": "盘前复核完成",
                    "reviewAdvice": [{"title": "关注 NVDL"}],
                    "riskFlags": [{"title": "波动放大"}],
                },
                "finishedAt": "2026-05-20T08:35:00Z",
                "reviewAction": "needs_review",
                "reviewedAt": "2026-05-20 08:40:00",
                "reviewedBy": "analyst",
            }
        ],
    )

    items = data_routes._collect_agent_review_notifications(user_id=1, limit=10)

    assert len(items) == 1
    assert items[0]["notificationKey"] == "agent:run-20260520-001"
    assert items[0]["type"] == "agent-risk"
    assert items[0]["runId"] == "run-20260520-001"
    assert items[0]["run_id"] == "run-20260520-001"
    assert items[0]["scene"] == "watchlist_pre_open_review"
    assert items[0]["route"] == "/scheduler-center?agentRunId=run-20260520-001&scene=watchlist_pre_open_review"
    assert "1 条建议" in items[0]["message"]
    assert "1 条风险" in items[0]["message"]
    assert items[0]["message"].startswith("复核已超期：")
    assert items[0]["reviewStatus"] == "needs_review"
    assert items[0]["reviewAction"] == "needs_review"
    assert items[0]["reviewedBy"] == "analyst"
    assert items[0]["reviewDeadlineAt"] == "2026-05-20 10:35:00"


def test_risk_notifications_include_agent_risk_runs(monkeypatch) -> None:
    monkeypatch.setattr(data_routes.StrategyMonitorService, "get_alerts", lambda *args, **kwargs: [])
    monkeypatch.setattr(data_routes, "_get_notification_states", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        data_routes.AgentRunService,
        "list_recent_runs",
        lambda *args, **kwargs: [
            {
                "runId": 88,
                "scene": "watchlist_post_close_review",
                "status": "succeeded",
                "resultSummary": {
                    "summary": "盘后风险复核完成",
                    "riskFlags": [{"level": "high", "symbol": "NVDL.US", "message": "波动放大"}],
                },
                "finishedAt": "2026-05-20T16:45:00Z",
            }
        ],
    )

    items = data_routes._collect_notifications(user_id=1, limit=10, notification_type="risk")

    assert len(items) == 1
    assert items[0]["type"] == "agent-risk"
    assert items[0]["title"] == "自选股盘后复核 待复核"
    assert items[0]["route"] == "/scheduler-center?agentRunId=88&scene=watchlist_post_close_review"
    assert items[0]["reviewStatus"] == "pending_review"
    assert items[0]["reviewSlaHours"] == 18


def test_risk_overview_merges_agent_risk_flags(monkeypatch) -> None:
    monkeypatch.setattr(data_routes.StrategyMonitorService, "get_alerts", lambda *args, **kwargs: [])
    monkeypatch.setattr(data_routes, "_load_risk_limits", lambda user_id: {
        "maxPositionSize": 35,
        "maxLossPerTrade": 1000,
        "maxDailyLoss": 5000,
        "maxDrawdown": 20,
        "volatilityLimit": 50,
    })
    monkeypatch.setattr(data_routes, "_load_risk_orders", lambda *args, **kwargs: [])
    monkeypatch.setattr(data_routes, "_load_position_snapshot", lambda *args, **kwargs: {})
    monkeypatch.setattr(data_routes, "_compute_asset_drawdown", lambda user_id: 0)
    monkeypatch.setattr(
        data_routes.AgentRunService,
        "list_recent_runs",
        lambda *args, **kwargs: [
            {
                "runId": 99,
                "scene": "watchlist_pre_open_review",
                "status": "succeeded",
                "resultSummary": {
                    "summary": "盘前风险复核完成",
                    "riskFlags": [
                        {
                            "severity": "high",
                            "symbols": ["NVDL.US"],
                            "message": "杠杆 ETF 波动放大",
                            "evidence": [{"source": "agent"}],
                        }
                    ],
                },
                "finishedAt": "2026-05-20T08:45:00Z",
            }
        ],
    )

    payload = data_routes._build_risk_overview(user_id=1)

    assert payload["events"][0]["id"] == "agent:99:risk:1"
    assert payload["events"][0]["source"] == "agent-review"
    assert payload["events"][0]["symbol"] == "NVDL.US"
    assert payload["events"][0]["route"] == "/scheduler-center?agentRunId=99&scene=watchlist_pre_open_review"
    assert payload["events"][0]["reviewStatus"] == "pending_review"
    assert payload["events"][0]["reviewDeadlineAt"] == "2026-05-20 10:45:00"
    assert "高风险 1 条" in payload["overview"]["scoreDescription"]


def test_risk_overview_ignores_dismissed_agent_risk_for_score(monkeypatch) -> None:
    monkeypatch.setattr(data_routes.StrategyMonitorService, "get_alerts", lambda *args, **kwargs: [])
    monkeypatch.setattr(data_routes, "_load_risk_limits", lambda user_id: {
        "maxPositionSize": 35,
        "maxLossPerTrade": 1000,
        "maxDailyLoss": 5000,
        "maxDrawdown": 20,
        "volatilityLimit": 50,
    })
    monkeypatch.setattr(data_routes, "_load_risk_orders", lambda *args, **kwargs: [])
    monkeypatch.setattr(data_routes, "_load_position_snapshot", lambda *args, **kwargs: {})
    monkeypatch.setattr(data_routes, "_compute_asset_drawdown", lambda user_id: 0)
    monkeypatch.setattr(
        data_routes.AgentRunService,
        "list_recent_runs",
        lambda *args, **kwargs: [
            {
                "runId": 101,
                "scene": "watchlist_pre_open_review",
                "status": "succeeded",
                "resultSummary": {
                    "summary": "盘前风险复核完成",
                    "riskFlags": [{"severity": "high", "symbol": "NVDL.US", "message": "已忽略风险"}],
                },
                "finishedAt": "2026-05-20T08:45:00Z",
                "reviewAction": "dismissed",
            }
        ],
    )

    payload = data_routes._build_risk_overview(user_id=1)

    assert payload["events"][0]["reviewStatus"] == "dismissed"
    assert payload["events"][0]["active"] is False
    assert payload["overview"]["scoreDescription"] == "高风险 0 条，中风险 0 条"


def test_agent_review_lifecycle_messages_reflect_review_actions(monkeypatch) -> None:
    monkeypatch.setattr(
        data_routes.AgentRunService,
        "list_recent_runs",
        lambda *args, **kwargs: [
            {
                "runId": "ack-1",
                "scene": "watchlist_pre_open_review",
                "status": "succeeded",
                "resultSummary": {"summary": "确认过的风险", "riskFlags": [{"level": "medium", "message": "已确认"}]},
                "finishedAt": "2026-05-20T08:35:00Z",
                "reviewAction": "acknowledged",
                "reviewedBy": "analyst",
            },
            {
                "runId": "dismiss-1",
                "scene": "watchlist_post_close_review",
                "status": "succeeded",
                "resultSummary": {"summary": "忽略噪声", "riskFlags": [{"level": "high", "message": "已忽略"}]},
                "finishedAt": "2026-05-20T16:35:00Z",
                "reviewAction": "dismissed",
                "reviewedBy": "analyst",
            },
        ],
    )

    items = data_routes._collect_agent_review_notifications(user_id=1, limit=10)

    by_run_id = {item["runId"]: item for item in items}
    assert by_run_id["ack-1"]["title"] == "自选股盘前复核 已确认"
    assert by_run_id["ack-1"]["message"].startswith("已人工确认：")
    assert by_run_id["ack-1"]["reviewStatus"] == "reviewed"
    assert by_run_id["dismiss-1"]["title"] == "自选股盘后复核 已忽略"
    assert by_run_id["dismiss-1"]["message"].startswith("已忽略：")
    assert by_run_id["dismiss-1"]["reviewStatus"] == "dismissed"


def test_risk_service_merge_reuses_existing_agent_events(monkeypatch) -> None:
    module = _load_module("risk_service_agent_merge_test", RISK_SERVICE_MAIN)
    calls = {"collect": 0}

    def fail_collect(*args, **kwargs):
        calls["collect"] += 1
        raise AssertionError("collect_agent_risk_events should not be called when events already exist")

    monkeypatch.setattr(module, "collect_agent_risk_events", fail_collect)
    payload = {
        "overview": {"scoreDescription": "高风险 1 条，中风险 0 条"},
        "events": [
            {
                "id": "agent:99:risk:1",
                "source": "agent-review",
                "level": "high",
                "type": "自选股盘前复核 Agent 风险",
                "message": "杠杆 ETF 波动放大",
                "timestamp": "2026-05-20T08:45:00Z",
            },
            {
                "id": "risk:1",
                "source": "strategy",
                "level": "medium",
                "type": "持仓规则",
                "message": "仓位偏高",
                "timestamp": "2026-05-20T08:40:00Z",
            },
        ],
    }

    result = module._merge_agent_risk_events(
        payload,
        user_id=1,
        agent_events=module._extract_existing_agent_risk_events(payload),
    )

    assert calls["collect"] == 0
    assert result["overview"]["agentRiskCount"] == 1
    assert result["overview"]["riskEventCount"] == 2
    assert result["meta"]["agentRiskEventCount"] == 1
    assert result["meta"]["eventCount"] == 2


def test_data_routes_do_not_fallback_to_bootstrap_user() -> None:
    source = (ROOT / "backend-server/src/api/data_routes.py").read_text(encoding="utf-8")
    banned_snippets = [
        "user_id or 1",
        "user_id: int = 1",
        "getattr(request, 'user_id', 1)",
        'getattr(request, "user_id", 1)',
    ]

    for snippet in banned_snippets:
        assert snippet not in source
