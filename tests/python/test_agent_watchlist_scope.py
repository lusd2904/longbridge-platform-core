from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_MAIN = ROOT / "apps/intelligence/analysis-service/src/main.py"


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
