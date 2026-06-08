from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException
from core.analysis.ai_analyst import AIAnalyst


ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_MAIN = ROOT / "apps" / "intelligence" / "analysis-service" / "src" / "main.py"


def _load_module(module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, ANALYSIS_MAIN)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ai_assistant_consult_uses_platform_ai_with_page_context(monkeypatch) -> None:
    module = _load_module("analysis_service_ai_assistant_consult_test")
    captured = {}

    def fake_get_decision(cls, model, prompt, task="general", user_id=1):
        captured.update({"model": model, "prompt": prompt, "task": task, "user_id": user_id})
        return "先看策略启用状态，再检查最近回测和风险保护单。"

    monkeypatch.setattr(module.AIAnalyst, "get_decision", classmethod(fake_get_decision))
    monkeypatch.setattr(
        module.AIAnalyst,
        "get_task_model_plan",
        classmethod(lambda cls, user_id=1: {"general": {"id": "gpt-5.5", "alias": "gpt-5.5"}}),
    )

    response = asyncio.run(
        module.assistant_consult(
            payload={
                "question": "这个页面先看什么？",
                "pageContext": {
                    "path": "/strategy?token=secret-token&symbol=AAPL.US",
                    "name": "Strategy",
                    "title": "策略管理",
                    "subsystem": "analysis",
                    "query": {
                        "symbol": "AAPL.US",
                        "token": "secret-token",
                        "api_key": "secret-key",
                    },
                },
                "messages": [
                    {"role": "assistant", "content": "我在。"},
                    {"role": "user", "content": "帮我看下。"},
                ],
            },
            session={"user_id": 7},
        )
    )

    assert response["success"] is True
    assert response["data"]["answer"] == "先看策略启用状态，再检查最近回测和风险保护单。"
    assert response["data"]["model"]["id"] == "gpt-5.5"
    assert captured["model"] is None
    assert captured["task"] == "assistant"
    assert captured["user_id"] == 7
    assert "只读咨询" in captured["prompt"]
    assert "策略管理" in captured["prompt"]
    assert "这个页面先看什么？" in captured["prompt"]
    assert "AAPL.US" in captured["prompt"]
    assert "secret-token" not in captured["prompt"]
    assert "secret-key" not in captured["prompt"]
    assert response["data"]["pageContext"]["path"] == "/strategy"


def test_ai_assistant_consult_rejects_empty_question() -> None:
    module = _load_module("analysis_service_ai_assistant_empty_question_test")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(module.assistant_consult(payload={"question": "   "}, session={"user_id": 7}))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "咨询内容不能为空"


def test_ai_assistant_consult_rate_limits_per_user(monkeypatch) -> None:
    module = _load_module("analysis_service_ai_assistant_rate_limit_test")

    def fake_get_decision(cls, model, prompt, task="general", user_id=1):
        return "可用回答"

    monkeypatch.setattr(module.AIAnalyst, "get_decision", classmethod(fake_get_decision))
    monkeypatch.setattr(
        module.AIAnalyst,
        "get_task_model_plan",
        classmethod(lambda cls, user_id=1: {"general": {"id": "gpt-5.5"}}),
    )
    monkeypatch.setattr(module, "_ASSISTANT_RATE_LIMIT_PER_WINDOW", 2)
    monkeypatch.setattr(module, "_ASSISTANT_RATE_LIMIT_WINDOW_SECONDS", 60)
    module._ASSISTANT_RATE_LIMIT_BUCKETS.clear()

    payload = {"question": "现在应该检查什么？"}
    assert asyncio.run(module.assistant_consult(payload=payload, session={"user_id": 7}))["success"] is True
    assert asyncio.run(module.assistant_consult(payload=payload, session={"user_id": 7}))["success"] is True

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(module.assistant_consult(payload=payload, session={"user_id": 7}))

    assert exc_info.value.status_code == 429
    assert "AI 咨询请求过于频繁" in exc_info.value.detail
    assert exc_info.value.headers["Retry-After"]


def test_ai_assistant_repairs_common_utf8_mojibake() -> None:
    module = _load_module("analysis_service_ai_assistant_mojibake_test")

    assert module._repair_assistant_mojibake("å¯ç¨ï¼ç³»ç»å·²è¿åã") == "可用：系统已返回。"
    assert module._repair_assistant_mojibake("正常中文回答") == "正常中文回答"


def test_ai_assistant_task_uses_interactive_timeout(monkeypatch) -> None:
    monkeypatch.setattr(AIAnalyst, "_provider", classmethod(lambda cls, user_id=1: "nvidia"))
    monkeypatch.setattr(
        "core.analysis.ai_analyst.AppConfig.get",
        lambda key, user_id=1, default=None: 8 if key == "AI_TIMEOUT" else default,
    )

    assert AIAnalyst._request_timeout_for_task("assistant", user_id=7, provider="nvidia") == 24
    assert AIAnalyst._request_timeout_for_task("scan_fast", user_id=7, provider="nvidia") == 8
