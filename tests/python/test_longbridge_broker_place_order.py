from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend-server" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from core.broker.LongbridgeAPI import LongbridgeAPI  # noqa: E402


def test_longbridge_place_order_maps_order_enums_without_sdk_imports(monkeypatch) -> None:
    api = LongbridgeAPI.__new__(LongbridgeAPI)
    submitted = {}

    class TradeContextDouble:
        def submit_order(self, **kwargs):
            submitted.update(kwargs)
            return SimpleNamespace(order_id="paper-ord-1", status=SimpleNamespace(name="Submitted"))

    api.trade_context = TradeContextDouble()
    api.account_id = 1
    api._ensure_connected = lambda: None
    api._throttle_request = lambda: None
    api._execute_with_resilience = lambda _operation, func, fallback=None: func()
    api._log_connection = lambda *args, **kwargs: None

    monkeypatch.setattr("core.broker.LongbridgeAPI.log_trade", lambda *args, **kwargs: None)

    result = api.place_order(
        symbol="MSFT.US",
        action="BUY",
        quantity=3,
        order_type="LIMIT",
        price=417.22,
        time_in_force="DAY",
    )

    assert result["order_id"] == "paper-ord-1"
    assert result["status"] == "Submitted"
    assert str(submitted["side"]) == "Buy"
    assert str(submitted["order_type"]) == "Limit"
    assert str(submitted["time_in_force"]) == "Day"
    assert submitted["submitted_quantity"] == 3
    assert submitted["submitted_price"] == 417.22


def test_longbridge_account_info_cache_miss_does_not_log_traceback(caplog) -> None:
    api = LongbridgeAPI.__new__(LongbridgeAPI)
    api.account_id = 7
    api._load_cached_account_info = lambda: None
    api._log_connection = lambda *args, **kwargs: None
    api._execute_with_resilience = lambda _operation, _func, fallback=None: fallback()

    with caplog.at_level(logging.WARNING, logger="core.broker.LongbridgeAPI"):
        with pytest.raises(RuntimeError, match="当前没有可用的长桥账户缓存"):
            api.get_account_info()

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "获取账户信息已降级且没有可用缓存" in messages
    assert "Traceback" not in messages
