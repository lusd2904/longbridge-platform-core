from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend-server" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from core.account.RiskManager import RiskConfig, RiskManager, RiskLevel  # noqa: E402


def test_risk_manager_does_not_reject_sub_1000_usd_one_share_order() -> None:
    manager = RiskManager(RiskConfig(max_position_ratio=1.0, min_single_order_value=0))

    passed, message, level = manager.check_order_risk(
        symbol="AAPL.US",
        side="BUY",
        quantity=1,
        price=180,
        account_info={"total_equity": 5000},
        positions=[],
    )

    assert passed is True
    assert message == "风险检查通过"
    assert level == RiskLevel.LOW
