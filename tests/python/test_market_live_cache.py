from __future__ import annotations

import importlib.util
import logging
import sys
import time
from datetime import date, datetime
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


def test_live_snapshot_reuses_component_cache(monkeypatch) -> None:
    class FakeContext:
        def __init__(self) -> None:
            self.calls = []

        def quote(self, symbols):
            self.calls.append(("quote", tuple(symbols)))
            return [{"symbol": symbols[0], "last_price": 190.5}]

        def depth(self, symbol):
            self.calls.append(("depth", symbol))
            return {"bids": [{"price": 190.4}], "asks": [{"price": 190.6}]}

        def trades(self, symbol, count):
            self.calls.append(("trades", symbol, count))
            return [{"trade_id": "t-1", "price": 190.5}]

    fake_context = FakeContext()
    monkeypatch.setattr(market_service, "_with_quote_context", lambda user_id: fake_context)

    with market_service._LIVE_MARKET_CACHE_LOCK:
        market_service._LIVE_MARKET_CACHE.clear()

    session = {"user_id": 1}
    first = market_service.asyncio.run(
        market_service.longbridge_snapshot(symbol="AAPL.US", count=18, session=session)
    )
    second = market_service.asyncio.run(
        market_service.longbridge_snapshot(symbol="AAPL.US", count=18, session=session)
    )

    assert first["data"]["payload"]["symbol"] == "AAPL.US"
    assert first["data"]["payload"]["quote"][0]["last_price"] == 190.5
    assert first["data"]["payload"]["depth"]["bids"][0]["price"] == 190.4
    assert first["data"]["payload"]["trades"][0]["trade_id"] == "t-1"
    assert first == second
    assert sorted(fake_context.calls) == sorted([
        ("quote", ("AAPL.US",)),
        ("depth", "AAPL.US"),
        ("trades", "AAPL.US", 18),
    ])


def test_longbridge_quote_failure_degrades_to_empty_payload(monkeypatch) -> None:
    class FailingContext:
        def quote(self, symbols):
            raise RuntimeError(f"paper account required: {symbols}")

    monkeypatch.setattr(market_service, "_with_quote_context", lambda user_id: FailingContext())
    with market_service._LIVE_MARKET_CACHE_LOCK:
        market_service._LIVE_MARKET_CACHE.clear()

    payload = market_service.asyncio.run(
        market_service._load_longbridge_quotes(user_id=1, symbols=["AAPL.US"])
    )

    assert payload["success"] is True
    assert payload["data"]["dataSource"] == "longbridge-live-unavailable"
    assert payload["data"]["fallback"] is True
    assert payload["data"]["payload"] == []


def test_longbridge_quote_pull_fallback_log_is_rate_limited(monkeypatch, caplog) -> None:
    class FailingContext:
        def quote(self, symbols):
            raise RuntimeError(f"paper account required: {symbols}")

    monkeypatch.setattr(market_service, "_with_quote_context", lambda user_id: FailingContext())
    monkeypatch.setattr(market_service, "_LIVE_FALLBACK_LOG_INTERVAL_SECONDS", 60.0)
    with market_service._LIVE_FALLBACK_LOG_LOCK:
        market_service._LIVE_FALLBACK_LAST_LOGS.clear()
    with market_service._LIVE_MARKET_CACHE_LOCK:
        market_service._LIVE_MARKET_CACHE.clear()

    with caplog.at_level(logging.WARNING, logger=market_service.LOGGER.name):
        market_service.asyncio.run(
            market_service._load_longbridge_quotes(user_id=1, symbols=["AAPL.US"], allow_stale=False)
        )
        market_service.asyncio.run(
            market_service._load_longbridge_quotes(user_id=1, symbols=["MSFT.US"], allow_stale=False)
        )

    warnings = [
        record
        for record in caplog.records
        if "Longbridge quote pull degraded" in record.getMessage()
    ]
    assert len(warnings) == 1


def test_trading_session_fallback_uses_rate_limited_logger(monkeypatch, caplog) -> None:
    class FailingContext:
        def trading_session(self):
            raise RuntimeError("paper account required")

    monkeypatch.setattr(market_service, "_with_quote_context", lambda user_id: FailingContext())
    monkeypatch.setattr(market_service, "_LIVE_FALLBACK_LOG_INTERVAL_SECONDS", 60.0)
    with market_service._LIVE_FALLBACK_LOG_LOCK:
        market_service._LIVE_FALLBACK_LAST_LOGS.clear()
    market_service._TRADING_SESSION_CACHE.update({"expires_at": 0.0, "payload": None})

    session = {"user_id": 1}
    with caplog.at_level(logging.WARNING, logger=market_service.LOGGER.name):
        first = market_service.asyncio.run(market_service.longbridge_trading_session(session=session))
        market_service._TRADING_SESSION_CACHE.update({"expires_at": 0.0, "payload": None})
        second = market_service.asyncio.run(market_service.longbridge_trading_session(session=session))

    assert first["success"] is True
    assert second["success"] is True
    assert first["data"]["payload"]["US"]["trade_sessions"] == []
    warnings = [
        record
        for record in caplog.records
        if "Longbridge trading-session degraded" in record.getMessage()
    ]
    assert len(warnings) == 1


def test_cli_push_poll_failure_enters_cooldown_without_log_spam(monkeypatch, caplog) -> None:
    push_hub_module = sys.modules["push_hub"]

    class CliQuoteContext:
        def set_on_quote(self, *_args, **_kwargs):
            pass

        def set_on_depth(self, *_args, **_kwargs):
            pass

        def set_on_brokers(self, *_args, **_kwargs):
            pass

        def set_on_trades(self, *_args, **_kwargs):
            pass

        def set_on_candlestick(self, *_args, **_kwargs):
            pass

        def subscriptions(self):
            return {}

        def realtime_quote(self, symbols):
            raise RuntimeError(f"paper account required: {symbols}")

    monkeypatch.setattr(push_hub_module, "build_quote_context", lambda **_kwargs: CliQuoteContext())
    monkeypatch.setattr(push_hub_module, "_cli_push_polling_enabled", lambda: True)
    monkeypatch.setattr(push_hub_module, "CLI_FAILURE_COOLDOWN_SECONDS", 60.0)
    monkeypatch.setattr(push_hub_module, "CLI_FAILURE_LOG_INTERVAL_SECONDS", 60.0)

    loop = market_service.asyncio.new_event_loop()
    try:
        session = push_hub_module.LongbridgePushSession(user_id=1, loop=loop)
        with caplog.at_level(logging.WARNING, logger=push_hub_module.LOGGER.name):
            session._poll_cli_event_type("quote", ["AAPL.US"])  # noqa: SLF001
            session._poll_cli_event_type("quote", ["AAPL.US"])  # noqa: SLF001

        warnings = [
            record
            for record in caplog.records
            if "Longbridge CLI polling degraded" in record.getMessage()
        ]
        assert len(warnings) == 1
        assert session._cli_polling_in_cooldown("quote") is True  # noqa: SLF001

        runtime = session.runtime()
        assert runtime["cliPolling"]["cooldowns"]["quote"] > 0
        assert runtime["cliPolling"]["lastFailure"]["eventType"] == "quote"
        assert runtime["cliPolling"]["lastFailure"]["symbolCount"] == 1
    finally:
        loop.close()


def test_cli_push_poll_rate_limit_is_logged_explicitly(monkeypatch, caplog) -> None:
    push_hub_module = sys.modules["push_hub"]

    class CliQuoteContext:
        def set_on_quote(self, *_args, **_kwargs):
            pass

        def set_on_depth(self, *_args, **_kwargs):
            pass

        def set_on_brokers(self, *_args, **_kwargs):
            pass

        def set_on_trades(self, *_args, **_kwargs):
            pass

        def set_on_candlestick(self, *_args, **_kwargs):
            pass

        def subscriptions(self):
            return {}

        def realtime_quote(self, symbols):
            raise RuntimeError("API error (code 429002): api request is limited")

    monkeypatch.setattr(push_hub_module, "build_quote_context", lambda **_kwargs: CliQuoteContext())
    monkeypatch.setattr(push_hub_module, "_cli_push_polling_enabled", lambda: True)
    monkeypatch.setattr(push_hub_module, "CLI_FAILURE_COOLDOWN_SECONDS", 60.0)
    monkeypatch.setattr(push_hub_module, "CLI_FAILURE_LOG_INTERVAL_SECONDS", 60.0)

    loop = market_service.asyncio.new_event_loop()
    try:
        session = push_hub_module.LongbridgePushSession(user_id=1, loop=loop)
        with caplog.at_level(logging.WARNING, logger=push_hub_module.LOGGER.name):
            session._poll_cli_event_type("quote", ["AAPL.US"])  # noqa: SLF001

        runtime = session.runtime()
        assert runtime["cliPolling"]["lastFailure"]["rateLimited"] is True
        assert any("Longbridge CLI polling rate limited" in record.getMessage() for record in caplog.records)
    finally:
        loop.close()


def test_cli_push_snapshot_failure_log_is_rate_limited(monkeypatch, caplog) -> None:
    push_hub_module = sys.modules["push_hub"]

    class CliQuoteContext:
        def set_on_quote(self, *_args, **_kwargs):
            pass

        def set_on_depth(self, *_args, **_kwargs):
            pass

        def set_on_brokers(self, *_args, **_kwargs):
            pass

        def set_on_trades(self, *_args, **_kwargs):
            pass

        def set_on_candlestick(self, *_args, **_kwargs):
            pass

        def subscriptions(self):
            return {}

        def realtime_quote(self, symbols):
            raise RuntimeError(f"paper account required: {symbols}")

    monkeypatch.setattr(push_hub_module, "build_quote_context", lambda **_kwargs: CliQuoteContext())
    monkeypatch.setattr(push_hub_module, "_cli_push_polling_enabled", lambda: True)
    monkeypatch.setattr(push_hub_module, "CLI_FAILURE_LOG_INTERVAL_SECONDS", 60.0)

    loop = market_service.asyncio.new_event_loop()
    try:
        session = push_hub_module.LongbridgePushSession(user_id=1, loop=loop)
        with caplog.at_level(logging.WARNING, logger=push_hub_module.LOGGER.name):
            session._build_snapshots(["AAPL.US"], [push_hub_module.SubType.Quote], trade_count=1)  # noqa: SLF001
            session._build_snapshots(["MSFT.US"], [push_hub_module.SubType.Quote], trade_count=1)  # noqa: SLF001

        warnings = [
            record
            for record in caplog.records
            if "Longbridge CLI snapshot degraded" in record.getMessage()
        ]
        assert len(warnings) == 1
    finally:
        loop.close()


def test_cli_push_polling_disabled_by_default_skips_snapshot_and_poller(monkeypatch, caplog) -> None:
    push_hub_module = sys.modules["push_hub"]

    class CliQuoteContext:
        def set_on_quote(self, *_args, **_kwargs):
            pass

        def set_on_depth(self, *_args, **_kwargs):
            pass

        def set_on_brokers(self, *_args, **_kwargs):
            pass

        def set_on_trades(self, *_args, **_kwargs):
            pass

        def set_on_candlestick(self, *_args, **_kwargs):
            pass

        def subscribe(self, *_args, **_kwargs):
            pass

        def subscriptions(self):
            return {}

        def realtime_quote(self, symbols):
            raise RuntimeError(f"would call external CLI: {symbols}")

    monkeypatch.delenv("LONGBRIDGE_CLI_PUSH_POLLING_ENABLED", raising=False)
    monkeypatch.setattr(push_hub_module, "build_quote_context", lambda **_kwargs: CliQuoteContext())

    loop = market_service.asyncio.new_event_loop()
    try:
        session = push_hub_module.LongbridgePushSession(user_id=1, loop=loop)
        with caplog.at_level(logging.WARNING, logger=push_hub_module.LOGGER.name):
            result = session.subscribe(["AAPL.US"], [push_hub_module.SubType.Quote])

        assert result["snapshots"] == {}
        assert session._cli_poller_thread is None  # noqa: SLF001
        assert result["runtime"]["cliPolling"]["available"] is True
        assert result["runtime"]["cliPolling"]["enabled"] is False
        assert result["runtime"]["cliPolling"]["disabledReason"] == "disabled-by-default"
        assert not any("Longbridge CLI" in record.getMessage() for record in caplog.records)
    finally:
        loop.close()


def test_push_broadcast_skips_stale_websocket_connections(monkeypatch, caplog) -> None:
    push_hub_module = sys.modules["push_hub"]

    class QuoteContext:
        def set_on_quote(self, *_args, **_kwargs):
            pass

        def set_on_depth(self, *_args, **_kwargs):
            pass

        def set_on_brokers(self, *_args, **_kwargs):
            pass

        def set_on_trades(self, *_args, **_kwargs):
            pass

        def set_on_candlestick(self, *_args, **_kwargs):
            pass

    class FakeWebSocket:
        def __init__(self, *, connected=True, fail=False):
            state = push_hub_module.WebSocketState.CONNECTED if connected else push_hub_module.WebSocketState.DISCONNECTED
            self.application_state = state
            self.client_state = state
            self.fail = fail
            self.sent = []

        async def send_json(self, payload):
            if self.fail:
                raise RuntimeError("socket closed")
            self.sent.append(payload)

    monkeypatch.setattr(push_hub_module, "build_quote_context", lambda **_kwargs: QuoteContext())

    loop = market_service.asyncio.new_event_loop()
    try:
        session = push_hub_module.LongbridgePushSession(user_id=1, loop=loop)
        healthy = FakeWebSocket()
        already_closed = FakeWebSocket(connected=False)
        fails_on_send = FakeWebSocket(fail=True)
        session._connections.update({healthy, already_closed, fails_on_send})  # noqa: SLF001

        with caplog.at_level(logging.WARNING, logger=push_hub_module.LOGGER.name):
            loop.run_until_complete(session._broadcast({"type": "quote"}))  # noqa: SLF001

        assert healthy.sent == [{"type": "quote"}]
        assert already_closed.sent == []
        assert session._connections == {healthy}  # noqa: SLF001
        assert any("Longbridge push WebSocket send failed" in record.getMessage() for record in caplog.records)
    finally:
        loop.close()


def test_push_broadcast_prunes_empty_disconnect_without_warning(monkeypatch, caplog) -> None:
    push_hub_module = sys.modules["push_hub"]

    class QuoteContext:
        def set_on_quote(self, *_args, **_kwargs):
            pass

        def set_on_depth(self, *_args, **_kwargs):
            pass

        def set_on_brokers(self, *_args, **_kwargs):
            pass

        def set_on_trades(self, *_args, **_kwargs):
            pass

        def set_on_candlestick(self, *_args, **_kwargs):
            pass

    class ClosingWebSocket:
        application_state = push_hub_module.WebSocketState.CONNECTED
        client_state = push_hub_module.WebSocketState.CONNECTED

        async def send_json(self, _payload):
            raise RuntimeError("")

    monkeypatch.setattr(push_hub_module, "build_quote_context", lambda **_kwargs: QuoteContext())

    loop = market_service.asyncio.new_event_loop()
    try:
        session = push_hub_module.LongbridgePushSession(user_id=1, loop=loop)
        closing = ClosingWebSocket()
        session._connections.add(closing)  # noqa: SLF001

        with caplog.at_level(logging.WARNING, logger=push_hub_module.LOGGER.name):
            loop.run_until_complete(session._broadcast({"type": "quote"}))  # noqa: SLF001

        assert session._connections == set()  # noqa: SLF001
        assert not any("Longbridge push WebSocket send failed" in record.getMessage() for record in caplog.records)
    finally:
        loop.close()


def test_cli_subscribe_snapshots_are_not_broadcast_to_websockets(monkeypatch) -> None:
    push_hub_module = sys.modules["push_hub"]

    class CliQuoteContext:
        def set_on_quote(self, *_args, **_kwargs):
            pass

        def set_on_depth(self, *_args, **_kwargs):
            pass

        def set_on_brokers(self, *_args, **_kwargs):
            pass

        def set_on_trades(self, *_args, **_kwargs):
            pass

        def set_on_candlestick(self, *_args, **_kwargs):
            pass

        def subscribe(self, *_args, **_kwargs):
            pass

        def subscriptions(self):
            return {}

        def realtime_quote(self, symbols):
            return [{"symbol": symbol, "last": "10", "prev_close": "9"} for symbol in symbols]

    class FakeWebSocket:
        application_state = push_hub_module.WebSocketState.CONNECTED
        client_state = push_hub_module.WebSocketState.CONNECTED

        def __init__(self):
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)

    monkeypatch.setattr(push_hub_module, "build_quote_context", lambda **_kwargs: CliQuoteContext())
    monkeypatch.setattr(push_hub_module, "_cli_push_polling_enabled", lambda: True)

    loop = market_service.asyncio.new_event_loop()
    try:
        session = push_hub_module.LongbridgePushSession(user_id=1, loop=loop)
        websocket = FakeWebSocket()
        session._connections.add(websocket)  # noqa: SLF001

        result = session.subscribe(["AAPL.US", "MSFT.US"], [push_hub_module.SubType.Quote])

        assert [row["symbol"] for row in result["snapshots"]["quote"]] == ["AAPL.US", "MSFT.US"]
        assert websocket.sent == []
        assert [event["symbol"] for event in session.runtime()["latestEvents"][:2]] == ["MSFT.US", "AAPL.US"]
    finally:
        session._stop_cli_poller()  # noqa: SLF001
        loop.close()


def test_cli_poller_delays_first_poll_until_interval() -> None:
    push_hub_module = sys.modules["push_hub"]
    last_run = {}

    assert push_hub_module._event_poll_due(last_run, "quote", 100.0, 4.0) is False  # noqa: SLF001
    assert last_run == {"quote": 100.0}
    assert push_hub_module._event_poll_due(last_run, "quote", 103.9, 4.0) is False  # noqa: SLF001
    assert push_hub_module._event_poll_due(last_run, "quote", 104.0, 4.0) is True  # noqa: SLF001


def test_initial_subscription_pushes_are_recorded_without_broadcast(monkeypatch) -> None:
    push_hub_module = sys.modules["push_hub"]

    class QuoteContext:
        def __init__(self):
            self.quote_callback = None

        def set_on_quote(self, callback):
            self.quote_callback = callback

        def set_on_depth(self, *_args, **_kwargs):
            pass

        def set_on_brokers(self, *_args, **_kwargs):
            pass

        def set_on_trades(self, *_args, **_kwargs):
            pass

        def set_on_candlestick(self, *_args, **_kwargs):
            pass

        def subscribe(self, symbols, *_args, **_kwargs):
            self.quote_callback(symbols[0], {"symbol": symbols[0], "last": "10", "prev_close": "9"})

        def subscriptions(self):
            return {}

        def quote(self, symbols):
            return [{"symbol": symbol, "last": "10", "prev_close": "9"} for symbol in symbols]

    class FakeWebSocket:
        application_state = push_hub_module.WebSocketState.CONNECTED
        client_state = push_hub_module.WebSocketState.CONNECTED

        def __init__(self):
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)

    monotonic = {"value": 100.0}
    monkeypatch.setattr(push_hub_module, "build_quote_context", lambda **_kwargs: QuoteContext())
    monkeypatch.setattr(push_hub_module.time, "monotonic", lambda: monotonic["value"])

    loop = market_service.asyncio.new_event_loop()
    try:
        session = push_hub_module.LongbridgePushSession(user_id=1, loop=loop)
        websocket = FakeWebSocket()
        session._connections.add(websocket)  # noqa: SLF001

        session.subscribe(["AAPL.US"], [push_hub_module.SubType.Quote])
        assert websocket.sent == []
        assert session.runtime()["latestEvents"][0]["symbol"] == "AAPL.US"

        monotonic["value"] = 103.0
        session._handle_push("quote", "AAPL.US", {"symbol": "AAPL.US"})  # noqa: SLF001
        loop.run_until_complete(market_service.asyncio.sleep(0))
        assert [item["symbol"] for item in websocket.sent] == ["AAPL.US"]
    finally:
        loop.close()


def test_live_snapshot_degrades_when_longbridge_pull_fails(monkeypatch) -> None:
    class FailingContext:
        def quote(self, symbols):
            raise RuntimeError(f"paper account required: {symbols}")

        def depth(self, symbol):
            raise RuntimeError(f"paper account required: {symbol}")

        def trades(self, symbol, count):
            raise RuntimeError(f"paper account required: {symbol}:{count}")

    monkeypatch.setattr(market_service, "_with_quote_context", lambda user_id: FailingContext())
    with market_service._LIVE_MARKET_CACHE_LOCK:
        market_service._LIVE_MARKET_CACHE.clear()

    payload = market_service.asyncio.run(
        market_service.longbridge_snapshot(symbol="AAPL.US", count=18, session={"user_id": 1})
    )

    snapshot = payload["data"]["payload"]
    assert snapshot["symbol"] == "AAPL.US"
    assert snapshot["quote"] == []
    assert snapshot["depth"] == {}
    assert snapshot["trades"] == []
    assert snapshot["sources"] == {
        "quote": "longbridge-live-unavailable",
        "depth": "longbridge-live-unavailable",
        "trades": "longbridge-live-unavailable",
    }


def test_symbol_overview_core_mode_defers_heavy_sections(monkeypatch) -> None:
    calls = []

    def fake_symbol_overview(symbol, user_id=1, allow_refresh=True):
        calls.append(("overview", symbol, user_id, allow_refresh))
        return {
            "symbol": symbol,
            "market": "US",
            "fundamentals": {"name": "Apple"},
            "snapshots": {},
        }

    def fail_heavy_section(*_args, **_kwargs):
        raise AssertionError("core overview must not load deferred sections")

    monkeypatch.setattr(market_service.IndicatorSnapshotService, "get_symbol_overview", fake_symbol_overview)
    monkeypatch.setattr(market_service.HistoricalMarketDataService, "get_history", fail_heavy_section)
    monkeypatch.setattr(market_service.MarketInsightService, "get_latest_snapshots", fail_heavy_section)
    monkeypatch.setattr(market_service.DailyMarketScanService, "get_latest_scans", fail_heavy_section)
    monkeypatch.setattr(market_service.DailySymbolTrendScanService, "get_latest_for_symbol", fail_heavy_section)
    monkeypatch.setattr(market_service, "_content_cache_bundle", fail_heavy_section)
    monkeypatch.setattr(
        market_service.QuoteSnapshotService,
        "get_latest",
        lambda symbol, max_age_minutes=20: {"symbol": symbol, "price": 190, "snapshotAt": "2026-05-20T10:00:00Z"},
    )
    monkeypatch.setattr(
        market_service,
        "get_persistence_manager",
        lambda: (_ for _ in ()).throw(AssertionError("core overview must not load AI analysis")),
    )
    with market_service._LIVE_MARKET_CACHE_LOCK:
        market_service._LIVE_MARKET_CACHE.clear()

    payload = market_service.asyncio.run(
        market_service.symbol_overview("aapl.us", include="core", session={"user_id": 9})
    )

    data = payload["data"]
    assert calls == [("overview", "AAPL.US", 9, False)]
    assert data["meta"]["responseMode"] == "core"
    assert data["meta"]["historyStatus"] == "deferred"
    assert "history" in data["meta"]["deferredSections"]
    assert data["history"] == {"items": [], "summary": {}}
    assert data["latestAiAnalysis"] is None
    assert data["contentCache"]["totalCount"] == 0


def test_symbol_overview_cache_separates_core_and_full_modes(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        market_service.IndicatorSnapshotService,
        "get_symbol_overview",
        lambda symbol, user_id=1, allow_refresh=True: calls.append((symbol, allow_refresh)) or {
            "symbol": symbol,
            "market": "US",
            "fundamentals": {},
            "snapshots": {},
        },
    )
    monkeypatch.setattr(market_service.QuoteSnapshotService, "get_latest", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(market_service.HistoricalMarketDataService, "get_history", lambda *_args, **_kwargs: {"items": [], "summary": {}})
    monkeypatch.setattr(market_service.MarketInsightService, "get_latest_snapshots", lambda **_kwargs: [])
    monkeypatch.setattr(market_service.DailyMarketScanService, "get_latest_scans", lambda: [])
    monkeypatch.setattr(market_service.DailySymbolTrendScanService, "get_latest_for_symbol", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(market_service, "_content_cache_bundle", lambda *_args, **_kwargs: market_service._empty_content_cache_bundle("content-cache"))
    monkeypatch.setattr(
        market_service,
        "get_persistence_manager",
        lambda: type("FakePersistence", (), {"get_latest_ai_analysis": lambda *_args, **_kwargs: None})(),
    )
    with market_service._LIVE_MARKET_CACHE_LOCK:
        market_service._LIVE_MARKET_CACHE.clear()

    core_payload = market_service.asyncio.run(
        market_service.symbol_overview("AAPL.US", include="core", session={"user_id": 1})
    )
    full_payload = market_service.asyncio.run(
        market_service.symbol_overview("AAPL.US", include="all", session={"user_id": 1})
    )

    assert core_payload["data"]["meta"]["responseMode"] == "core"
    assert full_payload["data"]["meta"]["responseMode"] == "all"
    assert calls == [("AAPL.US", False), ("AAPL.US", True)]


def test_history_backfill_endpoint_runs_single_symbol_and_clears_cache(monkeypatch) -> None:
    calls = []

    def fake_backfill_symbol_history(**kwargs):
        calls.append(kwargs)
        return {
            "complete": True,
            "savedCount": 3,
            "fetchedRanges": [{"startDate": "2024-01-01", "endDate": "2024-01-03", "savedCount": 3}],
        }

    monkeypatch.setattr(
        market_service.HistoricalMarketDataService,
        "backfill_symbol_history",
        fake_backfill_symbol_history,
    )
    with market_service._HISTORY_COVERAGE_CACHE_LOCK:
        market_service._HISTORY_COVERAGE_CACHE.clear()
        market_service._HISTORY_COVERAGE_CACHE[("history-coverage", "fixture")] = {
            "expires_at": time.time() + 60,
            "payload": {"items": [{"symbol": "NVDL.US"}]},
        }

    payload = market_service.asyncio.run(
        market_service.market_history_backfill(
            payload={"symbol": "nvdl.us", "startDate": "2024-01-01", "endDate": "2024-01-03"},
            session={"user_id": 7},
        )
    )

    assert payload["success"] is True
    assert payload["data"]["symbol"] == "NVDL.US"
    assert payload["data"]["savedCount"] == 3
    assert calls == [
        {
            "symbol": "NVDL.US",
            "start_date": market_service.date(2024, 1, 1),
            "end_date": market_service.date(2024, 1, 3),
            "user_id": 7,
        }
    ]
    with market_service._HISTORY_COVERAGE_CACHE_LOCK:
        assert market_service._HISTORY_COVERAGE_CACHE == {}


def test_history_backfill_endpoint_rejects_invalid_range() -> None:
    try:
        market_service.asyncio.run(
            market_service.market_history_backfill(
                payload={"symbol": "NVDL.US", "startDate": "2024-02-01", "endDate": "2024-01-01"},
                session={"user_id": 1},
            )
        )
    except market_service.HTTPException as exc:
        assert exc.status_code == 400
        assert "endDate" in exc.detail
    else:
        raise AssertionError("expected HTTPException for invalid backfill range")


def test_longbridge_history_rejects_explicit_sdk_storage(monkeypatch) -> None:
    monkeypatch.setattr(
        market_service,
        "_with_quote_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("SDK history path must stay disabled")),
    )

    try:
        market_service.asyncio.run(
            market_service.longbridge_history_candlesticks(
                symbol="AAPL.US",
                storage_mode="longbridge",
                session={"user_id": 1},
            )
        )
    except market_service.HTTPException as exc:
        assert exc.status_code == 410
        assert "历史 K 线 SDK 路径已停用" in exc.detail
    else:
        raise AssertionError("expected HTTPException for explicit Longbridge history mode")


def test_longbridge_candlesticks_endpoint_is_gone(monkeypatch) -> None:
    monkeypatch.setattr(
        market_service,
        "_with_quote_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("SDK candlesticks path must stay disabled")),
    )

    try:
        market_service.asyncio.run(
            market_service.longbridge_candlesticks(symbol="AAPL.US", session={"user_id": 1})
        )
    except market_service.HTTPException as exc:
        assert exc.status_code == 410
        assert "K 线 SDK 路径已停用" in exc.detail
    else:
        raise AssertionError("expected HTTPException for disabled Longbridge candlesticks endpoint")


def test_history_backfill_endpoint_rejects_duplicate_symbol(monkeypatch) -> None:
    with market_service._HISTORY_BACKFILL_LOCK:
        market_service._HISTORY_BACKFILL_SYMBOLS.clear()
        market_service._HISTORY_BACKFILL_SYMBOLS.add("NVDL.US")

    try:
        try:
            market_service.asyncio.run(
                market_service.market_history_backfill(
                    payload={"symbol": "NVDL.US"},
                    session={"user_id": 1},
                )
            )
        except market_service.HTTPException as exc:
            assert exc.status_code == 409
            assert "正在补价" in exc.detail
        else:
            raise AssertionError("expected HTTPException for duplicate backfill")
    finally:
        with market_service._HISTORY_BACKFILL_LOCK:
            market_service._HISTORY_BACKFILL_SYMBOLS.clear()


def test_history_backfill_endpoint_releases_lock_when_backfill_fails(monkeypatch) -> None:
    def fail_backfill_symbol_history(**_kwargs):
        raise RuntimeError("skshare unavailable")

    monkeypatch.setattr(
        market_service.HistoricalMarketDataService,
        "backfill_symbol_history",
        fail_backfill_symbol_history,
    )
    with market_service._HISTORY_BACKFILL_LOCK:
        market_service._HISTORY_BACKFILL_SYMBOLS.clear()

    try:
        market_service.asyncio.run(
            market_service.market_history_backfill(
                payload={"symbol": "NVDL.US"},
                session={"user_id": 1},
            )
        )
    except RuntimeError as exc:
        assert "skshare unavailable" in str(exc)
    else:
        raise AssertionError("expected RuntimeError from backfill service")

    with market_service._HISTORY_BACKFILL_LOCK:
        assert market_service._HISTORY_BACKFILL_SYMBOLS == set()


def test_history_coverage_exact_symbol_uses_fast_path(monkeypatch) -> None:
    captured_calls = []

    def fail_full_coverage_sql(**_kwargs):
        raise AssertionError("exact symbol coverage should not build the full-market query")

    def fake_exact_universe_rows(symbol, user_id):
        assert symbol == "NVDL.US"
        assert user_id == 1
        return [
            {
                "symbol": "NVDL.US",
                "display_name": "GraniteShares 2x Long NVDA Daily ETF",
                "market": "US",
                "universe_updated_at": datetime(2024, 5, 20, 15, 0, 0),
                "source_priority": 1,
            }
        ]

    def fake_fetch_one(sql, params):
        captured_calls.append((sql, params))
        return {
            "symbol": "NVDL.US",
            "market": "US",
            "first_date": date(2024, 1, 2),
            "latest_date": date(2024, 5, 20),
            "row_count": 98,
            "last_updated": datetime(2024, 5, 20, 15, 30, 0),
        }

    def fake_market_expectation(**kwargs):
        assert kwargs == {"start_date": date(2024, 1, 1), "market": "US"}
        return {
            "market": "US",
            "expected_start_trade_date": date(2024, 1, 2),
            "expected_end": date(2024, 5, 20),
            "expected_days": 98,
        }

    monkeypatch.setattr(market_service, "_build_history_coverage_sql", fail_full_coverage_sql)
    monkeypatch.setattr(market_service, "_load_exact_history_coverage_universe_rows", fake_exact_universe_rows)
    monkeypatch.setattr(market_service, "_get_history_market_expectation", fake_market_expectation)
    monkeypatch.setattr(market_service.DbUtil, "fetch_one", fake_fetch_one)

    payload = market_service._load_history_coverage_payload(
        user_id=1,
        start_date=date(2024, 1, 1),
        search="nvdl.us",
        status="",
        page=1,
        page_size=20,
    )

    assert len(captured_calls) == 1
    assert captured_calls[0][1] == ("NVDL.US", "US", date(2024, 1, 1))
    assert payload["total"] == 1
    assert payload["summary"]["filteredTotal"] == 1
    assert payload["summary"]["counts"] == {"complete": 1, "missing": 0, "partial": 0}
    assert payload["summary"]["markets"] == [
        {
            "market": "US",
            "expectedStart": "2024-01-01",
            "expectedFirstTradeDate": "2024-01-02",
            "expectedEnd": "2024-05-20",
            "expectedDays": 98,
        }
    ]
    assert payload["items"][0]["symbol"] == "NVDL.US"
    assert payload["items"][0]["status"] == "complete"


def test_history_coverage_bare_symbol_uses_fast_path_when_universe_matches(monkeypatch) -> None:
    calls = []

    def fail_full_coverage_sql(**_kwargs):
        raise AssertionError("bare symbol with a universe match should not build the full-market query")

    def fake_exact_universe_rows(symbol, user_id):
        assert symbol == "NVDL.US"
        assert user_id == 1
        return [
            {
                "symbol": "NVDL.US",
                "display_name": "NVDL",
                "market": "US",
                "universe_updated_at": datetime(2024, 5, 20, 15, 0, 0),
                "source_priority": 1,
            }
        ]

    def fake_fetch_one(sql, params):
        calls.append((sql, params))
        return {"symbol": "NVDL.US", "market": "US", "row_count": 0}

    monkeypatch.setattr(market_service, "_build_history_coverage_sql", fail_full_coverage_sql)
    monkeypatch.setattr(market_service, "_load_exact_history_coverage_universe_rows", fake_exact_universe_rows)
    monkeypatch.setattr(
        market_service,
        "_get_history_market_expectation",
        lambda **_kwargs: {"market": "US", "expected_days": 5},
    )
    monkeypatch.setattr(market_service.DbUtil, "fetch_one", fake_fetch_one)

    payload = market_service._load_history_coverage_payload(
        user_id=1,
        start_date=date(2024, 1, 1),
        search="NVDL",
        status="",
        page=1,
        page_size=20,
    )

    assert len(calls) == 1
    assert payload["total"] == 1
    assert payload["items"][0]["symbol"] == "NVDL.US"
    assert payload["items"][0]["status"] == "missing"


def test_history_coverage_name_search_keeps_full_query_path(monkeypatch) -> None:
    calls = []

    def fake_build_history_coverage_sql(**kwargs):
        calls.append(kwargs)
        return "", ()

    monkeypatch.setattr(market_service, "_build_history_coverage_sql", fake_build_history_coverage_sql)

    payload = market_service._load_history_coverage_payload(
        user_id=1,
        start_date=date(2024, 1, 1),
        search="英伟达",
        status="",
        page=1,
        page_size=20,
    )

    assert calls == [
        {
            "start_date": date(2024, 1, 1),
            "search": "英伟达",
            "status": "",
            "user_id": 1,
        }
    ]
    assert payload["total"] == 0


def test_history_coverage_cache_key_normalizes_exact_symbol_search() -> None:
    base_key = market_service._build_history_coverage_cache_key(
        user_id=1,
        start_date=date(2024, 1, 1),
        search=" nvdl.us ",
        status="",
        page=1,
        page_size=20,
        expected_start=None,
        expected_end=None,
    )
    normalized_key = market_service._build_history_coverage_cache_key(
        user_id=1,
        start_date=date(2024, 1, 1),
        search="NVDL.US",
        status=" ",
        page=1,
        page_size=20,
        expected_start="",
        expected_end="",
    )
    different_page_key = market_service._build_history_coverage_cache_key(
        user_id=1,
        start_date=date(2024, 1, 1),
        search="NVDL.US",
        status="",
        page=2,
        page_size=20,
        expected_start=None,
        expected_end=None,
    )

    assert base_key == normalized_key
    assert base_key != different_page_key
    assert "NVDL.US" in base_key
    assert "nvdl.us" not in base_key


def test_backfill_status_exposes_operational_progress(monkeypatch) -> None:
    def fake_fetch_one(sql, params=None):
        if "total_universe_symbols" in sql:
            return {"total_universe_symbols": 10}
        if "COUNT(DISTINCT symbol)" in sql:
            return {"synced_symbols": 4, "latest_trade_date": date(2026, 5, 19)}
        if "FROM scheduled_jobs" in sql:
            return {
                "job_name": "market_history_universe_backfill",
                "last_run_date": date(2026, 5, 20),
                "last_run_at": datetime(2026, 5, 20, 21, 5, 0),
                "status": "running",
                "message": "慢补数启动中",
            }
        return {}

    def fake_fetch_all(sql, params=None):
        return [{"market": "US", "row_count": 1200}]

    monkeypatch.setattr(market_service.HistoricalMarketDataService, "_BACKFILL_STATUS_CACHE", {"expires_at": 0.0, "payload": None})
    monkeypatch.setattr(market_service.HistoricalMarketDataService, "_estimate_history_total_rows", lambda: 1200)
    monkeypatch.setattr(
        market_service.HistoricalMarketDataService,
        "_ensure_backfill_status_schema",
        lambda: None,
    )
    history_module = sys.modules[market_service.HistoricalMarketDataService.__module__]
    monkeypatch.setattr(history_module.DbUtil, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(history_module.DbUtil, "fetch_all", fake_fetch_all)
    from core.platform.SystemTaskService import SystemTaskService

    monkeypatch.setattr(
        SystemTaskService,
        "get_policy",
        lambda task_key: {
            "enabled": True,
            "intervalSeconds": 900,
            "batchSize": 2,
            "maxRequestsPerMinute": 4,
            "settings": {
                "cursor": 42,
                "currentSymbol": "TSLA.US",
                "currentBatchSymbols": ["TSLA.US", "AAPL.US"],
                "processedInRun": ["TSLA.US"],
                "failedInRun": [{"symbol": "XYZ.US", "error": "not found"}],
                "lastProcessedSymbols": ["NVDL.US"],
                "lastFailedCount": 1,
                "lastRunAt": "2026-05-20 21:04:00",
            },
        },
    )

    payload = market_service.HistoricalMarketDataService.get_backfill_status()

    progress = payload["task"]["progress"]
    assert payload["coverageRate"] == 40.0
    assert progress["isRunning"] is True
    assert progress["cursor"] == 42
    assert progress["currentSymbol"] == "TSLA.US"
    assert progress["currentBatchSymbols"] == ["TSLA.US", "AAPL.US"]
    assert progress["failedInRun"] == [{"symbol": "XYZ.US", "error": "not found"}]
