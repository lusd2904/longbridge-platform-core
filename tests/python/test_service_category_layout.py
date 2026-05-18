from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_apps_category_layout_exists() -> None:
    expected = [
        "apps/frontend/web-portal",
        "apps/platform/api-gateway",
        "apps/platform/user-center",
        "apps/market/market-service",
        "apps/market/sentiment-service",
        "apps/intelligence/analysis-service",
        "apps/intelligence/strategy-service",
        "apps/trading/trade-service",
        "apps/governance/risk-service",
        "apps/operations/scheduler-service",
    ]
    missing = [relative_path for relative_path in expected if not (ROOT / relative_path).exists()]
    assert not missing, f"missing categorized app directories: {missing}"


def test_legacy_flat_paths_remain_available() -> None:
    expected = [
        "apps/web-portal",
        "apps/api-gateway",
        "apps/user-center",
        "apps/market-service",
        "apps/sentiment-service",
        "apps/analysis-service",
        "apps/strategy-service",
        "apps/trade-service",
        "apps/risk-service",
        "apps/risk-service/scheduler",
        "apps/strategy-service/sentiment-service",
    ]
    missing = [relative_path for relative_path in expected if not (ROOT / relative_path).exists()]
    assert not missing, f"missing compatibility app paths: {missing}"
