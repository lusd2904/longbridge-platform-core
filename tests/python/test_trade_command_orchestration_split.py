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


def test_trade_command_module_exists() -> None:
    expected = ["legacy_trade_service/trade_commands.py"]
    missing = [relative_path for relative_path in expected if not (ROOT / relative_path).exists()]
    assert not missing, f"missing trade command orchestration modules: {missing}"


def test_trade_runtime_main_stops_owning_trade_command_orchestration() -> None:
    definition_names = _top_level_definition_names("legacy_trade_service/main.py")

    extracted_names = {
        "_normalize_action",
        "_normalize_order_type",
        "_quote_last_price",
        "_load_reference_price_snapshot",
        "_load_reference_price",
        "_reference_price_meta",
        "_trade_error_detail",
        "_run_order_risk_check",
        "_audit_trade",
        "_submit_order",
        "_cancel_order",
    }
    assert definition_names.isdisjoint(extracted_names), (
        "legacy_trade_service/main.py still owns trade command orchestration responsibilities: "
        f"{sorted(definition_names.intersection(extracted_names))}"
    )

    source = (ROOT / "legacy_trade_service" / "main.py").read_text(encoding="utf-8")
    assert "from legacy_trade_service.trade_commands import (" in source


def test_trade_command_module_imports_and_main_keeps_compat_exports() -> None:
    script = """
import importlib

trade_commands = importlib.import_module("legacy_trade_service.trade_commands")
trade_main = importlib.import_module("legacy_trade_service.main")

assert hasattr(trade_commands, "_submit_order")
assert hasattr(trade_commands, "_cancel_order")
assert hasattr(trade_commands, "_trade_error_detail")
assert hasattr(trade_main, "_submit_order")
assert hasattr(trade_main, "_cancel_order")
print("trade_command_orchestration_split_ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
