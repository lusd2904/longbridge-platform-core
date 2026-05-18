# Module Standalone Run Plan

## Goal

Make each top-level business module directly runnable from its own folder.

## Module Contract

Each module category under `apps/` should expose:

- `README.md`
- `run.sh`

The `run.sh` script should allow a collaborator to enter the module folder and start that module without remembering root-level service paths.

## Module Mapping

| Module | Folder | Starts |
| --- | --- | --- |
| Frontend | `apps/frontend` | `web-portal` |
| Platform | `apps/platform` | `user-center`, `api-gateway` |
| Market | `apps/market` | `market-service`, optional `sentiment-service` |
| Intelligence | `apps/intelligence` | `analysis-service`, `strategy-service` |
| Trading | `apps/trading` | `trade-service` |
| Governance | `apps/governance` | `risk-service` |
| Operations | `apps/operations` | `scheduler-service` |

## Implementation Rules

1. Keep using the current root runtime, shared packages, and start scripts.
2. Add a generic `scripts/start_module.sh` as the single source of truth for module startup.
3. Keep module `run.sh` wrappers very small.
4. Support a dry-run mode for tests and inspection.
5. Do not change service internals in this pass.

## Verification

1. Every module folder must contain `run.sh` and `README.md`.
2. `run.sh` must work from inside the module folder.
3. Dry-run output must list the expected services for the module.
