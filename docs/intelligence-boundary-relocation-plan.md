# Intelligence Boundary Relocation Plan

## Goal

Move the intelligence-specific boundary implementation out of the root `service_boundaries/` package and into `apps/intelligence/`.

## Scope

This pass targets broker quote lookup and real-indicator context helpers currently owned by `service_boundaries/analysis_boundary.py`.

## Target

- New implementation:
  - `apps/intelligence/intelligence_shared/legacy_loader.py`
  - `apps/intelligence/intelligence_shared/boundary.py`
- Compatibility shim:
  - `service_boundaries/analysis_boundary.py`

## Rules

1. Keep the old import path working during transition.
2. Make `apps/intelligence/module_shared.py` depend on the module-local boundary.
3. Update tests that monkeypatch boundary loaders so they point at the module-local implementation.
