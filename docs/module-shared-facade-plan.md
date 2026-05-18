# Module Shared Facade Plan

## Goal

Reduce direct coupling from service entrypoints to the root-level shared layers by introducing module-scoped facade files.

## Scope

This pass only changes service entrypoints and adds thin module-level facades.

It does **not** move the actual implementation out of:

- `shared/`
- `core/`
- `utils/`
- `service_boundaries/`
- `config/`
- `legacy_trade_service/`

## Pattern

Each backend module gets a `module_shared.py` file:

- `apps/platform/module_shared.py`
- `apps/market/module_shared.py`
- `apps/intelligence/module_shared.py`
- `apps/trading/module_shared.py`
- `apps/governance/module_shared.py`
- `apps/operations/module_shared.py`

Service `src/main.py` files then import their root dependencies from the module facade first.

## Why

1. Entry scripts become easier to reason about by business domain.
2. Future moves from root shared code into module-private packages can happen behind stable facade imports.
3. The service entrypoint diff stays small and reversible.

## Verification

1. Facade files import successfully.
2. Service entrypoints compile.
3. Regression tests lock that entrypoints use module-scoped facade imports.
