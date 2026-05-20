from __future__ import annotations

import os
from typing import Any, Dict, Optional

from core.platform.SystemTaskService import SystemTaskService
from utils.DbUtil import DbUtil


def coerce_positive_int(value: Any) -> Optional[int]:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def load_active_user(user_id: Any) -> Optional[Dict[str, Any]]:
    normalized_user_id = coerce_positive_int(user_id)
    if normalized_user_id is None:
        return None
    row = DbUtil.fetch_one(
        """
        SELECT id, username, role, status
        FROM users
        WHERE id = %s
          AND COALESCE(status, 'active') NOT IN ('disabled', 'locked')
        LIMIT 1
        """,
        (normalized_user_id,),
    )
    if not row:
        return None
    return {
        "userId": int(row.get("id") or normalized_user_id),
        "username": row.get("username") or f"user-{normalized_user_id}",
        "role": row.get("role") or "user",
    }


def resolve_task_execution_user(task_key: str, requested_user_id: Any = None) -> Optional[Dict[str, Any]]:
    policy_settings: Dict[str, Any] = {}
    try:
        policy_settings = (SystemTaskService.get_policy(task_key) or {}).get("settings") or {}
    except Exception:
        policy_settings = {}

    env_key = f"REF_{str(task_key or '').upper()}_EXECUTION_USER_ID"
    candidates = [
        ("request-user", requested_user_id),
        ("task-policy", policy_settings.get("executionUserId")),
        ("task-policy", policy_settings.get("schedulerUserId")),
        ("task-policy", policy_settings.get("userId")),
        ("env", os.getenv(env_key)),
        ("env", os.getenv("REF_SYSTEM_TASK_EXECUTION_USER_ID")),
    ]
    for reason, candidate in candidates:
        user = load_active_user(candidate)
        if user:
            user["reason"] = reason
            return user

    row = DbUtil.fetch_one(
        """
        SELECT id, username, role
        FROM users
        WHERE COALESCE(status, 'active') NOT IN ('disabled', 'locked')
        ORDER BY CASE WHEN role = 'admin' THEN 0 ELSE 1 END, id ASC
        LIMIT 1
        """
    )
    if not row:
        return None
    return {
        "userId": int(row.get("id") or 0),
        "username": row.get("username") or f"user-{row.get('id')}",
        "role": row.get("role") or "user",
        "reason": "active-user-fallback",
    }

