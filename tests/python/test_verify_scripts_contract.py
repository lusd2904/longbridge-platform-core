from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def test_verify_platform_prefers_workspace_venv_and_runs_node_contracts() -> None:
    script = (ROOT / "scripts" / "verify_platform.sh").read_text(encoding="utf-8")

    assert "$ROOT_DIR/.venv/bin/python" in script
    assert '"$PYTHON_BIN" -m pytest tests/python' in script
    assert '"$NODE_BIN" --test tests/node/*.test.cjs' in script
    assert '"$PYTHON_BIN" scripts/check_platform_health.py' in script


def test_platform_health_check_retries_transient_payload_failures(monkeypatch) -> None:
    import check_platform_health

    attempts = {"count": 0}

    def fake_fetch_json(url: str) -> dict:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError("timed out")
        return {
            "service": "api-gateway",
            "version": "0.2.0",
            "status": "healthy",
            "status_text": "运行正常",
            "port": 5101,
            "checked_at": "2026-06-07T00:00:00Z",
            "deps": {},
            "brokerConnectivity": {},
        }

    monkeypatch.setattr(check_platform_health, "REQUEST_RETRIES", 2)
    monkeypatch.setattr(check_platform_health, "RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(check_platform_health, "fetch_json", fake_fetch_json)

    payload = check_platform_health.fetch_json_with_retries("http://127.0.0.1:5101/health")

    assert payload["service"] == "api-gateway"
    assert attempts["count"] == 2


def test_platform_log_check_allows_bounded_499_and_handled_provider_timeouts() -> None:
    import check_platform_logs

    text = "\n".join(
        [
            'web | "GET /svc/analysis/health HTTP/1.1" 200 12',
            'web | "GET /dashboard HTTP/1.1" 499 0',
            "analysis | OpenAI-compatible provider timeout handled: model=gpt task=scan",
        ]
    )

    report = check_platform_logs.parse_log_text(text)
    failures = check_platform_logs.evaluate_report(report, max_499_rate=0.5)

    assert report["status_counts"] == {"200": 1, "499": 1}
    assert report["handled_provider_timeout"] == 1
    assert failures == []


def test_platform_log_check_fails_on_server_errors_raw_timeouts_and_high_499() -> None:
    import check_platform_logs

    text = "\n".join(
        [
            'web | "GET /svc/analysis/health HTTP/1.1" 500 12',
            'web | "GET /dashboard HTTP/1.1" 499 0',
            "analysis | Read timed out",
        ]
    )

    report = check_platform_logs.parse_log_text(text)
    failures = check_platform_logs.evaluate_report(report, max_499_rate=0.1)

    assert "server_5xx=1" in failures
    assert "raw_timeout=1" in failures
    assert any(item.startswith("client_cancel_499_rate=") for item in failures)


def test_platform_log_check_ignores_redisbloom_error_rate_config_line() -> None:
    import check_platform_logs

    text = "\n".join(
        [
            'web | "GET /health HTTP/1.1" 200 12',
            "redis | 1:M 08 Jun 2026 04:53:51.425 * <bf>\t{ bf-error-rate       :      0.01 }",
        ]
    )

    report = check_platform_logs.parse_log_text(text)
    failures = check_platform_logs.evaluate_report(report, max_499_rate=0.1)

    assert report["anomalies"]["ERROR"] == 0
    assert failures == []


def test_platform_log_check_still_fails_on_real_error_lines() -> None:
    import check_platform_logs

    report = check_platform_logs.parse_log_text("analysis | ERROR failed to persist job")
    failures = check_platform_logs.evaluate_report(report, max_499_rate=0.1)

    assert report["anomalies"]["ERROR"] == 1
    assert "ERROR=1" in failures


def test_docker_api_probe_covers_release_api_contracts_without_persisting_tokens() -> None:
    script = (ROOT / "scripts" / "verify_docker_api_probe.mjs").read_text(encoding="utf-8")

    for endpoint in (
        "/svc/user/api/v1/auth/login",
        "/svc/trade/api/v1/trade/accounts",
        "/svc/analysis/health",
        "/svc/analysis/api/v1/analysis/analyze-positions",
        "/svc/analysis/api/v1/analysis/analyze-positions/jobs/definitely-missing-job-id",
        "/svc/risk/api/v1/risk/stoploss",
    ):
        assert endpoint in script

    assert "memory+redis_snapshot" in script
    assert "tradingMode" in script
    assert "isPaper" in script
    assert "DOCKER_API_PROBE_REPORT" in script
    assert "report.token" not in script
    assert "access_token:" not in script


def test_verify_module_exposes_all_module_contracts() -> None:
    script = (ROOT / "scripts" / "verify_module.sh").read_text(encoding="utf-8")

    for module_name in (
        "frontend",
        "platform",
        "market",
        "intelligence",
        "trading",
        "governance",
        "operations",
    ):
        assert f"verify_{module_name}()" in script

    assert "tests/python/test_watchlist_quant_strategy.py" in script
    assert "tests/python/test_trade_command_behaviors.py" in script
    assert "tests/python/test_notifications_read_model_fallback.py" in script
    assert "tests/node/*.test.cjs" in script


def test_verify_module_unknown_name_fails_fast() -> None:
    env = os.environ.copy()
    env["PYTHON_BIN"] = str(ROOT / ".venv" / "bin" / "python")
    result = subprocess.run(
        ["bash", "scripts/verify_module.sh", "unknown-module"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "usage:" in result.stdout


def test_verify_module_accepts_multiple_module_names() -> None:
    env = os.environ.copy()
    env["PYTHON_BIN"] = str(ROOT / ".venv" / "bin" / "python")
    result = subprocess.run(
        ["bash", "scripts/verify_module.sh", "governance", "operations"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "[module:governance]" in result.stdout
    assert "[module:operations]" in result.stdout


def test_longbridge_cli_auth_alias_is_created_from_latest_token(tmp_path) -> None:
    from ensure_refactor_env import ensure_longbridge_cli_auth_alias

    tokens_dir = tmp_path / ".longbridge" / "openapi" / "tokens"
    tokens_dir.mkdir(parents=True)
    old_token = tokens_dir / "old-token"
    new_token = tokens_dir / "new-token"
    old_token.write_text("old", encoding="utf-8")
    new_token.write_text("new", encoding="utf-8")
    os.utime(old_token, (100, 100))
    os.utime(new_token, (200, 200))

    alias = ensure_longbridge_cli_auth_alias(tmp_path)

    assert alias == tmp_path / ".longbridge" / "openapi" / "cli-auth"
    assert alias.is_symlink()
    assert os.readlink(alias) == "tokens/new-token"


def test_longbridge_cli_auth_alias_keeps_existing_alias(tmp_path) -> None:
    from ensure_refactor_env import ensure_longbridge_cli_auth_alias

    openapi_dir = tmp_path / ".longbridge" / "openapi"
    tokens_dir = openapi_dir / "tokens"
    tokens_dir.mkdir(parents=True)
    (tokens_dir / "new-token").write_text("new", encoding="utf-8")
    (tokens_dir / "existing-token").write_text("existing", encoding="utf-8")
    alias = openapi_dir / "cli-auth"
    alias.symlink_to(Path("tokens") / "existing-token")

    result = ensure_longbridge_cli_auth_alias(tmp_path)

    assert result == alias
    assert os.readlink(alias) == "tokens/existing-token"


def test_longbridge_cli_auth_alias_noops_without_tokens(tmp_path) -> None:
    from ensure_refactor_env import ensure_longbridge_cli_auth_alias

    assert ensure_longbridge_cli_auth_alias(tmp_path) is None


def test_longbridge_cli_runtime_files_sync_terminal_version(tmp_path) -> None:
    from ensure_refactor_env import ensure_longbridge_cli_runtime_files

    longbridge_home = tmp_path / ".longbridge"
    tokens_dir = longbridge_home / "openapi" / "tokens"
    tokens_dir.mkdir(parents=True)
    (tokens_dir / "token").write_text("{}", encoding="utf-8")
    (longbridge_home / ".terminal-last-run-version").write_text("0.21.0", encoding="utf-8")

    alias = ensure_longbridge_cli_runtime_files(tmp_path, cli_version="0.23.0")

    assert alias == longbridge_home / "openapi" / "cli-auth"
    assert (longbridge_home / ".terminal-last-run-version").read_text(encoding="utf-8") == "0.23.0"
    assert (longbridge_home / ".terminal-latest-version").read_text(encoding="utf-8") == "0.23.0"
