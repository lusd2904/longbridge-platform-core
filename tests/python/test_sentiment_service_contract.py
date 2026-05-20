from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE_FILE = ROOT / "apps" / "market" / "sentiment-service" / "src" / "main.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("sentiment_service_main_test", SERVICE_FILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_sentiment_config_reuses_sub2api_models(monkeypatch) -> None:
    monkeypatch.setenv("LONGBRIDGE_AI_BASE_URL", "http://sub2api:8080/v1")
    monkeypatch.setenv("LONGBRIDGE_AI_URL", "http://sub2api:8080/v1/chat/completions")
    monkeypatch.setenv("LONGBRIDGE_AI_MODEL", "gpt-5.5")
    monkeypatch.setenv("LONGBRIDGE_AI_MODEL_SCAN_PULSE", "gpt-5.4")
    monkeypatch.setenv("LONGBRIDGE_AI_MODEL_RECOMMEND_SUMMARY", "gpt-5.5")

    module = _load_module()

    payload = asyncio.run(module.get_config())
    assert payload["enabled"] is True
    assert payload["mode"] == "read-only-aggregator"
    assert payload["aiConfig"]["baseUrl"] == "http://sub2api:8080/v1"
    assert payload["aiConfig"]["chatCompletionsUrl"] == "http://sub2api:8080/v1/chat/completions"
    assert payload["aiConfig"]["models"]["default"] == "gpt-5.5"
    assert payload["aiConfig"]["models"]["scanPulse"] == "gpt-5.4"
    assert payload["aiConfig"]["source"] == "LONGBRIDGE_AI_*"


def test_sentiment_score_handles_json_payload_symbol() -> None:
    module = _load_module()

    scored = module._score_content_item(
        {
            "headline": "NVDA upgrade drives bullish AI demand",
            "summary": "Analysts flag growth and regulation risk.",
            "payload": '{"symbol": "NVDA.US"}',
            "market": "US",
            "generatedAt": "2026-05-20T08:00:00",
        }
    )

    assert scored["symbol"] == "NVDA.US"
    assert scored["market"] == "US"
    assert scored["score"] > 0
    assert "监管" in scored["riskKeywords"]
