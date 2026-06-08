#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-}"
NODE_BIN="${NODE_BIN:-node}"
NPM_BIN="${NPM_BIN:-npm}"

if [ -z "$PYTHON_BIN" ]; then
  if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"

usage() {
  echo "usage: $0 <frontend|platform|market|intelligence|trading|governance|operations|all> [module...]"
}

run_pytest() {
  "$PYTHON_BIN" -m pytest -q "$@"
}

verify_frontend() {
  echo "[module:frontend] vitest unit contract"
  "$NPM_BIN" --prefix apps/frontend/web-portal run test:unit
  echo "[module:frontend] node smoke/gate contract"
  "$NODE_BIN" --test tests/node/*.test.cjs
}

verify_platform() {
  echo "[module:platform] bootstrap, service map, health contract tests"
  run_pytest \
    tests/python/test_platform_bootstrap_cache.py \
    tests/python/test_service_category_layout.py \
    tests/python/test_service_edges_contract.py \
    tests/python/test_shared_health_contract.py \
    tests/python/test_module_standalone_entrypoints.py \
    tests/python/test_service_direct_entrypoints.py
}

verify_market() {
  echo "[module:market] market data, fallback, sentiment contract tests"
  run_pytest \
    tests/python/test_market_live_cache.py \
    tests/python/test_market_universe_sync.py \
    tests/python/test_skshare_history_and_sub2api.py \
    tests/python/test_fast_read_paths.py \
    tests/python/test_sentiment_service_contract.py
}

verify_intelligence() {
  echo "[module:intelligence] analysis, agent, strategy contract tests"
  run_pytest \
    tests/python/test_agent_override_workflow.py \
    tests/python/test_agent_watchlist_scope.py \
    tests/python/test_analysis_long_chain_guardrails.py \
    tests/python/test_analysis_service_real_data_only.py \
    tests/python/test_watchlist_quant_strategy.py \
    tests/python/test_strategy_monitor_auto_execution.py
}

verify_trading() {
  echo "[module:trading] trade runtime, command, broker boundary tests"
  run_pytest \
    tests/python/test_longbridge_broker_place_order.py \
    tests/python/test_risk_manager_order_minimum.py \
    tests/python/test_trade_command_behaviors.py \
    tests/python/test_trade_command_module_split.py \
    tests/python/test_trade_command_orchestration_split.py \
    tests/python/test_trade_dashboard_summary_snapshot_fast_path.py \
    tests/python/test_trade_realtime_ux_guardrails.py \
    tests/python/test_trade_runtime_explicit_package.py \
    tests/python/test_trade_runtime_internal_module_split.py \
    tests/python/test_trade_service_duplicate_helper_consolidation.py
}

verify_governance() {
  echo "[module:governance] risk and notification contract tests"
  run_pytest \
    tests/python/test_notifications_read_model_fallback.py \
    tests/python/test_risk_manager_order_minimum.py
}

verify_operations() {
  echo "[module:operations] scheduler and agent workflow contract tests"
  run_pytest \
    tests/python/test_daily_market_scan_status.py \
    tests/python/test_watchlist_us_open_ai_trade_scheduler.py \
    tests/python/test_agent_watchlist_scope.py
}

verify_one() {
  case "${1:-}" in
    frontend) verify_frontend ;;
    platform) verify_platform ;;
    market) verify_market ;;
    intelligence) verify_intelligence ;;
    trading) verify_trading ;;
    governance) verify_governance ;;
    operations) verify_operations ;;
    *)
      usage
      exit 1
      ;;
  esac
}

if [ "$#" -eq 0 ]; then
  usage
  exit 1
fi

if [ "$*" = "all" ]; then
  for module in frontend platform market intelligence trading governance operations; do
    verify_one "$module"
  done
else
  for module in "$@"; do
    if [ "$module" = "all" ]; then
      usage
      exit 1
    fi
    verify_one "$module"
  done
fi
