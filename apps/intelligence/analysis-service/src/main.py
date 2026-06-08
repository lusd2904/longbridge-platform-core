from __future__ import annotations

import importlib.util
import inspect
import asyncio
import hashlib
import json
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from fastapi import Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse


REFACTOR_ROOT = Path(__file__).resolve().parents[4]
if str(REFACTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(REFACTOR_ROOT))

from apps.intelligence.module_shared import (
    AIAnalysisHistory,
    AICache,
    AIAnalyst,
    AiConsultant,
    DailySymbolTrendScanService,
    FinanceBriefingService,
    HistoricalMarketDataService,
    QuantTradingService,
    RecommendationService,
    bootstrap_runtime,
    build_dependency_status,
    build_health_payload,
    build_market_snapshot,
    build_real_indicator_context,
    create_service_app,
    detect_market,
    extract_position_quote_fallback,
    get_current_session,
    get_persistence_manager,
    get_quote_from_broker,
    get_quotes_from_broker,
    legacy_boundary_status,
    redis_client,
    service_port,
    summarize_status,
    DbUtil,
)

bootstrap_runtime()


app = create_service_app(
    title="Refactor V2 Analysis Service",
    version="0.2.0",
    description="Phase 1 live service for AI model plans, trend scans and recommendation datasets.",
)
PORT = service_port("REF_ANALYSIS_SERVICE_PORT", 8103)


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


SYNC_ANALYZE_POSITIONS_LIMIT = _env_int("REF_ANALYSIS_SYNC_POSITIONS_LIMIT", 12)
AGNO_SIDECAR_BASE_URL = (
    str(os.getenv("REF_AGNO_SIDECAR_URL") or "http://127.0.0.1:3200").strip().rstrip("/")
)
WATCHLIST_REVIEW_IDEMPOTENCY_WINDOW_SECONDS = max(
    60,
    int(os.getenv("REF_WATCHLIST_REVIEW_IDEMPOTENCY_WINDOW_SECONDS", "900") or 900),
)
AGENT_RUN_STRANDED_MAX_AGE_MINUTES = max(
    5,
    int(os.getenv("REF_AGENT_RUN_STRANDED_MAX_AGE_MINUTES", "60") or 60),
)
_AGENT_RUN_SERVICE_FILE = REFACTOR_ROOT / "backend-server" / "src" / "core" / "analysis" / "AgentRunService.py"
_AGENT_RUN_SERVICE_CLASS = None
_AGENT_RUN_SERVICE_LOADED = False
_AGENT_RUN_DB_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled"}
_AGENT_RUN_OVERRIDE_ACTIONS = {"acknowledged", "needs_review", "dismissed"}
_AGENT_RUN_OVERRIDE_STATUS_OPTIONS = {
    "acknowledged": {"succeeded"},
    "needs_review": {"failed"},
    "dismissed": {"cancelled"},
}
_DEFERRED_ANALYSIS_JOBS: Dict[str, Dict[str, Any]] = {}
_DEFERRED_ANALYSIS_JOB_LOCK = threading.Lock()
_DEFERRED_ANALYSIS_JOB_MAX_RESULTS = 300
_DEFERRED_ANALYSIS_JOB_TTL_SECONDS = _env_int("REF_ANALYSIS_DEFERRED_JOB_TTL_SECONDS", 3600, minimum=60)
_DEFERRED_ANALYSIS_JOB_MAX_JOBS = _env_int("REF_ANALYSIS_DEFERRED_JOB_MAX_JOBS", 200, minimum=10)
_DEFERRED_ANALYSIS_JOB_STRANDED_SECONDS = _env_int("REF_ANALYSIS_DEFERRED_JOB_STRANDED_SECONDS", 1800, minimum=60)
_DEFERRED_ANALYSIS_JOB_REDIS_PREFIX = "analysis:deferred-job:"
_DEFERRED_ANALYSIS_JOB_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
_ASSISTANT_QUESTION_MAX_CHARS = 2400
_ASSISTANT_CONTEXT_MAX_CHARS = 900
_ASSISTANT_HISTORY_MAX_ITEMS = 6
_ASSISTANT_HISTORY_MAX_CHARS = 900


def _utc_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _clip_assistant_text(value: object, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _count_cjk_chars(value: str) -> int:
    return sum(1 for char in str(value or "") if "\u4e00" <= char <= "\u9fff")


def _repair_assistant_mojibake(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        repaired = text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    if _count_cjk_chars(repaired) > max(_count_cjk_chars(text), 0) + 2:
        return repaired.strip()
    return text


def _normalize_assistant_context(raw_context: object) -> Dict[str, str]:
    context = raw_context if isinstance(raw_context, dict) else {}
    safe_query = context.get("query") if isinstance(context.get("query"), dict) else {}
    return {
        "path": _clip_assistant_text(context.get("path"), 180),
        "name": _clip_assistant_text(context.get("name"), 120),
        "title": _clip_assistant_text(context.get("title"), 120),
        "subsystem": _clip_assistant_text(context.get("subsystem"), 80),
        "query": _clip_assistant_text(json.dumps(safe_query, ensure_ascii=False, default=str), 240),
    }


def _normalize_assistant_messages(raw_messages: object) -> List[Dict[str, str]]:
    messages = raw_messages if isinstance(raw_messages, list) else []
    normalized: List[Dict[str, str]] = []
    for item in messages[-_ASSISTANT_HISTORY_MAX_ITEMS:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = _clip_assistant_text(item.get("content"), _ASSISTANT_HISTORY_MAX_CHARS)
        if not content:
            continue
        normalized.append({"role": role, "content": content})
    return normalized


def _build_assistant_consult_prompt(
    *,
    question: str,
    page_context: Dict[str, str],
    messages: List[Dict[str, str]],
) -> str:
    history_text = "\n".join(
        f"{'用户' if item['role'] == 'user' else '助手'}: {item['content']}"
        for item in messages
    ) or "无"
    context_text = json.dumps(page_context, ensure_ascii=False, sort_keys=True)
    return (
        "你是量化交易平台的系统级 AI 咨询助手。"
        "请基于当前页面上下文和最近对话，用中文给出简洁、可执行、可复核的回答。\n"
        "边界要求：只做只读咨询、解释、排查和分析建议；不得声称已经下单、撤单、改单或修改平台配置；"
        "涉及交易时必须提示用户自行复核风险和账户状态。\n"
        f"当前页面上下文: {_clip_assistant_text(context_text, _ASSISTANT_CONTEXT_MAX_CHARS)}\n"
        f"最近对话:\n{history_text}\n"
        f"用户问题:\n{question}\n"
        "回答格式：先直接回答，再给必要的检查点。"
    )


def _utc_iso_from_epoch(epoch_seconds: float) -> str:
    return datetime.utcfromtimestamp(epoch_seconds).isoformat(timespec="seconds") + "Z"


def _normalize_position_batch_payload(raw_positions: object, sync_limit: int = SYNC_ANALYZE_POSITIONS_LIMIT) -> Tuple[List[dict], Dict[str, int | bool]]:
    positions = raw_positions if isinstance(raw_positions, list) else []
    safe_limit = max(1, int(sync_limit or 1))
    accepted = [item for item in positions[:safe_limit] if isinstance(item, dict)]
    requested = len(positions)
    deferred = max(requested - len(accepted), 0)
    return accepted, {
        "requested": requested,
        "accepted": len(accepted),
        "deferred": deferred,
        "syncLimit": safe_limit,
        "partial": deferred > 0,
    }


def _build_deferred_analysis_placeholders(
    raw_positions: object,
    *,
    model_plan: Dict[str, Any],
    sync_limit: int = SYNC_ANALYZE_POSITIONS_LIMIT,
) -> List[Dict[str, Any]]:
    positions = raw_positions if isinstance(raw_positions, list) else []
    placeholders: List[Dict[str, Any]] = []
    for item in positions:
        if not isinstance(item, dict):
            continue
        raw_symbol = str(item.get("symbol") or "").strip()
        if not raw_symbol:
            continue
        symbol = HistoricalMarketDataService.normalize_symbol(raw_symbol)
        placeholders.append(
            {
                "symbol": symbol,
                "name": item.get("name") or item.get("symbol_name") or symbol,
                "queued": True,
                "deferred": True,
                "reason": f"批量分析超过同步上限 {sync_limit}，已降级为异步/延后处理",
                "modelPlan": model_plan,
                "scanLayers": [],
                "source": "manual_scan",
                "analysisMode": "manual_deferred_scan",
                "finalSignal": "warning",
                "finalDecision": "排队中",
            }
        )
    return placeholders


def _deferred_analysis_job_redis_key(job_id: str) -> str:
    return f"{_DEFERRED_ANALYSIS_JOB_REDIS_PREFIX}{job_id}"


def _deferred_analysis_job_storage_mode() -> str:
    try:
        return "memory+redis_snapshot" if bool(redis_client.ping()) else "memory"
    except Exception:
        return "memory"


def _persist_deferred_analysis_job_snapshot(job: Dict[str, Any]) -> None:
    job_id = str(job.get("jobId") or "").strip()
    if not job_id:
        return
    try:
        redis_client.set(
            _deferred_analysis_job_redis_key(job_id),
            dict(job),
            expire=max(int(job.get("ttlSeconds") or _DEFERRED_ANALYSIS_JOB_TTL_SECONDS), 60),
        )
    except Exception:
        pass


def _load_deferred_analysis_job_snapshot_from_redis(job_id: str) -> Optional[Dict[str, Any]]:
    try:
        payload = redis_client.get_json(_deferred_analysis_job_redis_key(job_id))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _delete_deferred_analysis_job_snapshot_from_redis(job_id: str) -> None:
    try:
        redis_client.delete(_deferred_analysis_job_redis_key(job_id))
    except Exception:
        pass


def _deferred_analysis_job_snapshot(job_id: str) -> Optional[Dict[str, Any]]:
    with _DEFERRED_ANALYSIS_JOB_LOCK:
        _prune_deferred_analysis_jobs_locked()
        job = _DEFERRED_ANALYSIS_JOBS.get(job_id)
        if job:
            return dict(job)

    redis_job = _load_deferred_analysis_job_snapshot_from_redis(job_id)
    if not redis_job:
        return None
    if str(redis_job.get("status") or "").lower() in _DEFERRED_ANALYSIS_JOB_TERMINAL_STATUSES:
        return dict(redis_job)
    return None


def _deferred_job_epoch(job: Dict[str, Any]) -> float:
    raw_epoch = job.get("createdEpoch")
    try:
        epoch = float(raw_epoch)
        if epoch > 0:
            return epoch
    except (TypeError, ValueError):
        pass

    raw_created = str(job.get("createdAt") or "").strip()
    if raw_created:
        try:
            return datetime.fromisoformat(raw_created.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _prune_deferred_analysis_jobs_locked(now: Optional[float] = None) -> None:
    current_time = float(now if now is not None else time.time())
    expired_job_ids = [
        job_id
        for job_id, job in _DEFERRED_ANALYSIS_JOBS.items()
        if str(job.get("status") or "").lower() in _DEFERRED_ANALYSIS_JOB_TERMINAL_STATUSES
        and _deferred_job_epoch(job)
        and current_time - _deferred_job_epoch(job) > _DEFERRED_ANALYSIS_JOB_TTL_SECONDS
    ]
    for job_id in expired_job_ids:
        _DEFERRED_ANALYSIS_JOBS.pop(job_id, None)
        _delete_deferred_analysis_job_snapshot_from_redis(job_id)

    overflow = len(_DEFERRED_ANALYSIS_JOBS) - _DEFERRED_ANALYSIS_JOB_MAX_JOBS
    if overflow <= 0:
        return

    def sort_key(item: Tuple[str, Dict[str, Any]]) -> Tuple[int, float]:
        _, job = item
        is_active = str(job.get("status") or "").lower() not in _DEFERRED_ANALYSIS_JOB_TERMINAL_STATUSES
        return (1 if is_active else 0, _deferred_job_epoch(job))

    for job_id, _job in sorted(_DEFERRED_ANALYSIS_JOBS.items(), key=sort_key)[:overflow]:
        _DEFERRED_ANALYSIS_JOBS.pop(job_id, None)
        _delete_deferred_analysis_job_snapshot_from_redis(job_id)


def _set_deferred_analysis_job(job_id: str, **updates: Any) -> Dict[str, Any]:
    with _DEFERRED_ANALYSIS_JOB_LOCK:
        _prune_deferred_analysis_jobs_locked()
        current = dict(_DEFERRED_ANALYSIS_JOBS.get(job_id) or {})
        current.update(updates)
        current["updatedAt"] = _utc_iso()
        current.setdefault("createdEpoch", time.time())
        current.setdefault("jobId", job_id)
        current.setdefault("ttlSeconds", _DEFERRED_ANALYSIS_JOB_TTL_SECONDS)
        _DEFERRED_ANALYSIS_JOBS[job_id] = current
        snapshot = dict(current)
    _persist_deferred_analysis_job_snapshot(snapshot)
    return snapshot


def _deferred_analysis_job_runtime() -> Dict[str, Any]:
    with _DEFERRED_ANALYSIS_JOB_LOCK:
        _prune_deferred_analysis_jobs_locked()
        now = time.time()
        status_counts: Dict[str, int] = {}
        active_ages: List[float] = []
        for job in _DEFERRED_ANALYSIS_JOBS.values():
            status = str(job.get("status") or "unknown").lower()
            status_counts[status] = status_counts.get(status, 0) + 1
            if status in {"queued", "running"}:
                epoch = _deferred_job_epoch(job)
                if epoch:
                    active_ages.append(max(0.0, now - epoch))

    active_count = int(status_counts.get("queued", 0) + status_counts.get("running", 0))
    oldest_active_age = round(max(active_ages or [0.0]), 3)
    degraded_reasons: List[str] = []
    if active_count >= _DEFERRED_ANALYSIS_JOB_MAX_JOBS:
        degraded_reasons.append("active job count reached capacity")
    if oldest_active_age > _DEFERRED_ANALYSIS_JOB_STRANDED_SECONDS:
        degraded_reasons.append("oldest active job exceeded stranded threshold")

    return {
        "status": "degraded" if degraded_reasons else "healthy",
        "detail": ", ".join(degraded_reasons) or "deferred analysis jobs within healthy bounds",
        "statusCounts": status_counts,
        "activeCount": active_count,
        "oldestActiveAgeSeconds": oldest_active_age,
        "strandedThresholdSeconds": _DEFERRED_ANALYSIS_JOB_STRANDED_SECONDS,
        "maxJobs": _DEFERRED_ANALYSIS_JOB_MAX_JOBS,
        "storage": _deferred_analysis_job_storage_mode(),
        "restartBehavior": (
            "terminal snapshots may be read from redis until TTL; "
            "queued/running jobs missing from memory return 410 expired and must be resubmitted"
        ),
    }


def _json_response_payload(response: Any) -> Dict[str, Any]:
    if isinstance(response, JSONResponse):
        return json.loads(response.body.decode("utf-8"))
    return response if isinstance(response, dict) else {}


def _position_chunks(positions: List[dict], chunk_size: int) -> List[List[dict]]:
    safe_chunk_size = max(1, int(chunk_size or 1))
    return [positions[index:index + safe_chunk_size] for index in range(0, len(positions), safe_chunk_size)]


def _run_deferred_positions_analysis_job(
    job_id: str,
    positions: List[dict],
    base_payload: Dict[str, Any],
    session: Dict[str, Any],
) -> None:
    _set_deferred_analysis_job(job_id, status="running", startedAt=_utc_iso())
    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    market_summary = None
    try:
        chunks = _position_chunks(positions, SYNC_ANALYZE_POSITIONS_LIMIT)
        for index, chunk in enumerate(chunks):
            _set_deferred_analysis_job(
                job_id,
                progress={"chunk": index + 1, "chunks": len(chunks), "completed": len(results)},
            )
            chunk_payload = dict(base_payload)
            chunk_payload["positions"] = chunk
            response_payload = _json_response_payload(
                asyncio.run(analyze_positions(payload=chunk_payload, session=session))
            )
            chunk_results = response_payload.get("data") or []
            if isinstance(chunk_results, list):
                results.extend([item for item in chunk_results if isinstance(item, dict)])
            if response_payload.get("marketSummary"):
                market_summary = response_payload.get("marketSummary")
            for item in chunk_results if isinstance(chunk_results, list) else []:
                if isinstance(item, dict) and item.get("error"):
                    errors.append({"symbol": item.get("symbol"), "error": item.get("error")})

        result_payload = {
            "success": True,
            "data": results[:_DEFERRED_ANALYSIS_JOB_MAX_RESULTS],
            "marketSummary": market_summary,
            "message": f"后台持仓分析完成：{len(results)} / {len(positions)}",
            "stats": {
                "total": len(positions),
                "accepted": len(positions),
                "successful": len(results) - len(errors),
                "failed": len(errors),
                "deferred": 0,
            },
            "errors": errors,
        }
        _set_deferred_analysis_job(
            job_id,
            status="completed",
            completedAt=_utc_iso(),
            progress={"chunk": len(chunks), "chunks": len(chunks), "completed": len(results)},
            result=result_payload,
        )
    except Exception as exc:  # noqa: BLE001
        _set_deferred_analysis_job(
            job_id,
            status="failed",
            completedAt=_utc_iso(),
            error=str(exc),
            result={
                "success": False,
                "data": results[:_DEFERRED_ANALYSIS_JOB_MAX_RESULTS],
                "marketSummary": market_summary,
                "message": "后台持仓分析失败",
                "stats": {
                    "total": len(positions),
                    "accepted": len(positions),
                    "successful": len(results) - len(errors),
                    "failed": len(errors) + 1,
                    "deferred": 0,
                },
                "errors": [*errors, {"error": str(exc)}],
            },
        )


def _start_deferred_positions_analysis_worker(
    job_id: str,
    positions: List[dict],
    base_payload: Dict[str, Any],
    session: Dict[str, Any],
) -> None:
    worker = threading.Thread(
        target=_run_deferred_positions_analysis_job,
        args=(job_id, positions, base_payload, session),
        name=f"analysis-deferred-{job_id[:8]}",
        daemon=True,
    )
    worker.start()


def _enqueue_deferred_positions_analysis(
    *,
    positions: List[dict],
    base_payload: Dict[str, Any],
    session: Dict[str, Any],
    model_plan: Dict[str, Any],
    batch_meta: Dict[str, int | bool],
) -> Dict[str, Any]:
    job_id = uuid.uuid4().hex
    now = _utc_iso()
    job = {
        "jobId": job_id,
        "status": "queued",
        "createdAt": now,
        "createdEpoch": time.time(),
        "expiresAt": _utc_iso_from_epoch(time.time() + _DEFERRED_ANALYSIS_JOB_TTL_SECONDS),
        "ttlSeconds": _DEFERRED_ANALYSIS_JOB_TTL_SECONDS,
        "updatedAt": now,
        "requested": int(batch_meta.get("requested") or len(positions)),
        "syncLimit": int(batch_meta.get("syncLimit") or SYNC_ANALYZE_POSITIONS_LIMIT),
        "modelPlan": model_plan,
        "progress": {"chunk": 0, "chunks": len(_position_chunks(positions, SYNC_ANALYZE_POSITIONS_LIMIT)), "completed": 0},
        "userId": int(session.get("user_id") or 0),
    }
    with _DEFERRED_ANALYSIS_JOB_LOCK:
        _prune_deferred_analysis_jobs_locked()
        _DEFERRED_ANALYSIS_JOBS[job_id] = dict(job)
    _persist_deferred_analysis_job_snapshot(job)
    _start_deferred_positions_analysis_worker(
        job_id,
        list(positions),
        dict(base_payload),
        dict(session),
    )
    return dict(job)


def _normalize_watchlist_session(raw_value: object) -> str:
    normalized = str(raw_value or "").strip().lower()
    mapping = {
        "pre_open": "pre_open",
        "pre-open": "pre_open",
        "preopen": "pre_open",
        "post_close": "post_close",
        "post-close": "post_close",
        "postclose": "post_close",
    }
    if normalized in mapping:
        return mapping[normalized]
    raise HTTPException(status_code=400, detail="session 仅支持 pre_open / post_close")


def _resolve_watchlist_scene(session_name: str) -> str:
    scene_mapping = {
        "pre_open": "watchlist_pre_open_review",
        "post_close": "watchlist_post_close_review",
    }
    return scene_mapping[session_name]


def _normalize_watchlist_targets(raw_targets: object) -> List[object]:
    if raw_targets is None:
        return []
    if not isinstance(raw_targets, list):
        raise HTTPException(status_code=400, detail="targets 必须是数组")

    normalized_targets: List[object] = []
    for item in raw_targets:
        if isinstance(item, str):
            symbol = item.strip()
            if symbol:
                normalized_targets.append(symbol)
            continue
        if isinstance(item, dict):
            normalized_targets.append(dict(item))
            continue
        raise HTTPException(status_code=400, detail="targets 仅支持字符串或对象数组")
    return normalized_targets


def _load_watchlist_scan_targets(*, user_id: int, session_name: str) -> List[object]:
    session_filter = "before_open" if session_name == "pre_open" else "after_close"
    try:
        from apps.market.market_service.src.watchlist_service import WatchlistService  # type: ignore
    except Exception:
        try:
            service_path = REFACTOR_ROOT / "apps" / "market" / "market-service" / "src" / "watchlist_service.py"
            spec = importlib.util.spec_from_file_location("analysis_watchlist_service", str(service_path))
            if not spec or not spec.loader:
                return []
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            WatchlistService = getattr(module, "WatchlistService", None)
        except Exception:
            return []

    if not WatchlistService:
        return []
    try:
        payload = WatchlistService.build_scan_targets_response(
            user_id=int(user_id),
            session_filter=session_filter,
        )
        targets = payload.get("targets") if isinstance(payload, dict) else []
        return targets if isinstance(targets, list) else []
    except Exception:
        return []


def _normalize_watchlist_status(raw_status: object, *, default: str = "degraded") -> str:
    normalized = str(raw_status or "").strip().lower()
    if not normalized:
        return default
    alias_map = {
        "ok": "completed",
        "success": "completed",
        "succeeded": "completed",
        "done": "completed",
        "partial": "degraded",
        "warning": "degraded",
        "error": "failed",
    }
    return alias_map.get(normalized, normalized)


def _watchlist_db_status(status: object, *, degraded: bool = False, error: object = None) -> str:
    normalized = _normalize_watchlist_status(status, default="degraded")
    if normalized in {"completed", "succeeded", "success", "ok", "done"} and not degraded and not error:
        return "succeeded"
    if normalized in {"queued", "running", "cancelled"}:
        return normalized
    if normalized in {"failed", "error"}:
        return "failed"
    return "failed" if degraded or error else "succeeded"


def _clamp_watchlist_confidence(raw_value: object) -> float:
    if isinstance(raw_value, dict):
        level = str(raw_value.get("level") or raw_value.get("label") or "").strip().lower()
        if any(token in level for token in ("高", "high")):
            return 80.0
        if any(token in level for token in ("中", "medium")):
            return 55.0
        if any(token in level for token in ("低", "low")):
            return 30.0
        raw_value = raw_value.get("value") or raw_value.get("score") or raw_value.get("confidence")
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(value, 100.0))


def _sanitize_watchlist_payload(value: object) -> object:
    forbidden_tokens = ("order", "trade", "action")
    if isinstance(value, dict):
        sanitized: Dict[str, object] = {}
        for raw_key, raw_item in value.items():
            key = str(raw_key)
            normalized_key = key.lower().replace("_", "")
            if any(token in normalized_key for token in forbidden_tokens):
                continue
            sanitized[key] = _sanitize_watchlist_payload(raw_item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_watchlist_payload(item) for item in value]
    return value


def _coerce_watchlist_list(raw_value: object) -> List[object]:
    if isinstance(raw_value, dict):
        sanitized = _sanitize_watchlist_payload(raw_value)
        return [sanitized] if isinstance(sanitized, dict) and sanitized else []
    if not isinstance(raw_value, list):
        return []
    return [item for item in _sanitize_watchlist_payload(raw_value) if item not in (None, "")]


def _coerce_watchlist_error(raw_error: object) -> Optional[dict]:
    if raw_error in (None, "", {}):
        return None
    if isinstance(raw_error, dict):
        sanitized = _sanitize_watchlist_payload(raw_error)
        return sanitized if isinstance(sanitized, dict) else {"message": str(raw_error)}
    return {"message": str(raw_error)}


def _build_watchlist_review_result(
    *,
    run_id: str,
    scene: str,
    status: str,
    summary: str,
    signals: object = None,
    risk_flags: object = None,
    review_advice: object = None,
    evidence: object = None,
    confidence: object = 0,
    source: str = "agno-sidecar",
    degraded: bool = False,
    error: object = None,
) -> dict:
    normalized_status = _normalize_watchlist_status(status, default="failed")
    normalized_error = _coerce_watchlist_error(error)
    normalized_degraded = bool(degraded or normalized_status == "degraded" or normalized_error)
    return {
        "runId": str(run_id),
        "scene": scene,
        "status": normalized_status,
        "summary": str(summary or "").strip(),
        "signals": _coerce_watchlist_list(signals),
        "riskFlags": _coerce_watchlist_list(risk_flags),
        "reviewAdvice": _coerce_watchlist_list(review_advice),
        "evidence": _coerce_watchlist_list(evidence),
        "confidence": _clamp_watchlist_confidence(confidence),
        "source": str(source or "agno-sidecar"),
        "degraded": normalized_degraded,
        "error": normalized_error,
    }


def _extract_json_object_from_text(text: object) -> Optional[dict]:
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw).strip()
    candidates = [raw]
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _normalize_watchlist_sidecar_result(raw_payload: object, *, run_id: str, scene: str) -> dict:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    content_payload = _extract_json_object_from_text(payload.get("content") or data.get("content"))
    if content_payload:
        data = {**data, **content_payload}
    explicit_status = data.get("status", payload.get("status"))
    if explicit_status is None and payload.get("success") is True:
        explicit_status = "completed"
    if explicit_status is None and payload.get("success") is False:
        explicit_status = "failed"
    if explicit_status is None and str(payload.get("status") or "").upper() == "COMPLETED":
        explicit_status = "completed"

    summary = (
        data.get("summary")
        or payload.get("summary")
        or payload.get("message")
        or data.get("message")
        or data.get("content")
        or payload.get("content")
        or ""
    )
    result_run_id = (
        data.get("runId")
        or data.get("run_id")
        or payload.get("runId")
        or payload.get("run_id")
        or run_id
    )
    result_scene = str(data.get("scene") or payload.get("scene") or scene)
    return _build_watchlist_review_result(
        run_id=str(result_run_id),
        scene=result_scene,
        status=str(explicit_status or "degraded"),
        summary=str(summary),
        signals=data.get("signals", payload.get("signals")),
        risk_flags=data.get("riskFlags", data.get("risk_flags", payload.get("riskFlags", payload.get("risk_flags")))),
        review_advice=data.get(
            "reviewAdvice",
            data.get(
                "review_advice",
                payload.get(
                    "reviewAdvice",
                    payload.get("review_advice", ["Agno 团队已完成复核；请人工确认后再处理。"]),
                ),
            ),
        ),
        evidence=data.get(
            "evidence",
            payload.get(
                "evidence",
                [
                    {
                        "type": "agno-team-run",
                        "teamId": payload.get("team_id"),
                        "teamName": payload.get("team_name"),
                        "sessionId": payload.get("session_id"),
                        "model": payload.get("model"),
                        "status": payload.get("status"),
                    }
                ],
            ),
        ),
        confidence=data.get("confidence", payload.get("confidence", 0)),
        source=str(data.get("source") or payload.get("source") or "agno-sidecar"),
        degraded=bool(data.get("degraded", payload.get("degraded", False))),
        error=data.get("error", payload.get("error")),
    )


def _safe_watchlist_float(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def _safe_watchlist_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _extract_read_model_quote_fallback(symbol: str) -> Tuple[float, int, float, float]:
    try:
        trend_scan = DailySymbolTrendScanService.get_latest_for_symbol(symbol) or {}
    except Exception:
        trend_scan = {}
    indicators = trend_scan.get("indicators") if isinstance(trend_scan, dict) else {}
    indicators = indicators if isinstance(indicators, dict) else {}
    current_price = _safe_watchlist_float(
        indicators.get("latestClose")
        or indicators.get("closePrice")
        or indicators.get("close")
        or trend_scan.get("latestClose")
        or trend_scan.get("closePrice")
    )
    volume = _safe_watchlist_int(
        indicators.get("volume")
        or indicators.get("avgVolume20")
        or trend_scan.get("volume")
        or 0
    )
    change_percent = _safe_watchlist_float(
        indicators.get("dayChangePercent")
        or indicators.get("changePercent")
        or trend_scan.get("dayChangePercent")
        or 0
    )
    prev_close = _safe_watchlist_float(
        indicators.get("prevClose")
        or indicators.get("prev_close")
        or indicators.get("previousClose")
        or 0
    )
    if prev_close <= 0 and current_price > 0 and change_percent:
        denominator = 1 + (change_percent / 100)
        if denominator:
            prev_close = current_price / denominator
    if prev_close <= 0:
        prev_close = current_price
    return current_price, volume, change_percent, prev_close


def _watchlist_text_contains_buy_signal(value: object) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return any(token in text for token in ("buy", "long", "看多", "买入", "机会", "增持", "positive", "bullish", "success"))


def _normalize_watchlist_opportunity(raw_item: object, target_map: Dict[str, dict]) -> Optional[dict]:
    if isinstance(raw_item, str):
        symbol = HistoricalMarketDataService.normalize_symbol(raw_item)
        item = {"symbol": symbol}
    elif isinstance(raw_item, dict):
        item = dict(raw_item)
        symbol = HistoricalMarketDataService.normalize_symbol(
            item.get("symbol") or item.get("ticker") or item.get("code")
        )
    else:
        return None
    if not symbol:
        return None

    target = target_map.get(symbol) or {}
    signal_text = item.get("signal") or item.get("side") or item.get("action") or item.get("decision") or item.get("recommendation")
    if signal_text and not _watchlist_text_contains_buy_signal(signal_text):
        return None
    if not signal_text and not _watchlist_text_contains_buy_signal(item.get("summary") or item.get("reason") or item.get("title")):
        return None

    price = _safe_watchlist_float(
        item.get("price")
        or item.get("lastPrice")
        or item.get("latestClose")
        or item.get("closePrice")
        or target.get("price")
        or target.get("lastPrice")
        or target.get("latestClose")
    )
    if price <= 0:
        trend_scan = DailySymbolTrendScanService.get_latest_for_symbol(symbol)
        indicators = trend_scan.get("indicators") if isinstance(trend_scan, dict) else {}
        price = _safe_watchlist_float(
            (indicators or {}).get("latestClose")
            or (indicators or {}).get("closePrice")
            or (trend_scan or {}).get("latestClose")
        )

    confidence = _safe_watchlist_int(
        item.get("confidence")
        or item.get("score")
        or item.get("weight")
        or target.get("confidence")
        or target.get("score"),
        0,
    )
    if confidence <= 1 and _safe_watchlist_float(item.get("confidence"), 0) > 0:
        confidence = int(_safe_watchlist_float(item.get("confidence"), 0) * 100)

    return {
        "symbol": symbol,
        "name": item.get("name") or target.get("name") or symbol,
        "market": item.get("market") or target.get("market") or detect_market(symbol),
        "price": price,
        "confidence": confidence,
        "reason": item.get("reason") or item.get("summary") or item.get("advice") or "自选复核识别为机会股",
        "source": item.get("source") or "watchlist-review",
    }


def _extract_watchlist_opportunities(result: dict, sidecar_payload: dict) -> List[dict]:
    targets = sidecar_payload.get("targets") if isinstance(sidecar_payload.get("targets"), list) else []
    target_map = {
        HistoricalMarketDataService.normalize_symbol(item.get("symbol") if isinstance(item, dict) else item): item
        for item in targets
        if HistoricalMarketDataService.normalize_symbol(item.get("symbol") if isinstance(item, dict) else item)
    }
    raw_candidates: List[object] = []
    for key in ("opportunities", "opportunityStocks", "buyCandidates", "signals", "reviewAdvice"):
        value = result.get(key)
        if isinstance(value, list):
            raw_candidates.extend(value)
    opportunities: List[dict] = []
    seen: set[str] = set()
    for raw_item in raw_candidates:
        item = _normalize_watchlist_opportunity(raw_item, target_map)
        if not item or item["symbol"] in seen:
            continue
        seen.add(item["symbol"])
        opportunities.append(item)
    return opportunities


def _maybe_execute_watchlist_auto_buy(result: dict, sidecar_payload: dict) -> dict:
    auto_buy = sidecar_payload.get("autoBuy") if isinstance(sidecar_payload.get("autoBuy"), dict) else {}
    enabled = str(auto_buy.get("enabled") or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}
    if not enabled or bool(sidecar_payload.get("dryRun", True)):
        result["autoTrade"] = {"enabled": enabled, "executed": False, "reason": "dry-run-or-disabled"}
        return result

    opportunities = _extract_watchlist_opportunities(result, sidecar_payload)
    if not opportunities:
        result["autoTrade"] = {"enabled": True, "executed": False, "reason": "no-opportunities", "signals": []}
        return result

    try:
        execution = QuantTradingService.execute_watchlist_opportunities(
            user_id=int(sidecar_payload.get("userId") or sidecar_payload.get("user_id") or 1),
            opportunities=opportunities,
            source=str(sidecar_payload.get("scene") or "watchlist-review"),
            max_symbols=_safe_watchlist_int(auto_buy.get("maxSymbols"), 2),
            max_amount=_safe_watchlist_float(auto_buy.get("maxAmount"), 2000),
            max_position_ratio=_safe_watchlist_float(auto_buy.get("maxPositionRatio"), 0.08),
            min_confidence=_safe_watchlist_int(auto_buy.get("minConfidence"), 72),
        )
        result["autoTrade"] = {"enabled": True, **execution}
        result["evidence"] = [
            *(_coerce_watchlist_list(result.get("evidence"))),
            {
                "type": "auto-trade",
                "submittedCount": execution.get("submittedCount"),
                "positionControl": execution.get("positionControl"),
            },
        ]
    except Exception as exc:
        result["autoTrade"] = {"enabled": True, "executed": False, "error": str(exc)[:500]}
        result["riskFlags"] = [
            *(_coerce_watchlist_list(result.get("riskFlags"))),
            {"title": "自动买入失败", "message": str(exc)[:300]},
        ]
    return result


def _decode_sidecar_error_body(exc: urllib_error.HTTPError) -> str:
    try:
        raw_body = exc.read().decode("utf-8", errors="ignore").strip()
    except Exception:
        raw_body = ""
    return raw_body[:1000] if raw_body else ""


def _post_json(url: str, payload: dict, timeout_seconds: int) -> dict:
    request = urllib_request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
        raw_body = response.read().decode("utf-8", errors="ignore").strip()
        if not raw_body:
            return {}
        return json.loads(raw_body)


def _build_agno_watchlist_message(payload: dict) -> str:
    compact_targets = payload.get("targets") if isinstance(payload.get("targets"), list) else []
    return (
        "你是股票自选池盘前/盘后复核团队。请基于输入生成结构化中文复核建议，"
        "只能给出观察、风险提示、人工复核建议，严禁输出任何下单、撤单、改单或交易执行动作。\n"
        "请尽量按 JSON 字段回答：summary, signals, riskFlags, reviewAdvice, evidence, confidence。\n"
        f"场景: {payload.get('scene')}\n"
        f"时段: {payload.get('session')}\n"
        f"触发来源: {payload.get('triggerSource')}\n"
        f"dryRun: {payload.get('dryRun')}\n"
        f"标的数量: {len(compact_targets)}\n"
        f"标的: {json.dumps(compact_targets[:30], ensure_ascii=False, default=str)}"
    )


def _post_agno_team_run(url: str, payload: dict, timeout_seconds: int) -> dict:
    form_payload = {
        "message": _build_agno_watchlist_message(payload),
        "payload": json.dumps(payload, ensure_ascii=False, default=str),
        "stream": "false",
        "monitor": "true",
        "user_id": str(payload.get("userId") or payload.get("user_id") or ""),
        "session_id": str(payload.get("runId") or ""),
    }
    request = urllib_request.Request(
        url,
        data=urllib_parse.urlencode(form_payload).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
        raw_body = response.read().decode("utf-8", errors="ignore").strip()
        if not raw_body:
            return {}
        return json.loads(raw_body)


def _call_agno_watchlist_sidecar(payload: dict) -> Tuple[Optional[dict], Optional[dict]]:
    candidate_paths = (
        "/teams/sub2api-team/runs",
        "/api/v1/agent/watchlist-review",
        "/api/v1/watchlist-review",
        "/watchlist-review",
    )
    attempted_urls: List[str] = []

    for path in candidate_paths:
        url = f"{AGNO_SIDECAR_BASE_URL}{path}"
        attempted_urls.append(url)
        try:
            if path == "/teams/sub2api-team/runs":
                return _post_agno_team_run(url, payload, timeout_seconds=150), None
            return _post_json(url, payload, timeout_seconds=12), None
        except urllib_error.HTTPError as exc:
            if exc.code == 404:
                continue
            return None, {
                "code": "sidecar_http_error",
                "message": f"Agno sidecar 请求失败: HTTP {exc.code}",
                "statusCode": int(exc.code),
                "body": _decode_sidecar_error_body(exc),
                "url": url,
            }
        except (urllib_error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return None, {
                "code": "sidecar_unavailable",
                "message": f"Agno sidecar 不可用: {exc}",
                "url": url,
            }

    return None, {
        "code": "sidecar_route_not_found",
        "message": "Agno sidecar 未暴露 watchlist review 接口",
        "attemptedUrls": attempted_urls,
    }


def _load_agent_run_service():
    global _AGENT_RUN_SERVICE_CLASS, _AGENT_RUN_SERVICE_LOADED
    if _AGENT_RUN_SERVICE_LOADED:
        return _AGENT_RUN_SERVICE_CLASS

    _AGENT_RUN_SERVICE_LOADED = True
    if not _AGENT_RUN_SERVICE_FILE.exists():
        return None

    try:
        spec = importlib.util.spec_from_file_location(
            "analysis_service_agent_run_service",
            str(_AGENT_RUN_SERVICE_FILE),
        )
        if not spec or not spec.loader:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _AGENT_RUN_SERVICE_CLASS = getattr(module, "AgentRunService", None)
    except Exception:
        _AGENT_RUN_SERVICE_CLASS = None

    return _AGENT_RUN_SERVICE_CLASS


def _call_agent_run_service(method_names: Tuple[str, ...], **kwargs) -> Optional[object]:
    service_class = _load_agent_run_service()
    if not service_class:
        return None

    candidates: List[object] = [service_class]
    try:
        candidates.append(service_class())
    except Exception:
        pass

    for candidate in candidates:
        for method_name in method_names:
            method = getattr(candidate, method_name, None)
            if not callable(method):
                continue
            try:
                signature = inspect.signature(method)
                if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
                    filtered_kwargs = dict(kwargs)
                else:
                    filtered_kwargs = {
                        key: value
                        for key, value in kwargs.items()
                        if key in signature.parameters
                    }
                return method(**filtered_kwargs)
            except Exception:
                continue
    return None


def _cleanup_stranded_agent_runs() -> int:
    cleaned = _call_agent_run_service(
        ("cancel_stale_runs",),
        max_age_minutes=AGENT_RUN_STRANDED_MAX_AGE_MINUTES,
        scene_prefix="watchlist_",
        reason={
            "code": "analysis_service_startup_cleanup",
            "message": "analysis-service restarted before queued/running Agent review finished",
        },
    )
    try:
        return int(cleaned or 0)
    except (TypeError, ValueError):
        return 0


app.add_event_handler("startup", _cleanup_stranded_agent_runs)


def _build_watchlist_idempotency_key(
    *,
    scene: str,
    user_id: int,
    trigger_source: str,
    targets: List[object],
) -> str:
    window = max(60, int(WATCHLIST_REVIEW_IDEMPOTENCY_WINDOW_SECONDS or 900))
    bucket = int(time.time() // window)
    canonical = json.dumps(
        {
            "scene": scene,
            "userId": int(user_id),
            "triggerSource": str(trigger_source or "manual").strip().lower(),
            "targets": _sanitize_watchlist_payload(targets),
            "bucket": bucket,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
    return f"watchlist:{scene}:{int(user_id)}:{bucket}:{digest}"


def _find_recent_watchlist_run_by_idempotency_key(
    *,
    scene: str,
    user_id: int,
    idempotency_key: str,
) -> Optional[dict]:
    rows = _call_agent_run_service(
        ("list_recent_runs",),
        scene=scene,
        user_id=user_id,
        limit=30,
        use_primary=True,
    )
    if not isinstance(rows, list):
        return None
    for row in rows:
        status = str(row.get("status") or "").strip().lower()
        if status in {"failed", "cancelled"}:
            continue
        input_summary = row.get("inputSummary") if isinstance(row.get("inputSummary"), dict) else {}
        if input_summary.get("idempotencyKey") == idempotency_key:
            return row
    return None


def _is_admin_session(session: dict) -> bool:
    return str(session.get("role") or "").strip().lower() == "admin"


def _coerce_agent_run_user_id(raw_value: object, *, field_name: str = "userId") -> int:
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{field_name} 必须是有效整数")


def _resolve_agent_run_scope_user_id(
    *,
    session: dict,
    requested_user_id: Optional[object] = None,
) -> int:
    session_user_id = _coerce_agent_run_user_id(session.get("user_id"), field_name="session.user_id")
    if requested_user_id in (None, ""):
        return session_user_id
    target_user_id = _coerce_agent_run_user_id(requested_user_id)
    if target_user_id != session_user_id and not _is_admin_session(session):
        raise HTTPException(status_code=403, detail="仅管理员可查询其他用户的运行记录")
    return target_user_id


def _normalize_agent_run_limit(raw_limit: int, *, default: int = 20, max_limit: int = 100) -> int:
    try:
        value = int(raw_limit or default)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, max_limit))


def _normalize_agent_run_status(raw_status: Optional[str]) -> Optional[str]:
    text = str(raw_status or "").strip().lower()
    if not text:
        return None
    if text not in _AGENT_RUN_DB_STATUSES:
        raise HTTPException(status_code=400, detail="status 仅支持 queued/running/succeeded/failed/cancelled")
    return text


def _normalize_override_action(raw_action: object) -> str:
    action = str(raw_action or "").strip().lower().replace("-", "_").replace(" ", "_")
    if action not in _AGENT_RUN_OVERRIDE_ACTIONS:
        raise HTTPException(status_code=400, detail="action 仅支持 acknowledged/needs_review/dismissed")
    return action


def _normalize_override_new_status(raw_status: object) -> Optional[str]:
    text = str(raw_status or "").strip().lower()
    if not text:
        return None
    if text not in {"succeeded", "failed", "cancelled"}:
        raise HTTPException(status_code=400, detail="newStatus 仅支持 succeeded/failed/cancelled")
    return text


def _validate_override_status_transition(action: str, new_status: Optional[str]) -> Optional[str]:
    if not new_status:
        return None
    allowed_statuses = _AGENT_RUN_OVERRIDE_STATUS_OPTIONS.get(action) or set()
    if new_status not in allowed_statuses:
        allowed_text = "/".join(sorted(allowed_statuses)) or "空"
        raise HTTPException(status_code=400, detail=f"{action} 仅支持 newStatus={allowed_text}")
    return new_status


def _load_agent_run_or_404(run_id: int) -> dict:
    run = _call_agent_run_service(("get_run", "fetch_run", "find_run"), run_id=int(run_id), use_primary=True)
    if not isinstance(run, dict) or not run:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return run


def _assert_agent_run_visible(run: dict, *, session: dict, scoped_user_id: int) -> None:
    run_user_id = _coerce_agent_run_user_id(run.get("user_id", run.get("userId")), field_name="run.user_id")
    if run_user_id != scoped_user_id:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    if run_user_id != _coerce_agent_run_user_id(session.get("user_id"), field_name="session.user_id") and not _is_admin_session(session):
        raise HTTPException(status_code=403, detail="无权访问其他用户的运行记录")


def _create_watchlist_run(
    *,
    scene: str,
    user_id: int,
    trigger_source: str,
    targets: List[object],
    request_payload: Optional[dict] = None,
) -> Optional[int]:
    return _call_agent_run_service(
        ("create_run", "record_run", "save_run", "start_run", "upsert_run"),
        scene=scene,
        trigger_source=trigger_source,
        user_id=user_id,
        status="queued",
        input_summary=request_payload or {"targetsCount": len(targets)},
    )


def _record_watchlist_step(
    *,
    db_run_id: Optional[int],
    external_run_id: str,
    scene: str,
    status: str,
    request_payload: Optional[dict] = None,
    response_payload: Optional[dict] = None,
    error: Optional[dict] = None,
) -> None:
    if db_run_id is None:
        return
    db_status = _watchlist_db_status(status, degraded=bool(response_payload and response_payload.get("degraded")), error=error)
    _call_agent_run_service(
        ("record_step", "save_step", "create_step", "append_step", "upsert_step"),
        run_id=db_run_id,
        step_name="agno_watchlist_review",
        status=db_status,
        input_summary={
            "scene": scene,
            "externalRunId": external_run_id,
            "payload": request_payload,
        },
        output_summary=response_payload,
        model_tier="sidecar-agno",
        handoff="analysis-service",
        prompt_trace_ref=f"agno:{external_run_id}",
        error_summary=error,
        started_at=datetime.now(),
        finished_at=datetime.now(),
    )


def _mark_watchlist_run_running(
    *,
    db_run_id: Optional[int],
    request_payload: Optional[dict] = None,
) -> bool:
    if db_run_id is None:
        return True
    claimed = _call_agent_run_service(
        ("claim_run",),
        run_id=db_run_id,
        input_summary=request_payload,
        started_at=datetime.now(),
    )
    if claimed is not None:
        return bool(claimed)
    _call_agent_run_service(
        ("mark_run_running", "start_run", "save_run", "upsert_run"),
        run_id=db_run_id,
        input_summary=request_payload,
        started_at=datetime.now(),
    )
    return True


def _finish_watchlist_run(
    *,
    db_run_id: Optional[int],
    status: str,
    result: Optional[dict] = None,
    error: Optional[dict] = None,
) -> None:
    if db_run_id is None:
        return
    db_status = _watchlist_db_status(status, degraded=bool(result and result.get("degraded")), error=error)
    if db_status == "succeeded":
        _call_agent_run_service(
            ("complete_run", "finish_run", "save_run", "upsert_run"),
            run_id=db_run_id,
            result_summary=result,
            trace_ref=str(result.get("runId") or "") if isinstance(result, dict) else None,
            finished_at=datetime.now(),
        )
        return
    _call_agent_run_service(
        ("fail_run", "finish_run", "save_run", "upsert_run"),
        run_id=db_run_id,
        status=db_status,
        error_summary=error or result,
        trace_ref=str(result.get("runId") or "") if isinstance(result, dict) else None,
        finished_at=datetime.now(),
    )


def _build_watchlist_review_accepted_result(
    *,
    run_id: str,
    db_run_id: Optional[int],
    scene: str,
    normalized_session: str,
    trigger_source: str,
    dry_run: bool,
    targets_count: int,
    idempotency_key: Optional[str] = None,
    deduped: bool = False,
) -> dict:
    payload = _build_watchlist_review_result(
        run_id=run_id,
        scene=scene,
        status="queued",
        summary="自选股 Agent 复核已提交，后台生成结构化信号、风险和建议；仅生成 AI 建议，不执行交易。",
        signals=[],
        risk_flags=[],
        review_advice=[
            "复核任务已进入后台队列。",
            "请在任务中心查看最新 Agent 复核结果。",
        ],
        evidence=[
            {
                "type": "agent-run-queued",
                "session": normalized_session,
                "triggerSource": trigger_source,
                "dryRun": dry_run,
                "targetsCount": targets_count,
            }
        ],
        confidence=0,
        source="analysis-service-async",
    )
    payload["accepted"] = True
    payload["async"] = True
    payload["deduped"] = bool(deduped)
    if idempotency_key:
        payload["idempotencyKey"] = idempotency_key
    if db_run_id is not None:
        payload["agentRunId"] = db_run_id
    return payload


def _build_watchlist_review_skipped_result(
    *,
    run_id: str,
    scene: str,
    normalized_session: str,
    trigger_source: str,
    dry_run: bool,
    user_id: int,
) -> dict:
    payload = _build_watchlist_review_result(
        run_id=run_id,
        scene=scene,
        status="skipped",
        summary="自选股 Agent 复核已跳过：当前时段没有开启扫描的自选标的。",
        signals=[],
        risk_flags=[],
        review_advice=[
            "先在自选股票池添加标的，并开启开盘前或收盘后扫描。",
            "本次没有调用 AI，也没有执行任何交易操作。",
        ],
        evidence=[
            {
                "type": "watchlist-review-skipped",
                "reason": "empty-watchlist",
                "session": normalized_session,
                "triggerSource": trigger_source,
                "dryRun": dry_run,
                "userId": user_id,
                "targetsCount": 0,
            }
        ],
        confidence=100,
        source="analysis-service-skip",
    )
    payload["accepted"] = False
    payload["async"] = False
    payload["skipped"] = True
    payload["reason"] = "no_targets"
    payload["targetsCount"] = 0
    return payload


def _execute_watchlist_review(
    *,
    db_run_id: Optional[int],
    run_id: str,
    scene: str,
    sidecar_payload: dict,
) -> None:
    if not _mark_watchlist_run_running(db_run_id=db_run_id, request_payload=sidecar_payload):
        return
    sidecar_response, sidecar_error = _call_agno_watchlist_sidecar(sidecar_payload)
    if sidecar_response is not None:
        result = _normalize_watchlist_sidecar_result(
            sidecar_response,
            run_id=run_id,
            scene=scene,
        )
    else:
        degraded_status = "failed" if sidecar_error and sidecar_error.get("code") == "sidecar_http_error" else "degraded"
        summary = (
            "Agno watchlist review 暂时不可用，已返回降级结果。"
            if degraded_status == "degraded"
            else "Agno watchlist review 调用失败，未生成有效结论。"
        )
        result = _build_watchlist_review_result(
            run_id=run_id,
            scene=scene,
            status=degraded_status,
            summary=summary,
            signals=[],
            risk_flags=[],
            review_advice=[
                "稍后重试 Agno sidecar。",
                "当前结果仅表示执行链路状态，不代表任何交易或操作建议。",
            ],
            evidence=[
                {
                    "type": "sidecar",
                    "baseUrl": AGNO_SIDECAR_BASE_URL,
                    "requestedSession": sidecar_payload.get("session"),
                    "triggerSource": sidecar_payload.get("triggerSource"),
                    "dryRun": sidecar_payload.get("dryRun"),
                    "targetsCount": len(sidecar_payload.get("targets") or []),
                }
            ],
            confidence=0,
            source="analysis-service-fallback",
            degraded=True,
            error=sidecar_error,
        )

    result = _maybe_execute_watchlist_auto_buy(result, sidecar_payload)

    _record_watchlist_step(
        db_run_id=db_run_id,
        external_run_id=run_id,
        scene=scene,
        status=str(result.get("status") or "degraded"),
        request_payload=sidecar_payload,
        response_payload=result,
        error=result.get("error") if isinstance(result.get("error"), dict) else None,
    )
    _finish_watchlist_run(
        db_run_id=db_run_id,
        status=str(result.get("status") or "degraded"),
        result=result,
        error=result.get("error") if isinstance(result.get("error"), dict) else None,
    )


def _start_watchlist_review_worker(
    *,
    db_run_id: Optional[int],
    run_id: str,
    scene: str,
    sidecar_payload: dict,
) -> None:
    def _worker() -> None:
        try:
            _execute_watchlist_review(
                db_run_id=db_run_id,
                run_id=run_id,
                scene=scene,
                sidecar_payload=sidecar_payload,
            )
        except Exception as exc:
            error_payload = {
                "code": "watchlist_review_worker_failed",
                "message": str(exc)[:1000],
            }
            _record_watchlist_step(
                db_run_id=db_run_id,
                external_run_id=run_id,
                scene=scene,
                status="failed",
                request_payload=sidecar_payload,
                error=error_payload,
            )
            _finish_watchlist_run(
                db_run_id=db_run_id,
                status="failed",
                error=error_payload,
            )

    thread = threading.Thread(
        target=_worker,
        name=f"watchlist-review-{db_run_id or run_id}",
        daemon=True,
    )
    thread.start()


def _parse_symbols(raw_values: Optional[List[str]], merged: Optional[str] = None) -> List[str]:
    items: List[str] = []
    for raw in raw_values or []:
        for chunk in str(raw or "").split(","):
            symbol = chunk.strip()
            if symbol and symbol not in items:
                items.append(symbol)
    if merged:
        for chunk in str(merged or "").split(","):
            symbol = chunk.strip()
            if symbol and symbol not in items:
                items.append(symbol)
    return items


def _build_trend_scan_meta(
    *,
    items: List[dict],
    symbols: List[str],
    market: Optional[str],
    limit: int,
) -> Dict[str, object]:
    snapshot_candidates = [
        str(item.get("generatedAt") or item.get("analysisDate") or "")
        for item in items
        if isinstance(item, dict)
    ]
    snapshot_at = max([value for value in snapshot_candidates if value], default=None)
    normalized_market = str(market or "").strip().upper() or None
    return {
        "readModel": "trend-scans",
        "defaultMode": "database",
        "dataSource": "snapshot",
        "snapshotAt": snapshot_at,
        "sources": {
            "scans": "daily_symbol_trend_ai_scans",
            "history": "historical_market_data",
            "indicators": "indicator_snapshots",
        },
        "count": len(items),
        "query": {
            "symbols": symbols,
            "market": normalized_market,
            "limit": int(limit),
        },
        "realtimeOverlay": [],
    }


def _build_recommendation_meta(result: Optional[dict], profile: str) -> Dict[str, object]:
    payload = result if isinstance(result, dict) else {}
    generated_at = payload.get("generated_at")
    normalized_profile = str(payload.get("profile") or profile or "growth").strip().lower() or "growth"
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    return {
        "readModel": "recommendation-batch",
        "defaultMode": "database",
        "dataSource": "snapshot",
        "snapshotAt": generated_at,
        "generatedAt": generated_at,
        "sources": {
            "runs": "recommendation_runs",
            "items": "recommendation_items",
            "quotes": "quote_snapshots",
        },
        "profile": normalized_profile,
        "count": int(payload.get("candidate_count") or len(items)),
        "realtimeOverlay": ["quote"],
    }


def _build_finance_briefing_meta(
    *,
    items: List[dict],
    market: Optional[str],
    limit: int,
) -> Dict[str, object]:
    snapshot_candidates = [
        str(item.get("generatedAt") or "")
        for item in items
        if isinstance(item, dict)
    ]
    snapshot_at = max([value for value in snapshot_candidates if value], default=None)
    normalized_market = str(market or "").strip().upper() or None
    return {
        "readModel": "finance-briefings",
        "defaultMode": "database",
        "dataSource": "snapshot",
        "snapshotAt": snapshot_at,
        "sources": {
            "briefings": "finance_briefings",
            "marketInsight": "market_insight_snapshots",
            "marketScan": "daily_market_ai_scans",
            "recommendation": "recommendation_runs / recommendation_items",
            "content": "symbol_content_cache / external_rss",
        },
        "market": normalized_market,
        "count": len(items),
        "limit": int(limit),
        "realtimeOverlay": [],
    }


def _build_trend_scan_analysis_result(scan: dict) -> dict:
    signal_map = {"up": "positive", "down": "negative", "sideways": "warning"}
    decision_map = {"up": "看多", "down": "看空", "sideways": "观望"}
    risk_label_map = {"low": "低风险", "medium": "中风险", "high": "高风险"}

    trend_direction = str(scan.get("trendDirection") or "sideways").strip().lower()
    raw_indicators = scan.get("indicators") or {}
    latest_price = float(
        raw_indicators.get("latestClose")
        or raw_indicators.get("closePrice")
        or raw_indicators.get("close")
        or 0
    )
    change_percent = float(
        raw_indicators.get("dayChangePercent")
        or raw_indicators.get("changePercent")
        or 0
    )
    prev_close = latest_price
    denominator = 1 + (change_percent / 100)
    if latest_price > 0 and denominator:
        prev_close = latest_price / denominator

    indicators = {
        **raw_indicators,
        "closePrice": latest_price,
        "close": latest_price,
        "changePercent": change_percent,
        "rsi": float(raw_indicators.get("rsi") or raw_indicators.get("rsi14") or 0),
        "trendLabel": raw_indicators.get("trendLabel") or raw_indicators.get("trendHint") or "",
        "snapshotDate": raw_indicators.get("snapshotDate") or scan.get("dataTradeDate"),
        "momentumScore": float(raw_indicators.get("momentumScore") or scan.get("technicalScore") or 0),
    }


def _resolve_analysis_account_id(user_id: int, account_id: Optional[int]) -> int:
    db = DbUtil()

    if account_id:
        row = db.fetch_one(
            """
            SELECT id
            FROM broker_accounts
            WHERE id = %s AND user_id = %s AND is_active = 1
            LIMIT 1
            """,
            (int(account_id), user_id),
        )
        if row:
            return int(row["id"])

    row = db.fetch_one(
        """
        SELECT id
        FROM broker_accounts
        WHERE user_id = %s AND is_active = 1 AND is_default = 1
        ORDER BY id ASC
        LIMIT 1
        """,
        (user_id,),
    )
    if row:
        return int(row["id"])

    row = db.fetch_one(
        """
        SELECT id
        FROM broker_accounts
        WHERE user_id = %s AND is_active = 1
        ORDER BY id ASC
        LIMIT 1
        """,
        (user_id,),
    )
    if row:
        return int(row["id"])

    row = db.fetch_one(
        """
        SELECT id
        FROM broker_accounts
        WHERE is_active = 1
        ORDER BY is_default DESC, id ASC
        LIMIT 1
        """
    )
    if row:
        return int(row["id"])

    raise HTTPException(status_code=400, detail="没有可用的交易账户")


def _build_manual_scan_result(
    *,
    symbol: str,
    position: dict,
    current_price: float,
    prev_close: float,
    change_percent: float,
    volume: int,
    indicator_payload: dict,
    market_snapshot: Optional[dict],
    model_plan: dict,
    reason: str,
    gemma_analysis: dict,
    llama_analysis: dict,
    deepseek_analysis: dict,
    verdict: str,
) -> dict:
    signal_map = {
        "BUY": "success",
        "SELL": "danger",
        "HOLD": "warning",
    }
    decision_map = {
        "BUY": "买入",
        "SELL": "卖出",
        "HOLD": "观望",
    }
    final_signal = signal_map.get(verdict, "warning")
    final_decision = decision_map.get(verdict, "观望")

    scan_layers = [
        {
            "id": "pulse",
            "name": gemma_analysis.get("role", "市场脉冲层"),
            "summary": gemma_analysis.get("summary", ""),
            "fullText": gemma_analysis.get("full_text", ""),
            "signal": signal_map.get(gemma_analysis.get("signal", verdict), final_signal),
            "decision": decision_map.get(gemma_analysis.get("signal", verdict), final_decision),
            "modelId": model_plan.get("pulse", {}).get("id"),
            "modelAlias": model_plan.get("pulse", {}).get("alias"),
            "modelLatency": model_plan.get("pulse", {}).get("latency"),
            "highlights": [
                gemma_analysis.get("trend", ""),
                gemma_analysis.get("market_link", ""),
                gemma_analysis.get("window", ""),
            ],
        },
        {
            "id": "risk",
            "name": llama_analysis.get("role", "风险筛查层"),
            "summary": llama_analysis.get("summary", ""),
            "fullText": llama_analysis.get("full_text", ""),
            "signal": signal_map.get(llama_analysis.get("signal", verdict), final_signal),
            "decision": decision_map.get(llama_analysis.get("signal", verdict), final_decision),
            "modelId": model_plan.get("risk", {}).get("id"),
            "modelAlias": model_plan.get("risk", {}).get("alias"),
            "modelLatency": model_plan.get("risk", {}).get("latency"),
            "highlights": [
                llama_analysis.get("sentiment", ""),
                llama_analysis.get("risk", ""),
                llama_analysis.get("position_advice", ""),
            ],
        },
        {
            "id": "final",
            "name": deepseek_analysis.get("role", "决策终审层"),
            "summary": deepseek_analysis.get("summary", ""),
            "fullText": deepseek_analysis.get("full_text", ""),
            "signal": final_signal,
            "decision": final_decision,
            "modelId": model_plan.get("final", {}).get("id"),
            "modelAlias": model_plan.get("final", {}).get("alias"),
            "modelLatency": model_plan.get("final", {}).get("latency"),
            "highlights": [
                deepseek_analysis.get("strategy", ""),
                deepseek_analysis.get("market_scan", ""),
                f"置信度 {deepseek_analysis.get('confidence', 0)}%",
            ],
        },
    ]

    return {
        "symbol": symbol,
        "name": position.get("name") or position.get("symbol_name") or symbol,
        "price": current_price,
        "prevClose": prev_close,
        "changePercent": change_percent,
        "volume": volume,
        "indicators": indicator_payload,
        "marketSummary": market_snapshot,
        "modelPlan": model_plan,
        "scanLayers": scan_layers,
        "gemma": gemma_analysis.get("summary", ""),
        "gemmaFullText": gemma_analysis.get("full_text", ""),
        "gemmaTrend": gemma_analysis.get("trend", ""),
        "gemmaIndicators": gemma_analysis.get("indicators", ""),
        "gemmaLevels": gemma_analysis.get("levels", ""),
        "gemmaSignal": signal_map.get(gemma_analysis.get("signal", verdict), final_signal),
        "gemmaDecision": decision_map.get(gemma_analysis.get("signal", verdict), final_decision),
        "llama": llama_analysis.get("summary", ""),
        "llamaFullText": llama_analysis.get("full_text", ""),
        "llamaSentiment": llama_analysis.get("sentiment", ""),
        "llamaFlow": llama_analysis.get("flow", ""),
        "llamaRisk": llama_analysis.get("risk", ""),
        "llamaMarket": llama_analysis.get("market_env", ""),
        "llamaSignal": signal_map.get(llama_analysis.get("signal", verdict), final_signal),
        "llamaDecision": decision_map.get(llama_analysis.get("signal", verdict), final_decision),
        "deepseek": deepseek_analysis.get("summary", ""),
        "deepseekFullText": deepseek_analysis.get("full_text", ""),
        "deepseekTrend": deepseek_analysis.get("trend", ""),
        "deepseekIndicators": deepseek_analysis.get("indicators", ""),
        "deepseekMarketScan": deepseek_analysis.get("market_scan", ""),
        "deepseekStrategy": deepseek_analysis.get("strategy", ""),
        "deepseekTarget": deepseek_analysis.get("target", ""),
        "deepseekStopLoss": deepseek_analysis.get("stop_loss", ""),
        "deepseekFundamental": deepseek_analysis.get("fundamental_score", 0),
        "deepseekTechnical": deepseek_analysis.get("technical_score", 0),
        "deepseekCapital": deepseek_analysis.get("capital_score", 0),
        "deepseekMarketScore": deepseek_analysis.get("market_score", 0),
        "deepseekConfidence": deepseek_analysis.get("confidence", 0),
        "deepseekSignal": final_signal,
        "deepseekDecision": final_decision,
        "finalSignal": final_signal,
        "finalDecision": final_decision,
        "reason": reason,
        "analysisTime": time.time(),
        "timestamp": time.time(),
        "source": "manual_scan",
        "analysisMode": "manual_live_scan",
    }

def _build_manual_scan_error_result(
    *,
    symbol: str,
    position: dict,
    model_plan: dict,
    error: str,
    reason: Optional[str] = None,
    current_price: float = 0.0,
    prev_close: float = 0.0,
    change_percent: float = 0.0,
    volume: int = 0,
    indicator_payload: Optional[dict] = None,
    market_snapshot: Optional[dict] = None,
    indicator_source: str = "",
) -> dict:
    return {
        "symbol": symbol,
        "name": position.get("name") or position.get("symbol_name") or symbol,
        "price": float(current_price or 0),
        "prevClose": float(prev_close or 0),
        "changePercent": float(change_percent or 0),
        "volume": int(volume or 0),
        "indicators": indicator_payload or {},
        "marketSummary": market_snapshot,
        "modelPlan": model_plan,
        "scanLayers": [],
        "error": str(error or "分析失败"),
        "reason": str(reason or error or "分析失败"),
        "finalSignal": "danger",
        "finalDecision": "分析失败",
        "indicatorSource": indicator_source,
        "source": "manual_scan",
        "analysisMode": "manual_live_scan",
    }


def _build_trend_scan_analysis_result(scan: dict) -> dict:
    signal_map = {"up": "positive", "down": "negative", "sideways": "warning"}
    decision_map = {"up": "看多", "down": "看空", "sideways": "观望"}
    risk_label_map = {"low": "低风险", "medium": "中风险", "high": "高风险"}

    trend_direction = str(scan.get("trendDirection") or "sideways").strip().lower()
    raw_indicators = scan.get("indicators") or {}
    latest_price = float(
        raw_indicators.get("latestClose")
        or raw_indicators.get("closePrice")
        or raw_indicators.get("close")
        or 0
    )
    change_percent = float(
        raw_indicators.get("dayChangePercent")
        or raw_indicators.get("changePercent")
        or 0
    )
    prev_close = latest_price
    denominator = 1 + (change_percent / 100)
    if latest_price > 0 and denominator:
        prev_close = latest_price / denominator

    indicators = {
        **raw_indicators,
        "closePrice": latest_price,
        "close": latest_price,
        "changePercent": change_percent,
        "rsi": float(raw_indicators.get("rsi") or raw_indicators.get("rsi14") or 0),
        "trendLabel": raw_indicators.get("trendLabel") or raw_indicators.get("trendHint") or "",
        "snapshotDate": raw_indicators.get("snapshotDate") or scan.get("dataTradeDate"),
        "momentumScore": float(raw_indicators.get("momentumScore") or scan.get("technicalScore") or 0),
    }

    risk_level = str(scan.get("riskLevel") or "medium").strip().lower()
    provider_route = (scan.get("meta") or {}).get("providerRoute")
    headline = scan.get("headline") or ""
    summary = scan.get("summary") or ""
    data_trade_date = scan.get("dataTradeDate")

    highlights = [
        f"方向 {decision_map.get(trend_direction, '观望')}",
        risk_label_map.get(risk_level, "中风险"),
        f"技术分 {float(scan.get('technicalScore') or 0):.1f}",
    ]
    if data_trade_date:
        highlights.append(f"数据截至 {data_trade_date}")

    return {
        "symbol": scan.get("symbol"),
        "market": scan.get("market"),
        "price": latest_price,
        "prevClose": round(prev_close, 4) if prev_close else latest_price,
        "changePercent": change_percent,
        "volume": int(indicators.get("volume") or 0),
        "confidence": max(0, min(float(scan.get("trendStrength") or 0), 100)),
        "technicalScore": float(scan.get("technicalScore") or 0),
        "marketScore": 0,
        "finalSignal": signal_map.get(trend_direction, "warning"),
        "finalDecision": decision_map.get(trend_direction, "观望"),
        "reason": headline or summary or "已加载历史趋势扫描结果",
        "analysisTime": scan.get("generatedAt") or scan.get("analysisDate"),
        "indicators": indicators,
        "modelPlan": {
            "trendBatch": {
                "id": scan.get("modelId"),
                "alias": scan.get("modelAlias"),
                "latency": "batch",
                "providerRoute": provider_route,
            }
        },
        "scanLayers": [
            {
                "id": "trend",
                "name": "历史趋势扫描",
                "summary": summary or headline,
                "fullText": scan.get("analysisText") or summary or headline,
                "signal": signal_map.get(trend_direction, "warning"),
                "decision": decision_map.get(trend_direction, "观望"),
                "modelId": scan.get("modelId"),
                "modelAlias": scan.get("modelAlias"),
                "modelLatency": "batch",
                "highlights": highlights,
            }
        ],
        "trendDirection": trend_direction,
        "trendStrength": float(scan.get("trendStrength") or 0),
        "riskLevel": risk_level,
        "source": "trend_scan",
        "analysisMode": "scheduled_trend",
    }


@app.get("/health")
async def health():
    mysql_ok = bool(DbUtil.query_one("SELECT 1"))
    try:
        redis_ok = bool(redis_client.client.ping())
    except Exception:
        redis_ok = False
    deferred_jobs = _deferred_analysis_job_runtime()
    deps = {
        "mysql": build_dependency_status("mysql", "healthy" if mysql_ok else "degraded", detail="分析历史与推荐读写数据库"),
        "redis": build_dependency_status("redis", "healthy" if redis_ok else "degraded", detail="AI 缓存与热点结果缓存"),
        "deferredAnalysisJobs": build_dependency_status(
            "deferredAnalysisJobs",
            deferred_jobs["status"],
            detail=deferred_jobs["detail"],
            extra={
                "statusCounts": deferred_jobs["statusCounts"],
                "activeCount": deferred_jobs["activeCount"],
                "oldestActiveAgeSeconds": deferred_jobs["oldestActiveAgeSeconds"],
                "strandedThresholdSeconds": deferred_jobs["strandedThresholdSeconds"],
                "maxJobs": deferred_jobs["maxJobs"],
                "storage": deferred_jobs["storage"],
                "restartBehavior": deferred_jobs["restartBehavior"],
            },
        ),
    }
    return build_health_payload(
        service="analysis-service",
        version=app.version,
        port=PORT,
        status=summarize_status(deps.values()),
        deps=deps,
        capabilities=["ai-analysis", "recommendations", "finance-briefings"],
        legacy_compat=legacy_boundary_status("analysis"),
    )


@app.get("/api/v1/analysis/bootstrap")
async def bootstrap_analysis(session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    return {
        "success": True,
        "data": {
            "service": "analysis-service",
            "status": "live",
            "provider": AIAnalyst._provider(user_id=user_id),
            "modelPlan": AIAnalyst.get_task_model_plan(user_id=user_id),
            "latestTrendScans": DailySymbolTrendScanService.get_latest_batch(limit=6),
            "recommendationProfiles": ["growth", "balanced", "value", "dividend"],
            "legacySources": [
                "refactor-v2/backend-server/src/api/ai_routes.py",
                "refactor-v2/backend-server/src/core/analysis/DailySymbolTrendScanService.py",
                "refactor-v2/backend-server/src/core/analysis/RecommendationService.py",
            ],
        },
    }


@app.get("/api/v1/analysis/models")
async def analysis_models(session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    return {
        "success": True,
        "data": {
            "catalog": AIAnalyst.get_model_catalog(user_id=user_id),
            "defaultPlan": AIAnalyst.get_task_model_plan(user_id=user_id),
            "providerPlan": AIAnalyst.get_task_provider_plan(user_id=user_id),
            "provider": AIAnalyst._provider(user_id=user_id),
        },
    }


@app.post("/api/v1/analysis/assistant/consult")
async def assistant_consult(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    question = _clip_assistant_text(
        payload.get("question") or payload.get("message") or payload.get("prompt"),
        _ASSISTANT_QUESTION_MAX_CHARS,
    )
    if not question:
        raise HTTPException(status_code=400, detail="咨询内容不能为空")

    page_context = _normalize_assistant_context(payload.get("pageContext") or payload.get("page_context"))
    messages = _normalize_assistant_messages(payload.get("messages"))
    prompt = _build_assistant_consult_prompt(
        question=question,
        page_context=page_context,
        messages=messages,
    )
    answer = await asyncio.to_thread(
        AIAnalyst.get_decision,
        None,
        prompt,
        task="assistant",
        user_id=user_id,
    )
    answer_text = _repair_assistant_mojibake(answer)
    if not answer_text or answer_text.startswith("ERROR"):
        raise HTTPException(status_code=502, detail=AIAnalyst._build_business_error(answer_text))

    model_plan = AIAnalyst.get_task_model_plan(user_id=user_id)
    general_model = model_plan.get("general") if isinstance(model_plan, dict) else {}
    return {
        "success": True,
        "data": {
            "answer": answer_text,
            "createdAt": _utc_iso(),
            "model": general_model or {},
            "pageContext": page_context,
        },
    }


@app.post("/api/v1/analysis/analyze-positions")
async def analyze_positions(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    started_at = time.time()
    user_id = int(session["user_id"])
    positions = payload.get("positions") or []
    account_id = payload.get("account_id") or payload.get("accountId")
    force_refresh = bool(payload.get("force_refresh", payload.get("forceRefresh", True)))
    allow_single_quote_retry = bool(
        payload.get("allow_live_quote")
        or payload.get("allowLiveQuote")
        or payload.get("allow_single_quote_retry")
        or payload.get("allowSingleQuoteRetry")
    )
    model_plan = AIAnalyst.get_task_model_plan(user_id=user_id)

    if not positions:
        raise HTTPException(status_code=400, detail="持仓数据不能为空")

    original_positions = positions if isinstance(positions, list) else []
    positions, batch_meta = _normalize_position_batch_payload(original_positions)
    if batch_meta["partial"]:
        deferred_job = _enqueue_deferred_positions_analysis(
            positions=[item for item in original_positions if isinstance(item, dict)],
            base_payload={
                **payload,
                "force_refresh": force_refresh,
                "forceRefresh": force_refresh,
            },
            session={"user_id": user_id},
            model_plan=model_plan,
            batch_meta=batch_meta,
        )
        response_payload = {
            "success": True,
            "data": _build_deferred_analysis_placeholders(
                original_positions,
                model_plan=model_plan,
                sync_limit=int(batch_meta["syncLimit"]),
            ),
            "jobId": deferred_job["jobId"],
            "jobStatus": deferred_job["status"],
            "statusUrl": f"/api/v1/analysis/analyze-positions/jobs/{deferred_job['jobId']}",
            "jobExpiresAt": deferred_job.get("expiresAt"),
            "jobTtlSeconds": deferred_job.get("ttlSeconds"),
            "marketSummary": None,
            "modelPlan": model_plan,
            "message": f"批量分析请求共 {batch_meta['requested']} 只股票，超过同步上限 {batch_meta['syncLimit']}，已创建后台任务 {deferred_job['jobId']}",
            "duration": time.time() - started_at,
            "accepted": True,
            "degraded": True,
            "syncLimit": batch_meta["syncLimit"],
            "stats": {
                "total": batch_meta["requested"],
                "accepted": 0,
                "successful": 0,
                "failed": 0,
                "deferred": batch_meta["requested"],
            },
            "meta": {
                **batch_meta,
                "status": "accepted",
                "executionMode": "deferred",
                "jobId": deferred_job["jobId"],
                "jobExpiresAt": deferred_job.get("expiresAt"),
                "jobTtlSeconds": deferred_job.get("ttlSeconds"),
            },
        }
        return JSONResponse(status_code=202, content=response_payload)

    resolved_account_id = _resolve_analysis_account_id(user_id, account_id)
    results = []
    market_snapshot_cache: Dict[str, dict] = {}
    response_market_summary = None
    normalized_symbols = [
        HistoricalMarketDataService.normalize_symbol(str(position.get("symbol") or "").strip())
        for position in positions
        if str(position.get("symbol") or "").strip()
    ]
    quote_cache = (
        get_quotes_from_broker(
            normalized_symbols,
            resolved_account_id,
            user_id=user_id,
        )
        if normalized_symbols and allow_single_quote_retry
        else {}
    )

    for position in positions:
        raw_symbol = str(position.get("symbol") or "").strip()
        if not raw_symbol:
            continue

        symbol = HistoricalMarketDataService.normalize_symbol(raw_symbol)
        current_price = 0.0
        volume = 0
        change_percent = 0.0
        prev_close = 0.0
        indicator_payload = {}
        indicator_meta = {"source": "", "warning": ""}
        market_snapshot = response_market_summary or {}

        try:
            cached_result = None if force_refresh else AICache.get_analysis(symbol, "combined")
            if cached_result and cached_result.get("scanLayers"):
                refreshed_cached_result = dict(cached_result)
                cached_quote = quote_cache.get(symbol) or {}
                if cached_quote:
                    current_price = float(cached_quote.get("last_price") or 0)
                    volume = int(cached_quote.get("volume") or 0)
                    change_percent = float(cached_quote.get("change_percent") or 0)
                    prev_close = float(cached_quote.get("prev_close") or 0)
                else:
                    current_price, volume, change_percent, prev_close = (
                        extract_position_quote_fallback(position)
                    )
                    if current_price <= 0:
                        current_price, volume, change_percent, prev_close = (
                            _extract_read_model_quote_fallback(symbol)
                        )
                    if current_price <= 0 and allow_single_quote_retry:
                        current_price, volume, change_percent, prev_close = get_quote_from_broker(
                            symbol, resolved_account_id, user_id=user_id
                        )
                market_key = detect_market(symbol)
                market_snapshot = market_snapshot_cache.get(market_key)
                if not market_snapshot:
                    market_snapshot = build_market_snapshot(
                        resolved_account_id, symbol, user_id=user_id
                    )
                    market_snapshot_cache[market_key] = market_snapshot

                if current_price > 0:
                    refreshed_cached_result.update(
                        {
                            "price": current_price,
                            "volume": volume,
                            "changePercent": change_percent,
                            "prevClose": prev_close,
                            "analysisTime": time.time(),
                            "timestamp": time.time(),
                        }
                    )
                refreshed_cached_result["marketSummary"] = market_snapshot
                refreshed_cached_result["modelPlan"] = model_plan
                refreshed_cached_result["source"] = "manual_scan"
                refreshed_cached_result["analysisMode"] = "manual_live_scan"
                results.append(refreshed_cached_result)
                response_market_summary = market_snapshot or response_market_summary
                continue

            cached_quote = quote_cache.get(symbol) or {}
            if cached_quote:
                current_price = float(cached_quote.get("last_price") or 0)
                volume = int(cached_quote.get("volume") or 0)
                change_percent = float(cached_quote.get("change_percent") or 0)
                prev_close = float(cached_quote.get("prev_close") or 0)
            else:
                current_price, volume, change_percent, prev_close = (
                    extract_position_quote_fallback(position)
                )
                if current_price <= 0:
                    current_price, volume, change_percent, prev_close = (
                        _extract_read_model_quote_fallback(symbol)
                    )
                if current_price <= 0 and allow_single_quote_retry:
                    current_price, volume, change_percent, prev_close = get_quote_from_broker(
                        symbol, resolved_account_id, user_id=user_id
                    )

            if current_price <= 0:
                results.append(
                    {
                        "symbol": symbol,
                        "name": position.get("name") or position.get("symbol_name") or symbol,
                        "error": "无行情数据",
                        "reason": "当前未能从券商获取到实时行情，请稍后重试或检查代码格式。",
                        "modelPlan": model_plan,
                        "scanLayers": [],
                        "finalSignal": "danger",
                        "finalDecision": "无行情",
                        "source": "manual_scan",
                        "analysisMode": "manual_live_scan",
                    }
                )
                continue

            real_ai_payload, indicator_payload = build_real_indicator_context(
                symbol, current_price, volume, user_id=user_id
            )
            indicator_meta = {"source": "snapshot", "warning": ""}

            market_key = detect_market(symbol)
            market_snapshot = market_snapshot_cache.get(market_key)
            if not market_snapshot:
                market_snapshot = build_market_snapshot(
                    resolved_account_id, symbol, user_id=user_id
                )
                market_snapshot_cache[market_key] = market_snapshot
            response_market_summary = market_snapshot

            ai_data = {
                **real_ai_payload,
                "price": float(current_price or real_ai_payload.get("price") or 0),
                "market_context": market_snapshot,
                "account_id": resolved_account_id,
                "user_id": user_id,
                "indicator_source": indicator_meta.get("source"),
            }

            rsi = float(real_ai_payload.get("rsi") or 0)
            algo_side = "BUY" if rsi < 30 else "SELL" if rsi > 70 else "HOLD"
            verdict, reason, gemma_analysis, llama_analysis, deepseek_analysis = (
                AiConsultant.get_final_decision_with_details(symbol, algo_side, ai_data)
            )

            final_reason = (
                f"{reason}；{indicator_meta['warning']}"
                if indicator_meta.get("warning")
                else reason
            )
            analysis_result = _build_manual_scan_result(
                symbol=symbol,
                position=position,
                current_price=current_price,
                prev_close=prev_close,
                change_percent=change_percent,
                volume=volume,
                indicator_payload=indicator_payload,
                market_snapshot=market_snapshot,
                model_plan=model_plan,
                reason=final_reason,
                gemma_analysis=gemma_analysis,
                llama_analysis=llama_analysis,
                deepseek_analysis=deepseek_analysis,
                verdict=verdict,
            )
            analysis_result["indicatorSource"] = indicator_meta.get("source") or "snapshot"

            try:
                get_persistence_manager().save_ai_analysis(
                    AIAnalysisHistory(
                        user_id=user_id,
                        symbol=symbol,
                        market=detect_market(symbol),
                        price=current_price,
                        gemma_decision=analysis_result.get("gemmaDecision", ""),
                        gemma_confidence=80.0,
                        gemma_analysis=gemma_analysis.get("full_text", ""),
                        llama_decision=analysis_result.get("llamaDecision", ""),
                        llama_confidence=80.0,
                        llama_analysis=llama_analysis.get("full_text", ""),
                        deepseek_decision=analysis_result.get("deepseekDecision", ""),
                        deepseek_confidence=deepseek_analysis.get("confidence", 75.0),
                        deepseek_analysis=deepseek_analysis.get("full_text", ""),
                        final_decision=analysis_result["finalDecision"],
                        final_confidence=deepseek_analysis.get("confidence", 75.0),
                        indicators=analysis_result["indicators"],
                        analysis_time=datetime.now(),
                    )
                )
            except Exception:
                pass

            AICache.cache_analysis(symbol, analysis_result, "combined", 1800)
            results.append(analysis_result)
        except Exception as exc:
            results.append(
                _build_manual_scan_error_result(
                    symbol=symbol,
                    position=position,
                    model_plan=model_plan,
                    error=str(exc),
                    reason=str(exc),
                    current_price=current_price,
                    prev_close=prev_close,
                    change_percent=change_percent,
                    volume=volume,
                    indicator_payload=indicator_payload,
                    market_snapshot=market_snapshot,
                    indicator_source=indicator_meta.get("source") or "",
                )
            )

    response_payload = {
        "success": True,
        "data": results,
        "marketSummary": response_market_summary,
        "modelPlan": model_plan,
        "message": (
            f"本次同步分析 {batch_meta['accepted']} 只股票，成功分析 {len(results)} 只股票"
            + (f"；其余 {batch_meta['deferred']} 只已接受但延后处理" if batch_meta["partial"] else "")
        ),
        "duration": time.time() - started_at,
        "accepted": True,
        "degraded": bool(batch_meta["partial"]),
        "syncLimit": batch_meta["syncLimit"],
        "stats": {
            "total": batch_meta["requested"],
            "accepted": batch_meta["accepted"],
            "successful": len(results),
            "failed": len([item for item in results if item.get("error")]),
            "deferred": batch_meta["deferred"],
        },
        "meta": {
            **batch_meta,
            "status": "accepted" if batch_meta["partial"] else "completed",
        },
    }
    if batch_meta["partial"]:
        return JSONResponse(status_code=202, content=response_payload)
    return response_payload


@app.get("/api/v1/analysis/analyze-positions/jobs/{job_id}")
async def analyze_positions_job_status(
    job_id: str,
    session: dict = Depends(get_current_session),
):
    job = _deferred_analysis_job_snapshot(job_id)
    if not job:
        return JSONResponse(
            status_code=410,
            content={
                "success": False,
                "error": "分析任务已失效或不存在，请重新发起扫描",
                "data": {
                    "jobId": job_id,
                    "status": "expired",
                    "retryable": False,
                },
            },
        )
    if int(job.get("userId") or 0) != int(session["user_id"]):
        raise HTTPException(status_code=404, detail="分析任务不存在")
    return {
        "success": True,
        "data": job,
    }


@app.get("/api/v1/analysis/trend-scans")
async def trend_scans(
    symbols: List[str] = Query(default=[]),
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = 24,
    _: dict = Depends(get_current_session),
):
    parsed_symbols = _parse_symbols(symbols, symbol)
    safe_limit = max(1, min(int(limit or 24), 80))
    normalized_market = str(market or "").strip().upper() or None
    items = DailySymbolTrendScanService.get_latest_batch(
        symbols=parsed_symbols or None,
        market=normalized_market,
        limit=safe_limit,
    )
    results = [_build_trend_scan_analysis_result(item) for item in items]
    return {
        "success": True,
        "data": results,
        "meta": _build_trend_scan_meta(
            items=items,
            symbols=parsed_symbols,
            market=normalized_market,
            limit=safe_limit,
        ),
    }


@app.get("/api/v1/analysis/symbols/{symbol}/latest")
async def latest_symbol_analysis(symbol: str, session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    trend_scan = DailySymbolTrendScanService.get_latest_for_symbol(normalized_symbol)
    latest_ai = get_persistence_manager().get_latest_ai_analysis(normalized_symbol, user_id=user_id)
    return {
        "success": True,
        "data": {
            "symbol": normalized_symbol,
            "latestTrendScan": trend_scan,
            "latestAiAnalysis": latest_ai.to_dict() if latest_ai else None,
        },
    }


@app.get("/api/v1/analysis/recommendations")
async def recommendations(
    profile: str = "growth",
    refresh: bool = False,
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    normalized_profile = str(profile or "growth").strip().lower() or "growth"
    if refresh:
        result = RecommendationService.refresh(profile=normalized_profile, user_id=user_id, force=True)
    else:
        result = RecommendationService.get_latest(profile=normalized_profile, user_id=user_id)
        if not result:
            result = RecommendationService.refresh(profile=normalized_profile, user_id=user_id, force=True)
    return {
        "success": True,
        "data": result,
        "meta": _build_recommendation_meta(result, normalized_profile),
    }


@app.post("/api/v1/analysis/recommendations/refresh")
async def refresh_recommendations(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    profile = str(payload.get("profile", "growth") or "growth").strip().lower() or "growth"
    result = RecommendationService.refresh(
        profile=profile,
        user_id=int(session["user_id"]),
        force=True,
    )
    return {
        "success": True,
        "message": "智能推荐已刷新",
        "data": result,
        "meta": _build_recommendation_meta(result, profile),
    }


@app.post("/api/v1/analysis/agent/watchlist-review")
async def watchlist_review(
    payload: dict = Body(default={}),
    auth_session: dict = Depends(get_current_session),
):
    normalized_session = _normalize_watchlist_session(payload.get("session"))
    scene = _resolve_watchlist_scene(normalized_session)
    raw_user_id = payload.get("userId", payload.get("user_id", auth_session.get("user_id")))
    user_id = _resolve_agent_run_scope_user_id(
        session=auth_session,
        requested_user_id=raw_user_id,
    )

    trigger_source = str(payload.get("triggerSource") or "manual").strip() or "manual"
    dry_run = bool(payload.get("dryRun", True))
    targets = _normalize_watchlist_targets(payload.get("targets"))
    if not targets:
        targets = _load_watchlist_scan_targets(user_id=user_id, session_name=normalized_session)
    run_id = str(uuid.uuid4())
    sidecar_payload = {
        "runId": run_id,
        "scene": scene,
        "session": normalized_session,
        "userId": user_id,
        "user_id": user_id,
        "targets": targets,
        "triggerSource": trigger_source,
        "dryRun": dry_run,
    }
    if isinstance(payload.get("autoBuy"), dict):
        sidecar_payload["autoBuy"] = payload["autoBuy"]

    if not targets:
        return _build_watchlist_review_skipped_result(
            run_id=run_id,
            scene=scene,
            normalized_session=normalized_session,
            trigger_source=trigger_source,
            dry_run=dry_run,
            user_id=user_id,
        )

    idempotency_key = _build_watchlist_idempotency_key(
        scene=scene,
        user_id=user_id,
        trigger_source=trigger_source,
        targets=targets,
    )
    sidecar_payload["idempotencyKey"] = idempotency_key
    existing_run = _find_recent_watchlist_run_by_idempotency_key(
        scene=scene,
        user_id=user_id,
        idempotency_key=idempotency_key,
    )
    if isinstance(existing_run, dict):
        existing_run_id = existing_run.get("runId") or existing_run.get("run_id")
        return _build_watchlist_review_accepted_result(
            run_id=str(existing_run_id or run_id),
            db_run_id=int(existing_run_id) if existing_run_id else None,
            scene=scene,
            normalized_session=normalized_session,
            trigger_source=trigger_source,
            dry_run=dry_run,
            targets_count=len(targets),
            idempotency_key=idempotency_key,
            deduped=True,
        )

    db_run_id = _create_watchlist_run(
        scene=scene,
        user_id=user_id,
        trigger_source=trigger_source,
        targets=targets,
        request_payload=sidecar_payload,
    )

    _start_watchlist_review_worker(
        db_run_id=db_run_id,
        run_id=run_id,
        scene=scene,
        sidecar_payload=sidecar_payload,
    )
    return _build_watchlist_review_accepted_result(
        run_id=run_id,
        db_run_id=db_run_id,
        scene=scene,
        normalized_session=normalized_session,
        trigger_source=trigger_source,
        dry_run=dry_run,
        targets_count=len(targets),
        idempotency_key=idempotency_key,
    )


@app.get("/api/v1/analysis/agent/runs")
async def list_agent_runs(
    scene: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
    userId: Optional[int] = Query(default=None),
    session: dict = Depends(get_current_session),
):
    scoped_user_id = _resolve_agent_run_scope_user_id(session=session, requested_user_id=userId)
    runs = _call_agent_run_service(
        ("list_recent_runs", "list_runs", "get_runs"),
        scene=str(scene or "").strip() or None,
        status=_normalize_agent_run_status(status),
        user_id=scoped_user_id,
        limit=_normalize_agent_run_limit(limit),
        use_primary=True,
    )
    return {
        "success": True,
        "data": runs if isinstance(runs, list) else [],
        "message": "获取 Agent 运行记录成功",
    }


@app.get("/api/v1/analysis/agent/runs/{run_id}")
async def get_agent_run_detail(
    run_id: int,
    userId: Optional[int] = Query(default=None),
    session: dict = Depends(get_current_session),
):
    scoped_user_id = _resolve_agent_run_scope_user_id(session=session, requested_user_id=userId)
    run = _load_agent_run_or_404(int(run_id))
    _assert_agent_run_visible(run, session=session, scoped_user_id=scoped_user_id)
    return {
        "success": True,
        "data": run,
        "message": "获取 Agent 运行详情成功",
    }


@app.post("/api/v1/analysis/agent/runs/{run_id}/override")
async def override_agent_run(
    run_id: int,
    payload: dict = Body(default={}),
    userId: Optional[int] = Query(default=None),
    session: dict = Depends(get_current_session),
):
    current_user_id = _coerce_agent_run_user_id(session.get("user_id"), field_name="session.user_id")
    scoped_user_id = _resolve_agent_run_scope_user_id(session=session, requested_user_id=userId)
    run = _load_agent_run_or_404(int(run_id))
    _assert_agent_run_visible(run, session=session, scoped_user_id=scoped_user_id)

    action = _normalize_override_action(payload.get("action"))
    new_status = _validate_override_status_transition(
        action,
        _normalize_override_new_status(payload.get("newStatus", payload.get("new_status"))),
    )
    actor = str(payload.get("actor") or session.get("username") or session.get("role") or "human-review").strip() or "human-review"

    override_id = _call_agent_run_service(
        ("record_override", "create_override", "save_override"),
        run_id=int(run_id),
        user_id=current_user_id,
        actor=actor,
        action=action,
        reason=payload.get("reason"),
        old_status=run.get("status"),
        new_status=new_status,
        review_note=payload.get("reviewNote", payload.get("review_note")),
    )
    if override_id is None:
        raise HTTPException(status_code=500, detail="人工复核记录写入失败")

    updated_run = _load_agent_run_or_404(int(run_id))
    _assert_agent_run_visible(updated_run, session=session, scoped_user_id=scoped_user_id)
    return {
        "success": True,
        "data": updated_run,
        "message": "人工复核结果已记录",
    }


@app.get("/api/v1/analysis/finance-briefings")
async def finance_briefings(
    limit: int = 20,
    market: Optional[str] = None,
    refresh: bool = False,
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    safe_limit = max(1, min(int(limit or 20), 60))
    normalized_market = str(market or "").strip().upper() or None
    items = FinanceBriefingService.get_latest(limit=safe_limit, market=normalized_market)
    if refresh:
        FinanceBriefingService.refresh_all_markets(user_id=user_id)
        items = FinanceBriefingService.get_latest(limit=safe_limit, market=normalized_market)
    return {
        "success": True,
        "data": items,
        "meta": _build_finance_briefing_meta(
            items=items,
            market=normalized_market,
            limit=safe_limit,
        ),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
