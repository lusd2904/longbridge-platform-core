# Watchlist Quant Review 2026-05-21

## Scope

本轮补齐自选池量化策略后续项：

- 券商当日未完成委托防重。
- 自选池量化扫描历史。
- 单标的策略复盘。
- 策略页扫描历史和复盘入口。
- README 与架构文档同步。

## External Tool Status

| Tool | Result |
| --- | --- |
| Antigravity CLI | `python3 scripts/antigravity_cli_adapter.py probe` 可定位 `/Users/lusd/.local/bin/agy`，并显示 Gemini fallback `/Users/lusd/.local/bin/gemini` 可用；adapter 已支持 OAuth/auth 阻塞时自动改用 Gemini CLI。 |
| Gemini CLI | `gemini --help` 验证 `--prompt` 非交互入口可用；实际只读评估结论为“暂无明显阻塞项”，同时确认 fallback 描述与自动买入安全边界自洽。 |
| NotebookLM CLI | `nlm` 版本 `0.6.10`，`server_info` 显示 `auth_status=configured` 且无更新；`nlm notebook list` 可列出既有 refactor-v2 README / 架构评估 notebook。 |

NotebookLM 对既有 `refactor-v2 架构联动评估 20260521` notebook 的只读 query 明确提示：notebook 来源未包含本轮最新改动，因此只能基于旧 README / 架构材料推演。采纳其中两条仍有效的文档风险：

- 防重权威源需要写清，避免读者误以为前端或策略页缓存可以判断当日未完成委托。
- “策略复盘”需要和 Agent review / 人工复核区分。

## Accepted Fixes

- `QuantTradingService.execute_watchlist_opportunities()` 在执行前查询券商当日订单；如果查询失败或发现同标的同方向未完成委托，则阻止自动下单。
- `QuantTradingService.execute_watchlist_opportunities()` 已按规范化标的去重，避免 `AAPL` 与 `AAPL.US` 这类同股不同写法触发重复买入决策。
- `QuantTradingService.run_watchlist_strategy_cycle()` 保存每次扫描 run 和 item 明细。
- `QuantTradingService.run_watchlist_strategy_backtest()` 用历史日线回放同一套评分逻辑，输出信号次数、胜率、5 日后收益均值和评分路径。
- Strategy Service 新增：
  - `GET /api/v1/strategy/quant/watchlist/history`
  - `POST /api/v1/strategy/quant/watchlist/backtest`
- Strategy 页面新增“扫描历史”和“策略复盘”两个面板。
- 根 README、Strategy Service README、Trade Service README、架构联动文档和 service map 已同步执行条件、返回字段、阅读顺序、验证点和执行边界。
- Strategy Service README 和架构联动文档已补充：防重以券商当日实时订单查询为当前权威源；策略复盘是历史价格回放，不是 Agent review。
- Trade Service README 已补充：它是唯一 broker 写边界，策略和分析只能送建议，不能直接写订单状态。
- `docs/service-map.yaml` 已补充 analysis 的量化因子输入、strategy 的轻量仓位预算建议、trade 的规范化订单状态投影。
- Antigravity CLI adapter 已补齐授权阻塞 fallback，后续外部评估不会因为反复 OAuth 授权而停住。
- 新增 `docs/adr-quant-github-patterns-20260522.md`，把 Lean/Qlib/vn.py/PyPortfolioOpt 的借鉴范围、非目标和边界归属单独固定下来。

## Verification

- `python3 -m py_compile backend-server/src/core/analysis/QuantTradingService.py apps/intelligence/strategy-service/src/main.py`
- `python3 -m py_compile scripts/antigravity_cli_adapter.py`
- `.venv/bin/python -m pytest -q tests/python/test_antigravity_cli_adapter.py` -> 9 passed
- `.venv/bin/python -m pytest -q tests/python/test_watchlist_quant_strategy.py tests/python/test_agent_watchlist_scope.py tests/python/test_service_edges_contract.py tests/python/test_phase1_lifecycle_contract.py tests/python/test_antigravity_cli_adapter.py` -> 57 passed
- `npm --prefix apps/frontend/web-portal run test:unit -- tests/unit/market-shell-pages.spec.js` -> 11 passed
- `npm --prefix apps/frontend/web-portal run test:unit -- tests/unit/watchlist-pool.spec.js tests/unit/watchlist-scan-result.spec.js tests/unit/scheduler-center-agent-run.spec.js tests/unit/market-sentiment.spec.js tests/unit/market-shell-pages.spec.js` -> 21 passed
- `npm --prefix apps/frontend/web-portal run build`
- `git diff --check`
- Codex verifier subagent found the normalized-symbol duplicate gap; it is now fixed and covered by `test_execute_watchlist_opportunities_dedupes_normalized_symbol_variants`.
- Gemini CLI fallback reviewer confirmed no obvious blocking issue; the lazy schema initialization note has been resolved by strategy-service startup schema initialization.
- Playwright visual smoke against `http://127.0.0.1:3173/strategy`
  - Screenshot: `output/playwright/strategy-watchlist-quant.png`
  - Page title: `策略管理 - LongbridgeTrade`
  - Found: `扫描历史`, `策略复盘`
  - Horizontal overflow: `false`

## Operational Note

- Antigravity CLI may still request a fresh OAuth authorization for native Antigravity review output. The adapter now treats that as recoverable for review tasks by switching to Gemini CLI; a strict Antigravity-only review can set `REF_AGENT_CLI_DISABLE_GEMINI_FALLBACK=true`.
