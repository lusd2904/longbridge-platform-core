# Operations Boundary And Longbridge Facade Plan

## Goal

Reduce direct root-level dependencies in `apps/operations/` by:

1. routing risk overview access through `apps.operations.module_shared`
2. routing Longbridge access through module-local facade files

## Scope

This pass does not move the real `shared.longbridge` implementation.

It only changes the import surfaces used by market and operations.

## Target

- `apps/market/longbridge_shared.py`
- `apps/operations/longbridge_shared.py`
- `apps/operations/module_shared.py`
- `apps/operations/scheduler-service/src/main.py`
- `apps/market/market-service/src/push_hub.py`

## Outcome

Service entrypoints and module facades stop importing `shared.longbridge` and `service_boundaries.risk_boundary` directly.
