"""
用户认证相关API路由
"""

from datetime import datetime, timedelta
from functools import wraps

import bcrypt
import jwt
from flask import Blueprint, jsonify, request

from config.settings import settings
from core.platform.PlatformAccessService import PlatformAccessService
from utils.DbUtil import DbUtil
from utils.rate_limiter import rate_limit

auth_bp = Blueprint("auth", __name__)


def hash_password(password):
    """密码哈希"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password, password_hash):
    """验证密码"""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_token(user_id, username, role):
    """生成JWT令牌"""
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRE_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def verify_token(token):
    """验证JWT令牌"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def login_required(f):
    """登录验证装饰器"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token:
            return jsonify({"success": False, "error": "未登录"}), 401

        # 移除Bearer前缀
        if token.startswith("Bearer "):
            token = token[7:]

        payload = verify_token(token)
        if not payload:
            return jsonify({"success": False, "error": "登录已过期"}), 401

        # 将用户信息存入request
        request.user_id = payload["user_id"]
        request.username = payload["username"]
        request.role = payload["role"]

        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """管理员权限验证装饰器"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(request, "role") or request.role != "admin":
            return jsonify({"success": False, "error": "无权限访问"}), 403
        return f(*args, **kwargs)

    return decorated_function


@auth_bp.route("/api/auth/login", methods=["POST"])
@rate_limit(key_func=lambda: f"login:{request.remote_addr or 'unknown'}", limit=12, window=60)
def login():
    """用户登录"""
    try:
        data = request.get_json()
        username = data.get("username", "").strip()
        password = data.get("password", "")

        print(f"✅ [登录] 尝试登录: username={username}")

        if not username or not password:
            return jsonify({"success": False, "error": "用户名和密码不能为空"}), 400

        # 查询用户
        sql = """
            SELECT id, username, password_hash, role, status, nickname, avatar
            FROM users WHERE username = %s
        """
        print(f"✅ [登录] 执行SQL: {sql} with params: {username}")
        result = DbUtil.query_one(sql, (username,))

        print(f"✅ [登录] 查询结果: {result}")

        if not result:
            # 记录登录失败日志
            _log_login(None, username, "failed", request.remote_addr, "用户名不存在")
            return jsonify({"success": False, "error": "用户名或密码错误"}), 401

        user_id, db_username, password_hash, role, status, nickname, avatar = result

        # 检查用户状态
        if status == "disabled":
            _log_login(user_id, username, "failed", request.remote_addr, "账户已禁用")
            return jsonify({"success": False, "error": "账户已禁用"}), 403

        if status == "locked":
            _log_login(user_id, username, "failed", request.remote_addr, "账户已锁定")
            return jsonify({"success": False, "error": "账户已锁定"}), 403

        # 验证密码
        print(f"✅ [登录] 验证密码: password={password}, hash={password_hash[:20]}...")
        if not verify_password(password, password_hash):
            _log_login(user_id, username, "failed", request.remote_addr, "密码错误")
            return jsonify({"success": False, "error": "用户名或密码错误"}), 401

        # 更新最后登录时间
        update_sql = "UPDATE users SET last_login_time = NOW(), last_login_ip = %s WHERE id = %s"
        DbUtil.execute(update_sql, (request.remote_addr, user_id))

        # 记录登录成功日志
        _log_login(user_id, username, "success", request.remote_addr)

        # 生成令牌
        token = generate_token(user_id, username, role)
        bootstrap = PlatformAccessService.build_user_bootstrap(user_id)

        return jsonify({"success": True, "data": {"token": token, **bootstrap}})

    except Exception as e:
        print(f"❌ [登录] 登录失败: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/auth/logout", methods=["POST"])
@login_required
def logout():
    """用户登出"""
    # 这里可以添加令牌黑名单逻辑
    return jsonify({"success": True, "message": "登出成功"})


@auth_bp.route("/api/auth/refresh", methods=["POST"])
@login_required
@rate_limit(key_func=lambda: f"refresh:{getattr(request, 'user_id', 'anonymous')}", limit=30, window=60)
def refresh_token():
    """刷新访问令牌。"""
    try:
        token = generate_token(request.user_id, request.username, request.role)
        return jsonify({"success": True, "data": {"token": token}, "message": "令牌已刷新"})
    except Exception as e:
        print(f"❌ [刷新令牌] 失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/auth/info", methods=["GET"])
@login_required
def get_user_info():
    """获取当前用户信息"""
    try:
        sql = """
            SELECT id, username, email, phone, nickname, avatar, role, status,
                   last_login_time, created_at
            FROM users WHERE id = %s
        """
        result = DbUtil.query_one(sql, (request.user_id,))

        if not result:
            return jsonify({"success": False, "error": "用户不存在"}), 404

        bootstrap = PlatformAccessService.build_user_bootstrap(request.user_id)

        return jsonify(
            {
                "success": True,
                "data": {
                    **bootstrap,
                    "user": {
                        **bootstrap.get("user", {}),
                        "email": result[2],
                        "phone": result[3],
                        "nickname": result[4],
                        "avatar": result[5],
                        "role": result[6],
                        "status": result[7],
                        "last_login_time": result[8].strftime("%Y-%m-%d %H:%M:%S") if result[8] else None,
                        "created_at": result[9].strftime("%Y-%m-%d %H:%M:%S") if result[9] else None,
                    },
                },
            }
        )

    except Exception as e:
        print(f"❌ [用户信息] 获取失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/auth/info", methods=["PUT"])
@login_required
def update_user_info():
    """更新当前用户信息"""
    try:
        data = request.get_json() or {}
        username = str(data.get("username", "")).strip()
        email = str(data.get("email", "")).strip()
        phone = str(data.get("phone", "")).strip()
        nickname = str(data.get("nickname", "")).strip() or username

        if not username:
            return jsonify({"success": False, "error": "用户名不能为空"}), 400

        duplicate = DbUtil.query_one(
            "SELECT id FROM users WHERE username = %s AND id <> %s", (username, request.user_id)
        )
        if duplicate:
            return jsonify({"success": False, "error": "用户名已存在"}), 400

        DbUtil.execute(
            """
            UPDATE users
            SET username = %s,
                email = %s,
                phone = %s,
                nickname = %s
            WHERE id = %s
            """,
            (username, email, phone, nickname, request.user_id),
        )

        return jsonify({"success": True, "message": "个人信息已更新"})
    except Exception as e:
        print(f"❌ [用户信息] 更新失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/auth/password", methods=["PUT"])
@login_required
@rate_limit(key_func=lambda: f"password:{getattr(request, 'user_id', 'anonymous')}", limit=6, window=300)
def change_password():
    """修改密码"""
    try:
        data = request.get_json()
        old_password = data.get("old_password", "")
        new_password = data.get("new_password", "")

        if not old_password or not new_password:
            return jsonify({"success": False, "error": "旧密码和新密码不能为空"}), 400

        if len(new_password) < 6:
            return jsonify({"success": False, "error": "新密码长度不能少于6位"}), 400

        # 验证旧密码
        sql = "SELECT password_hash FROM users WHERE id = %s"
        result = DbUtil.query_one(sql, (request.user_id,))

        if not result or not verify_password(old_password, result[0]):
            return jsonify({"success": False, "error": "旧密码错误"}), 400

        # 更新密码
        new_hash = hash_password(new_password)
        update_sql = "UPDATE users SET password_hash = %s WHERE id = %s"
        DbUtil.execute(update_sql, (new_hash, request.user_id))

        return jsonify({"success": True, "message": "密码修改成功"})

    except Exception as e:
        print(f"❌ [修改密码] 失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/config", methods=["GET"])
@login_required
def get_config():
    """获取用户配置"""
    try:
        from config.Config import AppConfig
        from core.analysis.ai_analyst import AIAnalyst

        migration = AIAnalyst.migrate_user_ai_settings(request.user_id)
        configs = migration.get("configs") or AppConfig.get_all(request.user_id)

        return jsonify(
            {
                "success": True,
                "data": configs,
                "migration": {
                    "changedCount": int(migration.get("changedCount") or 0),
                    "changedKeys": list((migration.get("changed") or {}).keys()),
                },
            }
        )

    except Exception as e:
        print(f"❌ [配置] 获取失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/config", methods=["PUT"])
@login_required
def update_config():
    """更新用户配置"""
    try:
        from config.Config import AppConfig
        from core.analysis.ai_analyst import AIAnalyst

        data = request.get_json()
        configs = AIAnalyst.normalize_ai_config_map(data.get("configs", {}))

        # 配置描述映射
        config_descriptions = {
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

        success_count = 0
        for key, value in configs.items():
            description = config_descriptions.get(key)
            if AppConfig.set(key.upper(), value, request.user_id, description):
                success_count += 1

        return jsonify(
            {
                "success": True,
                "message": f"成功更新 {success_count} 项配置",
                "data": {"updated_count": success_count, "total_count": len(configs)},
            }
        )

    except Exception as e:
        print(f"❌ [配置] 更新失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def _log_login(user_id, username, status, ip, fail_reason=None):
    """记录登录日志"""
    try:
        sql = """
            INSERT INTO login_logs (user_id, username, login_ip, login_status, fail_reason, user_agent)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        DbUtil.execute(sql, (user_id, username, ip, status, fail_reason, request.headers.get("User-Agent")))
    except Exception as e:
        print(f"❌ [登录日志] 记录失败: {e}")
