# Market Boundary Relocation Plan

## Goal

Move the market-specific boundary implementation out of the root `service_boundaries/` package and into `apps/market/`.

## Scope

This pass targets stock-pool table resolution and symbol normalization helpers currently owned by `service_boundaries/market_boundary.py`.

## Target

- New implementation:
  - `apps/market/market_shared/legacy_loader.py`
  - `apps/market/market_shared/boundary.py`
- Compatibility shim:
  - `service_boundaries/market_boundary.py`

## Rules

1. Keep the old import path working during transition.
2. Make `apps/market/module_shared.py` and `apps/market/market-service/src/stock_pool_query.py` depend on the module-local boundary.
3. Do not change market-service behavior in this pass.
