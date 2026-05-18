from __future__ import annotations

from functools import lru_cache

from apps.runtime_shared.bootstrap import bootstrap_runtime, legacy_compat_enabled


bootstrap_runtime()


def _require_legacy_backend() -> None:
    if not legacy_compat_enabled():
        raise RuntimeError("legacy compat 已关闭，无法访问交易边界实现")


@lru_cache(maxsize=1)
def broker_routes():
    _require_legacy_backend()
    from api import broker_routes

    return broker_routes
