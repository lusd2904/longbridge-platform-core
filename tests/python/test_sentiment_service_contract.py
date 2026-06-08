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
    monkeypatch.setenv("LONGBRIDGE_AI_BASE_URL", "https://lucen.cc/v1")
    monkeypatch.setenv("LONGBRIDGE_AI_URL", "https://lucen.cc/v1/chat/completions")
    monkeypatch.setenv("LONGBRIDGE_AI_MODEL", "gpt-5.5")
    monkeypatch.setenv("LONGBRIDGE_AI_MODEL_SCAN_PULSE", "gpt-5.4")
    monkeypatch.setenv("LONGBRIDGE_AI_MODEL_RECOMMEND_SUMMARY", "gpt-5.5")

    module = _load_module()

    payload = asyncio.run(module.get_config())
    assert payload["enabled"] is True
    assert payload["mode"] == "read-only-aggregator"
    assert payload["aiConfig"]["baseUrl"] == "https://lucen.cc/v1"
    assert payload["aiConfig"]["chatCompletionsUrl"] == "https://lucen.cc/v1/chat/completions"
    assert payload["aiConfig"]["models"]["default"] == "gpt-5.5"
    assert payload["aiConfig"]["models"]["scanPulse"] == "gpt-5.4"
    assert payload["aiConfig"]["source"] == "LONGBRIDGE_AI_*"


def test_sentiment_bootstrap_exposes_github_adoption_contract(monkeypatch) -> None:
    monkeypatch.setenv("LONGBRIDGE_AI_BASE_URL", "https://lucen.cc/v1")
    monkeypatch.setenv("LONGBRIDGE_AI_MODEL", "gpt-5.5")
    module = _load_module()
    monkeypatch.setattr(module, "_build_recommendation_map", lambda user_id: {})
    monkeypatch.setattr(
        module,
        "_build_market_summary",
        lambda market, user_id, recommendation_map=None: {
            "market": market,
            "sentimentScore": 0,
            "sentimentLabel": "neutral",
            "positiveCount": 0,
            "negativeCount": 0,
            "heat": 0,
            "topRiskKeywords": [],
            "leaders": [],
        },
    )

    contract = module._build_page_contract(user_id=1)["githubAdoption"]

    assert contract["decision"] == "native-contract-first"
    assert "FinNLP collectors" in contract["recommendedStack"]
    assert "sub2api gpt-5.4/gpt-5.5 synthesis" in contract["recommendedStack"]
    assert contract["aiModelPolicy"].startswith("reuse LONGBRIDGE_AI_* / sub2api")
    assert "must not submit orders" in contract["quantPolicy"]
    assert any(item["name"] == "FinNLP" and item["adoption"] == "reference-adapter" for item in contract["candidates"])
    assert any(item["license"] == "GPL family" and item["adoption"] == "do-not-vendor" for item in contract["candidates"])


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
