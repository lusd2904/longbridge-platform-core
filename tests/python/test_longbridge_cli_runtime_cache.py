from __future__ import annotations

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
