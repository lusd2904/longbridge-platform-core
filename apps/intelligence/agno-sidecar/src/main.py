from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


REFACTOR_ROOT = Path(__file__).resolve().parents[4]
if str(REFACTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(REFACTOR_ROOT))

from apps.runtime_shared.health import build_dependency_status, build_health_payload


PORT = int(os.getenv("REF_AGNO_SIDECAR_PORT", os.getenv("SERVICE_PORT", "3200")))
AI_BASE_URL = str(os.getenv("LONGBRIDGE_AI_BASE_URL") or "http://sub2api:8080/v1").strip().rstrip("/")
AI_CHAT_URL = str(os.getenv("LONGBRIDGE_AI_URL") or f"{AI_BASE_URL}/chat/completions").strip()
AI_API_KEY = str(os.getenv("LONGBRIDGE_AI_API_KEY") or "").strip()
AI_MODEL = str(os.getenv("LONGBRIDGE_AI_MODEL_SCAN_FINAL") or os.getenv("LONGBRIDGE_AI_MODEL") or "gpt-5.5").strip()
AI_REASONING_EFFORT = str(os.getenv("LONGBRIDGE_AI_SCAN_REASONING_EFFORT") or os.getenv("LONGBRIDGE_AI_REASONING_EFFORT") or "high").strip()

app = FastAPI(
    title="Refactor V2 Agno-compatible Sidecar",
    version="0.1.0",
    description="Review-only watchlist sidecar using the existing sub2api/OpenAI-compatible gateway.",
)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    candidates = [raw]
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


def _build_review_prompt(message: str, payload: Dict[str, Any]) -> str:
    return (
        "你是 review-only 的金融自选股复核智能体。"
        "只能输出观察、风险提示、人工复核建议和证据，不得输出任何下单、撤单、改单、持仓变更或交易执行动作。\n"
        "必须返回 JSON，字段为 summary, signals, riskFlags, reviewAdvice, evidence, confidence, status。\n"
        f"原始请求: {message}\n"
        f"结构化上下文: {json.dumps(payload, ensure_ascii=False, default=str)[:4000]}"
    )


async def _parse_request_payload(request: Request) -> Dict[str, Any]:
    content_type = str(request.headers.get("content-type") or "").lower()
    raw_body = await request.body()
    if not raw_body:
        return {}

    if "application/x-www-form-urlencoded" in content_type:
        parsed_form = urllib_parse.parse_qs(raw_body.decode("utf-8", errors="ignore"), keep_blank_values=True)
        payload: Dict[str, Any] = {
            key: values[-1] if values else ""
            for key, values in parsed_form.items()
        }
        embedded_payload = payload.get("payload")
        if embedded_payload:
            try:
                parsed_payload = json.loads(str(embedded_payload))
                if isinstance(parsed_payload, dict):
                    parsed_payload.setdefault("message", payload.get("message") or "")
                    parsed_payload.setdefault("runId", payload.get("session_id") or "")
                    parsed_payload.setdefault("userId", payload.get("user_id") or "")
                    return parsed_payload
            except Exception:
                pass
        return payload

    try:
        parsed_json = json.loads(raw_body.decode("utf-8", errors="ignore"))
    except Exception:
        return {}
    if not isinstance(parsed_json, dict):
        return {}
    nested_payload = parsed_json.get("payload")
    if isinstance(nested_payload, dict):
        nested_payload.setdefault("message", parsed_json.get("message") or "")
        nested_payload.setdefault("runId", parsed_json.get("session_id") or parsed_json.get("runId") or "")
        nested_payload.setdefault("userId", parsed_json.get("user_id") or parsed_json.get("userId") or "")
        return nested_payload
    return parsed_json


def _call_ai(prompt: str) -> Dict[str, Any]:
    request_payload = {
        "model": AI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是只读金融复核助手，严禁执行或建议执行交易写动作。请用严格 JSON 输出。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "reasoning_effort": AI_REASONING_EFFORT,
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if AI_API_KEY:
        headers["Authorization"] = f"Bearer {AI_API_KEY}"
    request = urllib_request.Request(
        AI_CHAT_URL,
        data=json.dumps(request_payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=150) as response:
        raw_body = response.read().decode("utf-8", errors="ignore")
    payload = json.loads(raw_body) if raw_body else {}
    choices = payload.get("choices") if isinstance(payload, dict) else []
    message = choices[0].get("message", {}) if choices and isinstance(choices[0], dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    parsed = _extract_json(str(content or ""))
    if parsed:
        return parsed
    return {
        "status": "completed",
        "summary": str(content or "AI 复核已完成，请人工查看原始输出。")[:800],
        "signals": [],
        "riskFlags": [],
        "reviewAdvice": ["请人工复核 AI 原始输出后再处理。"],
        "evidence": [{"type": "sub2api-response", "model": AI_MODEL}],
        "confidence": 40,
    }


def _fallback_result(payload: Dict[str, Any], error: str) -> Dict[str, Any]:
    targets = payload.get("targets") if isinstance(payload.get("targets"), list) else []
    return {
        "status": "degraded",
        "summary": "Agno-compatible sidecar 未能调用 AI，已返回只读降级复核结果。",
        "signals": [],
        "riskFlags": [
            {
                "level": "medium",
                "message": "AI 复核链路暂时不可用，请人工复核自选股风险。",
            }
        ],
        "reviewAdvice": ["稍后重试复核任务。", "不要基于本降级结果执行交易。"],
        "evidence": [
            {
                "type": "sidecar-fallback",
                "targetsCount": len(targets),
                "aiUrl": AI_CHAT_URL,
                "error": error[:500],
            }
        ],
        "confidence": 0,
        "degraded": True,
        "source": "agno-compatible-sidecar",
    }


def _normalize_result(result: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": str(result.get("status") or "completed"),
        "summary": str(result.get("summary") or "自选股复核完成。"),
        "signals": result.get("signals") if isinstance(result.get("signals"), list) else [],
        "riskFlags": result.get("riskFlags") if isinstance(result.get("riskFlags"), list) else [],
        "reviewAdvice": result.get("reviewAdvice") if isinstance(result.get("reviewAdvice"), list) else ["请人工确认后再处理。"],
        "evidence": result.get("evidence") if isinstance(result.get("evidence"), list) else [{"type": "sub2api", "model": AI_MODEL}],
        "confidence": result.get("confidence", 0),
        "source": "agno-compatible-sidecar",
        "scene": payload.get("scene"),
        "runId": payload.get("runId") or payload.get("session_id"),
        "model": AI_MODEL,
    }


@app.get("/health")
async def health() -> Dict[str, Any]:
    ai_config = {
        "provider": "sub2api",
        "baseUrl": AI_BASE_URL,
        "chatCompletionsUrl": AI_CHAT_URL,
        "model": AI_MODEL,
    }
    return build_health_payload(
        service="agno-sidecar",
        version=app.version,
        port=PORT,
        status="healthy",
        deps={
            "ai-gateway": build_dependency_status(
                "ai-gateway",
                "healthy" if AI_CHAT_URL else "degraded",
                detail="configured; review endpoints degrade safely when unavailable",
                optional=True,
                observed=ai_config,
            )
        },
        capabilities=["agno-team-run", "watchlist-review", "review-only-fallback"],
        extra={
            "success": True,
            "aiConfig": ai_config,
            "safety": "review-only",
        },
    )


@app.post("/teams/sub2api-team/runs")
async def sub2api_team_runs(request: Request) -> JSONResponse:
    request_payload = await _parse_request_payload(request)
    message = str(request_payload.get("message") or "")
    prompt = _build_review_prompt(message, request_payload)
    try:
        result = _call_ai(prompt)
    except Exception as exc:
        result = _fallback_result(request_payload, str(exc))
    return JSONResponse(
        {
            "success": True,
            "status": "COMPLETED",
            "team_id": "sub2api-team",
            "team_name": "Sub2API Review Team",
            "model": AI_MODEL,
            "data": _normalize_result(result, request_payload),
        }
    )


@app.post("/api/v1/agent/watchlist-review")
@app.post("/api/v1/watchlist-review")
@app.post("/watchlist-review")
async def watchlist_review(request: Request) -> Dict[str, Any]:
    request_payload = await _parse_request_payload(request)
    prompt = _build_review_prompt("", request_payload)
    try:
        result = _call_ai(prompt)
    except Exception as exc:
        result = _fallback_result(request_payload, str(exc))
    return {"success": True, "data": _normalize_result(result, request_payload)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
