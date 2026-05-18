from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEGACY_SRC = ROOT / "backend-server" / "src"


def test_explicit_legacy_root_packages_exist() -> None:
    expected = [
        "api/__init__.py",
        "config/__init__.py",
        "core/__init__.py",
        "database/__init__.py",
        "market/__init__.py",
        "social/__init__.py",
        "strategy/__init__.py",
        "utils/__init__.py",
    ]
    missing = [relative_path for relative_path in expected if not (ROOT / relative_path).exists()]
    assert not missing, f"missing explicit legacy packages: {missing}"


def test_bootstrap_uses_explicit_root_packages_without_legacy_src_injection() -> None:
    script = f"""
import importlib
import sys
from pathlib import Path

from apps.runtime_shared.bootstrap import LEGACY_SRC, bootstrap_runtime

bootstrap_runtime()

assert str(LEGACY_SRC) not in sys.path, sys.path

api = importlib.import_module("api")
config = importlib.import_module("config")
core = importlib.import_module("core")
database = importlib.import_module("database")
market = importlib.import_module("market")
social = importlib.import_module("social")
strategy = importlib.import_module("strategy")
utils = importlib.import_module("utils")

assert Path(api.__file__).resolve() == Path({str(ROOT / "api" / "__init__.py")!r}).resolve()
assert Path(config.__file__).resolve() == Path({str(ROOT / "config" / "__init__.py")!r}).resolve()
assert Path(core.__file__).resolve() == Path({str(ROOT / "core" / "__init__.py")!r}).resolve()
assert Path(database.__file__).resolve() == Path({str(ROOT / "database" / "__init__.py")!r}).resolve()
assert Path(market.__file__).resolve() == Path({str(ROOT / "market" / "__init__.py")!r}).resolve()
assert Path(social.__file__).resolve() == Path({str(ROOT / "social" / "__init__.py")!r}).resolve()
assert Path(strategy.__file__).resolve() == Path({str(ROOT / "strategy" / "__init__.py")!r}).resolve()
assert Path(utils.__file__).resolve() == Path({str(ROOT / "utils" / "__init__.py")!r}).resolve()

assert hasattr(api, "create_app")

for name in [
    "config.settings",
    "utils.DbUtil",
    "core.analysis.HistoricalMarketDataService",
    "database.DbUtil",
    "api.data_routes",
]:
    assert importlib.util.find_spec(name) is not None, name
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_bootstrap_file_does_not_add_backend_server_src_to_import_paths() -> None:
    source = (ROOT / "shared" / "bootstrap.py").read_text(encoding="utf-8")
    runtime_source = (ROOT / "apps" / "runtime_shared" / "bootstrap.py").read_text(encoding="utf-8")
    assert "from apps.runtime_shared.bootstrap import *" in source
    assert "import_paths.append(LEGACY_SRC)" not in runtime_source
    assert "if legacy_compat_enabled():" not in runtime_source


def test_runtime_shared_bootstrap_uses_repo_root_not_backend_server_src() -> None:
    script = """
import sys
from apps.runtime_shared.bootstrap import LEGACY_SRC, REFACTOR_ROOT, bootstrap_runtime

bootstrap_runtime()

assert str(REFACTOR_ROOT) in sys.path
assert str(LEGACY_SRC) not in sys.path
print("runtime_shared_bootstrap_ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
