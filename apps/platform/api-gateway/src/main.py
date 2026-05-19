from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


REFACTOR_ROOT = Path(__file__).resolve().parents[3]
if str(REFACTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(REFACTOR_ROOT))

from apps.platform.module_shared import (
    build_alert,
    build_dependency_status,
    build_health_payload,
    create_service_app,
    service_port,
    summarize_status,
)


app = create_service_app(
    title="Refactor V2 API Gateway",
    version="0.2.0",
    description="Phase 1 live gateway for dependency health and service catalog.",
)
PORT = service_port("REF_GATEWAY_PORT", 5101)
HEALTH_PROBE_TIMEOUT_SECONDS = float(os.getenv("REF_GATEWAY_HEALTH_PROBE_TIMEOUT", "3.0"))


def _config_port(env_var: str, default: int) -> int:
    return int(os.getenv(env_var, str(default)))


def _service_url(url_env_var: str, port_env_var: str, default_port: int) -> str:
    explicit_url = str(os.getenv(url_env_var, "")).strip().rstrip("/")
    if explicit_url:
        return explicit_url
    return f"http://127.0.0.1:{_config_port(port_env_var, default_port)}"


SERVICE_REGISTRY = {
    "user-center": {
        "port": _config_port("REF_USER_CENTER_PORT", 8101),
        "url": _service_url("REF_USER_CENTER_URL", "REF_USER_CENTER_PORT", 8101),
        "basePath": "/api/v1/auth",
        "description": "登录、会话和用户引导",
    },
    "market-service": {
        "port": _config_port("REF_MARKET_SERVICE_PORT", 8102),
        "url": _service_url("REF_MARKET_SERVICE_URL", "REF_MARKET_SERVICE_PORT", 8102),
        "basePath": "/api/v1/market",
        "description": "行情、指标、市场扫描和标的总览",
    },
    "analysis-service": {
        "port": _config_port("REF_ANALYSIS_SERVICE_PORT", 8103),
        "url": _service_url("REF_ANALYSIS_SERVICE_URL", "REF_ANALYSIS_SERVICE_PORT", 8103),
        "basePath": "/api/v1/analysis",
        "description": "模型计划、趋势扫描和智能推荐",
    },
    "strategy-service": {
        "port": _config_port("REF_STRATEGY_SERVICE_PORT", 8104),
        "url": _service_url("REF_STRATEGY_SERVICE_URL", "REF_STRATEGY_SERVICE_PORT", 8104),
        "basePath": "/api/v1/strategy",
        "description": "策略规则、回测、监控告警和量化状态",
    },
    "trade-service": {
        "port": _config_port("REF_TRADE_SERVICE_PORT", 8105),
        "url": _service_url("REF_TRADE_SERVICE_URL", "REF_TRADE_SERVICE_PORT", 8105),
        "basePath": "/api/v1/trade",
        "description": "券商账户、订单、持仓和人工交易执行",
    },
    "risk-service": {
        "port": _config_port("REF_RISK_SERVICE_PORT", 8108),
        "url": _service_url("REF_RISK_SERVICE_URL", "REF_RISK_SERVICE_PORT", 8108),
        "basePath": "/api/v1/risk",
        "description": "风控总览、保护单和通知中心",
    },
    "scheduler-service": {
        "port": _config_port("REF_SCHEDULER_SERVICE_PORT", 8107),
        "url": _service_url("REF_SCHEDULER_SERVICE_URL", "REF_SCHEDULER_SERVICE_PORT", 8107),
        "basePath": "/api/v1/scheduler",
        "description": "调度线程、任务策略、执行记录和手动触发",
    },
    "sentiment-service": {
        "port": _config_port("REF_SENTIMENT_SERVICE_PORT", 8106),
        "url": _service_url("REF_SENTIMENT_SERVICE_URL", "REF_SENTIMENT_SERVICE_PORT", 8106),
        "basePath": "/api/v1/sentiment",
        "description": "舆情接口预留，占位中",
    },
}


def probe_health(base_url: str):
    started_at = time.perf_counter()
    health_url = f"{str(base_url or '').rstrip('/')}/health"
    try:
        with urlopen(health_url, timeout=HEALTH_PROBE_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {
                "reachable": True,
                "payload": payload,
                "latencyMs": (time.perf_counter() - started_at) * 1000,
            }
    except (URLError, TimeoutError, ValueError) as exc:
        return {
            "reachable": False,
            "latencyMs": (time.perf_counter() - started_at) * 1000,
            "error": str(exc),
        }


def _collect_dependency_snapshot() -> dict:
    deps = {}
    alerts = []
    for code, meta in SERVICE_REGISTRY.items():
        result = probe_health(meta["url"])
        payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
        status = payload.get("status") if result.get("reachable") else "unhealthy"
        detail = payload.get("status_text") if result.get("reachable") else result.get("error", "health probe failed")
        deps[code] = build_dependency_status(
            code,
            status,
            detail=detail or meta["description"],
            latency_ms=result.get("latencyMs"),
            observed={
                "port": meta["port"],
                "url": meta["url"],
                "basePath": meta["basePath"],
                "reachable": bool(result.get("reachable")),
            },
            extra={
                "service": payload.get("service", code),
                "phase": payload.get("phase", ""),
                "version": payload.get("version", ""),
            },
        )
        if deps[code]["status"] in {"degraded", "unhealthy"}:
            alerts.append(build_alert(
                f"{code}-health",
                "critical" if deps[code]["status"] == "unhealthy" else "warning",
                f"{meta['description']}状态为 {deps[code]['status_text']}",
                action=f"检查 {meta['url']}/health 与对应服务日志",
                extra={"service": code},
            ))
    return {"deps": deps, "alerts": alerts}


@app.get("/health")
async def health():
    snapshot = await asyncio.to_thread(_collect_dependency_snapshot)
    return build_health_payload(
        service="api-gateway",
        version=app.version,
        port=PORT,
        status=summarize_status(snapshot["deps"].values()),
        deps=snapshot["deps"],
        alerts=snapshot["alerts"],
        capabilities=["service-catalog", "dependency-probe", "observability"],
        extra={
            "registryCount": len(SERVICE_REGISTRY),
        },
    )


@app.get("/api/v1/bootstrap")
async def bootstrap():
    return {
        "success": True,
        "data": {
            "service": "api-gateway",
            "status": "live",
            "phase": "phase-1",
            "registry": SERVICE_REGISTRY,
        },
    }


@app.get("/api/v1/system/dependencies")
async def dependencies():
    async def _probe(code: str, meta: dict):
        result = await asyncio.to_thread(probe_health, meta["url"])
        return code, {
            "port": meta["port"],
            "url": meta["url"],
            "basePath": meta["basePath"],
            "description": meta["description"],
            **result,
        }

    probed = await asyncio.gather(*[
        _probe(code, meta)
        for code, meta in SERVICE_REGISTRY.items()
    ])

    return {
        "service": "api-gateway",
        "dependencies": dict(probed),
    }


@app.get("/api/v1/system/observability")
async def observability():
    snapshot = await asyncio.to_thread(_collect_dependency_snapshot)
    return {
        "success": True,
        "data": {
            "service": "api-gateway",
            "status": summarize_status(snapshot["deps"].values()),
            "deps": snapshot["deps"],
            "alerts": snapshot["alerts"],
            "registry": SERVICE_REGISTRY,
        },
    }


@app.get("/api/v1/system/catalog")
async def catalog():
    return {
        "success": True,
        "data": {
            "gateway": {"port": PORT, "baseUrl": f"http://127.0.0.1:{PORT}"},
            "services": SERVICE_REGISTRY,
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
    )
