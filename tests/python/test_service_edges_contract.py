from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INTERNAL_SERVICES = {
    "web-portal",
    "api-gateway",
    "user-center",
    "market-service",
    "analysis-service",
    "strategy-service",
    "trade-service",
    "sentiment-service",
    "scheduler-service",
    "risk-service",
    "agno-sidecar",
}
EXTERNAL_TARGETS = {
    "ai-gateway",
    "longbridge-cli",
    "skshare",
    "longbridge-quote",
}
LONGBRIDGE_CREDENTIAL_SERVICES = {
    "market-service",
    "scheduler-service",
    "trade-service",
}


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_service_map() -> dict:
    script = "require 'yaml'; require 'json'; puts JSON.generate(YAML.load_file(ARGV[0]))"
    result = subprocess.run(
        ["ruby", "-e", script, str(ROOT / "docs/service-map.yaml")],
        check=True,
        capture_output=True,
        text=True,
    )
    import json

    return json.loads(result.stdout)


def _service_block(source: str, service_name: str) -> str:
    pattern = rf"\n  {re.escape(service_name)}:\n(?P<body>.*?)(?=\n  [a-zA-Z0-9_-]+:\n|\nnetworks:|\Z)"
    match = re.search(pattern, source, flags=re.S)
    assert match, f"{service_name} compose block missing"
    return match.group("body")


def test_service_edges_reference_known_services() -> None:
    service_map = _load_service_map()
    service_codes = {item["code"] for item in service_map["services"]}
    edges = service_map.get("service_edges") or []

    assert service_codes == INTERNAL_SERVICES
    assert edges, "docs/service-map.yaml must define service_edges"

    for edge in edges:
        assert edge["from"] in service_codes, f"unknown source service: {edge}"
        target = edge["to"]
        assert target in service_codes or target in EXTERNAL_TARGETS, f"unknown edge target: {edge}"
        assert edge.get("kind"), f"edge kind missing: {edge}"
        assert edge.get("purpose"), f"edge purpose missing: {edge}"


def test_gateway_registry_covers_health_probe_edges() -> None:
    service_map = _load_service_map()
    gateway_probe_targets = {
        edge["to"]
        for edge in service_map["service_edges"]
        if edge["from"] == "api-gateway" and edge["kind"] == "health_probe"
    }
    gateway = _load_module("api_gateway_edges_test", ROOT / "apps/platform/api-gateway/src/main.py")

    assert gateway_probe_targets == set(gateway.SERVICE_REGISTRY)
    for service_name in gateway_probe_targets:
        registry_entry = gateway.SERVICE_REGISTRY[service_name]
        assert registry_entry["basePath"].startswith("/api/v1/")
        assert registry_entry["port"]
        assert registry_entry["url"].startswith("http")


def test_portal_proxy_edges_match_nginx_vite_and_compose() -> None:
    service_map = _load_service_map()
    portal_edges = [
        edge
        for edge in service_map["service_edges"]
        if edge["from"] == "web-portal" and edge["kind"] == "frontend_proxy"
    ]
    compose_source = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    web_block = _service_block(compose_source, "web-portal")
    nginx_source = (ROOT / "apps/frontend/web-portal/nginx.conf").read_text(encoding="utf-8")
    vite_source = (ROOT / "apps/frontend/web-portal/vite.config.js").read_text(encoding="utf-8")

    assert portal_edges, "web-portal frontend_proxy edges missing"
    for edge in portal_edges:
        target = edge["to"]
        proxy_path = edge["path"]
        assert f"      {target}:" in web_block, f"web-portal compose depends_on missing {target}"
        assert f"location {proxy_path}/" in nginx_source, f"nginx proxy missing {proxy_path}"
        assert f"'{proxy_path}'" in vite_source, f"Vite proxy missing {proxy_path}"


def test_compose_service_dependencies_match_service_edges() -> None:
    service_map = _load_service_map()
    compose_source = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    edge_targets_by_source: dict[str, set[str]] = {}
    for edge in service_map["service_edges"]:
        if edge["to"] in INTERNAL_SERVICES and edge["kind"] in {"health_probe", "service_call"}:
            edge_targets_by_source.setdefault(edge["from"], set()).add(edge["to"])

    for service_name, expected_targets in edge_targets_by_source.items():
        if service_name == "web-portal":
            continue
        block = _service_block(compose_source, service_name)
        for target in expected_targets:
            assert f"      {target}:" in block, f"{service_name} compose depends_on missing {target}"


def test_longbridge_credentials_are_mounted_only_on_direct_cli_callers() -> None:
    compose_source = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    backend_template = re.search(
        r"\nx-backend-service: &backend-service\n(?P<body>.*?)(?=\n\nx-|\n\nservices:|\Z)",
        compose_source,
        flags=re.S,
    )
    assert backend_template, "x-backend-service compose template missing"
    assert "/root/.longbridge" not in backend_template.group("body")
    assert "x-longbridge-cli-volumes: &longbridge-cli-volumes" in compose_source

    mounted_services = set()
    for service_name in INTERNAL_SERVICES - {"web-portal"}:
        block = _service_block(compose_source, service_name)
        if "*longbridge-cli-volumes" in block or "/root/.longbridge" in block:
            mounted_services.add(service_name)

    assert mounted_services == LONGBRIDGE_CREDENTIAL_SERVICES

    service_map = _load_service_map()
    direct_longbridge_callers = {
        edge["from"]
        for edge in service_map["service_edges"]
        if edge["to"] in {"longbridge-cli", "longbridge-quote"}
    }
    assert direct_longbridge_callers == LONGBRIDGE_CREDENTIAL_SERVICES
