"""
安全工具模块
包含JWT认证、密码加密、审计日志等功能
"""

import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta
from functools import wraps
from typing import Any

from flask import g, has_request_context, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext

from config.settings import settings

logger = logging.getLogger(__name__)

# 密码加密上下文
# 使用更兼容的密码哈希方案，首选 pbkdf2_sha256，fallback bcrypt
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")


class SecurityManager:
    """安全管理器"""

    def __init__(self):
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = "HS256"
        self.access_token_expire_hours = settings.JWT_EXPIRE_HOURS

    def hash_password(self, password: str) -> str:
        """哈希密码"""
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(self, data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
        """
        创建JWT访问令牌

        Args:
            data: 要编码的数据
            expires_delta: 过期时间增量

        Returns:
            JWT令牌字符串
        """
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(hours=self.access_token_expire_hours)

        to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "access"})

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def decode_token(self, token: str) -> dict[str, Any] | None:
        """
        解码JWT令牌

        Args:
            token: JWT令牌字符串

        Returns:
            解码后的数据，失败返回None
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError as e:
            logger.warning(f"JWT解码失败: {e}")
            return None

    def generate_api_key(self) -> str:
        """生成API密钥"""
        return secrets.token_urlsafe(32)

    def generate_nonce(self, length: int = 16) -> str:
        """生成随机nonce"""
        return secrets.token_hex(length)


# 全局安全实例
security = SecurityManager()


def require_auth(f):
    """
    认证装饰器
    用于保护需要登录的API端点

    使用示例：
        @app.route('/protected')
        @require_auth
        def protected():
            return jsonify({"user_id": g.user_id})
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return jsonify({"error": "缺少认证信息"}), 401

        # 解析Bearer令牌
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return jsonify({"error": "无效的认证格式"}), 401

        token = parts[1]
        payload = security.decode_token(token)

        if payload is None:
            return jsonify({"error": "无效的令牌或已过期"}), 401

        # 将用户信息存储在g对象中
        g.user_id = payload.get("sub")
        g.username = payload.get("username")
        g.token_payload = payload

        return f(*args, **kwargs)

    return decorated_function


def require_role(roles: list):
    """
    角色权限装饰器

    使用示例：
        @app.route('/admin')
        @require_auth
        @require_role(['admin'])
        def admin_only():
            return jsonify({"message": "Admin access"})
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_roles = g.token_payload.get("roles", [])

            if not any(role in user_roles for role in roles):
                return jsonify({"error": "权限不足"}), 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator


class AuditLogger:
    """审计日志记录器"""

    def __init__(self):
        self.logger = logging.getLogger("audit")

        # 确保日志目录存在
        log_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(log_dir, exist_ok=True)

        # 创建审计日志处理器（避免重复添加）
        if not any(
            isinstance(h, logging.FileHandler) and h.baseFilename.endswith("audit.log") for h in self.logger.handlers
        ):
            audit_handler = logging.FileHandler(os.path.join(log_dir, "audit.log"))
            audit_handler.setLevel(logging.INFO)

            # 设置格式
            formatter = logging.Formatter("%(asctime)s - %(message)s")
            audit_handler.setFormatter(formatter)
            self.logger.addHandler(audit_handler)

        self.logger.setLevel(logging.INFO)

    def log_action(self, action: str, resource: str, details: dict[str, Any] = None):
        """
        记录操作日志

        Args:
            action: 操作类型 (create, read, update, delete, login, logout, trade)
            resource: 资源类型
            details: 详细信息
        """
        # Safe logging without Flask context
        if has_request_context():
            user_id = getattr(g, "user_id", "anonymous")
            username = getattr(g, "username", "anonymous")
            ip_address = request.remote_addr if request.remote_addr else "unknown"
            user_agent = request.user_agent.string if request.user_agent else "unknown"
            endpoint = request.endpoint
            method = request.method
        else:
            user_id = "anonymous"
            username = "anonymous"
            ip_address = "unknown"
            user_agent = "unknown"
            endpoint = None
            method = None

        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "resource": resource,
            "user_id": user_id,
            "username": username,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "endpoint": endpoint,
            "method": method,
            "details": details or {},
        }

        self.logger.info(json.dumps(log_entry, ensure_ascii=False))

    def log_login(self, username: str, success: bool, ip_address: str):
        """记录登录日志"""
        self.log_action(
            action="login",
            resource="auth",
            details={"username": username, "success": success, "ip_address": ip_address},
        )

    def log_trade(self, symbol: str, action: str, quantity: float, price: float):
        """记录交易日志"""
        self.log_action(
            action="trade",
            resource="order",
            details={"symbol": symbol, "trade_action": action, "quantity": quantity, "price": price},
        )

    def log_data_access(self, table: str, record_id: str, action: str):
        """记录数据访问日志"""
        self.log_action(action=action, resource=table, details={"record_id": record_id})


# 全局审计日志实例
audit_logger = AuditLogger()


def sanitize_input(data: str) -> str:
    """
    清理用户输入，防止XSS攻击

    Args:
        data: 原始输入字符串

    Returns:
        清理后的字符串
    """
    import html

    return html.escape(data)


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    验证密码强度

    Args:
        password: 密码字符串

    Returns:
        (是否通过, 错误信息)
    """
    if len(password) < 8:
        return False, "密码长度至少8位"

    if not any(c.isupper() for c in password):
        return False, "密码必须包含大写字母"

    if not any(c.islower() for c in password):
        return False, "密码必须包含小写字母"

    if not any(c.isdigit() for c in password):
        return False, "密码必须包含数字"

    if not any(c in '!@#$%^&*(),.?":{}|<>' for c in password):
        return False, "密码必须包含特殊字符"

    return True, "密码强度符合要求"


def generate_csrf_token() -> str:
    """生成CSRF令牌"""
    return secrets.token_urlsafe(32)


def verify_csrf_token(token: str, session_token: str) -> bool:
    """验证CSRF令牌"""
    return hmac.compare_digest(token, session_token)


# 导入json用于审计日志
import json
