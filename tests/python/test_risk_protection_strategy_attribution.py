from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA_ROUTES = ROOT / "backend-server" / "src" / "api" / "data_routes.py"
RISK_SERVICE_MAIN = ROOT / "apps" / "governance" / "risk-service" / "src" / "main.py"


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_legacy_risk_order_schema_and_read_model_include_strategy_id() -> None:
    source = DATA_ROUTES.read_text(encoding="utf-8")

    assert "strategy_id INT NOT NULL DEFAULT 0" in source
    assert "idx_user_strategy_type_status" in source
    assert "uniq_user_strategy_symbol_type" in source
    assert "DROP INDEX uniq_user_symbol_type" in source
    assert "SELECT id, account_id, strategy_id, symbol" in source
    assert '"strategyId": int(row.get("strategy_id") or 0) or None' in source
    assert "INSERT INTO user_risk_orders (user_id, account_id, strategy_id, symbol" in source
    assert "strategy_id = VALUES(strategy_id)" in source


def test_risk_service_parses_and_persists_strategy_id(monkeypatch) -> None:
    module = _load_module("risk_service_strategy_id_parse_test", RISK_SERVICE_MAIN)
    captured = {}

    monkeypatch.setattr(module, "ensure_risk_control_tables", lambda: None)
    monkeypatch.setattr(
        module.DbUtil,
        "execute_sql",
        lambda sql, params=None: captured.update({"sql": sql, "params": params}) or 1,
    )

    parsed = module._parse_order_payload(
        {
            "symbol": "nvdl.us",
            "stopPrice": 42.5,
            "quantity": "3",
            "accountId": "8",
            "strategyId": "17",
            "note": "guard",
        },
        "stopPrice",
    )

    assert parsed["symbol"] == "NVDL.US"
    assert parsed["accountId"] == 8
    assert parsed["strategyId"] == 17
    assert parsed["quantity"] == 3


def test_risk_service_strategy_order_records_are_exactly_linked_by_strategy_id() -> None:
    module = _load_module("risk_service_strategy_order_records_test", RISK_SERVICE_MAIN)

    payload = module._build_strategy_order_records(
        {"id": 17, "type": "stop_loss"},
        stop_loss_orders=[
            {"id": 1, "symbol": "AAPL.US", "strategyId": 17},
            {"id": 2, "symbol": "MSFT.US", "strategyId": 18},
            {"id": 3, "symbol": "NVDA.US", "strategyId": None},
        ],
        take_profit_orders=[{"id": 4, "symbol": "AAPL.US", "strategyId": 17}],
    )

    assert payload["orderLinkMode"] == "linked-by-strategy-id"
    assert payload["stopLossOrders"] == [{"id": 1, "symbol": "AAPL.US", "strategyId": 17}]
    assert payload["takeProfitOrders"] == []
    assert "旧保护单缺少 strategyId" in " ".join(payload["notes"])


def test_risk_service_cached_orders_return_strategy_id(monkeypatch) -> None:
    module = _load_module("risk_service_cached_orders_strategy_id_test", RISK_SERVICE_MAIN)

    monkeypatch.setattr(module, "ensure_risk_control_tables", lambda: None)
    monkeypatch.setattr(
        module.DbUtil,
        "fetch_all",
        lambda *args, **kwargs: [
            {
                "id": 9,
                "account_id": 8,
                "strategy_id": 17,
                "symbol": "AAPL.US",
                "trigger_price": 180,
                "quantity": 2,
                "status": "active",
                "note": "",
                "created_at": None,
                "updated_at": None,
            }
        ],
    )
    monkeypatch.setattr(module.QuoteSnapshotService, "get_latest_map", lambda symbols: {})
    monkeypatch.setattr(module.PositionSnapshotService, "get_latest", lambda *args, **kwargs: [])

    rows = module._load_cached_risk_orders(user_id=1, order_type="stop_loss", account_id=8)

    assert rows[0]["strategyId"] == 17


def test_risk_service_public_order_reads_use_cached_read_model() -> None:
    source = RISK_SERVICE_MAIN.read_text(encoding="utf-8")
    function_start = source.index("def _load_risk_orders(")
    function_end = source.index("@app.get(\"/api/v1/risk/bootstrap\")", function_start)
    function_source = source[function_start:function_end]

    assert "_load_cached_risk_orders(" in function_source
    assert "return load_risk_orders(" not in function_source
