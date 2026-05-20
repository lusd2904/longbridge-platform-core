from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

import bcrypt
from fastapi import Body, Depends, Header, HTTPException


REFACTOR_ROOT = Path(__file__).resolve().parents[3]
if str(REFACTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(REFACTOR_ROOT))

from apps.platform.module_shared import (
    AIAnalyst,
    AppConfig,
    DbUtil,
    PlatformAccessService,
    authenticate_user,
    bootstrap_runtime,
    build_bootstrap_payload,
    build_dependency_status,
    build_health_payload,
    create_service_app,
    generate_token,
    get_current_session,
    get_current_user_payload,
    service_port,
    summarize_status,
    verify_password,
)

bootstrap_runtime()


app = create_service_app(
    title="Refactor V2 User Center",
    version="0.2.0",
    description="Phase 1 live service for authentication, bootstrap and current-user session.",
)
PORT = service_port("REF_USER_CENTER_PORT", 8101)


CONFIG_DESCRIPTIONS = {
    "ai_provider": "AI 服务提供方",
    "ai_fallback_provider": "AI 失败回退服务提供方",
    "ai_base_url": "AI 服务基础地址",
    "ai_url": "AI 模型 API URL",
    "ai_api_style": "AI 接口风格",
    "ai_local_url": "本地 AI 模型 API URL",
    "ai_local_model": "本地 AI 模型名称",
    "ai_model": "AI 模型名称",
    "ai_model_scan_pulse": "脉冲扫描模型",
    "ai_model_scan_fast": "快速扫描模型",
    "ai_model_scan_risk": "风险扫描模型",
    "ai_model_scan_final": "终审扫描模型",
    "ai_model_trend_batch": "逐股趋势扫描模型",
    "ai_model_recommend_brief": "推荐快评模型",
    "ai_model_recommend_summary": "推荐总结模型",
    "ai_model_vision": "视觉理解模型",
    "ai_reasoning_effort": "AI 默认推理质量",
    "ai_scan_reasoning_effort": "AI 扫描推理质量",
    "ai_api_key": "AI 服务 API Key",
    "ai_timeout": "AI 请求超时时间（秒）",
    "ai_local_timeout": "本地 AI 请求超时时间（秒）",
    "num_thread": "线程数",
    "temperature": "AI 生成温度",
    "num_predict": "AI 预测数量",
    "recommendation_refresh_interval": "智能推荐刷新间隔（秒）",
    "market_insight_refresh_interval": "市场动态分析刷新间隔（秒）",
    "market_insight_enabled": "是否启用市场动态分析",
    "position_monitor_interval": "持仓规则监控间隔（秒）",
    "ai_quant_interval": "AI量化交易分析间隔（秒）",
    "ai_quant_confidence_threshold": "AI量化交易执行置信度阈值",
    "ai_quant_max_buy_amount": "AI量化单次买入预算上限",
    "ai_quant_trading_enabled": "是否启用AI量化交易",
    "ai_quant_auto_execute": "是否允许AI量化自动执行",
    "historical_data_sync_enabled": "是否启用历史行情定时同步",
    "historical_data_sync_hour": "历史行情定时同步小时",
    "historical_data_sync_minute": "历史行情定时同步分钟",
    "historical_data_lookback_days": "历史行情默认回补天数",
    "historical_data_max_symbols": "历史行情单轮最大同步标的数",
    "historical_backfill_start_date": "历史行情慢补数起始日期",
    "rsi_over_buy": "RSI 超买阈值",
    "rsi_over_sell": "RSI 超卖阈值",
    "scan_interval": "扫描间隔（秒）",
    "enable_cancel_strategy": "是否启用撤单策略",
    "cancel_order_threshold_seconds": "订单超时撤单阈值（秒）",
}

PROFILE_CONFIG_KEYS = [
    "ai_quant_trading_enabled",
    "ai_quant_auto_execute",
    "position_monitor_interval",
    "ai_quant_interval",
    "ai_quant_confidence_threshold",
    "ai_quant_max_buy_amount",
]


def _serialize_datetime(value: Any) -> Optional[str]:
    if not value:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _load_current_user_row(user_id: int) -> Dict[str, Any]:
    row = DbUtil.fetch_one(
        """
        SELECT id, username, email, phone, nickname, avatar, role, status,
               last_login_time, created_at
        FROM users
        WHERE id = %s
        LIMIT 1
        """,
        (user_id,),
    )
    if not row:
        raise ValueError("用户不存在")
    return row


def _build_profile_payload(user_id: int) -> Dict[str, Any]:
    bootstrap = build_bootstrap_payload(user_id)
    user = bootstrap.get("user") or {}
    return {
        "service": "user-center",
        "profile": {
            "id": user.get("id"),
            "username": user.get("username"),
            "nickname": user.get("nickname"),
            "email": user.get("email"),
            "phone": user.get("phone"),
            "avatar": user.get("avatar"),
            "role": user.get("role"),
            "status": user.get("status"),
            "lastLoginTime": user.get("last_login_time"),
            "createdAt": user.get("created_at"),
        },
        "access": bootstrap.get("access") or {},
        "homePath": bootstrap.get("homePath") or "/dashboard",
    }


def _build_config_payload(user_id: int) -> Dict[str, Any]:
    migration = AIAnalyst.migrate_user_ai_settings(user_id)
    configs = migration.get("configs") or AppConfig.get_all(user_id)
    profile_configs = {key: configs.get(key) for key in PROFILE_CONFIG_KEYS}
    return {
        "service": "user-center",
        "configs": configs,
        "profileConfigs": profile_configs,
        "migration": {
            "changedCount": int(migration.get("changedCount") or 0),
            "changedKeys": list((migration.get("changed") or {}).keys()),
        },
    }


def _ensure_admin(session: Dict[str, Any]) -> Dict[str, Any]:
    bootstrap = build_bootstrap_payload(int(session["user_id"]))
    access = bootstrap.get("access") or {}
    user = bootstrap.get("user") or {}
    if not (access.get("isAdmin") or access.get("canManageUsers") or user.get("role") == "admin"):
        raise HTTPException(status_code=403, detail="无权访问用户管理")
    return bootstrap


def _ensure_platform_role_exists(role_code: str) -> str:
    normalized_role_code = str(role_code or "").strip().lower()
    if not normalized_role_code:
        raise ValueError("平台角色不能为空")

    PlatformAccessService.ensure_schema()
    role = DbUtil.fetch_one(
        """
        SELECT role_code
        FROM platform_roles
        WHERE role_code = %s
        LIMIT 1
        """,
        (normalized_role_code,),
    )
    if not role:
        raise ValueError("平台角色不存在")
    return normalized_role_code


def _normalize_user_row(row: tuple) -> Dict[str, Any]:
    return {
        "id": row[0],
        "username": row[1],
        "email": row[2],
        "phone": row[3],
        "nickname": row[4],
        "role": row[5],
        "status": row[6],
        "platform_role_code": row[7] or ("admin" if row[5] == "admin" else "user"),
        "quant_api_enabled": bool(row[8]),
        "task_admin_enabled": bool(row[9]),
        "preferred_subsystem_code": row[10] or "workspace",
        "last_login_time": _serialize_datetime(row[11]),
        "created_at": _serialize_datetime(row[12]),
        "broker_account_count": int(row[13] or 0),
    }


@app.get("/health")
async def health():
    mysql_ok = bool(DbUtil.query_one("SELECT 1"))
    deps = {
        "mysql": build_dependency_status(
            "mysql",
            "healthy" if mysql_ok else "degraded",
            detail="用户与配置读写数据库",
        ),
    }
    return build_health_payload(
        service="user-center",
        version=app.version,
        port=PORT,
        status=summarize_status(deps.values()),
        deps=deps,
        capabilities=["auth", "bootstrap", "profile-config"],
    )


@app.post("/api/v1/auth/login")
async def login(payload: dict = Body(default={})):
    data = authenticate_user(
        username=payload.get("username", ""),
        password=payload.get("password", ""),
        client_ip=payload.get("client_ip"),
    )
    return {"success": True, "data": data}


@app.post("/api/v1/auth/logout")
async def logout(_: dict = Depends(get_current_session)):
    return {"success": True, "message": "登出成功"}


@app.post("/api/v1/auth/refresh")
async def refresh_token(session: dict = Depends(get_current_session)):
    token = generate_token(
        int(session["user_id"]),
        str(session["username"]),
        str(session["role"]),
    )
    return {"success": True, "data": {"token": token}, "message": "令牌已刷新"}


@app.get("/api/v1/auth/info")
async def get_auth_info(data: dict = Depends(get_current_user_payload)):
    return {"success": True, "data": data}


@app.get("/api/v1/users/bootstrap")
async def get_user_bootstrap(session: dict = Depends(get_current_session)):
    return {"success": True, "data": build_bootstrap_payload(int(session["user_id"]))}


@app.get("/api/v1/users/profile/bootstrap")
async def get_profile_bootstrap(session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    return {
        "success": True,
        "data": {
            **_build_profile_payload(user_id),
            **_build_config_payload(user_id),
            "legacySources": [
                "refactor-v2/backend-server/src/api/auth_routes.py",
                "refactor-v2/backend-server/src/api/user_routes.py",
                "refactor-v2/backend-server/src/config/Config.py",
                "refactor-v2/apps/web-portal/src/views/ProfileView.vue",
            ],
        },
    }


@app.get("/api/v1/users/profile")
async def get_profile(session: dict = Depends(get_current_session)):
    return {"success": True, "data": _build_profile_payload(int(session["user_id"]))}


@app.put("/api/v1/users/profile")
async def update_profile(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    current = _load_current_user_row(user_id)
    username = str(payload.get("username", current.get("username") or "")).strip()
    nickname = str(payload.get("nickname", current.get("nickname") or username)).strip()
    email = str(payload.get("email", current.get("email") or "")).strip()
    phone = str(payload.get("phone", current.get("phone") or "")).strip()

    if not username:
        raise ValueError("用户名不能为空")

    duplicate = DbUtil.fetch_one(
        "SELECT id FROM users WHERE username = %s AND id <> %s LIMIT 1",
        (username, user_id),
    )
    if duplicate:
        raise ValueError("用户名已存在")

    DbUtil.execute(
        """
        UPDATE users
        SET username = %s,
            email = %s,
            phone = %s,
            nickname = %s
        WHERE id = %s
        """,
        (username, email or None, phone or None, nickname or username, user_id),
    )
    PlatformAccessService.invalidate_bootstrap_cache(user_id)

    return {
        "success": True,
        "message": "个人信息已更新",
        "data": _build_profile_payload(user_id),
    }


@app.get("/api/v1/users/me")
async def get_current_user(data: dict = Depends(get_current_user_payload)):
    return {"success": True, "data": data}


@app.get("/api/v1/users/session")
async def get_current_session_info(
    authorization: Optional[str] = Header(default=None),
    session: dict = Depends(get_current_session),
):
    return {
        "success": True,
        "data": {
            "authorization": "present" if authorization else "missing",
            "session": session,
            "user": build_bootstrap_payload(int(session["user_id"])).get("user"),
        },
    }


@app.put("/api/v1/auth/password")
async def change_password(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    old_password = str(payload.get("old_password") or "").strip()
    new_password = str(payload.get("new_password") or "").strip()

    if not old_password or not new_password:
        raise ValueError("旧密码和新密码不能为空")
    if len(new_password) < 6:
        raise ValueError("新密码长度不能少于6位")

    row = DbUtil.fetch_one("SELECT password_hash FROM users WHERE id = %s LIMIT 1", (user_id,))
    if not row or not verify_password(old_password, str(row.get("password_hash") or "")):
        raise ValueError("旧密码错误")

    password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    DbUtil.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))
    PlatformAccessService.invalidate_bootstrap_cache(user_id)
    return {"success": True, "message": "密码修改成功"}


@app.get("/api/v1/config")
async def get_user_config(session: dict = Depends(get_current_session)):
    return {"success": True, "data": _build_config_payload(int(session["user_id"]))}


@app.put("/api/v1/config")
async def update_user_config(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    raw_configs = payload.get("configs") or {}
    normalized_configs = AIAnalyst.normalize_ai_config_map(raw_configs)

    success_count = 0
    for key, value in normalized_configs.items():
        description = CONFIG_DESCRIPTIONS.get(str(key), str(key))
        if AppConfig.set(str(key).upper(), value, user_id=user_id, description=description):
            success_count += 1

    return {
        "success": True,
        "message": f"成功更新 {success_count} 项配置",
        "data": {
            "updatedCount": success_count,
            "totalCount": len(normalized_configs),
            **_build_config_payload(user_id),
        },
    }


@app.get("/api/v1/users/asset-trend")
async def get_asset_trend(days: int = 30, session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    rows = DbUtil.get_asset_trend(days=max(1, min(int(days or 30), 3650)), user_id=user_id) or []
    return {
        "success": True,
        "data": [
            {
                "date": row.get("trend_date").strftime("%Y-%m-%d") if row.get("trend_date") else "",
                "total_assets": float(row.get("total_assets") or 0),
                "market_value": float(row.get("market_value") or 0),
            }
            for row in rows
        ],
    }


@app.get("/api/v1/system/logs")
async def get_system_logs(
    level: str = "all",
    limit: int = 120,
    session: dict = Depends(get_current_session),
):
    _ensure_admin(session)
    safe_limit = max(20, min(int(limit or 120), 300))
    normalized_level = str(level or "").strip().lower()

    system_rows = DbUtil.fetch_all(
        """
        SELECT id, log_content, created_at
        FROM system_logs
        ORDER BY id DESC
        LIMIT %s
        """,
        (safe_limit,),
    ) or []
    login_rows = DbUtil.fetch_all(
        """
        SELECT id, username, login_time, login_status, fail_reason
        FROM login_logs
        ORDER BY id DESC
        LIMIT %s
        """,
        (safe_limit,),
    ) or []
    task_rows = DbUtil.fetch_all(
        """
        SELECT job_name, status, message, COALESCE(last_run_at, updated_at) AS event_time
        FROM scheduled_jobs
        ORDER BY COALESCE(last_run_at, updated_at) DESC
        LIMIT %s
        """,
        (safe_limit,),
    ) or []

    items = [
        {
            "id": int(row.get("id") or 0),
            "time": _serialize_datetime(row.get("created_at")),
            "level": "error" if "失败" in str(row.get("log_content") or "") or "ERROR" in str(row.get("log_content") or "") else "info",
            "module": "system",
            "message": row.get("log_content") or "",
        }
        for row in system_rows
    ] + [
        {
            "id": int(row.get("id") or 0),
            "time": _serialize_datetime(row.get("login_time")),
            "level": "warning" if row.get("login_status") == "failed" else "info",
            "module": "auth",
            "message": f"{row.get('username') or 'unknown'} 登录{'失败' if row.get('login_status') == 'failed' else '成功'}"
                       + (f"：{row.get('fail_reason')}" if row.get("fail_reason") else ""),
        }
        for row in login_rows
    ] + [
        {
            "id": index + 100000,
            "time": _serialize_datetime(row.get("event_time")),
            "level": "error" if str(row.get("status") or "").lower() in {"failed", "error"} else "info",
            "module": "scheduler",
            "message": f"{row.get('job_name') or 'task'} · {row.get('status') or 'unknown'}"
                       + (f" · {row.get('message')}" if row.get("message") else ""),
        }
        for index, row in enumerate(task_rows)
    ]

    if normalized_level and normalized_level != "all":
        items = [item for item in items if item.get("level") == normalized_level]

    items.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
    return {"success": True, "data": items[:safe_limit]}


@app.get("/api/v1/platform/roles")
async def get_platform_roles(session: dict = Depends(get_current_session)):
    _ensure_admin(session)
    return {"success": True, "data": PlatformAccessService.list_roles()}


@app.get("/api/v1/platform/menus")
async def get_platform_menus(session: dict = Depends(get_current_session)):
    _ensure_admin(session)
    return {"success": True, "data": PlatformAccessService.list_menus()}


@app.post("/api/v1/platform/roles")
async def create_platform_role(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    _ensure_admin(session)
    role = PlatformAccessService.upsert_role(
        role_code=payload.get("roleCode") or payload.get("role_code"),
        role_name=payload.get("roleName") or payload.get("role_name"),
        description=payload.get("description") or "",
        priority=int(payload.get("priority") or 0),
        menu_codes=payload.get("menuCodes") or payload.get("menu_codes") or [],
        extra_capabilities=payload.get("extraCapabilities") or payload.get("extra_capabilities"),
        is_system=bool(payload.get("isSystem", False)),
    )
    return {"success": True, "data": role, "message": "角色已创建"}


@app.put("/api/v1/platform/roles/{role_code}")
async def update_platform_role(
    role_code: str,
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    _ensure_admin(session)
    role = PlatformAccessService.upsert_role(
        role_code=role_code,
        role_name=payload.get("roleName") or payload.get("role_name"),
        description=payload.get("description") or "",
        priority=int(payload.get("priority") or 0),
        menu_codes=payload.get("menuCodes") or payload.get("menu_codes") or [],
        extra_capabilities=payload.get("extraCapabilities") or payload.get("extra_capabilities"),
        is_system=payload.get("isSystem"),
    )
    return {"success": True, "data": role, "message": "角色权限已更新"}


@app.get("/api/v1/admin/users")
async def get_users(
    page: int = 1,
    page_size: int = 10,
    search: str = "",
    role: str = "",
    status: str = "",
    session: dict = Depends(get_current_session),
):
    _ensure_admin(session)

    where_conditions = ["1=1"]
    params = []

    if search:
        where_conditions.append("(u.username LIKE %s OR u.nickname LIKE %s OR u.email LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    if role:
        if role in {"admin", "user"}:
            where_conditions.append("u.role = %s")
        else:
            where_conditions.append("u.platform_role_code = %s")
        params.append(role)

    if status:
        where_conditions.append("u.status = %s")
        params.append(status)

    where_clause = f"WHERE {' AND '.join(where_conditions)}"
    count_sql = f"SELECT COUNT(*) FROM users u {where_clause}"
    total_row = DbUtil.query_one(count_sql, tuple(params) if params else None)
    total = int(total_row[0] if total_row else 0)

    offset = max(page - 1, 0) * max(page_size, 1)
    sql = f"""
        SELECT u.id, u.username, u.email, u.phone, u.nickname, u.role, u.status,
               u.platform_role_code, u.quant_api_enabled, u.task_admin_enabled, u.preferred_subsystem_code,
               u.last_login_time, u.created_at,
               COUNT(ba.id) AS broker_account_count
        FROM users u
        LEFT JOIN broker_accounts ba ON ba.user_id = u.id AND ba.is_active = 1
        {where_clause}
        GROUP BY u.id, u.username, u.email, u.phone, u.nickname, u.role, u.status,
                 u.platform_role_code, u.quant_api_enabled, u.task_admin_enabled, u.preferred_subsystem_code,
                 u.last_login_time, u.created_at
        ORDER BY u.created_at DESC
        LIMIT %s OFFSET %s
    """
    list_params = [*params, page_size, offset]
    rows = DbUtil.query_all(sql, tuple(list_params))
    return {
        "success": True,
        "data": {
            "list": [_normalize_user_row(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@app.post("/api/v1/admin/users")
async def create_user(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    _ensure_admin(session)

    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "").strip()
    email = str(payload.get("email") or "").strip()
    phone = str(payload.get("phone") or "").strip()
    nickname = str(payload.get("nickname") or "").strip()
    role = str(payload.get("role") or "user").strip() or "user"
    status = str(payload.get("status") or "active").strip() or "active"
    platform_role_code = _ensure_platform_role_exists(
        payload.get("platform_role_code") or ("admin" if role == "admin" else "user")
    )
    preferred_subsystem_code = str(payload.get("preferred_subsystem_code") or "workspace").strip() or "workspace"
    quant_api_enabled = bool(payload.get("quant_api_enabled", False))
    task_admin_enabled = bool(payload.get("task_admin_enabled", False))

    if not username or not password:
        raise ValueError("用户名和密码不能为空")
    if len(password) < 6:
        raise ValueError("密码长度不能少于6位")
    if DbUtil.query_one("SELECT id FROM users WHERE username = %s", (username,)):
        raise ValueError("用户名已存在")

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    DbUtil.execute(
        """
        INSERT INTO users (
            username, password_hash, email, phone, nickname, role, status,
            platform_role_code, quant_api_enabled, task_admin_enabled, preferred_subsystem_code
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            username,
            password_hash,
            email or None,
            phone or None,
            nickname or username,
            role,
            status,
            platform_role_code or ("admin" if role == "admin" else "user"),
            1 if quant_api_enabled else 0,
            1 if task_admin_enabled else 0,
            preferred_subsystem_code,
        ),
    )
    PlatformAccessService.invalidate_bootstrap_cache()
    return {"success": True, "message": "用户创建成功"}


@app.put("/api/v1/admin/users/{user_id}")
async def update_user(
    user_id: int,
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    _ensure_admin(session)

    updates = []
    params = []

    if "email" in payload:
        updates.append("email = %s")
        params.append(str(payload.get("email") or "").strip() or None)
    if "phone" in payload:
        updates.append("phone = %s")
        params.append(str(payload.get("phone") or "").strip() or None)
    if "nickname" in payload:
        updates.append("nickname = %s")
        params.append(str(payload.get("nickname") or "").strip() or None)
    if payload.get("role"):
        updates.append("role = %s")
        params.append(str(payload.get("role")).strip())
    if payload.get("status"):
        updates.append("status = %s")
        params.append(str(payload.get("status")).strip())
    if payload.get("platform_role_code"):
        updates.append("platform_role_code = %s")
        params.append(_ensure_platform_role_exists(payload.get("platform_role_code")))
    if "quant_api_enabled" in payload:
        updates.append("quant_api_enabled = %s")
        params.append(1 if payload.get("quant_api_enabled") else 0)
    if "task_admin_enabled" in payload:
        updates.append("task_admin_enabled = %s")
        params.append(1 if payload.get("task_admin_enabled") else 0)
    if "preferred_subsystem_code" in payload:
        updates.append("preferred_subsystem_code = %s")
        params.append(str(payload.get("preferred_subsystem_code") or "workspace").strip() or "workspace")

    if not updates:
        raise ValueError("没有要更新的字段")

    params.append(user_id)
    DbUtil.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = %s", tuple(params))
    PlatformAccessService.invalidate_bootstrap_cache(user_id)
    return {"success": True, "message": "用户信息更新成功"}


@app.delete("/api/v1/admin/users/{user_id}")
async def delete_user(user_id: int, session: dict = Depends(get_current_session)):
    bootstrap = _ensure_admin(session)
    if int(bootstrap.get("user", {}).get("id") or 0) == user_id:
        raise ValueError("不能删除当前登录用户")
    DbUtil.execute("DELETE FROM users WHERE id = %s", (user_id,))
    PlatformAccessService.invalidate_bootstrap_cache(user_id)
    return {"success": True, "message": "用户已删除"}


@app.put("/api/v1/admin/users/{user_id}/password")
async def admin_reset_user_password(
    user_id: int,
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    _ensure_admin(session)
    new_password = str(payload.get("new_password") or "").strip()
    if len(new_password) < 6:
        raise ValueError("密码至少 6 位")
    password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    DbUtil.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))
    PlatformAccessService.invalidate_bootstrap_cache(user_id)
    return {"success": True, "message": "密码已重置"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
