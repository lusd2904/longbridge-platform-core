from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_MAIN = ROOT / "apps/intelligence/analysis-service/src/main.py"
AGENT_RUN_SERVICE = ROOT / "backend-server/src/core/analysis/AgentRunService.py"


def _function_source(function_name: str) -> str:
    source = ANALYSIS_MAIN.read_text(encoding="utf-8")
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
    assert "_finish_watchlist_run(" not in source


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
