from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOUNDARY_PACKAGE = ROOT / "service_boundaries"


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_domain_boundary_package_exists() -> None:
    expected_files = [
        "__init__.py",
        "_legacy_loader.py",
        "runtime.py",
        "market_boundary.py",
        "analysis_boundary.py",
        "risk_boundary.py",
        "trade_boundary.py",
    ]
    missing = [name for name in expected_files if not (BOUNDARY_PACKAGE / name).exists()]
    assert not missing, f"missing service_boundaries files: {missing}"


def test_application_sources_stop_importing_shared_legacy_compat() -> None:
    targets = [
        "apps/market-service/src/main.py",
        "apps/market-service/src/stock_pool_query.py",
        "apps/analysis-service/src/main.py",
        "apps/risk-service/src/main.py",
        "apps/risk-service/scheduler/src/main.py",
        "apps/trade-service/src/main.py",
    ]
    offenders = []
    for relative_path in targets:
        source = _read(relative_path)
        if "shared.legacy_compat" in source:
            offenders.append(relative_path)

    assert not offenders, f"shared.legacy_compat still imported by: {offenders}"


def test_application_sources_use_domain_boundaries() -> None:
    expected_imports = {
        "apps/market-service/src/main.py": "from apps.market.module_shared import",
        "apps/market-service/src/stock_pool_query.py": "from apps.market.market_shared.boundary import",
        "apps/analysis-service/src/main.py": "from apps.intelligence.module_shared import",
        "apps/risk-service/src/main.py": "from apps.governance.module_shared import",
        "apps/risk-service/scheduler/src/main.py": "from apps.operations.module_shared import",
        "apps/trade-service/src/main.py": "from apps.trading.module_shared import",
    }
    missing = []
    for relative_path, snippet in expected_imports.items():
        if snippet not in _read(relative_path):
            missing.append(f"{relative_path}: {snippet}")

    assert not missing, f"domain boundary imports missing: {missing}"


def test_legacy_compat_monolith_removed() -> None:
    assert not (ROOT / "shared" / "legacy_compat.py").exists()


def test_trade_boundary_moves_under_trading_module_with_root_shim() -> None:
    module_boundary = ROOT / "apps" / "trading" / "trade_shared" / "boundary.py"
    shim_boundary = ROOT / "service_boundaries" / "trade_boundary.py"

    assert module_boundary.exists()
    shim_source = shim_boundary.read_text(encoding="utf-8")
    assert "from apps.trading.trade_shared.boundary import" in shim_source


def test_market_boundary_moves_under_market_module_with_root_shim() -> None:
    module_boundary = ROOT / "apps" / "market" / "market_shared" / "boundary.py"
    shim_boundary = ROOT / "service_boundaries" / "market_boundary.py"

    assert module_boundary.exists()
    shim_source = shim_boundary.read_text(encoding="utf-8")
    assert "from apps.market.market_shared.boundary import" in shim_source


def test_analysis_boundary_moves_under_intelligence_module_with_root_shim() -> None:
    module_boundary = ROOT / "apps" / "intelligence" / "intelligence_shared" / "boundary.py"
    shim_boundary = ROOT / "service_boundaries" / "analysis_boundary.py"

    assert module_boundary.exists()
    shim_source = shim_boundary.read_text(encoding="utf-8")
    assert "from apps.intelligence.intelligence_shared.boundary import" in shim_source


def test_risk_boundary_moves_under_governance_module_with_root_shim() -> None:
    module_boundary = ROOT / "apps" / "governance" / "risk_shared" / "boundary.py"
    shim_boundary = ROOT / "service_boundaries" / "risk_boundary.py"

    assert module_boundary.exists()
    shim_source = shim_boundary.read_text(encoding="utf-8")
    assert "from apps.governance.risk_shared.boundary import" in shim_source
