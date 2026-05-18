from __future__ import annotations

import subprocess

import pandas as pd

from utils.MarketUniverseSync import MarketUniverseSync


def test_fetch_dataframe_falls_back_to_existing_table(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fail_source(market: str, asset_type: str):
        calls.append((market, asset_type))
        raise RuntimeError("upstream disconnected")

    fallback = pd.DataFrame([
        {
            "symbol": "AAPL.US",
            "name": "Apple Inc",
            "price": 190.12,
            "change_percent": 1.2,
            "volume": 1000,
            "market_cap": 100000,
            "pe_ratio": 30,
            "sector": "Tech",
        }
    ])

    monkeypatch.setattr(MarketUniverseSync, "_fetch_dataframe_from_skshare", fail_source)
    monkeypatch.setattr(MarketUniverseSync, "_fetch_dataframe_from_akshare_subprocess", fail_source)
    monkeypatch.setattr(MarketUniverseSync, "_fetch_dataframe_from_existing_table", lambda market, asset_type: fallback)

    frame = MarketUniverseSync._fetch_dataframe("US", "stock")

    assert calls == [("US", "stock")]
    assert frame.attrs["source"] == "database"
    assert "外部数据源不可用" in frame.attrs["warning"]
    assert frame.to_dict("records")[0]["symbol"] == "AAPL.US"


def test_subprocess_errors_are_summarized() -> None:
    error = subprocess.CalledProcessError(
        returncode=1,
        cmd=["python", "-c", "import akshare"],
        stderr="Traceback (most recent call last):\nboom",
    )

    assert MarketUniverseSync._safe_error_text(error) == "本地 AkShare 进程退出码 1"


def test_sync_markets_collects_partial_warnings(monkeypatch) -> None:
    monkeypatch.setattr(MarketUniverseSync, "_normalize_markets", lambda markets: ["US"])
    monkeypatch.setattr(MarketUniverseSync, "ensure_schema", lambda: None)
    monkeypatch.setattr(
        MarketUniverseSync,
        "sync_market",
        lambda market, user_id=1: {
            "market": market,
            "saved": 3,
            "warnings": ["US stocks: 外部数据源不可用，已使用可用降级数据"],
        },
    )

    result = MarketUniverseSync.sync_markets(markets=["US"], user_id=7)

    assert result["total_saved"] == 3
    assert result["partial_failure"] is True
    assert result["warning_count"] == 1
    assert result["warnings"][0].startswith("US stocks")


def test_sync_market_reuses_database_fallback_without_rewriting(monkeypatch) -> None:
    frame = pd.DataFrame([
        {
            "symbol": "AAPL.US",
            "name": "Apple Inc",
            "price": 190.12,
            "change_percent": 1.2,
            "volume": 1000,
            "market_cap": 100000,
            "pe_ratio": 30,
            "sector": "Tech",
        }
    ])
    frame.attrs["source"] = "database"
    frame.attrs["warning"] = "外部数据源不可用，已使用可用降级数据"

    monkeypatch.setattr(MarketUniverseSync, "_normalize_markets", lambda markets: ["US"])
    monkeypatch.setattr(MarketUniverseSync, "_fetch_dataframe", lambda market, asset_type: frame)

    def fail_upsert(*args, **kwargs):
        raise AssertionError("database fallback should not be rewritten")

    monkeypatch.setattr(MarketUniverseSync, "_upsert_rows", fail_upsert)

    result = MarketUniverseSync.sync_market("US", user_id=7)

    assert result["saved"] == 0
    assert result["reused"] == 1
    assert result["available"] == 1
    assert result["sources"] == {"stocks": "database", "etfs": "database"}
