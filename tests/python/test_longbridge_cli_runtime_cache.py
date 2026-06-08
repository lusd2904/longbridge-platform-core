from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from apps.market import longbridge_cli_runtime as runtime


def test_auth_status_is_cached_and_returned_as_copy(monkeypatch) -> None:
    calls = []

    def fake_run(args, timeout=None, require_paper_account=True):
        calls.append((tuple(args), timeout, require_paper_account))
        return {
            "account": {
                "account_channel": runtime.PAPER_ACCOUNT_CHANNEL,
                "account_no": f"{runtime.PAPER_ACCOUNT_NO_PREFIX}123",
            }
        }

    monkeypatch.setattr(runtime, "run_longbridge_cli", fake_run)
    with runtime._AUTH_STATUS_CACHE_LOCK:
        runtime._AUTH_STATUS_CACHE["expires_at"] = 0.0
        runtime._AUTH_STATUS_CACHE["payload"] = None

    first = runtime.auth_status()
    first["account"] = {"account_channel": "mutated"}
    second = runtime.auth_status()

    assert calls == [(("auth", "status"), 15, False)]
    assert second["account"]["account_channel"] == runtime.PAPER_ACCOUNT_CHANNEL


def test_ensure_paper_trading_reuses_cached_auth_status(monkeypatch) -> None:
    calls = []

    def fake_run(args, timeout=None, require_paper_account=True):
        calls.append(args)
        return {
            "account": {
                "account_channel": runtime.PAPER_ACCOUNT_CHANNEL,
                "account_no": f"{runtime.PAPER_ACCOUNT_NO_PREFIX}123",
            }
        }

    monkeypatch.setattr(runtime, "run_longbridge_cli", fake_run)
    with runtime._AUTH_STATUS_CACHE_LOCK:
        runtime._AUTH_STATUS_CACHE["expires_at"] = 0.0
        runtime._AUTH_STATUS_CACHE["payload"] = None

    runtime.ensure_paper_trading()
    runtime.ensure_paper_trading()

    assert calls == [["auth", "status"]]


def test_trade_context_cancel_order_accepts_plain_text_cli_success(monkeypatch) -> None:
    calls = []

    def fake_run(args, timeout=None, expect_json=True, require_paper_account=True):
        calls.append((args, timeout, expect_json, require_paper_account))
        return "Order ord-1 cancelled.\n"

    monkeypatch.setattr(runtime, "ensure_paper_trading", lambda: None)
    monkeypatch.setattr(runtime, "run_longbridge_cli", fake_run)

    result = runtime.CliTradeContext().cancel_order("ord-1")

    assert result.success is True
    assert result.order_id == "ord-1"
    assert result.message == "Order ord-1 cancelled."
    assert calls == [(["order", "cancel", "ord-1", "--yes"], 60, False, True)]


def test_run_longbridge_cli_records_rate_limit_cooldown(monkeypatch, caplog) -> None:
    monkeypatch.setattr(runtime, "ensure_paper_trading", lambda: None)
    monkeypatch.setattr(runtime, "_CLI_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(runtime, "_CLI_RATE_LIMIT_COOLDOWN_SECONDS", 8.0)
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(runtime.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="Error: API error (code 429002): api request is limited, please slow down request frequency",
        ),
    )
    runtime._CLI_LAST_REQUEST_AT = 0.0
    runtime._CLI_RATE_LIMIT_UNTIL = 0.0

    with caplog.at_level(logging.WARNING, logger=runtime.LOGGER.name):
        with pytest.raises(runtime.LongbridgeCliRateLimitError):
            runtime.run_longbridge_cli(["quote", "AAPL.US"])

    assert runtime._CLI_RATE_LIMIT_UNTIL == 108.0
    assert any("Longbridge CLI rate limit cooldown activated" in record.getMessage() for record in caplog.records)


def test_run_longbridge_cli_respects_minimum_interval(monkeypatch) -> None:
    monotonic_values = iter([10.2, 10.75])
    slept = []

    monkeypatch.setattr(runtime, "ensure_paper_trading", lambda: None)
    monkeypatch.setattr(runtime, "_CLI_MIN_INTERVAL_SECONDS", 0.75)
    monkeypatch.setattr(runtime.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(runtime.time, "sleep", lambda seconds: slept.append(round(seconds, 2)))
    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="{}", stderr=""),
    )
    runtime._CLI_LAST_REQUEST_AT = 10.0
    runtime._CLI_RATE_LIMIT_UNTIL = 0.0

    assert runtime.run_longbridge_cli(["quote", "AAPL.US"]) == {}
    assert slept == [0.55]
    assert runtime._CLI_LAST_REQUEST_AT == 10.75


def test_quote_batches_large_symbol_lists(monkeypatch) -> None:
    calls = []

    def fake_run(args):
        calls.append(tuple(args))
        return [{"symbol": symbol, "last": "10", "prev_close": "9"} for symbol in args[1:]]

    monkeypatch.setenv("LONGBRIDGE_CLI_QUOTE_BATCH_SIZE", "2")
    monkeypatch.setattr(runtime, "run_longbridge_cli", fake_run)

    result = runtime.CliQuoteContext().quote(["aapl.us", "MSFT.US", " tsla.us ", "NVDA.US", "GOOG.US"])

    assert calls == [
        ("quote", "AAPL.US", "MSFT.US"),
        ("quote", "TSLA.US", "NVDA.US"),
        ("quote", "GOOG.US"),
    ]
    assert [item.symbol for item in result] == ["AAPL.US", "MSFT.US", "TSLA.US", "NVDA.US", "GOOG.US"]
    assert [item.change for item in result] == [1.0, 1.0, 1.0, 1.0, 1.0]


def test_quote_skips_empty_symbols_without_cli(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(runtime, "run_longbridge_cli", lambda args: calls.append(tuple(args)))

    assert runtime.CliQuoteContext().quote(["", "  ", None]) == []
    assert calls == []
