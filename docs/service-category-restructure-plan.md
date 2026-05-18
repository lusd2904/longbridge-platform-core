# Service Category Restructure Plan

## Goal

Reorganize `apps/` so each category owns its own service folders while preserving the old flat paths as compatibility links.

## Target Structure

```text
apps/
  frontend/
    web-portal/
  platform/
    api-gateway/
    user-center/
  market/
    market-service/
    sentiment-service/
  intelligence/
    analysis-service/
    strategy-service/
  trading/
    trade-service/
  governance/
    risk-service/
  operations/
    scheduler-service/
```

## Compatibility Strategy

Keep the existing flat paths as symlinks:

- `apps/web-portal -> apps/frontend/web-portal`
- `apps/api-gateway -> apps/platform/api-gateway`
- `apps/user-center -> apps/platform/user-center`
- `apps/market-service -> apps/market/market-service`
- `apps/sentiment-service -> apps/market/sentiment-service`
- `apps/analysis-service -> apps/intelligence/analysis-service`
- `apps/strategy-service -> apps/intelligence/strategy-service`
- `apps/trade-service -> apps/trading/trade-service`
- `apps/risk-service -> apps/governance/risk-service`

Legacy nested paths remain available too:

- `apps/risk-service/scheduler -> apps/operations/scheduler-service`
- `apps/strategy-service/sentiment-service -> apps/market/sentiment-service`

## Rules

1. Do not rewrite internal imports in this pass.
2. Do not break `scripts/start_phase1_stack.sh` and related start scripts.
3. Update top-level docs to describe the categorized layout.
4. Add a regression test to lock the new folder contract and compatibility links.

## Expected Benefits

- Services become easier to discover by business domain.
- Frontend is clearly separated from backend services.
- Scheduler and sentiment stop living as hidden nested sub-services under unrelated domains.
- Existing scripts and tests continue to work through compatibility links.
