from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

from fastapi.responses import JSONResponse
from flask import Flask, request


ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_MAIN = ROOT / "apps" / "intelligence" / "analysis-service" / "src" / "main.py"
AI_ROUTES = ROOT / "backend-server" / "src" / "api" / "ai_routes.py"


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_analysis_service_analyze_positions_returns_202_when_sync_limit_exceeded(monkeypatch) -> None:
    module = _load_module("analysis_service_long_chain_guardrails_test", ANALYSIS_MAIN)
    heavy_calls = {"quotes": 0, "context": 0, "decision": 0}

    monkeypatch.setattr(module, "_resolve_analysis_account_id", lambda user_id, account_id: 1)
    monkeypatch.setattr(module.AIAnalyst, "get_task_model_plan", classmethod(lambda cls, user_id=1: {"task": "scan"}))
    monkeypatch.setattr(
        module,
        "get_quotes_from_broker",
        lambda *args, **kwargs: heavy_calls.__setitem__("quotes", heavy_calls["quotes"] + 1) or (_ for _ in ()).throw(AssertionError("over-limit path must not fetch quotes")),
    )
    monkeypatch.setattr(
        module,
        "build_real_indicator_context",
        lambda *args, **kwargs: heavy_calls.__setitem__("context", heavy_calls["context"] + 1) or (_ for _ in ()).throw(AssertionError("over-limit path must not build indicators")),
    )
    monkeypatch.setattr(
        module.AiConsultant,
        "get_final_decision_with_details",
        staticmethod(lambda *args, **kwargs: heavy_calls.__setitem__("decision", heavy_calls["decision"] + 1) or (_ for _ in ()).throw(AssertionError("over-limit path must not call AI consultant"))),
    )

    positions = [{"symbol": f"T{i}.US"} for i in range(module.SYNC_ANALYZE_POSITIONS_LIMIT + 3)]
    response = asyncio.run(
        module.analyze_positions(
            payload={"positions": positions, "force_refresh": True},
            session={"user_id": 7},
        )
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 202
    payload = response.body and __import__("json").loads(response.body)
    assert payload["success"] is True
    assert payload["accepted"] is True
    assert payload["degraded"] is True
    assert payload["stats"]["total"] == len(positions)
    assert payload["stats"]["accepted"] == 0
    assert payload["stats"]["successful"] == 0
    assert payload["stats"]["deferred"] == len(positions)
    assert len(payload["data"]) == len(positions)
    assert payload["meta"]["executionMode"] == "deferred"
    assert heavy_calls == {"quotes": 0, "context": 0, "decision": 0}


def test_analysis_service_analyze_positions_keeps_200_for_small_batches(monkeypatch) -> None:
    module = _load_module("analysis_service_long_chain_guardrails_small_batch_test", ANALYSIS_MAIN)
    monkeypatch.setattr(module, "_resolve_analysis_account_id", lambda user_id, account_id: 1)
    monkeypatch.setattr(module.AIAnalyst, "get_task_model_plan", classmethod(lambda cls, user_id=1: {"task": "scan"}))
    monkeypatch.setattr(
        module,
        "get_quotes_from_broker",
        lambda symbols, account_id=None, user_id=None: {
            symbol: {"last_price": 100.0, "volume": 1000, "change_percent": 1.2, "prev_close": 98.8}
            for symbol in symbols
        },
    )
    monkeypatch.setattr(module, "build_market_snapshot", lambda account_id, symbol, user_id=None: {"market": "US"})
    monkeypatch.setattr(
        module,
        "build_real_indicator_context",
        lambda symbol, current_price, volume, user_id=1: ({"rsi": 50, "price": current_price}, {"rsi": 50}),
    )
    monkeypatch.setattr(
        module.AiConsultant,
        "get_final_decision_with_details",
        staticmethod(lambda symbol, algo_side, ai_data: ("HOLD", "ok", {"full_text": "g"}, {"full_text": "l"}, {"full_text": "d", "confidence": 80.0})),
    )
    monkeypatch.setattr(
        module,
        "_build_manual_scan_result",
        lambda **kwargs: {
            "symbol": kwargs["symbol"],
            "finalDecision": "HOLD",
            "indicators": kwargs["indicator_payload"],
            "marketSummary": kwargs["market_snapshot"],
        },
    )
    monkeypatch.setattr(module, "detect_market", lambda symbol: "US")
    monkeypatch.setattr(module.AICache, "cache_analysis", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "get_persistence_manager", lambda: type("P", (), {"save_ai_analysis": lambda self, item: None})())

    payload = asyncio.run(
        module.analyze_positions(
            payload={"positions": [{"symbol": "AAPL.US"}, {"symbol": "MSFT.US"}], "force_refresh": True},
            session={"user_id": 9},
        )
    )

    assert payload["success"] is True
    assert payload["degraded"] is False
    assert payload["stats"]["accepted"] == 2
    assert payload["stats"]["deferred"] == 0


def test_legacy_batch_analyze_positions_returns_202_with_compat_stats(monkeypatch) -> None:
    module = _load_module("legacy_ai_routes_long_chain_guardrails_test", AI_ROUTES)
    app = Flask(__name__)
    raw_handler = module.batch_analyze_positions.__wrapped__.__wrapped__
    heavy_calls = {"process": 0, "indicator": 0, "analyze": 0, "decision": 0}

    monkeypatch.setattr(module.Logger, "get_logger", staticmethod(lambda name: type("L", (), {"info": lambda self, msg: None})()))
    monkeypatch.setattr(module.Logger, "log_api_call", staticmethod(lambda *args, **kwargs: None))
    monkeypatch.setattr(module.Logger, "log_error", staticmethod(lambda *args, **kwargs: None))
    monkeypatch.setattr(module.MonitorLink, "log", staticmethod(lambda *args, **kwargs: None))
    monkeypatch.setattr(module, "_process_stock_data", lambda *args, **kwargs: heavy_calls.__setitem__("process", heavy_calls["process"] + 1) or (_ for _ in ()).throw(AssertionError("over-limit path must not process stocks")))
    monkeypatch.setattr(module, "_calculate_indicators", lambda *args, **kwargs: heavy_calls.__setitem__("indicator", heavy_calls["indicator"] + 1) or (_ for _ in ()).throw(AssertionError("over-limit path must not calculate indicators")))
    monkeypatch.setattr(module, "_analyze_stock", lambda *args, **kwargs: heavy_calls.__setitem__("analyze", heavy_calls["analyze"] + 1) or (_ for _ in ()).throw(AssertionError("over-limit path must not analyze stocks")))
    monkeypatch.setattr(module, "_generate_decision", lambda *args, **kwargs: heavy_calls.__setitem__("decision", heavy_calls["decision"] + 1) or (_ for _ in ()).throw(AssertionError("over-limit path must not generate decisions")))

    positions = [{"symbol": f"T{i}.US"} for i in range(module.SYNC_BATCH_ANALYZE_LIMIT + 2)]
    with app.test_request_context("/api/ai/batch_analyze_positions", method="POST", json={"positions": positions}):
        request.user_id = 5
        response, status_code = raw_handler()

    payload = response.get_json()
    assert status_code == 202
    assert payload["success"] is True
    assert payload["accepted"] is True
    assert payload["degraded"] is True
    assert payload["stats"]["total"] == len(positions)
    assert payload["stats"]["accepted"] == 0
    assert payload["stats"]["successful"] == 0
    assert payload["stats"]["deferred"] == len(positions)
    assert len(payload["data"]) == len(positions)
    assert payload["meta"]["executionMode"] == "deferred"
    assert heavy_calls == {"process": 0, "indicator": 0, "analyze": 0, "decision": 0}
