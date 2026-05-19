from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = ROOT / "apps/market/market-service/src"
SERVICE_PATH = SERVICE_DIR / "main.py"


def _load_market_service_module():
    for path in (ROOT, ROOT / "backend-server/src", SERVICE_DIR):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    spec = importlib.util.spec_from_file_location("_market_service_cache_under_test", SERVICE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


market_service = _load_market_service_module()


def test_live_cache_can_return_marked_stale_payload() -> None:
    cache_key = ("longbridge-quotes", 1, ("AAPL.US",))
    with market_service._LIVE_MARKET_CACHE_LOCK:
        market_service._LIVE_MARKET_CACHE.clear()
        market_service._LIVE_MARKET_CACHE[cache_key] = {
            "expires_at": time.time() - 1,
            "stale_until": time.time() + 30,
            "payload": {
                "success": True,
                "data": {
                    "dataSource": "longbridge-live",
                    "payload": [{"symbol": "AAPL.US", "last_price": 190}],
                },
            },
        }

    payload = market_service._live_cache_get(cache_key, allow_stale=True)

    assert payload["data"]["stale"] is True
    assert payload["data"]["dataSource"] == "longbridge-live-stale"
    assert market_service._live_cache_get(cache_key) is None


def test_live_cache_sets_stale_window_on_write() -> None:
    cache_key = ("longbridge-depth", 1, "AAPL.US")
    with market_service._LIVE_MARKET_CACHE_LOCK:
        market_service._LIVE_MARKET_CACHE.clear()

    market_service._live_cache_set(
        cache_key,
        {"success": True, "data": {"dataSource": "longbridge-live", "payload": {}}},
        ttl_seconds=3,
    )

    with market_service._LIVE_MARKET_CACHE_LOCK:
        cached = market_service._LIVE_MARKET_CACHE[cache_key]

    assert cached["stale_until"] > cached["expires_at"]
