# ADR: Quant Strategy GitHub Pattern Adoption

Date: 2026-05-22

## Context

The quant strategy work in Refactor V2 needed a documented decision for how to borrow ideas from Longbridge OpenAPI, Longbridge Terminal, FinRL-Trading, Lean, Qlib, vn.py, and PyPortfolioOpt without adding heavy dependencies or weakening the existing broker boundary.

The repository already has a clear execution rule:

- `strategy-service` may score, preview, backtest, and request controlled execution.
- `trade-service` is the only service that may write broker-side trade state.
- `analysis-service`, sentiment, Agno review, and scheduler flows remain advisory unless they route through the existing controlled execution path.

## Decision

Borrow design ideas only.

- Use Longbridge OpenAPI as the primary reference for broker gateway, quote refresh, account, position, and order submission boundaries.
- Use Longbridge Terminal as a reference for CLI/tooling ergonomics, not as an embedded strategy engine.
- Use FinRL-Trading as a reference for the "stock selection -> portfolio allocation -> timing -> risk overlay" research contract.
- Use Lean as a reference for signal and order-lifecycle separation.
- Use Qlib as a reference for factor-driven scoring and research-to-signal separation.
- Use vn.py as a reference for splitting strategy logic, risk checks, and execution boundaries.
- Use PyPortfolioOpt as a reference for lightweight position-budget thinking.

Do not vendor these projects into the repository.

Do not introduce a separate optimizer service.

Do not let `analysis-service` or `strategy-service` bypass `trade-service` for broker-side writes.

## Consequences

Positive:

- The current architecture keeps the broker boundary explicit.
- The quant strategy docs can refer to a clear design lineage without implying runtime coupling.
- The unattended paper-account path uses realtime broker quotes before order sizing and keeps daily order/notional guardrails visible in scan records.
- The implementation stays lightweight and easier to verify.

Negative:

- The repository does not get a full Lean-style event engine.
- The repository does not get a Qlib-style factor registry or a portfolio optimizer runtime.
- Any future move toward a richer optimizer or event bus needs a new decision record.

## Boundary Map

| Idea | Where it lands | Owner |
| --- | --- | --- |
| Broker gateway and realtime quotes | `apps/trading/trade-service` + `core.broker.LongbridgeAPI` | Trading Module |
| CLI/tooling ergonomics | `apps/trading` operational tooling | Trading Module |
| Stock selection to risk overlay contract | `apps/intelligence/strategy-service` | Strategy Service |
| Signal staging and lifecycle separation | `apps/intelligence/strategy-service` | Strategy Service |
| Factor inputs and research outputs | `apps/intelligence/analysis-service` + `apps/intelligence/strategy-service` | Intelligence Module |
| Risk gating and broker guardrails | `apps/governance/risk-service` + `apps/trading/trade-service` | Governance / Trading |
| Order state projection | `apps/trading/trade-service` | Trade Service |
| Lightweight position budgets | `apps/intelligence/strategy-service` | Strategy Service |

## Current Implementation

- 美股开盘 AI 自动交易仍先用历史日线、指标快照和 AI 趋势扫描做候选评分。
- 自动提交前必须通过券商接口刷新实时行情；默认缺少实时价时跳过，不再用历史收盘价直接定价下单。
- 任务中心暴露实时价刷新、缺价阻止、当日最多订单和当日名义金额比例。
- 扫描记录保存实时价刷新结果、当日订单计数和当日名义金额护栏。

## Notes for Future Changes

- If a change would let strategy or analysis write broker state directly, reject it.
- If a change needs factor registries, optimizer logic, or event bus semantics beyond the current preview-first flow, write a new ADR first.
- If a future implementation copies API shapes or order semantics from a reference project, confirm the license and document the difference from the reference before shipping.
