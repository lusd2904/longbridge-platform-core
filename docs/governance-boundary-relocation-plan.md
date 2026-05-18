# Governance Boundary Relocation Plan

## Goal

Move the governance-specific boundary implementation out of the root `service_boundaries/` package and into `apps/governance/`.

## Scope

This pass targets risk overview, notification state, and risk order helpers currently owned by `service_boundaries/risk_boundary.py`.

## Target

- New implementation:
  - `apps/governance/risk_shared/legacy_loader.py`
  - `apps/governance/risk_shared/boundary.py`
- Compatibility shim:
  - `service_boundaries/risk_boundary.py`

## Rules

1. Keep the old import path working during transition.
2. Make `apps/governance/module_shared.py` depend on the module-local boundary.
3. Leave scheduler imports on the root shim for now to keep that slice small.
