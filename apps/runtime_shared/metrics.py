"""Prometheus metrics middleware for refactor-v2 services.

Mounts automatically via ``create_service_app`` so every service exposes
``/metrics`` (Prometheus text format) without per-service boilerplate.

Exported counters / histograms / gauges::

    http_requests_total{method,endpoint,status}  — request count
    http_request_duration_seconds_bucket{method,endpoint,le}  — latency histogram
    http_request_duration_seconds_sum  — sum of latencies
    http_request_duration_seconds_count  — total observations
    ai_calls_total{provider,model}  — AI invocation counter
    ai_call_duration_seconds  — AI call duration histogram
    ai_call_cost_usd  — cumulative AI spend (USD)
    db_queries_total{operation}  — raw DB query counter
    redis_operations_total{operation,status}  — Redis op counter
    ws_connections_current  — live WebSocket connections
    uptime_seconds  — service uptime gauge
"""

from __future__ import annotations

import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

# ---------------------------------------------------------------------------
# Lazy import so the module works without prometheus-client installed (graceful
# degradation — the middleware silently skips instrumentation when absent).
# ---------------------------------------------------------------------------

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    _HAS_PROM = True
except ImportError:  # pragma: no cover
    _HAS_PROM = False

# ---------------------------------------------------------------------------
# Registry (dedicated per-process to avoid duplicate registration errors)
# ---------------------------------------------------------------------------

_registry: CollectorRegistry | None = None


def _get_registry() -> CollectorRegistry:
    global _registry
    if _registry is None:
        _registry = CollectorRegistry()
    return _registry


# ---------------------------------------------------------------------------
# HTTP request metrics
# ---------------------------------------------------------------------------

_HTTP_REQUESTS: Counter | None = None
_HTTP_DURATION: Histogram | None = None


def _ensure_http_metrics() -> tuple[Counter | None, Histogram | None]:
    if not _HAS_PROM:
        return None, None
    global _HTTP_REQUESTS, _HTTP_DURATION
    reg = _get_registry()
    if _HTTP_REQUESTS is None:
        _HTTP_REQUESTS = Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status"],
            registry=reg,
        )
    if _HTTP_DURATION is None:
        _HTTP_DURATION = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency in seconds",
            ["method", "endpoint"],
            buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            registry=reg,
        )
    return _HTTP_REQUESTS, _HTTP_DURATION


def _normalize_endpoint(path: str, route_name: str | None) -> str:
    """Collapse path params (/symbols/AAPL) into template (/symbols/{param})."""
    if route_name:
        return route_name
    # Replace numeric/uuid segments with {param}
    import re

    parts = path.strip("/").split("/")
    normalized = []
    for part in parts:
        if part and (
            part.isdigit()
            or bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", part, re.I))
        ):
            normalized.append("{param}")
        else:
            normalized.append(part)
    return "/" + "/".join(normalized) if normalized else "/"


class MetricsMiddleware(BaseHTTPMiddleware):
    """Collects per-request Prometheus metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()

        http_req, http_dur = _ensure_http_metrics()

        # Determine endpoint label *before* the request completes so we can
        # catch 404s (no matched route).
        raw_path = request.url.path
        route_name: str | None = None
        if request.scope.get("route"):
            route_name = getattr(request.scope["route"], "name", None)
        endpoint = _normalize_endpoint(raw_path, route_name)

        method = request.method.upper()

        try:
            response = await call_next(request)
            status = str(response.status_code)
        except Exception:
            status = "500"
            raise
        finally:
            elapsed = time.perf_counter() - start
            if http_req is not None:
                http_req.labels(method=method, endpoint=endpoint, status=status).inc()
            if http_dur is not None:
                http_dur.labels(method=method, endpoint=endpoint).observe(elapsed)

        response.headers["Content-Type"] = response.headers.get("Content-Type", "application/json")
        return response


# ---------------------------------------------------------------------------
# /metrics HTTP endpoint helper
# ---------------------------------------------------------------------------


def mount_metrics_route(app: Any) -> None:
    """Add ``/metrics`` GET endpoint to a FastAPI or Starlette app."""
    if not _HAS_PROM:
        return

    from starlette.routing import Route

    async def metrics_endpoint(request: Request) -> Response:  # noqa: F821
        reg = _get_registry()
        body = generate_latest(reg).decode("utf-8")
        return StreamingResponse(
            iter([body]),
            media_type=CONTENT_TYPE_LATEST,
        )

    # FastAPI style
    if hasattr(app, "get"):
        app.get("/metrics", include_in_schema=False)(metrics_endpoint)
    # Starlette style
    elif hasattr(app, "route"):
        app.route("/metrics")(metrics_endpoint)
    # Generic ASGI — add to routes list if available
    elif hasattr(app, "router") and hasattr(app.router, "routes"):
        app.router.routes.append(Route("/metrics", endpoint=metrics_endpoint))


# ---------------------------------------------------------------------------
# AI call metrics (service-side instrumentation)
# ---------------------------------------------------------------------------

_ai_calls: Counter | None = None
_ai_duration: Histogram | None = None
_ai_cost: Gauge | None = None


def _ensure_ai_metrics() -> tuple[Counter | None, Histogram | None, Gauge | None]:
    global _ai_calls, _ai_duration, _ai_cost
    if not _HAS_PROM:
        return None, None, None
    reg = _get_registry()
    if _ai_calls is None:
        _ai_calls = Counter(
            "ai_calls_total",
            "Total AI provider calls",
            ["provider", "model"],
            registry=reg,
        )
    if _ai_duration is None:
        _ai_duration = Histogram(
            "ai_call_duration_seconds",
            "AI call latency in seconds",
            ["provider", "model"],
            buckets=[1.0, 3.0, 5.0, 10.0, 30.0, 60.0, 120.0],
            registry=reg,
        )
    if _ai_cost is None:
        _ai_cost = Gauge(
            "ai_call_cost_usd",
            "Cumulative AI spend in USD",
            ["provider", "model"],
            registry=reg,
        )
    return _ai_calls, _ai_duration, _ai_cost


def record_ai_call(
    provider: str = "unknown",
    model: str = "unknown",
    duration_seconds: float = 0.0,
    cost_usd: float = 0.0,
) -> None:
    """Record a single AI provider call to Prometheus metrics."""
    calls, dur, cost = _ensure_ai_metrics()
    if calls is None:
        return
    calls.labels(provider=provider, model=model).inc()
    dur.labels(provider=provider, model=model).observe(duration_seconds)
    if cost_usd:
        cost.labels(provider=provider, model=model).set(cost_usd)


# ---------------------------------------------------------------------------
# Redis operation metrics
# ---------------------------------------------------------------------------

_redis_ops: Counter | None = None


def _ensure_redis_metrics() -> Counter | None:
    global _redis_ops
    if not _HAS_PROM:
        return None
    reg = _get_registry()
    if _redis_ops is None:
        _redis_ops = Counter(
            "redis_operations_total",
            "Total Redis operations",
            ["operation", "status"],
            registry=reg,
        )
    return _redis_ops


def record_redis_op(operation: str = "unknown", status: str = "ok") -> None:
    ops = _ensure_redis_metrics()
    if ops is None:
        return
    ops.labels(operation=operation, status=status).inc()


# ---------------------------------------------------------------------------
# DB query metrics
# ---------------------------------------------------------------------------

_db_queries: Counter | None = None


def _ensure_db_metrics() -> Counter | None:
    global _db_queries
    if not _HAS_PROM:
        return None
    reg = _get_registry()
    if _db_queries is None:
        _db_queries = Counter(
            "db_queries_total",
            "Total database queries",
            ["operation"],
            registry=reg,
        )
    return _db_queries


def record_db_query(operation: str = "unknown") -> None:
    queries = _ensure_db_metrics()
    if queries is None:
        return
    queries.labels(operation=operation).inc()


# ---------------------------------------------------------------------------
# WebSocket connection gauge
# ---------------------------------------------------------------------------

_ws_connections: Gauge | None = None


def _ensure_ws_metrics() -> Gauge | None:
    global _ws_connections
    if not _HAS_PROM:
        return None
    reg = _get_registry()
    if _ws_connections is None:
        _ws_connections = Gauge(
            "ws_connections_current",
            "Current open WebSocket connections",
            registry=reg,
        )
    return _ws_connections


def inc_ws_connections(delta: int = 1) -> None:
    gauge = _ensure_ws_metrics()
    if gauge is None:
        return
    gauge.inc(delta)


def dec_ws_connections(delta: int = 1) -> None:
    gauge = _ensure_ws_metrics()
    if gauge is None:
        return
    gauge.dec(delta)


# ---------------------------------------------------------------------------
# Uptime gauge
# ---------------------------------------------------------------------------

_uptime: Gauge | None = None
_START_TIME: float = time.time()


def _ensure_uptime_metric() -> Gauge | None:
    global _uptime
    if not _HAS_PROM:
        return None
    reg = _get_registry()
    if _uptime is None:
        _uptime = Gauge(
            "uptime_seconds",
            "Service uptime in seconds",
            registry=reg,
        )
    return _uptime


def _update_uptime() -> None:
    gauge = _ensure_uptime_metric()
    if gauge is not None:
        gauge.set(time.time() - _START_TIME)


# Periodic updater (called from middleware on each request)
def _tick() -> None:
    _update_uptime()
