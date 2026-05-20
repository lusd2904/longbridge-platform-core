from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _function_source(relative_path: str, function_name: str) -> str:
    path = ROOT / relative_path
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"{function_name} not found in {relative_path}")


def test_risk_snapshot_endpoint_stays_snapshot_only() -> None:
    source = _function_source("apps/governance/risk-service/src/main.py", "risk_overview_snapshot")

    assert "_build_risk_snapshot_payload(" in source
    assert "_load_risk_orders(" not in source
    assert "build_risk_overview(" not in source


def test_risk_overview_defaults_to_snapshot_with_explicit_realtime() -> None:
    source = _function_source("apps/governance/risk-service/src/main.py", "risk_overview")

    assert "realtime: bool = Query(default=False)" in source
    assert "if not realtime:" in source
    assert "_build_risk_snapshot_payload(" in source
    assert "build_risk_overview(" in source
    assert source.index("if not realtime:") < source.index("try:")


def test_trade_orders_default_uses_projection_without_live_fallback() -> None:
    source = _function_source("apps/trading/trade-service/src/main.py", "get_orders")

    assert "realtime: bool = Query(default=False)" in source
    assert "if realtime:" in source
    assert "_list_projected_orders(" in source
    assert "allow_fallback=False" in source


def test_trade_fast_order_route_is_registered_before_legacy_mount() -> None:
    source = (ROOT / "apps/trading/trade-service/src/main.py").read_text(encoding="utf-8")

    route_index = source.index('@app.get("/api/v1/trade/orders")')
    mount_index = source.index('app.mount("/api/v1/trade", legacy_trade_service.app)')
    assert route_index < mount_index


def test_trade_dashboard_summary_snapshot_path_avoids_full_snapshot_state() -> None:
    source = _function_source("apps/trading/trade-service/src/main.py", "get_dashboard_summary")

    assert "_build_snapshot_summary_state(" in source
    assert "_build_snapshot_state(" not in source
