from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import warnings

import bcrypt
import jwt
from fastapi import Header, HTTPException

from .bootstrap import bootstrap_runtime

bootstrap_runtime()

from config.settings import settings
from core.platform.PlatformAccessService import PlatformAccessService
from utils.DbUtil import DbUtil


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def generate_token(user_id: int, username: str, role: str) -> str:
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRE_HOURS),
        "iat": datetime.utcnow(),
    }
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="The HMAC key is .*")
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return token.decode("utf-8") if isinstance(token, bytes) else token


def decode_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="登录已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="未登录或令牌无效") from exc


def _parse_bearer_token(authorization: Optional[str]) -> str:
    raw = str(authorization or "").strip()
    if not raw:
        raise HTTPException(status_code=401, detail="未登录")
    if raw.startswith("Bearer "):
        raw = raw[7:].strip()
    if not raw:
        raise HTTPException(status_code=401, detail="未登录")
    return raw


def _log_login(
    user_id: Optional[int],
    username: str,
    status: str,
    ip: Optional[str],
    fail_reason: Optional[str] = None,
) -> None:
    try:
        DbUtil.execute(
            """
            INSERT INTO login_logs (user_id, username, login_ip, login_status, fail_reason, user_agent)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, username, ip, status, fail_reason, "refactor-v2"),
        )
    except Exception:
        pass


def _serialize_datetime(value: Any) -> Optional[str]:
    if not value:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def build_bootstrap_payload(user_id: int) -> Dict[str, Any]:
    PlatformAccessService.ensure_schema()
    bootstrap, record = PlatformAccessService.build_user_bootstrap_bundle(user_id)
    row = record or {}
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")

    user_payload = {
        **(bootstrap.get("user") or {}),
        "id": row.get("id"),
        "username": row.get("username"),
        "email": row.get("email"),
        "phone": row.get("phone"),
        "nickname": row.get("nickname") or row.get("username"),
        "avatar": row.get("avatar"),
        "role": row.get("role"),
        "status": row.get("status"),
        "last_login_time": _serialize_datetime(row.get("last_login_time")),
        "created_at": _serialize_datetime(row.get("created_at")),
    }

    return {
        **bootstrap,
        "homePath": bootstrap.get("homePath") or (bootstrap.get("navigation") or {}).get("homePath") or "/dashboard",
        "user": user_payload,
    }


def authenticate_user(username: str, password: str, client_ip: Optional[str] = None) -> Dict[str, Any]:
    clean_username = str(username or "").strip()
    if not clean_username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")

    row = DbUtil.query_one(
        """
        SELECT id, username, password_hash, role, status
        FROM users WHERE username = %s
        """,
        (clean_username,),
    )
    if not row:
        _log_login(None, clean_username, "failed", client_ip, "用户名不存在")
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user_id, db_username, password_hash, role, status = row
    if status == "disabled":
        _log_login(user_id, clean_username, "failed", client_ip, "账户已禁用")
        raise HTTPException(status_code=403, detail="账户已禁用")
    if status == "locked":
        _log_login(user_id, clean_username, "failed", client_ip, "账户已锁定")
        raise HTTPException(status_code=403, detail="账户已锁定")
    if not verify_password(password, password_hash):
        _log_login(user_id, clean_username, "failed", client_ip, "密码错误")
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    DbUtil.execute(
        "UPDATE users SET last_login_time = NOW(), last_login_ip = %s WHERE id = %s",
        (client_ip, user_id),
    )
    PlatformAccessService.invalidate_bootstrap_cache(user_id)
    _log_login(user_id, clean_username, "success", client_ip)

    return {
        "token": generate_token(user_id, db_username, role),
        **build_bootstrap_payload(user_id),
    }


def get_current_session(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    token = _parse_bearer_token(authorization)
    return decode_token(token)


def get_current_user_payload(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    session = get_current_session(authorization)
    return build_bootstrap_payload(int(session["user_id"]))
