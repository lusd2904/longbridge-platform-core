from __future__ import annotations

from apps.runtime_shared.health import build_alert, build_dependency_status, build_health_payload, summarize_status


def test_build_health_payload_exposes_unified_contract() -> None:
    deps = {
        "mysql": build_dependency_status("mysql", "healthy", detail="db ready"),
        "redis": build_dependency_status("redis", "degraded", detail="cache lagging"),
    }

    payload = build_health_payload(
        service="trade-service",
        version="0.2.0",
        port=8105,
        status=summarize_status(deps.values()),
        deps=deps,
        broker_connectivity={"longbridge": {"status": "healthy"}},
        alerts=[build_alert("trade-outbox-backlog", "warning", "存在事件积压")],
        capabilities=["order-submit"],
    )

    assert payload["service"] == "trade-service"
    assert payload["version"] == "0.2.0"
    assert payload["port"] == 8105
    assert payload["status"] == "degraded"
    assert payload["status_text"] == "部分受限"
    assert "checked_at" in payload
    assert payload["deps"]["mysql"]["status"] == "healthy"
    assert payload["deps"]["redis"]["status"] == "degraded"
    assert payload["brokerConnectivity"]["longbridge"]["status"] == "healthy"
    assert payload["alerts"][0]["code"] == "trade-outbox-backlog"
    assert payload["capabilities"] == ["order-submit"]


def test_summarize_status_prioritizes_unhealthy_then_degraded() -> None:
    healthy = [build_dependency_status("mysql", "healthy")]
    degraded = [build_dependency_status("redis", "degraded")]
    unhealthy = [build_dependency_status("kafka", "unhealthy")]

    assert summarize_status(healthy) == "healthy"
    assert summarize_status(healthy, degraded) == "degraded"
    assert summarize_status(healthy, degraded, unhealthy) == "unhealthy"
