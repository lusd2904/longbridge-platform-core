from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_MAIN = ROOT / "apps" / "intelligence" / "analysis-service" / "src" / "main.py"
AGENT_RUN_SERVICE = ROOT / "backend-server" / "src" / "core" / "analysis" / "AgentRunService.py"


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_run_service_list_recent_runs_includes_latest_override_state(monkeypatch) -> None:
    module = _load_module("agent_run_service_override_state_test", AGENT_RUN_SERVICE)

    run_rows = [
        {
            "run_id": 12,
            "scene": "watchlist_pre_open_review",
            "trigger_source": "scheduler",
            "user_id": 8,
            "status": "succeeded",
            "input_summary": None,
            "result_summary": json.dumps({"summary": "ok"}),
            "error_summary": None,
            "trace_ref": None,
            "started_at": None,
            "finished_at": None,
            "created_at": "2026-05-20 10:00:00",
            "updated_at": "2026-05-20 10:02:00",
        }
    ]
    override_rows = [
        {
            "override_id": 3,
            "run_id": 12,
            "user_id": 99,
            "actor": "admin",
            "action": "needs_review",
            "reason": json.dumps({"note": "recheck"}),
            "old_status": "succeeded",
            "new_status": "failed",
            "review_note": json.dumps({"summary": "missing evidence"}),
            "created_at": "2026-05-20 10:05:00",
        }
    ]

    monkeypatch.setattr(module.AgentRunService, "ensure_schema", classmethod(lambda cls: None))

    def fake_fetch_all(sql, params):
        if "FROM agent_runs" in sql:
            return run_rows
        if "FROM agent_human_overrides" in sql:
            return override_rows
        return []

    monkeypatch.setattr(module.DbUtil, "fetch_all_primary", fake_fetch_all)
    monkeypatch.setattr(module.DbUtil, "fetch_all", fake_fetch_all)

    data = module.AgentRunService.list_recent_runs(user_id=8, limit=5, use_primary=True)

    assert len(data) == 1
    assert data[0]["reviewAction"] == "needs_review"
    assert data[0]["reviewedBy"] == "admin"
    assert data[0]["reviewedAt"] == "2026-05-20 10:05:00"
    assert data[0]["latestOverride"]["newStatus"] == "failed"
    assert data[0]["overrides"][0]["reasonDetail"] == {"note": "recheck"}


def test_analysis_service_override_rejects_invalid_status_transition() -> None:
    module = _load_module("analysis_service_override_transition_test", ANALYSIS_MAIN)

    with pytest.raises(HTTPException) as exc_info:
        module._validate_override_status_transition("dismissed", "failed")

    assert exc_info.value.status_code == 400
    assert "dismissed" in str(exc_info.value.detail)


def test_analysis_service_override_records_allowed_transition(monkeypatch) -> None:
    module = _load_module("analysis_service_override_record_test", ANALYSIS_MAIN)
    recorded = {}

    monkeypatch.setattr(module, "_load_agent_run_or_404", lambda run_id: {"run_id": run_id, "user_id": 7, "status": "succeeded", "scene": "watchlist_pre_open_review"})
    monkeypatch.setattr(module, "_assert_agent_run_visible", lambda run, session, scoped_user_id: None)

    def fake_call_agent_run_service(method_names, **kwargs):
        if method_names[0] == "record_override":
            recorded.update(kwargs)
            return 101
        if method_names[0] == "get_run":
            return {
                "run_id": kwargs["run_id"],
                "user_id": 7,
                "status": "succeeded",
                "scene": "watchlist_pre_open_review",
                "overrides": [
                    {
                        "overrideId": 101,
                        "actor": recorded.get("actor"),
                        "action": recorded.get("action"),
                        "newStatus": recorded.get("new_status"),
                    }
                ],
            }
        raise AssertionError(f"unexpected service call: {method_names}")

    monkeypatch.setattr(module, "_call_agent_run_service", fake_call_agent_run_service)

    response = asyncio.run(
        module.override_agent_run(
            run_id=18,
            payload={
                "action": "dismissed",
                "newStatus": "cancelled",
                "reason": {"source": "human"},
                "reviewNote": {"summary": "not actionable"},
            },
            userId=None,
            session={"user_id": 7, "username": "admin"},
        )
    )

    assert response["success"] is True
    assert recorded["action"] == "dismissed"
    assert recorded["new_status"] == "cancelled"
    assert recorded["user_id"] == 7
    assert recorded["actor"] == "admin"
    assert recorded["review_note"] == {"summary": "not actionable"}
