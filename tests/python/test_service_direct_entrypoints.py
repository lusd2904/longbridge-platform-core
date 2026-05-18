from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


SERVICES = {
    "apps/frontend/web-portal": "start_web_portal.sh",
    "apps/platform/api-gateway": "service=api-gateway dir=apps/platform/api-gateway port=5101",
    "apps/platform/user-center": "service=user-center dir=apps/platform/user-center port=8101",
    "apps/market/market-service": "service=market-service dir=apps/market/market-service port=8102",
    "apps/market/sentiment-service": "service=sentiment-service dir=apps/market/sentiment-service port=8106",
    "apps/intelligence/analysis-service": "service=analysis-service dir=apps/intelligence/analysis-service port=8103",
    "apps/intelligence/strategy-service": "service=strategy-service dir=apps/intelligence/strategy-service port=8104",
    "apps/trading/trade-service": "service=trade-service dir=apps/trading/trade-service port=8105",
    "apps/governance/risk-service": "service=risk-service dir=apps/governance/risk-service port=8108",
    "apps/operations/scheduler-service": "service=scheduler-service dir=apps/operations/scheduler-service port=8107",
}


def test_service_run_wrappers_exist() -> None:
    missing = [path for path in SERVICES if not (ROOT / path / "run.sh").exists()]
    assert not missing, f"missing service run wrappers: {missing}"


def test_service_run_wrappers_support_dry_run() -> None:
    for relative_path, expected_fragment in SERVICES.items():
        env = os.environ.copy()
        env["REF_SERVICE_DRY_RUN"] = "true"
        result = subprocess.run(
            ["bash", "./run.sh"],
            cwd=ROOT / relative_path,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        combined_output = f"{result.stdout}\n{result.stderr}"
        assert expected_fragment in combined_output, f"{relative_path} missing fragment: {expected_fragment}"
