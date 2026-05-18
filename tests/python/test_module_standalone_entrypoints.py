from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


MODULES = {
    "frontend": ["start_web_portal.sh"],
    "platform": ["apps/platform/user-center", "apps/platform/api-gateway"],
    "market": ["apps/market/market-service"],
    "intelligence": ["apps/intelligence/analysis-service", "apps/intelligence/strategy-service"],
    "trading": ["apps/trading/trade-service"],
    "governance": ["apps/governance/risk-service"],
    "operations": ["apps/operations/scheduler-service"],
}


def test_module_docs_and_run_wrappers_exist() -> None:
    for module_name in MODULES:
        assert (ROOT / "apps" / module_name / "README.md").exists()
        assert (ROOT / "apps" / module_name / "run.sh").exists()


def test_start_module_dry_run_lists_expected_services() -> None:
    for module_name, expected_fragments in MODULES.items():
        env = os.environ.copy()
        env["REF_MODULE_DRY_RUN"] = "true"
        result = subprocess.run(
            ["bash", "scripts/start_module.sh", module_name],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        combined_output = f"{result.stdout}\n{result.stderr}"
        for fragment in expected_fragments:
            assert fragment in combined_output, f"{module_name} missing fragment: {fragment}"
