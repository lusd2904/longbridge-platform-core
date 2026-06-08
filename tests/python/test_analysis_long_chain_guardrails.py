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
    enqueued_jobs = []

    monkeypatch.setattr(module, "_resolve_analysis_account_id", lambda user_id, account_id: 1)
    monkeypatch.setattr(module.AIAnalyst, "get_task_model_plan", classmethod(lambda cls, user_id=1: {"task": "scan"}))
    monkeypatch.setattr(
        module,
        "_start_deferred_positions_analysis_worker",
        lambda job_id, positions, base_payload, session: enqueued_jobs.append(
            {
                "job_id": job_id,
                "positions": positions,
                "base_payload": base_payload,
                "session": session,
            }
        ),
    )
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
    assert payload["jobId"]
    assert payload["jobStatus"] == "queued"
    assert payload["statusUrl"].endswith(payload["jobId"])
    assert payload["jobExpiresAt"]
    assert payload["jobTtlSeconds"] == module._DEFERRED_ANALYSIS_JOB_TTL_SECONDS
    assert payload["stats"]["total"] == len(positions)
    assert payload["stats"]["accepted"] == 0
    assert payload["stats"]["successful"] == 0
    assert payload["stats"]["deferred"] == len(positions)
    assert len(payload["data"]) == len(positions)
    assert payload["meta"]["executionMode"] == "deferred"
    assert payload["meta"]["jobId"] == payload["jobId"]
    assert payload["meta"]["jobExpiresAt"] == payload["jobExpiresAt"]
    assert payload["meta"]["jobTtlSeconds"] == payload["jobTtlSeconds"]
    assert heavy_calls == {"quotes": 0, "context": 0, "decision": 0}
    assert enqueued_jobs == [
        {
            "job_id": payload["jobId"],
            "positions": positions,
            "base_payload": {"positions": positions, "force_refresh": True, "forceRefresh": True},
            "session": {"user_id": 7},
        }
    ]
    assert module._deferred_analysis_job_snapshot(payload["jobId"])["status"] == "queued"


def test_analysis_service_missing_deferred_job_status_returns_expired_response() -> None:
    module = _load_module("analysis_service_missing_deferred_job_status_test", ANALYSIS_MAIN)
    module._DEFERRED_ANALYSIS_JOBS.clear()

    response = asyncio.run(
        module.analyze_positions_job_status(
            job_id="missing-job",
            session={"user_id": 7},
        )
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 410
    payload = response.body and __import__("json").loads(response.body)
    assert payload["success"] is False
    assert payload["data"]["jobId"] == "missing-job"
    assert payload["data"]["status"] == "expired"
    assert payload["data"]["retryable"] is False


def test_analysis_service_reads_terminal_deferred_job_snapshot_from_redis(monkeypatch) -> None:
    module = _load_module("analysis_service_deferred_job_redis_snapshot_test", ANALYSIS_MAIN)
    module._DEFERRED_ANALYSIS_JOBS.clear()

    class FakeRedis:
        def get_json(self, key):
            assert key.endswith("redis-completed")
            return {
                "jobId": "redis-completed",
                "status": "completed",
                "userId": 7,
                "result": {"success": True, "data": []},
            }

    monkeypatch.setattr(module, "redis_client", FakeRedis())

    snapshot = module._deferred_analysis_job_snapshot("redis-completed")

    assert snapshot["status"] == "completed"
    assert snapshot["result"]["success"] is True


def test_analysis_service_treats_redis_only_active_job_as_expired(monkeypatch) -> None:
    module = _load_module("analysis_service_deferred_job_redis_active_test", ANALYSIS_MAIN)
    module._DEFERRED_ANALYSIS_JOBS.clear()

    class FakeRedis:
        def get_json(self, key):
            return {"jobId": "redis-running", "status": "running", "userId": 7}

    monkeypatch.setattr(module, "redis_client", FakeRedis())

    response = asyncio.run(
        module.analyze_positions_job_status(
            job_id="redis-running",
            session={"user_id": 7},
        )
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 410
    payload = response.body and __import__("json").loads(response.body)
    assert payload["data"]["status"] == "expired"


def test_analysis_service_deferred_worker_completes_background_job(monkeypatch) -> None:
    module = _load_module("analysis_service_deferred_worker_test", ANALYSIS_MAIN)
    module._DEFERRED_ANALYSIS_JOBS.clear()
    calls = []

    async def fake_analyze_positions(payload, session):
        calls.append({"payload": payload, "session": session})
        return {
            "success": True,
            "data": [{"symbol": item["symbol"], "finalDecision": "HOLD"} for item in payload["positions"]],
            "marketSummary": {"market": "US"},
        }

    monkeypatch.setattr(module, "SYNC_ANALYZE_POSITIONS_LIMIT", 2)
    monkeypatch.setattr(module, "analyze_positions", fake_analyze_positions)
    job_id = "job-test-1"
    module._set_deferred_analysis_job(
        job_id,
        jobId=job_id,
        status="queued",
        userId=9,
        requested=3,
        syncLimit=2,
        createdAt="2026-06-08T00:00:00Z",
    )

    module._run_deferred_positions_analysis_job(
        job_id,
        [{"symbol": "AAPL.US"}, {"symbol": "MSFT.US"}, {"symbol": "NVDA.US"}],
        {"force_refresh": True},
        {"user_id": 9},
    )

    snapshot = module._deferred_analysis_job_snapshot(job_id)
    assert snapshot["status"] == "completed"
    assert snapshot["result"]["success"] is True
    assert snapshot["result"]["stats"]["total"] == 3
    assert snapshot["result"]["stats"]["successful"] == 3
    assert [call["payload"]["positions"] for call in calls] == [
        [{"symbol": "AAPL.US"}, {"symbol": "MSFT.US"}],
        [{"symbol": "NVDA.US"}],
    ]


def test_analysis_service_deferred_worker_marks_job_failed_on_chunk_exception(monkeypatch) -> None:
    module = _load_module("analysis_service_deferred_worker_failure_test", ANALYSIS_MAIN)
    module._DEFERRED_ANALYSIS_JOBS.clear()

    async def fake_analyze_positions(payload, session):
        if payload["positions"][0]["symbol"] == "BROKEN.US":
            raise RuntimeError("chunk exploded")
        return {
            "success": True,
            "data": [{"symbol": item["symbol"], "finalDecision": "HOLD"} for item in payload["positions"]],
        }

    monkeypatch.setattr(module, "SYNC_ANALYZE_POSITIONS_LIMIT", 1)
    monkeypatch.setattr(module, "analyze_positions", fake_analyze_positions)
    job_id = "job-failure-1"
    module._set_deferred_analysis_job(
        job_id,
        jobId=job_id,
        status="queued",
        userId=9,
        requested=2,
        syncLimit=1,
        createdAt="2026-06-08T00:00:00Z",
    )

    module._run_deferred_positions_analysis_job(
        job_id,
        [{"symbol": "AAPL.US"}, {"symbol": "BROKEN.US"}],
        {"force_refresh": True},
        {"user_id": 9},
    )

    snapshot = module._deferred_analysis_job_snapshot(job_id)
    assert snapshot["status"] == "failed"
    assert snapshot["error"] == "chunk exploded"
    assert snapshot["result"]["success"] is False
    assert snapshot["result"]["stats"]["total"] == 2
    assert snapshot["result"]["stats"]["successful"] == 1
    assert snapshot["result"]["stats"]["failed"] == 1
    assert snapshot["result"]["data"] == [{"symbol": "AAPL.US", "finalDecision": "HOLD"}]
    assert snapshot["result"]["errors"] == [{"error": "chunk exploded"}]


def test_analysis_service_prunes_expired_terminal_deferred_jobs(monkeypatch) -> None:
    module = _load_module("analysis_service_deferred_job_ttl_test", ANALYSIS_MAIN)
    module._DEFERRED_ANALYSIS_JOBS.clear()

    monkeypatch.setattr(module, "_DEFERRED_ANALYSIS_JOB_TTL_SECONDS", 60)
    module._DEFERRED_ANALYSIS_JOBS.update({
        "old-completed": {
            "jobId": "old-completed",
            "status": "completed",
            "createdEpoch": 100.0,
            "createdAt": "2026-06-08T00:00:00Z",
        },
        "old-running": {
            "jobId": "old-running",
            "status": "running",
            "createdEpoch": 100.0,
            "createdAt": "2026-06-08T00:00:00Z",
        },
        "fresh-completed": {
            "jobId": "fresh-completed",
            "status": "completed",
            "createdEpoch": 170.0,
            "createdAt": "2026-06-08T00:01:00Z",
        },
    })

    with module._DEFERRED_ANALYSIS_JOB_LOCK:
        module._prune_deferred_analysis_jobs_locked(now=200.0)

    assert "old-completed" not in module._DEFERRED_ANALYSIS_JOBS
    assert "old-running" in module._DEFERRED_ANALYSIS_JOBS
    assert "fresh-completed" in module._DEFERRED_ANALYSIS_JOBS


def test_analysis_service_prunes_deferred_job_overflow_terminal_first(monkeypatch) -> None:
    module = _load_module("analysis_service_deferred_job_overflow_test", ANALYSIS_MAIN)
    module._DEFERRED_ANALYSIS_JOBS.clear()

    monkeypatch.setattr(module, "_DEFERRED_ANALYSIS_JOB_MAX_JOBS", 2)
    monkeypatch.setattr(module, "_DEFERRED_ANALYSIS_JOB_TTL_SECONDS", 10_000)
    module._DEFERRED_ANALYSIS_JOBS.update({
        "terminal-old": {"jobId": "terminal-old", "status": "completed", "createdEpoch": 100.0},
        "terminal-fresh": {"jobId": "terminal-fresh", "status": "failed", "createdEpoch": 200.0},
        "active-old": {"jobId": "active-old", "status": "running", "createdEpoch": 50.0},
    })

    with module._DEFERRED_ANALYSIS_JOB_LOCK:
        module._prune_deferred_analysis_jobs_locked(now=250.0)

    assert "terminal-old" not in module._DEFERRED_ANALYSIS_JOBS
    assert "terminal-fresh" in module._DEFERRED_ANALYSIS_JOBS
    assert "active-old" in module._DEFERRED_ANALYSIS_JOBS


def test_analysis_service_deferred_job_runtime_reports_stranded_active_jobs(monkeypatch) -> None:
    module = _load_module("analysis_service_deferred_job_runtime_test", ANALYSIS_MAIN)
    module._DEFERRED_ANALYSIS_JOBS.clear()

    monkeypatch.setattr(module, "_DEFERRED_ANALYSIS_JOB_STRANDED_SECONDS", 60)
    monkeypatch.setattr(module.time, "time", lambda: 200.0)
    module._DEFERRED_ANALYSIS_JOBS.update({
        "running-old": {"jobId": "running-old", "status": "running", "createdEpoch": 100.0},
        "completed-old": {"jobId": "completed-old", "status": "completed", "createdEpoch": 100.0},
    })

    runtime = module._deferred_analysis_job_runtime()

    assert runtime["status"] == "degraded"
    assert runtime["activeCount"] == 1
    assert runtime["oldestActiveAgeSeconds"] == 100.0
    assert "stranded threshold" in runtime["detail"]


def test_analysis_service_deferred_job_runtime_is_healthy_without_active_backlog(monkeypatch) -> None:
    module = _load_module("analysis_service_deferred_job_runtime_healthy_test", ANALYSIS_MAIN)
    module._DEFERRED_ANALYSIS_JOBS.clear()
    monkeypatch.setattr(module.redis_client, "ping", lambda: False)

    runtime = module._deferred_analysis_job_runtime()

    assert runtime["status"] == "healthy"
    assert runtime["activeCount"] == 0
    assert runtime["oldestActiveAgeSeconds"] == 0.0
    assert runtime["storage"] == "memory"
    assert "410 expired" in runtime["restartBehavior"]


def test_analysis_service_deferred_job_runtime_reports_redis_snapshot_storage(monkeypatch) -> None:
    module = _load_module("analysis_service_deferred_job_runtime_redis_storage_test", ANALYSIS_MAIN)
    module._DEFERRED_ANALYSIS_JOBS.clear()
    monkeypatch.setattr(module.redis_client, "ping", lambda: True)

    runtime = module._deferred_analysis_job_runtime()

    assert runtime["storage"] == "memory+redis_snapshot"
    assert "terminal snapshots may be read from redis" in runtime["restartBehavior"]


def test_analysis_service_sync_limit_is_env_configurable(monkeypatch) -> None:
    monkeypatch.setenv("REF_ANALYSIS_SYNC_POSITIONS_LIMIT", "2")
    module = _load_module("analysis_service_sync_limit_env_test", ANALYSIS_MAIN)

    _, meta = module._normalize_position_batch_payload([
        {"symbol": "AAPL.US"},
        {"symbol": "MSFT.US"},
        {"symbol": "NVDA.US"},
    ])

    assert module.SYNC_ANALYZE_POSITIONS_LIMIT == 2
    assert meta["accepted"] == 2
    assert meta["deferred"] == 1
    assert meta["syncLimit"] == 2


def test_legacy_batch_sync_limit_is_env_configurable(monkeypatch) -> None:
    monkeypatch.setenv("REF_ANALYSIS_SYNC_POSITIONS_LIMIT", "3")
    module = _load_module("legacy_ai_routes_sync_limit_env_test", AI_ROUTES)

    _, meta = module._normalize_position_batch_payload([
        {"symbol": "AAPL.US"},
        {"symbol": "MSFT.US"},
        {"symbol": "NVDA.US"},
        {"symbol": "TSLA.US"},
    ])

    assert module.SYNC_BATCH_ANALYZE_LIMIT == 3
    assert meta["accepted"] == 3
    assert meta["deferred"] == 1
    assert meta["syncLimit"] == 3


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


def test_analysis_service_analyze_positions_avoids_bulk_broker_quotes_by_default(monkeypatch) -> None:
    module = _load_module("analysis_service_no_default_bulk_broker_quotes_test", ANALYSIS_MAIN)

    monkeypatch.setattr(module, "_resolve_analysis_account_id", lambda user_id, account_id: 1)
    monkeypatch.setattr(module.AIAnalyst, "get_task_model_plan", classmethod(lambda cls, user_id=1: {"task": "scan"}))
    monkeypatch.setattr(
        module,
        "get_quotes_from_broker",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("default analyze_positions must not call bulk broker quotes")),
    )
    monkeypatch.setattr(
        module,
        "get_quote_from_broker",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("default analyze_positions must not call single broker quote")),
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
            "price": kwargs["current_price"],
            "finalDecision": "HOLD",
        },
    )
    monkeypatch.setattr(module, "detect_market", lambda symbol: "US")
    monkeypatch.setattr(module.AICache, "cache_analysis", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "get_persistence_manager", lambda: type("P", (), {"save_ai_analysis": lambda self, item: None})())

    payload = asyncio.run(
        module.analyze_positions(
            payload={
                "positions": [{"symbol": "AAPL.US", "current_price": 185.25, "volume": 1234}],
                "force_refresh": True,
            },
            session={"user_id": 9},
        )
    )

    assert payload["success"] is True
    assert payload["data"][0]["price"] == 185.25
    assert payload["stats"]["accepted"] == 1


def test_analysis_service_uses_position_quote_before_single_quote_retry(monkeypatch) -> None:
    module = _load_module("analysis_service_position_quote_fallback_test", ANALYSIS_MAIN)

    monkeypatch.setattr(module, "_resolve_analysis_account_id", lambda user_id, account_id: 1)
    monkeypatch.setattr(module.AIAnalyst, "get_task_model_plan", classmethod(lambda cls, user_id=1: {"task": "scan"}))
    monkeypatch.setattr(module, "get_quotes_from_broker", lambda symbols, account_id=None, user_id=None: {})
    monkeypatch.setattr(
        module,
        "get_quote_from_broker",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("position price should avoid single quote retry")),
    )
    monkeypatch.setattr(module, "build_market_snapshot", lambda account_id, symbol, user_id=None: {"market": "US"})
    monkeypatch.setattr(
        module,
        "build_real_indicator_context",
        lambda symbol, current_price, volume, user_id=1: ({"price": current_price, "volume": volume}, {"price": current_price}),
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
            "price": kwargs["current_price"],
            "volume": kwargs["volume"],
            "finalDecision": "HOLD",
        },
    )
    monkeypatch.setattr(module, "detect_market", lambda symbol: "US")
    monkeypatch.setattr(module.AICache, "cache_analysis", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "get_persistence_manager", lambda: type("P", (), {"save_ai_analysis": lambda self, item: None})())

    payload = asyncio.run(
        module.analyze_positions(
            payload={
                "positions": [
                    {
                        "symbol": "NVDL.US",
                        "currentPrice": 42.5,
                        "volume": 1200,
                        "changePercent": 1.5,
                    }
                ],
                "force_refresh": True,
            },
            session={"user_id": 9},
        )
    )

    assert payload["success"] is True
    assert payload["data"][0]["symbol"] == "NVDL.US"
    assert payload["data"][0]["price"] == 42.5
    assert payload["stats"]["accepted"] == 1


def test_analysis_service_derives_position_quote_from_market_value(monkeypatch) -> None:
    module = _load_module("analysis_service_position_market_value_fallback_test", ANALYSIS_MAIN)

    monkeypatch.setattr(module, "_resolve_analysis_account_id", lambda user_id, account_id: 1)
    monkeypatch.setattr(module.AIAnalyst, "get_task_model_plan", classmethod(lambda cls, user_id=1: {"task": "scan"}))
    monkeypatch.setattr(module, "get_quotes_from_broker", lambda symbols, account_id=None, user_id=None: {})
    monkeypatch.setattr(
        module,
        "get_quote_from_broker",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("market value fallback should avoid single quote retry")),
    )
    monkeypatch.setattr(module, "build_market_snapshot", lambda account_id, symbol, user_id=None: {"market": "US"})
    monkeypatch.setattr(
        module,
        "build_real_indicator_context",
        lambda symbol, current_price, volume, user_id=1: ({"price": current_price, "volume": volume}, {"price": current_price}),
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
            "price": kwargs["current_price"],
            "finalDecision": "HOLD",
        },
    )
    monkeypatch.setattr(module, "detect_market", lambda symbol: "US")
    monkeypatch.setattr(module.AICache, "cache_analysis", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "get_persistence_manager", lambda: type("P", (), {"save_ai_analysis": lambda self, item: None})())

    payload = asyncio.run(
        module.analyze_positions(
            payload={
                "positions": [
                    {
                        "symbol": "NVDL.US",
                        "current_price": 0,
                        "market_value": 425,
                        "quantity": 10,
                    }
                ],
                "force_refresh": True,
            },
            session={"user_id": 9},
        )
    )

    assert payload["success"] is True
    assert payload["data"][0]["price"] == 42.5
    assert payload["stats"]["accepted"] == 1


def test_analysis_service_uses_trend_scan_quote_before_single_retry(monkeypatch) -> None:
    module = _load_module("analysis_service_trend_scan_quote_fallback_test", ANALYSIS_MAIN)

    monkeypatch.setattr(module, "_resolve_analysis_account_id", lambda user_id, account_id: 1)
    monkeypatch.setattr(module.AIAnalyst, "get_task_model_plan", classmethod(lambda cls, user_id=1: {"task": "scan"}))
    monkeypatch.setattr(module, "get_quotes_from_broker", lambda symbols, account_id=None, user_id=None: {})
    monkeypatch.setattr(
        module.DailySymbolTrendScanService,
        "get_latest_for_symbol",
        lambda symbol: {
            "symbol": symbol,
            "indicators": {
                "latestClose": 33.3,
                "dayChangePercent": 1.2,
                "avgVolume20": 8800,
            },
        },
    )
    monkeypatch.setattr(
        module,
        "get_quote_from_broker",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("trend scan quote should avoid single quote retry")),
    )
    monkeypatch.setattr(module, "build_market_snapshot", lambda account_id, symbol, user_id=None: {"market": "US"})
    monkeypatch.setattr(
        module,
        "build_real_indicator_context",
        lambda symbol, current_price, volume, user_id=1: ({"price": current_price, "volume": volume}, {"price": current_price}),
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
            "price": kwargs["current_price"],
            "volume": kwargs["volume"],
            "finalDecision": "HOLD",
        },
    )
    monkeypatch.setattr(module, "detect_market", lambda symbol: "US")
    monkeypatch.setattr(module.AICache, "cache_analysis", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "get_persistence_manager", lambda: type("P", (), {"save_ai_analysis": lambda self, item: None})())

    payload = asyncio.run(
        module.analyze_positions(
            payload={
                "positions": [{"symbol": "NVDL.US", "current_price": 0}],
                "force_refresh": True,
            },
            session={"user_id": 9},
        )
    )

    assert payload["success"] is True
    assert payload["data"][0]["price"] == 33.3
    assert payload["data"][0]["volume"] == 8800
    assert payload["stats"]["accepted"] == 1


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
