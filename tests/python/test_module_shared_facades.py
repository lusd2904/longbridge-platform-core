from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


ENTRYPOINTS = {
    "apps/platform/api-gateway/src/main.py": "from apps.platform.module_shared import",
    "apps/platform/user-center/src/main.py": "from apps.platform.module_shared import",
    "apps/market/market-service/src/main.py": "from apps.market.module_shared import",
    "apps/market/sentiment-service/src/main.py": "from apps.market.module_shared import",
    "apps/intelligence/analysis-service/src/main.py": "from apps.intelligence.module_shared import",
    "apps/intelligence/strategy-service/src/main.py": "from apps.intelligence.module_shared import",
    "apps/trading/trade-service/src/main.py": "from apps.trading.module_shared import",
    "apps/governance/risk-service/src/main.py": "from apps.governance.module_shared import",
    "apps/operations/scheduler-service/src/main.py": "from apps.operations.module_shared import",
}


def test_module_shared_facade_files_exist() -> None:
    expected = [
        "apps/runtime_shared/__init__.py",
        "apps/runtime_shared/app.py",
        "apps/runtime_shared/auth.py",
        "apps/runtime_shared/bootstrap.py",
        "apps/runtime_shared/health.py",
        "apps/runtime_shared/legacy_runtime.py",
        "apps/platform/module_shared.py",
        "apps/market/module_shared.py",
        "apps/market/longbridge_shared.py",
        "apps/market/longbridge_runtime.py",
        "apps/market/market_shared/boundary.py",
        "apps/intelligence/module_shared.py",
        "apps/intelligence/intelligence_shared/boundary.py",
        "apps/trading/module_shared.py",
        "apps/trading/trade_shared/boundary.py",
        "apps/governance/module_shared.py",
        "apps/governance/risk_shared/boundary.py",
        "apps/operations/module_shared.py",
        "apps/operations/longbridge_shared.py",
    ]
    missing = [relative_path for relative_path in expected if not (ROOT / relative_path).exists()]
    assert not missing, f"missing module shared facades: {missing}"


def test_service_entrypoints_use_module_shared_facades() -> None:
    for relative_path, expected_import in ENTRYPOINTS.items():
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert expected_import in source, f"{relative_path} missing module facade import"


def test_market_and_operations_surfaces_stop_importing_root_longbridge_directly() -> None:
    targets = [
        ("apps/market/module_shared.py", "from apps.market.longbridge_shared import"),
        ("apps/market/market-service/src/push_hub.py", "from apps.market.longbridge_shared import"),
        ("apps/operations/module_shared.py", "from apps.operations.longbridge_shared import"),
    ]
    for relative_path, expected_import in targets:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert expected_import in source, f"{relative_path} missing facade import"
        assert "from shared.longbridge import" not in source, f"{relative_path} still imports shared.longbridge directly"


def test_root_longbridge_becomes_market_owned_shim() -> None:
    source = (ROOT / "shared" / "longbridge.py").read_text(encoding="utf-8")
    assert "from apps.market.longbridge_runtime import *" in source


def test_market_owned_longbridge_runtime_is_used_by_rebuild_scripts() -> None:
    targets = [
        "scripts/rebuild_longbridge_kline.py",
        "scripts/rebuild_longbridge_us_options.py",
    ]
    for relative_path in targets:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "from apps.market.longbridge_runtime import" in source
        assert "from shared.longbridge import" not in source


def test_root_runtime_surfaces_become_runtime_shared_shims() -> None:
    expected = {
        "shared/app.py": "from apps.runtime_shared.app import *",
        "shared/auth.py": "from apps.runtime_shared.auth import *",
        "shared/bootstrap.py": "from apps.runtime_shared.bootstrap import *",
        "shared/health.py": "from apps.runtime_shared.health import *",
        "service_boundaries/runtime.py": "from apps.runtime_shared.legacy_runtime import *",
    }
    for relative_path, snippet in expected.items():
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert snippet in source, f"{relative_path} missing shim import"
