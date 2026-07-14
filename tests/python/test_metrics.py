"""Tests for apps.runtime_shared.metrics module.

Covers:
- Middleware correctly records HTTP request counters and histograms
- /metrics endpoint returns Prometheus text format
- Graceful degradation when prometheus-client is absent
- AI / Redis / DB / WS helper functions
- Endpoint path normalization
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is on sys.path so apps.runtime_shared resolves
ROOT = Path(__file__).resolve().parents[2]  # platform-core
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_prom_state():
    """Reset module-level metric singletons between tests."""
    import apps.runtime_shared.metrics as mod

    mod._registry = None
    mod._HTTP_REQUESTS = None
    mod._HTTP_DURATION = None
    mod._ai_calls = None
    mod._ai_duration = None
    mod._ai_cost = None
    mod._redis_ops = None
    mod._db_queries = None
    mod._ws_connections = None
    mod._uptime = None

    yield

    # Cleanup
    mod._registry = None
    mod._HTTP_REQUESTS = None
    mod._HTTP_DURATION = None
    mod._ai_calls = None
    mod._ai_duration = None
    mod._ai_cost = None
    mod._redis_ops = None
    mod._db_queries = None
    mod._ws_connections = None
    mod._uptime = None


# ---------------------------------------------------------------------------
# Prometheus-available path
# ---------------------------------------------------------------------------


class TestMetricsMiddleware:
    """HTTP request metrics via the middleware."""

    def test_metrics_middleware_exists(self):
        from apps.runtime_shared.metrics import MetricsMiddleware

        assert MetricsMiddleware is not None

    def test_middleware_records_requests(self):
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route
        from starlette.testclient import TestClient

        from apps.runtime_shared.metrics import MetricsMiddleware, _get_registry

        def health(request):
            return PlainTextResponse("healthy")

        def catchall(request):
            return PlainTextResponse("ok")

        routes = [
            Route("/health", endpoint=health),
            Route("/{path:path}", endpoint=catchall),
        ]

        app = Starlette(routes=routes)
        app.add_middleware(MetricsMiddleware)

        client = TestClient(app, raise_server_exceptions=False)

        # Hit various paths
        resp = client.get("/health")
        assert resp.status_code == 200

        resp = client.get("/api/v1/market/symbols/AAPL")
        assert resp.status_code == 200

        resp = client.get("/api/v1/market/symbols/00700.HK")
        assert resp.status_code == 200

        # Verify metrics were recorded
        reg = _get_registry()
        assert reg is not None

        # Parse the output
        from prometheus_client import generate_latest

        output = generate_latest(reg).decode()

        assert "http_requests_total" in output
        assert 'method="GET"' in output
        assert 'endpoint="/health"' in output
        # Static routes should be recorded as-is (middleware sees the raw path)
        assert 'endpoint="/api/v1/market/symbols/AAPL"' in output

    def test_metrics_endpoint_returns_prometheus_text(self):
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route
        from starlette.testclient import TestClient

        from apps.runtime_shared.metrics import MetricsMiddleware, mount_metrics_route

        def dummy(request):
            return PlainTextResponse("ok")

        app = Starlette(routes=[Route("/", endpoint=dummy)])
        app.add_middleware(MetricsMiddleware)
        mount_metrics_route(app)

        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "http_requests_total" in resp.text


class TestRecordHelpers:
    """AI / Redis / DB / WS recording helpers."""

    def test_record_ai_call(self):
        from apps.runtime_shared.metrics import (
            _ensure_ai_metrics,
            _get_registry,
            record_ai_call,
        )

        record_ai_call(provider="openai", model="gpt-4", duration_seconds=2.5, cost_usd=0.03)

        calls, dur, cost = _ensure_ai_metrics()
        assert calls is not None

        # Verify via registry
        from prometheus_client import generate_latest

        output = generate_latest(_get_registry()).decode()
        assert "ai_calls_total" in output
        assert 'provider="openai"' in output
        assert 'model="gpt-4"' in output

    def test_record_redis_op(self):
        from apps.runtime_shared.metrics import _get_registry, record_redis_op

        record_redis_op(operation="GET", status="ok")
        record_redis_op(operation="SET", status="error")

        from prometheus_client import generate_latest

        output = generate_latest(_get_registry()).decode()
        assert 'redis_operations_total{operation="GET"' in output
        assert 'operation="SET"' in output

    def test_record_db_query(self):
        from apps.runtime_shared.metrics import _get_registry, record_db_query

        record_db_query(operation="SELECT")
        record_db_query(operation="INSERT")

        from prometheus_client import generate_latest

        output = generate_latest(_get_registry()).decode()
        assert 'db_queries_total{operation="SELECT"}' in output

    def test_ws_connection_gauge(self):
        from apps.runtime_shared.metrics import (
            _get_registry,
            dec_ws_connections,
            inc_ws_connections,
        )

        inc_ws_connections(3)
        dec_ws_connections(1)

        from prometheus_client import generate_latest

        output = generate_latest(_get_registry()).decode()
        assert "ws_connections_current" in output


class TestGracefulDegradation:
    """Ensure metrics module works when prometheus-client is absent."""

    def test_mount_metrics_noop_without_prom(self):
        from starlette.applications import Starlette
        from starlette.routing import Route

        def dummy(request):
            from starlette.responses import PlainTextResponse

            return PlainTextResponse("ok")

        # Patch _HAS_PROM to simulate absence
        import apps.runtime_shared.metrics as mod

        original = mod._HAS_PROM

        try:
            mod._HAS_PROM = False
            mod._registry = None

            app = Starlette(routes=[Route("/", endpoint=dummy)])
            mod.mount_metrics_route(app)

            from starlette.testclient import TestClient

            client = TestClient(app, raise_server_exceptions=False)

            # /metrics should not exist when prometheus is absent
            resp = client.get("/metrics")
            assert resp.status_code == 404
        finally:
            mod._HAS_PROM = original


class TestNormalizeEndpoint:
    """Test endpoint path normalization."""

    def test_normalize_preserves_static_paths(self):
        from apps.runtime_shared.metrics import _normalize_endpoint

        assert _normalize_endpoint("/health", None) == "/health"
        assert _normalize_endpoint("/api/v1/auth/info", None) == "/api/v1/auth/info"

    def test_normalize_replaces_uuids(self):
        from apps.runtime_shared.metrics import _normalize_endpoint

        uuid = "550e8400-e29b-41d4-a716-446655440000"
        result = _normalize_endpoint(f"/api/v1/analysis/agent/runs/{uuid}", None)
        assert "{param}" in result

    def test_normalize_replaces_digit_segments(self):
        from apps.runtime_shared.metrics import _normalize_endpoint

        result = _normalize_endpoint("/api/v1/trade/accounts/12345/orders", None)
        assert "{param}" in result

    def test_normalize_prefers_route_name(self):
        from apps.runtime_shared.metrics import _normalize_endpoint

        result = _normalize_endpoint("/api/v1/market/symbols/AAPL", "get_symbol_overview")
        assert result == "get_symbol_overview"
