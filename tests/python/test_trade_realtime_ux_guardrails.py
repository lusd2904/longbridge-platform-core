from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TRADE_SERVICE_MAIN = ROOT / "apps" / "trading" / "trade-service" / "src" / "main.py"
TRADING_VIEW = ROOT / "apps" / "frontend" / "web-portal" / "src" / "views" / "Trading.vue"
WEBSOCKET_COMPOSABLE = ROOT / "apps" / "frontend" / "web-portal" / "src" / "composables" / "useWebSocket.js"


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_trade_service_build_account_runtime_hints_marks_tiger_non_prod_as_paper() -> None:
    module = _load_module("trade_service_runtime_hints_test", TRADE_SERVICE_MAIN)

    hints = module._build_account_runtime_hints(
        {"broker_type": "tiger", "display_name": "Tiger - DEMO"},
        {"broker_type": "tiger", "tiger_env": "SIMULATE"},
    )

    assert hints["tradingMode"] == "paper"
    assert hints["isPaper"] is True
    assert "模拟" in hints["safetyMessage"] or "演练" in hints["safetyMessage"]


def test_trade_service_build_account_runtime_hints_marks_tiger_prod_as_live() -> None:
    module = _load_module("trade_service_runtime_hints_live_test", TRADE_SERVICE_MAIN)

    hints = module._build_account_runtime_hints(
        {"broker_type": "tiger", "display_name": "Tiger - PROD"},
        {"broker_type": "tiger", "tiger_env": "PROD"},
    )

    assert hints["tradingMode"] == "live"
    assert hints["isPaper"] is False
    assert "实盘" in hints["accountModeLabel"]


def test_trade_service_marks_missing_longbridge_observability_as_disabled() -> None:
    module = _load_module("trade_service_longbridge_health_disabled_test", TRADE_SERVICE_MAIN)

    status = module._build_longbridge_connectivity_status({
        "tradeContextAttachCount": 0,
        "quoteContextAttachCount": 0,
        "lastError": "",
        "lastSuccessAt": "",
    })

    assert status["status"] == "disabled"
    assert status["configured"] is False
    assert status["enabled"] is False
    assert "模拟账户保护" in status["status_text"]


def test_trade_service_marks_longbridge_observability_healthy_after_success() -> None:
    module = _load_module("trade_service_longbridge_health_success_test", TRADE_SERVICE_MAIN)

    status = module._build_longbridge_connectivity_status({
        "lastError": "",
        "lastSuccessAt": "2026-06-08T02:54:19",
        "lastSuccessOperation": "orders",
    })

    assert status["status"] == "healthy"


def test_trade_service_live_failure_snapshot_meta_is_marked_degraded(monkeypatch) -> None:
    module = _load_module("trade_service_snapshot_degraded_test", TRADE_SERVICE_MAIN)

    monkeypatch.setattr(module, "_get_account_or_404", lambda user_id, account_id: {"id": account_id, "account_id": "ACC-2"})
    monkeypatch.setattr(module.AccountAssetSnapshotService, "get_latest", lambda user_id, account_id: {"snapshotAt": "2026-05-20 10:00:00"})
    monkeypatch.setattr(module.PositionSnapshotService, "get_latest", lambda user_id, account_id: [])
    monkeypatch.setattr(module.legacy_trade_service, "_load_account_state", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("broker down")))

    state = module._build_account_state(user_id=3, account_id=8)

    assert state["dataSource"] == "snapshot"
    assert state["meta"]["degraded"] is True
    assert state["meta"]["fallbackSource"] == "snapshot"
    assert state["meta"]["requestedMode"] == "live"
    assert state["meta"]["warnings"]


def test_trading_view_contains_safety_panel_and_zero_quote_detail_format() -> None:
    source = TRADING_VIEW.read_text(encoding="utf-8")

    assert "trade-safety-panel" in source
    assert "quoteDataStatusTag" in source
    assert "formatQuoteDetailPrice" in source


def test_websocket_quote_normalizer_preserves_quote_ready_and_data_status() -> None:
    source = WEBSOCKET_COMPOSABLE.read_text(encoding="utf-8")

    assert "quoteReady: Boolean(" in source
    assert "dataStatus: row.dataStatus" in source
