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


def test_trade_runtime_internal_modules_exist() -> None:
    expected = [
        "legacy_trade_service/models.py",
        "legacy_trade_service/outbox.py",
        "legacy_trade_service/account_views.py",
    ]
    missing = [relative_path for relative_path in expected if not (ROOT / relative_path).exists()]
    assert not missing, f"missing trade runtime split modules: {missing}"


def test_trade_runtime_main_stops_owning_outbox_and_account_view_blocks() -> None:
    definition_names = _top_level_definition_names("legacy_trade_service/main.py")

    extracted_names = {
        "OrderSubmitRequest",
        "OrderCancelRequest",
        "AuthUser",
        "_ensure_trade_schema",
        "_ensure_trade_outbox_columns",
        "_serialize_payload",
        "_serialize_datetime",
        "_insert_step",
        "_insert_outbox",
        "_create_saga",
        "_update_saga_status",
        "_record_saga_step",
        "_record_outbox_event",
        "_upsert_projection",
        "OutboxRelay",
        "_ensure_broker_connected",
        "_load_account_row",
        "_get_broker_for_user",
        "_account_display_name",
        "_serialize_order",
        "_load_orders_for_account",
        "_list_orders",
        "_serialize_account_summary",
        "_serialize_position",
        "_list_accounts",
        "_get_default_account",
        "_load_account_positions",
        "_load_account_state",
        "_build_account_summary_payload",
        "_build_order_stream_event",
    }
    assert definition_names.isdisjoint(extracted_names), (
        "legacy_trade_service/main.py still owns split responsibilities: "
        f"{sorted(definition_names.intersection(extracted_names))}"
    )

    source = (ROOT / "legacy_trade_service" / "main.py").read_text(encoding="utf-8")
    assert "from legacy_trade_service.models import (" in source
    assert "from legacy_trade_service.outbox import (" in source
    assert "from legacy_trade_service.account_views import (" in source


def test_trade_runtime_split_modules_import_and_main_keeps_compat_exports() -> None:
    script = """
import importlib

models = importlib.import_module("legacy_trade_service.models")
outbox = importlib.import_module("legacy_trade_service.outbox")
account_views = importlib.import_module("legacy_trade_service.account_views")
trade_main = importlib.import_module("legacy_trade_service.main")

assert hasattr(models, "AuthUser")
assert hasattr(outbox, "OutboxRelay")
assert hasattr(outbox, "_ensure_trade_schema")
assert hasattr(account_views, "_serialize_order")
assert hasattr(account_views, "_build_account_summary_payload")
assert hasattr(trade_main, "outbox_relay")
assert hasattr(trade_main, "_ensure_trade_schema")
assert hasattr(trade_main, "_serialize_order")
print("trade_runtime_internal_split_ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
