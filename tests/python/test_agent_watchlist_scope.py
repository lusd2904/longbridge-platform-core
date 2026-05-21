from __future__ import annotations

import ast
import asyncio
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_MAIN = ROOT / "apps/intelligence/analysis-service/src/main.py"
SCHEDULER_MAIN = ROOT / "apps/operations/scheduler-service/src/main.py"
AGENT_RUN_SERVICE = ROOT / "backend-server/src/core/analysis/AgentRunService.py"
DAILY_MARKET_SCAN_SCHEDULER = ROOT / "backend-server/src/core/analysis/DailyMarketScanScheduler.py"
LEGACY_SCHEDULER_PATHS = [
    ROOT / "backend-server/src/core/analysis/FinanceBriefingScheduler.py",
    ROOT / "backend-server/src/core/analysis/HistoricalMarketDataScheduler.py",
    ROOT / "backend-server/src/core/analysis/MarketHistoryBackfillScheduler.py",
    ROOT / "backend-server/src/core/analysis/MarketInsightScheduler.py",
    ROOT / "backend-server/src/core/analysis/MarketUniverseScheduler.py",
    ROOT / "backend-server/src/core/analysis/RecommendationScheduler.py",
    ROOT / "backend-server/src/core/analysis/DailySymbolTrendScanScheduler.py",
]
MARKET_INSIGHT_SERVICE = ROOT / "backend-server/src/core/analysis/MarketInsightService.py"
RECOMMENDATION_SERVICE = ROOT / "backend-server/src/core/analysis/RecommendationService.py"
BROKER_INTERFACE = ROOT / "backend-server/src/core/broker/BrokerInterface.py"
COMPOSE_FILE = ROOT / "docker-compose.yml"
MARKET_SERVICE_MAIN = ROOT / "apps/market/market-service/src/main.py"
MARKET_STOCK_POOL_QUERY = ROOT / "apps/market/market-service/src/stock_pool_query.py"
DATA_ROUTES = ROOT / "backend-server/src/api/data_routes.py"
AGNO_SIDECAR_MAIN = ROOT / "apps/intelligence/agno-sidecar/src/main.py"


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _function_source(function_name: str) -> str:
    source = ANALYSIS_MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"{function_name} not found")


def _scheduler_function_source(function_name: str) -> str:
    source = SCHEDULER_MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"{function_name} not found")


def test_watchlist_review_resolves_requested_user_through_session_scope() -> None:
    source = _function_source("watchlist_review")

    assert "_resolve_agent_run_scope_user_id(" in source
    assert "session=auth_session" in source
    assert "requested_user_id=raw_user_id" in source
    assert "user_id = int(raw_user_id)" not in source


def test_watchlist_review_returns_accepted_before_sidecar_call() -> None:
    source = _function_source("watchlist_review")

    assert "_start_watchlist_review_worker(" in source
    assert "_build_watchlist_review_accepted_result(" in source
    assert "_call_agno_watchlist_sidecar(" not in source


def test_watchlist_review_skips_empty_targets_before_creating_run() -> None:
    source = _function_source("watchlist_review")

    empty_check = "if not targets:\n        return _build_watchlist_review_skipped_result("
    assert empty_check in source
    assert source.index(empty_check) < source.index("db_run_id = _create_watchlist_run(")
    assert source.index(empty_check) < source.index("_start_watchlist_review_worker(")


def test_watchlist_skipped_result_uses_business_status_without_worker() -> None:
    source = _function_source("_build_watchlist_review_skipped_result")

    assert 'status="skipped"' in source
    assert 'payload["accepted"] = False' in source
    assert 'payload["async"] = False' in source
    assert 'payload["skipped"] = True' in source
    assert 'payload["reason"] = "no_targets"' in source
    assert "_create_watchlist_run(" not in source
    assert "_start_watchlist_review_worker(" not in source


def test_watchlist_review_empty_targets_returns_skipped_without_run(monkeypatch) -> None:
    module = _load_module("analysis_service_main_empty_targets_test", ANALYSIS_MAIN)
    calls = {"create": 0, "worker": 0, "load": 0}

    monkeypatch.setattr(module, "_load_watchlist_scan_targets", lambda *args, **kwargs: calls.__setitem__("load", calls["load"] + 1) or [])
    monkeypatch.setattr(module, "_create_watchlist_run", lambda *args, **kwargs: calls.__setitem__("create", calls["create"] + 1) or 101)
    monkeypatch.setattr(module, "_start_watchlist_review_worker", lambda *args, **kwargs: calls.__setitem__("worker", calls["worker"] + 1))

    result = asyncio.run(module.watchlist_review(
        payload={"session": "pre_open", "targets": [], "triggerSource": "test", "dryRun": True},
        auth_session={"user_id": 1, "role": "admin"},
    ))

    assert result["status"] == "skipped"
    assert result["reason"] == "no_targets"
    assert result["accepted"] is False
    assert result["async"] is False
    assert result["skipped"] is True
    assert result["targetsCount"] == 0
    assert calls == {"create": 0, "worker": 0, "load": 1}


def test_watchlist_review_reuses_recent_idempotent_run(monkeypatch) -> None:
    module = _load_module("analysis_service_watchlist_idempotency_test", ANALYSIS_MAIN)
    calls = {"create": 0, "worker": 0}

    monkeypatch.setattr(module, "_load_watchlist_scan_targets", lambda *args, **kwargs: ["AAPL.US"])
    monkeypatch.setattr(module, "_build_watchlist_idempotency_key", lambda **kwargs: "idem-1")
    monkeypatch.setattr(
        module,
        "_find_recent_watchlist_run_by_idempotency_key",
        lambda **kwargs: {"runId": 77, "status": "queued", "inputSummary": {"idempotencyKey": "idem-1"}},
    )
    monkeypatch.setattr(module, "_create_watchlist_run", lambda *args, **kwargs: calls.__setitem__("create", calls["create"] + 1) or 101)
    monkeypatch.setattr(module, "_start_watchlist_review_worker", lambda *args, **kwargs: calls.__setitem__("worker", calls["worker"] + 1))

    result = asyncio.run(module.watchlist_review(
        payload={"session": "pre_open", "targets": ["AAPL.US"], "triggerSource": "manual", "dryRun": True},
        auth_session={"user_id": 1, "role": "admin"},
    ))

    assert result["accepted"] is True
    assert result["deduped"] is True
    assert result["agentRunId"] == 77
    assert result["idempotencyKey"] == "idem-1"
    assert calls == {"create": 0, "worker": 0}


def test_watchlist_review_preserves_auto_buy_payload_for_worker(monkeypatch) -> None:
    module = _load_module("analysis_service_watchlist_auto_buy_payload_test", ANALYSIS_MAIN)
    captured = {}

    monkeypatch.setattr(module, "_load_watchlist_scan_targets", lambda *args, **kwargs: ["AAPL.US"])
    monkeypatch.setattr(module, "_build_watchlist_idempotency_key", lambda **kwargs: "idem-auto-buy")
    monkeypatch.setattr(module, "_find_recent_watchlist_run_by_idempotency_key", lambda **kwargs: None)
    monkeypatch.setattr(module, "_create_watchlist_run", lambda **kwargs: captured.setdefault("created", kwargs) or 101)
    monkeypatch.setattr(module, "_start_watchlist_review_worker", lambda **kwargs: captured.setdefault("worker", kwargs))

    auto_buy = {
        "enabled": True,
        "maxSymbols": 3,
        "maxAmount": 5000.0,
        "maxPositionRatio": 0.12,
        "minConfidence": 80,
    }
    result = asyncio.run(module.watchlist_review(
        payload={
            "session": "pre_open",
            "targets": ["AAPL.US"],
            "triggerSource": "scheduler",
            "dryRun": False,
            "autoBuy": auto_buy,
        },
        auth_session={"user_id": 1, "role": "admin"},
    ))

    assert result["accepted"] is True
    assert captured["created"]["request_payload"]["autoBuy"] == auto_buy
    assert captured["worker"]["sidecar_payload"]["autoBuy"] == auto_buy
    assert captured["worker"]["sidecar_payload"]["dryRun"] is False


def test_scheduler_does_not_fallback_to_first_active_user_when_watchlist_empty() -> None:
    list_users_source = _scheduler_function_source("_list_watchlist_review_users")

    assert list_users_source
    assert "empty-watchlist-fallback" not in list_users_source
    assert "ORDER BY CASE WHEN role = 'admin'" not in list_users_source
    assert "return []" in list_users_source


def test_scheduler_watchlist_user_query_uses_target_session_and_active_users() -> None:
    list_users_source = _scheduler_function_source("_list_watchlist_review_users")

    assert 'flag_column = "scan_before_open" if session_name == "pre_open" else "scan_after_close"' in list_users_source
    assert "JOIN user_watchlist_stocks w" in list_users_source
    assert "w.{flag_column} = 1" in list_users_source
    assert "COALESCE(u.status, 'active') NOT IN ('disabled', 'locked')" in list_users_source
    assert "ORDER BY target_count DESC, u.id ASC" in list_users_source


def test_scheduler_empty_watchlist_marks_skipped_without_analysis_call(monkeypatch) -> None:
    module = _load_module("scheduler_service_main_empty_watchlist_test", SCHEDULER_MAIN)
    writes = []
    calls = {"analysis": 0}

    monkeypatch.setattr(module, "_list_watchlist_review_users", lambda session_name: [])
    monkeypatch.setattr(module, "_write_job_status", lambda *args, **kwargs: writes.append((args, kwargs)))
    monkeypatch.setattr(module, "_request_watchlist_review_for_user", lambda *args, **kwargs: calls.__setitem__("analysis", calls["analysis"] + 1))

    result = module._run_watchlist_review("pre_open")

    assert result["success"] is True
    assert result["skipped"] is True
    assert result["reason"] == "empty-watchlist"
    assert result["userCount"] == 0
    assert result["results"] == []
    assert calls["analysis"] == 0
    assert writes[-1][0][0] == "watchlist_pre_open_review"
    assert writes[-1][0][1] == "skipped"


def test_scheduler_counts_skipped_reviews_separately_from_success() -> None:
    run_source = _scheduler_function_source("_run_watchlist_review")

    assert run_source
    assert "_is_watchlist_review_skipped(result_payload)" in run_source
    assert "skipped_count = len(skipped)" in run_source
    assert "len(users) - len(failures) - skipped_count" in run_source
    assert '"skippedCount": skipped_count' in run_source


def test_scheduler_watchlist_auto_buy_settings_are_bounded(monkeypatch) -> None:
    module = _load_module("scheduler_service_auto_buy_settings_test", SCHEDULER_MAIN)

    monkeypatch.setattr(
        module.SystemTaskService,
        "get_policy",
        lambda task_key: {
            "settings": {
                "autoBuyEnabled": "yes",
                "autoBuyMaxSymbols": "99",
                "autoBuyMaxAmount": "-5",
                "autoBuyMaxPositionRatio": "bad-value",
                "autoBuyMinConfidence": "101",
            }
        },
    )

    assert module._watchlist_auto_buy_settings("pre_open") == {
        "enabled": True,
        "maxSymbols": 10,
        "maxAmount": 0.0,
        "maxPositionRatio": 0.08,
        "minConfidence": 100,
    }


def test_scheduler_watchlist_payload_disables_dry_run_when_auto_buy_enabled(monkeypatch) -> None:
    module = _load_module("scheduler_service_auto_buy_payload_test", SCHEDULER_MAIN)
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"success": true, "data": {"status": "accepted"}}'

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        captured["payload"] = __import__("json").loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(module, "generate_token", lambda *args, **kwargs: "token")
    monkeypatch.setattr(
        module,
        "_watchlist_auto_buy_settings",
        lambda session_name: {
            "enabled": True,
            "maxSymbols": 3,
            "maxAmount": 5000.0,
            "maxPositionRatio": 0.12,
            "minConfidence": 80,
        },
    )
    monkeypatch.setattr(module.urlrequest, "urlopen", fake_urlopen)

    result = module._request_watchlist_review_for_user(
        "pre_open",
        {"userId": 7, "username": "alpha", "role": "user"},
    )

    assert result["success"] is True
    assert captured["payload"]["dryRun"] is False
    assert captured["payload"]["autoBuy"] == {
        "enabled": True,
        "maxSymbols": 3,
        "maxAmount": 5000.0,
        "maxPositionRatio": 0.12,
        "minConfidence": 80,
    }


def test_scheduler_watchlist_payload_keeps_dry_run_when_auto_buy_disabled(monkeypatch) -> None:
    module = _load_module("scheduler_service_auto_buy_disabled_payload_test", SCHEDULER_MAIN)
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"success": true, "data": {"status": "accepted"}}'

    def fake_urlopen(request, timeout):
        captured["payload"] = __import__("json").loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(module, "generate_token", lambda *args, **kwargs: "token")
    monkeypatch.setattr(
        module,
        "_watchlist_auto_buy_settings",
        lambda session_name: {
            "enabled": False,
            "maxSymbols": 3,
            "maxAmount": 5000.0,
            "maxPositionRatio": 0.0,
            "minConfidence": 80,
        },
    )
    monkeypatch.setattr(module.urlrequest, "urlopen", fake_urlopen)

    result = module._request_watchlist_review_for_user(
        "pre_open",
        {"userId": 7, "username": "alpha", "role": "user"},
    )

    assert result["success"] is True
    assert captured["payload"]["dryRun"] is True
    assert captured["payload"]["autoBuy"] == {
        "enabled": False,
        "maxSymbols": 3,
        "maxAmount": 5000.0,
        "maxPositionRatio": 0.0,
        "minConfidence": 80,
    }


def test_scheduler_runs_watchlist_review_for_listed_users_only(monkeypatch) -> None:
    module = _load_module("scheduler_service_main_listed_users_test", SCHEDULER_MAIN)
    requested = []
    writes = []
    users = [
        {"userId": 7, "username": "alpha", "role": "user", "targetCount": 4, "reason": "watchlist-targets"},
        {"userId": 9, "username": "beta", "role": "admin", "targetCount": 2, "reason": "watchlist-targets"},
    ]

    def fake_request(session_name, user):
        requested.append((session_name, user["userId"]))
        return {"success": True, "data": {"status": "succeeded", "summary": "ok"}}

    monkeypatch.setattr(module, "_list_watchlist_review_users", lambda session_name: list(users))
    monkeypatch.setattr(module, "_request_watchlist_review_for_user", fake_request)
    monkeypatch.setattr(module, "_write_job_status", lambda *args, **kwargs: writes.append((args, kwargs)))

    result = module._run_watchlist_review("post_close")

    assert requested == [("post_close", 7), ("post_close", 9)]
    assert result["success"] is True
    assert result["userCount"] == 2
    assert result["successCount"] == 2
    assert result["failureCount"] == 0
    assert writes[-1][0][0] == "watchlist_post_close_review"
    assert writes[-1][0][1] == "success"


def test_market_scan_scheduler_does_not_hardcode_bootstrap_user() -> None:
    run_source = _scheduler_function_source("_run_market_scan")
    runner_source = SCHEDULER_MAIN.read_text(encoding="utf-8")
    legacy_scheduler_source = DAILY_MARKET_SCAN_SCHEDULER.read_text(encoding="utf-8")

    assert "refresh_all_markets(user_id=1)" not in run_source
    assert "refresh_all_markets(user_id=1)" not in legacy_scheduler_source
    assert '"daily_market_ai_scan": lambda user_id: _run_market_scan(user_id)' in runner_source
    assert "resolve_task_execution_user(" in run_source
    assert "resolve_task_execution_user(" in legacy_scheduler_source


def test_market_scan_manual_run_uses_resolved_execution_user(monkeypatch) -> None:
    module = _load_module("scheduler_service_main_market_scan_user_test", SCHEDULER_MAIN)
    calls = {"user_ids": [], "updates": []}

    monkeypatch.setattr(module.daily_market_scan_scheduler, "_ensure_job_table", lambda: None)
    monkeypatch.setattr(
        module.daily_market_scan_scheduler,
        "_update_job",
        lambda *args, **kwargs: calls["updates"].append((args, kwargs)),
    )
    monkeypatch.setattr(
        module,
        "resolve_task_execution_user",
        lambda task_key, requested_user_id=None: {
            "userId": int(requested_user_id),
            "username": "real-user",
            "role": "admin",
            "reason": "request-user",
        },
    )

    import core.analysis.DailyMarketScanService as market_scan_module

    monkeypatch.setattr(
        market_scan_module.DailyMarketScanService,
        "refresh_all_markets",
        lambda user_id: calls["user_ids"].append(user_id) or {"markets": [{"market": "US"}]},
    )

    result = module._run_market_scan(user_id=8)

    assert calls["user_ids"] == [8]
    assert result["executionUser"]["userId"] == 8
    assert result["executionUser"]["reason"] == "request-user"
    assert calls["updates"][-1][0][0] == "success"


def test_legacy_scheduler_paths_do_not_hardcode_bootstrap_user() -> None:
    banned_snippets = [
        "refresh_all_markets(user_id=1",
        "refresh_all_profiles(user_id=1",
        "sync_markets(markets=markets, user_id=1",
        "run_batch(\n            analysis_date=target_date,\n            batch_size=batch_size,\n            cursor=cursor,\n            user_id=1",
        "backfill_symbol_history(\n                    symbol,\n                    start_date=start_date,\n                    end_date=end_date,\n                    user_id=1",
        "refresh_symbol(\n                        symbol,\n                        user_id=1",
        "sync_tracked_universe()",
    ]

    for path in LEGACY_SCHEDULER_PATHS:
        source = path.read_text(encoding="utf-8")
        assert "resolve_task_execution_user" in source, path.name
        for snippet in banned_snippets:
            assert snippet not in source, path.name


def test_historical_sync_service_uses_resolved_user_instead_of_bootstrap() -> None:
    source = (ROOT / "backend-server/src/core/analysis/HistoricalMarketDataService.py").read_text(encoding="utf-8")
    assert "saved_count += cls.sync_symbol(symbol, user_id=1" not in source
    assert "sync_user_id = cls._resolve_symbol_sync_user_id(symbol, user_ids)" in source
    assert "saved_count += cls.sync_symbol(symbol, user_id=sync_user_id" in source


def test_market_insight_quotes_do_not_fallback_to_bootstrap_account() -> None:
    source = MARKET_INSIGHT_SERVICE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fetch_quotes_source = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_fetch_quotes":
            fetch_quotes_source = ast.get_source_segment(source, node) or ""
            break

    assert fetch_quotes_source
    assert "manager.list_accounts(user_id=user_id) or manager.list_accounts(user_id=1)" not in fetch_quotes_source
    assert "owner_user_id =" not in fetch_quotes_source
    assert "manager.get_broker(account_id, user_id=user_id)" in fetch_quotes_source
    assert "return cls._fetch_quotes_from_database(symbols)" in fetch_quotes_source


def test_recommendation_ai_calls_preserve_execution_user() -> None:
    source = RECOMMENDATION_SERVICE.read_text(encoding="utf-8")

    assert "cls._enrich_with_ai(profile, candidates[:12], user_id=user_id)" in source
    assert "cls._generate_summary(profile, enriched_items, user_id=user_id)" in source
    assert "AIAnalyst.get_decision(None, prompt, task='recommend_brief', user_id=user_id)" in source
    assert "AIAnalyst.get_decision(None, prompt, task='recommend_summary', user_id=user_id)" in source
    assert "AIAnalyst.get_decision(None, prompt, task='recommend_brief')" not in source
    assert "AIAnalyst.get_decision(None, prompt, task='recommend_summary')" not in source


def test_broker_account_list_excludes_inactive_by_default() -> None:
    source = BROKER_INTERFACE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    list_accounts_source = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "list_accounts":
            list_accounts_source = ast.get_source_segment(source, node) or ""
            break

    assert list_accounts_source
    assert "include_inactive: bool = False" in list_accounts_source
    assert "AND (%s = 1 OR is_active = 1)" in list_accounts_source
    assert "rows = self.db.query_all(sql, (user_id, 1 if include_inactive else 0))" in list_accounts_source


def test_agent_run_service_exposes_atomic_claim() -> None:
    source = AGENT_RUN_SERVICE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    claim_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "claim_run":
            claim_node = node
            break

    assert claim_node is not None, "AgentRunService.claim_run is required for async workers"
    claim_source = ast.get_source_segment(source, claim_node) or ""
    assert "WHERE run_id = %s AND status = %s" in claim_source
    assert '"queued"' in claim_source


def test_agent_run_service_exposes_stranded_cleanup() -> None:
    source = AGENT_RUN_SERVICE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    cleanup_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "cancel_stale_runs":
            cleanup_node = node
            break

    assert cleanup_node is not None, "AgentRunService.cancel_stale_runs is required for restart cleanup"
    cleanup_source = ast.get_source_segment(source, cleanup_node) or ""
    assert "status IN (%s, %s)" in cleanup_source
    assert '"queued"' in cleanup_source
    assert '"running"' in cleanup_source
    assert "DATE_SUB(NOW(), INTERVAL %s MINUTE)" in cleanup_source
    assert '"cancelled"' in cleanup_source


def test_analysis_service_registers_startup_stranded_cleanup() -> None:
    source = ANALYSIS_MAIN.read_text(encoding="utf-8")
    assert 'app.add_event_handler("startup", _cleanup_stranded_agent_runs)' in source
    assert '("cancel_stale_runs",)' in source


def test_compose_runs_agno_sidecar_container() -> None:
    source = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "agno-sidecar:" in source
    assert "container_name: refactor-v2-agno-sidecar" in source
    assert "apps/intelligence/agno-sidecar/src" in source
    assert "REF_AGNO_SIDECAR_URL: ${REF_AGNO_SIDECAR_URL:-http://agno-sidecar:3200}" in source


def test_analysis_service_posts_payload_to_agno_form_endpoint() -> None:
    source = _function_source("_post_agno_team_run")

    assert '"payload": json.dumps(payload, ensure_ascii=False, default=str)' in source
    assert '"Content-Type": "application/x-www-form-urlencoded"' in source
    assert "urllib_parse.urlencode(form_payload)" in source


def test_agno_sidecar_parses_form_encoded_team_runs() -> None:
    source = AGNO_SIDECAR_MAIN.read_text(encoding="utf-8")

    assert "application/x-www-form-urlencoded" in source
    assert "urllib_parse.parse_qs" in source
    assert 'payload.get("payload")' in source
    assert "json.loads(str(embedded_payload))" in source
    assert "async def watchlist_review(request: Request)" in source
    assert "request_payload = await _parse_request_payload(request)" in source


def test_user_stock_pool_paths_do_not_use_bootstrap_user_fallback() -> None:
    banned_snippets = [
        "user_id = %s OR user_id = 1",
        "user_id = 1 OR user_id = %s",
        "OR user_id = 1",
        "user_id IN (%s, 1)",
        "user_id = 1 OR user_id IS NULL",
        "CASE WHEN user_id = 1",
    ]
    for path in (DATA_ROUTES, MARKET_SERVICE_MAIN, MARKET_STOCK_POOL_QUERY):
        source = path.read_text(encoding="utf-8")
        for snippet in banned_snippets:
            assert snippet not in source, path.name
