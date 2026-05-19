from __future__ import annotations

from datetime import datetime
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[2]
LEGACY_SRC = ROOT / "backend-server" / "src"
if str(LEGACY_SRC) not in sys.path:
    sys.path.insert(0, str(LEGACY_SRC))

from api import data_routes


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
            }
        ],
    )

    items = data_routes._collect_agent_review_notifications(user_id=1, limit=10)

    assert len(items) == 1
    assert items[0]["notificationKey"] == "agent:run-20260520-001"
    assert items[0]["runId"] == "run-20260520-001"
    assert items[0]["run_id"] == "run-20260520-001"
    assert items[0]["scene"] == "watchlist_pre_open_review"
    assert items[0]["route"] == "/scheduler-center?agentRunId=run-20260520-001&scene=watchlist_pre_open_review"
    assert "1 条建议" in items[0]["message"]
    assert "1 条风险" in items[0]["message"]
