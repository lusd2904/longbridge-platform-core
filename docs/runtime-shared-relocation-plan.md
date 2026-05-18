# Runtime Shared Relocation Plan

## Goal

Move the remaining root-level runtime entry surfaces into `apps/runtime_shared/`.

## Scope

- `shared/app.py`
- `shared/auth.py`
- `shared/bootstrap.py`
- `shared/health.py`
- `service_boundaries/runtime.py`

## Target

- `apps/runtime_shared/app.py`
- `apps/runtime_shared/auth.py`
- `apps/runtime_shared/bootstrap.py`
- `apps/runtime_shared/health.py`
- `apps/runtime_shared/legacy_runtime.py`

Root files remain as compatibility shims.
