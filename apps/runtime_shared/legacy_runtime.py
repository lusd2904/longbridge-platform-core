from __future__ import annotations

from typing import Any, Dict

from apps.runtime_shared.bootstrap import runtime_profile


def legacy_boundary_status(boundary_name: str) -> Dict[str, Any]:
    profile = runtime_profile()
    profile["mode"] = "split-domain-boundaries"
    profile["boundary"] = str(boundary_name or "").strip() or "unknown"
    return profile
