from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Optional


HEALTHY = "healthy"
DEGRADED = "degraded"
UNHEALTHY = "unhealthy"
UNKNOWN = "unknown"

_STATUS_TEXT = {
    HEALTHY: "运行正常",
    DEGRADED: "部分受限",
    UNHEALTHY: "异常",
    UNKNOWN: "待确认",
    "disabled": "未启用",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_status(value: object) -> str:
    raw = str(value or UNKNOWN).strip().lower()
    if raw in {"ok", "healthy", "success", "ready", "connected"}:
        return HEALTHY
    if raw in {"degraded", "warning", "partial"}:
        return DEGRADED
    if raw in {"error", "failed", "failure", "unhealthy", "disconnected"}:
        return UNHEALTHY
    if raw == "disabled":
        return "disabled"
    return UNKNOWN


def build_dependency_status(
    name: str,
    status: object,
    *,
    detail: str = "",
    latency_ms: Optional[float] = None,
    observed: object = None,
    optional: bool = False,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    normalized = normalize_status(status)
    payload: Dict[str, Any] = {
        "name": name,
        "status": normalized,
        "status_text": _STATUS_TEXT.get(normalized, _STATUS_TEXT[UNKNOWN]),
        "detail": detail,
        "optional": optional,
    }
    if latency_ms is not None:
        payload["latency_ms"] = round(float(latency_ms), 2)
    if observed is not None:
        payload["observed"] = observed
    if extra:
        payload.update(dict(extra))
    return payload


def summarize_status(*sections: Iterable[Mapping[str, Any] | None]) -> str:
    statuses = [
        normalize_status(item.get("status"))
        for section in sections
        for item in (section or [])
        if isinstance(item, Mapping)
    ]
    if any(status == UNHEALTHY for status in statuses):
        return UNHEALTHY
    if any(status == DEGRADED for status in statuses):
        return DEGRADED
    if any(status == HEALTHY for status in statuses):
        return HEALTHY
    return UNKNOWN


def build_alert(
    code: str,
    level: str,
    message: str,
    *,
    scope: str = "service",
    action: str = "",
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "code": code,
        "level": str(level or "info").strip().lower() or "info",
        "scope": scope,
        "message": message,
    }
    if action:
        payload["action"] = action
    if extra:
        payload.update(dict(extra))
    return payload


def build_health_payload(
    *,
    service: str,
    version: str,
    port: int,
    phase: str = "phase-1-live",
    status: object = UNKNOWN,
    deps: Optional[Mapping[str, Mapping[str, Any]]] = None,
    broker_connectivity: Optional[Mapping[str, Any]] = None,
    alerts: Optional[list[Mapping[str, Any]]] = None,
    capabilities: Optional[Iterable[str]] = None,
    legacy_compat: Any = None,
    latency_ms: Optional[float] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    normalized = normalize_status(status)
    payload: Dict[str, Any] = {
        "service": service,
        "version": version,
        "status": normalized,
        "status_text": _STATUS_TEXT.get(normalized, _STATUS_TEXT[UNKNOWN]),
        "phase": phase,
        "environment": os.getenv("REF_ENVIRONMENT", os.getenv("ENVIRONMENT", "development")),
        "port": port,
        "checked_at": utc_now_iso(),
        "deps": dict(deps or {}),
        "brokerConnectivity": dict(broker_connectivity or {}),
        "broker_connectivity": dict(broker_connectivity or {}),
        "alerts": list(alerts or []),
        "capabilities": list(capabilities or []),
    }
    if legacy_compat is not None:
        payload["legacyCompat"] = legacy_compat
    if latency_ms is not None:
        payload["latency_ms"] = round(float(latency_ms), 2)
    if extra:
        payload.update(dict(extra))
    return payload
