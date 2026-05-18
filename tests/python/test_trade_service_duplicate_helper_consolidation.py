from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _top_level_definition_names(relative_path: str) -> set[str]:
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    module = ast.parse(source)
    names: set[str] = set()
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def test_trade_service_main_stops_owning_duplicate_trade_runtime_helpers() -> None:
    definition_names = _top_level_definition_names("apps/trade-service/src/main.py")

    extracted_names = {
        "_serialize_account_info",
        "_serialize_position",
        "_ensure_broker_connected",
        "_ensure_order_projection_schema",
        "_get_broker",
    }
    assert definition_names.isdisjoint(extracted_names), (
        "apps/trade-service/src/main.py still owns duplicate trade runtime helpers: "
        f"{sorted(definition_names.intersection(extracted_names))}"
    )

    source = (ROOT / "apps" / "trade-service" / "src" / "main.py").read_text(encoding="utf-8")
    assert "legacy_trade_service._load_account_state(" in source
    assert "legacy_trade_service._load_orders_for_account(" in source


def test_trade_projection_schema_moves_to_legacy_outbox() -> None:
    app_source = (ROOT / "apps" / "trade-service" / "src" / "main.py").read_text(encoding="utf-8")
    outbox_source = (ROOT / "legacy_trade_service" / "outbox.py").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS trade_order_projections" not in app_source
    assert "idx_user_status_updated (user_id, status, updated_at)" in outbox_source


def test_trade_service_module_import_smoke_after_helper_consolidation() -> None:
    script = f"""
import importlib.util
from pathlib import Path

module_path = Path({str(ROOT / "apps" / "trade-service" / "src" / "main.py")!r})
spec = importlib.util.spec_from_file_location("trade_service_main", module_path)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)

assert hasattr(module, "app")
print("trade_service_duplicate_helper_consolidation_ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
