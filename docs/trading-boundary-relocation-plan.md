# Trading Boundary Relocation Plan

## Goal

Move the trading-specific boundary implementation out of the root `service_boundaries/` package and into `apps/trading/`.

## Scope

This pass targets only the trading boundary helpers that wrap legacy broker account routes.

## Target

- New implementation:
  - `apps/trading/trade_shared/legacy_loader.py`
  - `apps/trading/trade_shared/boundary.py`
- Compatibility shim:
  - `service_boundaries/trade_boundary.py`

## Rules

1. Keep the old import path working during the transition.
2. Make `apps/trading/module_shared.py` depend on the module-local boundary, not the root boundary.
3. Update tests so architecture checks reflect the new module-local ownership.
4. Do not change trade-service behavior in this pass.
