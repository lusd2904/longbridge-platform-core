from __future__ import annotations

import importlib.util
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

    def fake_exact_universe_rows(symbol):
        assert symbol == "NVDL.US"
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

    def fake_exact_universe_rows(symbol):
        assert symbol == "NVDL.US"
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
        }
    ]
    assert payload["total"] == 0


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
