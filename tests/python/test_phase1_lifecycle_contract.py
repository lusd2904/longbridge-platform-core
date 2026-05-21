from __future__ import annotations

import importlib.util
import asyncio
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase1_stop_script_covers_agno_sidecar() -> None:
    source = (ROOT / "scripts/stop_phase1_stack.sh").read_text(encoding="utf-8")

    assert '"$ROOT_DIR/scripts/stop_service.sh" agno-sidecar "${REF_AGNO_SIDECAR_PORT:-3200}"' in source


def test_platform_health_contract_checks_agno_sidecar() -> None:
    module = _load_module("check_platform_health_test", ROOT / "scripts/check_platform_health.py")

    assert module.SERVICE_PORTS["agno-sidecar"] == 3200


def test_gateway_registry_checks_agno_sidecar() -> None:
    module = _load_module("api_gateway_main_test", ROOT / "apps/platform/api-gateway/src/main.py")
    agno = module.SERVICE_REGISTRY["agno-sidecar"]

    assert agno["port"] == 3200
    assert agno["basePath"] == "/api/v1/agent/watchlist-review"
    assert "watchlist review" in agno["description"]


def test_web_portal_compose_dependencies_cover_proxy_upstreams() -> None:
    source = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    match = re.search(r"\n  web-portal:\n(?P<body>.*?)(?:\nnetworks:|\Z)", source, flags=re.S)
    assert match, "web-portal service block missing"
    body = match.group("body")

    for service_name in [
        "api-gateway",
        "user-center",
        "market-service",
        "analysis-service",
        "strategy-service",
        "trade-service",
        "sentiment-service",
        "scheduler-service",
        "risk-service",
    ]:
        assert f"      {service_name}:" in body


def test_service_map_keeps_watchlist_in_market_domain() -> None:
    source = (ROOT / "docs/service-map.yaml").read_text(encoding="utf-8")
    user_center_block = re.search(r"  - code: user-center\n(?P<body>.*?)(?=\n  - code:|\Z)", source, flags=re.S)
    market_block = re.search(r"  - code: market-service\n(?P<body>.*?)(?=\n  - code:|\Z)", source, flags=re.S)
    assert user_center_block and market_block

    assert "watchlist" not in user_center_block.group("body")
    assert "stock pool and watchlist" in market_block.group("body")


def test_agno_sidecar_health_matches_platform_contract() -> None:
    module = _load_module("agno_sidecar_main_test", ROOT / "apps/intelligence/agno-sidecar/src/main.py")
    payload = asyncio.run(module.health())

    assert payload["service"] == "agno-sidecar"
    assert payload["version"] == module.app.version
    assert payload["status"] == "healthy"
    assert payload["status_text"]
    assert payload["port"] == 3200
    assert payload["checked_at"]
    assert "ai-gateway" in payload["deps"]
    assert payload["brokerConnectivity"] == {}
    assert payload["safety"] == "review-only"
