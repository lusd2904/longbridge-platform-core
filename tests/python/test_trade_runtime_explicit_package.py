from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_trade_runtime_explicit_package_exists() -> None:
    expected = [
        "legacy_trade_service/__init__.py",
        "legacy_trade_service/main.py",
    ]
    missing = [relative_path for relative_path in expected if not (ROOT / relative_path).exists()]
    assert not missing, f"missing legacy trade runtime package files: {missing}"


def test_trade_service_app_stops_dynamic_loading_file_path() -> None:
    source = (ROOT / "apps" / "trade-service" / "src" / "main.py").read_text(encoding="utf-8")
    module_shared_source = (ROOT / "apps" / "trading" / "module_shared.py").read_text(encoding="utf-8")
    assert "importlib.util" not in source
    assert "LEGACY_TRADE_PATH" not in source
    assert "_load_legacy_trade_module" not in source
    assert "from apps.trading.module_shared import" in source
    assert "from legacy_trade_service import main as legacy_trade_service" in module_shared_source


def test_old_trade_runtime_directory_removed() -> None:
    assert not (ROOT / "services" / "trade-service" / "src" / "main.py").exists()


def test_trade_runtime_package_import_smoke() -> None:
    script = """
import importlib

legacy_trade_service = importlib.import_module("legacy_trade_service.main")

assert hasattr(legacy_trade_service, "app")
assert hasattr(legacy_trade_service, "outbox_relay")
assert hasattr(legacy_trade_service, "_serialize_order")
print("trade_runtime_ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
