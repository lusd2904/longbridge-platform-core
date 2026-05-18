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


def test_trade_flow_split_modules_exist() -> None:
    expected = [
        "legacy_trade_service/trade_submit_flow.py",
        "legacy_trade_service/trade_cancel_flow.py",
    ]
    missing = [relative_path for relative_path in expected if not (ROOT / relative_path).exists()]
    assert not missing, f"missing trade flow split modules: {missing}"


def test_trade_commands_stops_owning_submit_and_cancel_flow_blocks() -> None:
    definition_names = _top_level_definition_names("legacy_trade_service/trade_commands.py")

    extracted_names = {
        "_create_submit_order_saga",
        "_raise_submit_reference_price_failure",
        "_complete_reference_price_step",
        "_run_submit_risk_gate",
        "_submit_to_broker",
        "_handle_submit_persistence_failure",
        "_persist_submitted_order",
        "_build_submit_success_response",
        "_submit_order",
        "_create_cancel_order_saga",
        "_raise_cancel_failure",
        "_build_cancel_success_response",
        "_cancel_order",
    }
    assert definition_names.isdisjoint(extracted_names), (
        "legacy_trade_service/trade_commands.py still owns submit/cancel flow responsibilities: "
        f"{sorted(definition_names.intersection(extracted_names))}"
    )

    source = (ROOT / "legacy_trade_service" / "trade_commands.py").read_text(encoding="utf-8")
    assert "from legacy_trade_service.trade_submit_flow import (" in source
    assert "from legacy_trade_service.trade_cancel_flow import (" in source


def test_trade_flow_modules_import_and_trade_commands_keeps_compat_exports() -> None:
    script = """
import importlib

submit_flow = importlib.import_module("legacy_trade_service.trade_submit_flow")
cancel_flow = importlib.import_module("legacy_trade_service.trade_cancel_flow")
trade_commands = importlib.import_module("legacy_trade_service.trade_commands")

assert hasattr(submit_flow, "_submit_order")
assert hasattr(submit_flow, "_persist_submitted_order")
assert hasattr(cancel_flow, "_cancel_order")
assert hasattr(trade_commands, "_submit_order")
assert hasattr(trade_commands, "_cancel_order")
print("trade_command_module_split_ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
