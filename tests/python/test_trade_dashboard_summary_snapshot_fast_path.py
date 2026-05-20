from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "apps/trading/trade-service/src/main.py"


def _load_trade_service_module():
    spec = importlib.util.spec_from_file_location("trade_service_main_for_tests", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_snapshot_summary_state_avoids_loading_full_positions(monkeypatch) -> None:
    module = _load_trade_service_module()

    monkeypatch.setattr(module, "_get_account_or_404", lambda user_id, account_id: {"id": account_id, "account_id": "ACC-1"})
    monkeypatch.setattr(
        module.AccountAssetSnapshotService,
        "get_latest",
        lambda user_id, account_id: {
            "currency": "USD",
            "cash": 1200.5,
            "marketValue": 3400.25,
            "totalAssets": 4600.75,
            "buyingPower": 1800.0,
            "maintenanceMargin": 99.5,
            "todayPnL": 88.12,
            "todayPnLPercent": 1.91,
            "snapshotAt": "2026-05-20 09:30:00",
            "payload": {
                "orderCount": 7,
                "recentOrders": [{"orderId": "o-1"}],
            },
        },
    )

    def fail_get_latest(*args, **kwargs):
        raise AssertionError("summary fast path should not load full positions snapshot")

    monkeypatch.setattr(module.PositionSnapshotService, "get_latest", fail_get_latest)
    monkeypatch.setattr(module.PositionSnapshotService, "get_latest_count", lambda user_id, account_id: 3)

    state = module._build_snapshot_summary_state(user_id=9, account_id=11)
    payload = module._build_dashboard_summary_payload(
        state=state,
        data_source=state.get("dataSource") or "snapshot",
        default_mode="database",
    )

    assert state["positionCount"] == 3
    assert state["orders"] == [{"orderId": "o-1"}]
    assert payload["today_pnl"] == 88.12
    assert payload["today_pnl_percent"] == 1.91
    assert payload["total_assets"] == 4600.75
    assert payload["meta"]["positionCount"] == 3
    assert payload["meta"]["orderCount"] == 7


def test_empty_snapshot_summary_can_still_build_fallback_payload(monkeypatch) -> None:
    module = _load_trade_service_module()

    monkeypatch.setattr(module, "_get_account_or_404", lambda user_id, account_id: {"id": account_id, "account_id": "ACC-1"})
    monkeypatch.setattr(module.AccountAssetSnapshotService, "get_latest", lambda user_id, account_id: {})
    monkeypatch.setattr(module.PositionSnapshotService, "get_latest_count", lambda user_id, account_id: 0)

    state = module._build_snapshot_summary_state(user_id=9, account_id=11)
    payload = module._build_dashboard_summary_payload(
        state=state,
        data_source=state.get("dataSource") or "snapshot",
        default_mode="database",
    )

    assert payload["source"] == "snapshot"
    assert payload["total_assets"] == 0
    assert payload["meta"]["positionCount"] == 0
