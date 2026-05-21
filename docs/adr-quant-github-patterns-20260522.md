# ADR: Quant Strategy GitHub Pattern Adoption

Date: 2026-05-22

## Context

The quant strategy work in Refactor V2 needed a documented decision for how to borrow ideas from Lean, Qlib, vn.py, and PyPortfolioOpt without adding heavy dependencies or weakening the existing broker boundary.

The repository already has a clear execution rule:

- `strategy-service` may score, preview, backtest, and request controlled execution.
- `trade-service` is the only service that may write broker-side trade state.
- `analysis-service`, sentiment, Agno review, and scheduler flows remain advisory unless they route through the existing controlled execution path.

## Decision

Borrow design ideas only.

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
- The implementation stays lightweight and easier to verify.

Negative:

- The repository does not get a full Lean-style event engine.
- The repository does not get a Qlib-style factor registry or a portfolio optimizer runtime.
- Any future move toward a richer optimizer or event bus needs a new decision record.

## Boundary Map

| Idea | Where it lands | Owner |
| --- | --- | --- |
| Signal staging and lifecycle separation | `apps/intelligence/strategy-service` | Strategy Service |
| Factor inputs and research outputs | `apps/intelligence/analysis-service` + `apps/intelligence/strategy-service` | Intelligence Module |
| Risk gating and broker guardrails | `apps/governance/risk-service` + `apps/trading/trade-service` | Governance / Trading |
| Order state projection | `apps/trading/trade-service` | Trade Service |
| Lightweight position budgets | `apps/intelligence/strategy-service` | Strategy Service |

## Notes for Future Changes

- If a change would let strategy or analysis write broker state directly, reject it.
- If a change needs factor registries, optimizer logic, or event bus semantics beyond the current preview-first flow, write a new ADR first.
- If a future implementation copies API shapes or order semantics from a reference project, confirm the license and document the difference from the reference before shipping.
