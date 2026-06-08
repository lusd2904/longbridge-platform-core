from __future__ import annotations

from datetime import date

from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService
from core.analysis.ai_analyst import AIAnalyst


def _sample_candle(trade_date: str = "2026-01-02"):
    return {
        "trade_date": trade_date,
        "open": 10,
        "high": 11,
        "low": 9,
        "close": 10.5,
        "volume": 1000,
        "turnover": 10500,
    }


def test_sync_symbol_uses_skshare_source(monkeypatch) -> None:
    saved = {}

    monkeypatch.setattr(HistoricalMarketDataService, "ensure_schema", lambda: None)
    monkeypatch.setattr(
        HistoricalMarketDataService,
        "_fetch_candles_with_source",
        lambda symbol, user_id=1, count=420: ([_sample_candle()], "skshare"),
    )

    def fake_save(symbol, candles, source=""):
        saved["symbol"] = symbol
        saved["candles"] = candles
        saved["source"] = source
        return len(candles)

    monkeypatch.setattr(HistoricalMarketDataService, "_save_candles", fake_save)

    assert HistoricalMarketDataService.sync_symbol("000001.SZ", user_id=7, count=30) == 1
    assert saved["symbol"] == "000001.SZ"
    assert saved["source"] == "skshare"


def test_sync_symbol_preserves_fallback_source(monkeypatch) -> None:
    saved = {}

    monkeypatch.setattr(HistoricalMarketDataService, "ensure_schema", lambda: None)
    monkeypatch.setattr(
        HistoricalMarketDataService,
        "_fetch_candles_with_source",
        lambda symbol, user_id=1, count=420: ([_sample_candle()], "akshare-fallback"),
    )

    def fake_save(symbol, candles, source=""):
        saved["source"] = source
        return len(candles)

    monkeypatch.setattr(HistoricalMarketDataService, "_save_candles", fake_save)

    assert HistoricalMarketDataService.sync_symbol("000001.SZ", user_id=7, count=30) == 1
    assert saved["source"] == "akshare-fallback"


def test_skshare_request_shape_for_cn_hk_us() -> None:
    cn_requests = HistoricalMarketDataService._skshare_history_requests("000001.SZ")
    assert [item["interface"] for item in cn_requests] == [
        "stock_zh_a_daily",
        "stock_zh_a_hist_tx",
        "stock_zh_a_hist",
    ]
    assert cn_requests[0]["params"]["symbol"] == "sz000001"
    assert cn_requests[1]["params"]["symbol"] == "sz000001"
    assert cn_requests[2]["params"] == {
        "symbol": "000001",
        "period": "daily",
        "adjust": "qfq",
    }

    hk_requests = HistoricalMarketDataService._skshare_history_requests("700.HK")
    assert [item["interface"] for item in hk_requests] == ["stock_hk_daily", "stock_hk_hist"]
    assert hk_requests[0]["params"]["symbol"] == "00700"
    assert hk_requests[0]["client_date_filter"] is True

    us_requests = HistoricalMarketDataService._skshare_history_requests("AAPL.US")
    assert us_requests[0]["interface"] == "stock_us_daily"
    assert us_requests[0]["params"] == {"symbol": "AAPL"}
    assert [item["params"]["symbol"] for item in us_requests[1:3]] == ["105.AAPL", "106.AAPL"]
    assert us_requests[0]["client_date_filter"] is True


def test_format_skshare_rows_normalizes_ohlcv() -> None:
    rows = [
        {
            "日期": "2026-01-02T00:00:00",
            "开盘": "10.1",
            "最高": "11.2",
            "最低": "9.9",
            "收盘": "10.8",
            "成交量": "12345",
            "成交额": "98765.4",
        }
    ]

    assert HistoricalMarketDataService._format_skshare_rows(rows) == [
        {
            "trade_date": "2026-01-02",
            "open": 10.1,
            "high": 11.2,
            "low": 9.9,
            "close": 10.8,
            "volume": 12345,
            "turnover": 98765.4,
        }
    ]


def test_format_skshare_rows_uses_amount_as_volume_when_needed() -> None:
    rows = [
        {
            "date": "2026-01-02T00:00:00",
            "open": 10.1,
            "high": 11.2,
            "low": 9.9,
            "close": 10.8,
            "amount": 12345.0,
        }
    ]

    assert HistoricalMarketDataService._format_skshare_rows(rows)[0]["volume"] == 12345


def test_format_skshare_rows_uses_amount_as_turnover_when_volume_exists() -> None:
    rows = [
        {
            "date": "2026-01-02T00:00:00",
            "open": 10.1,
            "high": 11.2,
            "low": 9.9,
            "close": 10.8,
            "volume": 12345,
            "amount": 98765.4,
            "turnover": 0.12,
        }
    ]

    result = HistoricalMarketDataService._format_skshare_rows(rows)[0]
    assert result["volume"] == 12345
    assert result["turnover"] == 98765.4


def test_skshare_fetch_falls_through_to_next_platform_interface(monkeypatch) -> None:
    calls = []

    class FakeResponse:
        def __init__(self, status_code, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload or []
            self.text = text

        def json(self):
            return self._payload

    class FakeSession:
        trust_env = False

        def get(self, url, params=None, timeout=None):
            calls.append((url, params, timeout))
            if url.endswith("/stock_zh_a_daily"):
                return FakeResponse(500, text="bad upstream")
            return FakeResponse(
                200,
                [
                    {
                        "date": "2026-01-02T00:00:00",
                        "open": 10,
                        "high": 11,
                        "low": 9,
                        "close": 10.5,
                        "amount": 1000,
                    }
                ],
            )

    monkeypatch.setattr("core.analysis.HistoricalMarketDataService.requests.Session", lambda: FakeSession())
    monkeypatch.setattr(HistoricalMarketDataService, "_skshare_base_urls", lambda: ["http://skshare"])

    candles = HistoricalMarketDataService._fetch_candles_from_skshare(
        "000001.SZ",
        date(2026, 1, 1),
        date(2026, 1, 10),
    )

    assert [call[0].rsplit("/", 1)[-1] for call in calls[:2]] == [
        "stock_zh_a_daily",
        "stock_zh_a_hist_tx",
    ]
    assert calls[1][1]["symbol"] == "sz000001"
    assert candles[0]["trade_date"] == "2026-01-02"


def test_history_fallback_errors_do_not_escape(monkeypatch) -> None:
    def raise_runtime(*args, **kwargs):
        raise RuntimeError("upstream exploded")

    monkeypatch.setattr(HistoricalMarketDataService, "_fetch_candles_by_date_range", raise_runtime)
    monkeypatch.setattr(HistoricalMarketDataService, "_fetch_candles_from_akshare", raise_runtime)
    monkeypatch.setattr(HistoricalMarketDataService, "_fetch_candles_from_yfinance", raise_runtime)

    assert HistoricalMarketDataService._fetch_candles_by_date_range_with_fallback(
        "000001.SZ",
        date(2026, 1, 1),
        date(2026, 1, 10),
    ) == []


def test_history_fallback_reports_actual_source(monkeypatch) -> None:
    monkeypatch.setattr(HistoricalMarketDataService, "_fetch_candles_by_date_range", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(HistoricalMarketDataService, "_fetch_candles_from_akshare", lambda *_args, **_kwargs: [_sample_candle()])
    monkeypatch.setattr(HistoricalMarketDataService, "_fetch_candles_from_yfinance", lambda *_args, **_kwargs: [])

    candles, source = HistoricalMarketDataService._fetch_candles_by_date_range_with_fallback_source(
        "000001.SZ",
        date(2026, 1, 1),
        date(2026, 1, 10),
    )

    assert candles == [_sample_candle()]
    assert source == "akshare-fallback"


def test_backfill_symbol_history_saves_fallback_source(monkeypatch) -> None:
    saved_sources = []
    coverage_calls = []

    def fake_coverage(symbol, start_date=None, end_date=None):
        coverage_calls.append((symbol, start_date, end_date))
        if len(coverage_calls) == 1:
            return {
                "symbol": symbol,
                "complete": False,
                "missingRanges": [{"startDate": "2026-01-01", "endDate": "2026-01-10"}],
            }
        return {
            "symbol": symbol,
            "complete": True,
            "missingRanges": [],
        }

    monkeypatch.setattr(HistoricalMarketDataService, "ensure_schema", lambda: None)
    monkeypatch.setattr(HistoricalMarketDataService, "get_symbol_history_coverage", fake_coverage)
    monkeypatch.setattr(
        HistoricalMarketDataService,
        "_fetch_candles_by_date_range_with_fallback_source",
        lambda *_args, **_kwargs: ([_sample_candle()], "yfinance-fallback"),
    )
    monkeypatch.setattr(
        HistoricalMarketDataService,
        "_save_candles",
        lambda symbol, candles, source="": saved_sources.append(source) or len(candles),
    )

    result = HistoricalMarketDataService.backfill_symbol_history(
        "AAPL.US",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 10),
        user_id=7,
    )

    assert saved_sources == ["yfinance-fallback-backfill"]
    assert result["savedCount"] == 1
    assert result["fetchedRanges"] == [
        {
            "startDate": "2026-01-01",
            "endDate": "2026-01-10",
            "savedCount": 1,
            "dataSource": "yfinance-fallback-backfill",
            "upstreamSource": "yfinance-fallback",
        }
    ]


def test_ai_defaults_route_to_sub2api_models(monkeypatch) -> None:
    values = {
        "AI_PROVIDER": "nvidia",
        "AI_FALLBACK_PROVIDER": "",
        "AI_BASE_URL": "https://lucen.cc/v1",
        "AI_URL": "https://lucen.cc/v1/chat/completions",
        "AI_API_STYLE": "openai-chat-completions",
    }

    def fake_get(key, user_id=1, default=None):
        return values.get(key, default)

    monkeypatch.setattr("core.analysis.ai_analyst.AppConfig.get", fake_get)

    assert AIAnalyst._provider(user_id=1) == "nvidia"
    assert AIAnalyst._provider_order(task="scan_final", user_id=1) == ["nvidia"]
    assert AIAnalyst._nvidia_endpoints(user_id=1)[0] == "https://lucen.cc/v1/chat/completions"
    assert AIAnalyst._resolve_model(task="scan_final", user_id=1, provider="nvidia") == "gpt-5.5"
    assert AIAnalyst._resolve_model(task="scan_pulse", user_id=1, provider="nvidia") == "gpt-5.4"
    assert AIAnalyst._build_nvidia_payload(
        "https://lucen.cc/v1/chat/completions",
        "test",
        "gpt-5.4",
        task="scan_pulse",
        user_id=1,
    )["reasoning_effort"] == "high"
