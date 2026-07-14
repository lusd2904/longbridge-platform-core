"""
用户管理相关API路由
"""

from flask import Blueprint, jsonify, request

from api.auth_routes import admin_required, hash_password, login_required
from core.platform.PlatformAuditService import PlatformAuditService
from utils.DbUtil import DbUtil

user_bp = Blueprint("user", __name__)


@user_bp.route("/api/users", methods=["GET"])
@login_required
@admin_required
def get_users():
    """获取用户列表"""
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 10))
        search = request.args.get("search", "")
        role = request.args.get("role", "")
        status = request.args.get("status", "")

        where_conditions = ["1=1"]
        params = []

        if search:
            where_conditions.append("(u.username LIKE %s OR u.nickname LIKE %s OR u.email LIKE %s)")
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

        if role:
            if role in {"admin", "user"}:
                where_conditions.append("u.role = %s")
                params.append(role)
            else:
                where_conditions.append("u.platform_role_code = %s")
                params.append(role)

        if status:
            where_conditions.append("u.status = %s")
            params.append(status)

        where_clause = f"WHERE {' AND '.join(where_conditions)}"

        # 查询总数
        count_sql = f"SELECT COUNT(*) FROM users u {where_clause}"
        total = DbUtil.query_one(count_sql, tuple(params) if params else None)[0]

        # 查询列表
        offset = (page - 1) * page_size
        sql = f"""
            SELECT u.id, u.username, u.email, u.phone, u.nickname, u.role, u.status,
                   u.platform_role_code, u.quant_api_enabled, u.task_admin_enabled, u.preferred_subsystem_code,
                   u.last_login_time, u.created_at,
                   COUNT(ba.id) AS broker_account_count
            FROM users u
            LEFT JOIN broker_accounts ba ON ba.user_id = u.id AND ba.is_active = 1
            {where_clause}
            GROUP BY u.id, u.username, u.email, u.phone, u.nickname, u.role, u.status,
                     u.platform_role_code, u.quant_api_enabled, u.task_admin_enabled, u.preferred_subsystem_code, u.last_login_time, u.created_at
            ORDER BY u.created_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([page_size, offset])
        results = DbUtil.query_all(sql, tuple(params))

        users = []
        for row in results:
            users.append(
                {
                    "id": row[0],
                    "username": row[1],
                    "email": row[2],
                    "phone": row[3],
                    "nickname": row[4],
                    "role": row[5],
                    "status": row[6],
                    "platform_role_code": row[7] or ("admin" if row[5] == "admin" else "analyst"),
                    "quant_api_enabled": bool(row[8]),
                    "task_admin_enabled": bool(row[9]),
                    "preferred_subsystem_code": row[10] or "workspace",
                    "last_login_time": row[11].strftime("%Y-%m-%d %H:%M:%S") if row[11] else None,
                    "created_at": row[12].strftime("%Y-%m-%d %H:%M:%S") if row[12] else None,
                    "broker_account_count": int(row[13] or 0),
                }
            )

        return jsonify({"success": True, "data": {"list": users, "total": total, "page": page, "page_size": page_size}})

    except Exception as e:
        print(f"❌ [用户列表] 获取失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@user_bp.route("/api/users", methods=["POST"])
@login_required
@admin_required
def create_user():
    """创建用户"""
    try:
        data = request.get_json()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        email = data.get("email", "").strip()
        phone = data.get("phone", "").strip()
        nickname = data.get("nickname", "").strip()
        role = data.get("role", "user")
        status = data.get("status", "active")
        platform_role_code = data.get("platform_role_code", "analyst")
        quant_api_enabled = bool(data.get("quant_api_enabled", False))
        task_admin_enabled = bool(data.get("task_admin_enabled", False))
        preferred_subsystem_code = data.get("preferred_subsystem_code", "workspace")

        if not username or not password:
            return jsonify({"success": False, "error": "用户名和密码不能为空"}), 400

        if len(password) < 6:
            return jsonify({"success": False, "error": "密码长度不能少于6位"}), 400

        # 检查用户名是否已存在
        check_sql = "SELECT id FROM users WHERE username = %s"
        if DbUtil.query_one(check_sql, (username,)):
            return jsonify({"success": False, "error": "用户名已存在"}), 400

        # 创建用户
        password_hash = hash_password(password)
        sql = """
            INSERT INTO users (
                username, password_hash, email, phone, nickname, role, status,
                platform_role_code, quant_api_enabled, task_admin_enabled, preferred_subsystem_code
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        DbUtil.execute(
            sql,
            (
                username,
                password_hash,
                email or None,
                phone or None,
                nickname or username,
                role,
                status or "active",
                platform_role_code or ("admin" if role == "admin" else "analyst"),
                1 if quant_api_enabled else 0,
                1 if task_admin_enabled else 0,
                str(preferred_subsystem_code or "workspace").strip() or "workspace",
            ),
        )

        PlatformAuditService.log(
            user_id=request.user_id,
            username=getattr(request, "username", None),
            module="users",
            operation="create-user",
            description=f"创建用户 {username}",
        )

        return jsonify({"success": True, "message": "用户创建成功"})

    except Exception as e:
        print(f"❌ [创建用户] 失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@user_bp.route("/api/users/<int:user_id>", methods=["PUT"])
@login_required
@admin_required
def update_user(user_id):
    """更新用户信息"""
    try:
        data = request.get_json()
        email = data.get("email", "").strip()
        phone = data.get("phone", "").strip()
        nickname = data.get("nickname", "").strip()
        role = data.get("role")
        status = data.get("status")
        platform_role_code = data.get("platform_role_code")
        quant_api_enabled = data.get("quant_api_enabled")
        task_admin_enabled = data.get("task_admin_enabled")
        preferred_subsystem_code = data.get("preferred_subsystem_code")

        # 构建更新语句
        updates = []
        params = []

        if email is not None:
            updates.append("email = %s")
            params.append(email or None)

        if phone is not None:
            updates.append("phone = %s")
            params.append(phone or None)

        if nickname is not None:
            updates.append("nickname = %s")
            params.append(nickname or None)

        if role:
            updates.append("role = %s")
            params.append(role)

        if status:
            updates.append("status = %s")
            params.append(status)

        if platform_role_code:
            updates.append("platform_role_code = %s")
            params.append(platform_role_code)

        if quant_api_enabled is not None:
            updates.append("quant_api_enabled = %s")
            params.append(1 if quant_api_enabled else 0)

        if task_admin_enabled is not None:
            updates.append("task_admin_enabled = %s")
            params.append(1 if task_admin_enabled else 0)

        if preferred_subsystem_code is not None:
            updates.append("preferred_subsystem_code = %s")
            params.append(str(preferred_subsystem_code).strip() or "workspace")

        if not updates:
            return jsonify({"success": False, "error": "没有要更新的字段"}), 400

        params.append(user_id)
        sql = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"
        DbUtil.execute(sql, tuple(params))

        PlatformAuditService.log(
            user_id=request.user_id,
            username=getattr(request, "username", None),
            module="users",
            operation="update-user",
            description=f"更新用户 {user_id}",
        )

        return jsonify({"success": True, "message": "用户信息更新成功"})

    except Exception as e:
        print(f"❌ [更新用户] 失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@user_bp.route("/api/users/<int:user_id>/password", methods=["PUT"])
@login_required
@admin_required
def reset_password(user_id):
    """重置用户密码"""
    try:
        data = request.get_json()
        new_password = data.get("new_password", "")

        if not new_password or len(new_password) < 6:
            return jsonify({"success": False, "error": "密码长度不能少于6位"}), 400

        password_hash = hash_password(new_password)
        sql = "UPDATE users SET password_hash = %s WHERE id = %s"
        DbUtil.execute(sql, (password_hash, user_id))

        PlatformAuditService.log(
            user_id=request.user_id,
            username=getattr(request, "username", None),
            module="users",
            operation="reset-password",
            description=f"重置用户 {user_id} 密码",
            level="warning",
        )

        return jsonify({"success": True, "message": "密码重置成功"})

    except Exception as e:
        print(f"❌ [重置密码] 失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@user_bp.route("/api/users/<int:user_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_user(user_id):
    """删除用户"""
    try:
        # 不能删除自己
        if user_id == request.user_id:
            return jsonify({"success": False, "error": "不能删除当前登录用户"}), 400

        sql = "DELETE FROM users WHERE id = %s"
        DbUtil.execute(sql, (user_id,))

        PlatformAuditService.log(
            user_id=request.user_id,
            username=getattr(request, "username", None),
            module="users",
            operation="delete-user",
            description=f"删除用户 {user_id}",
            level="warning",
        )

        return jsonify({"success": True, "message": "用户删除成功"})

    except Exception as e:
        print(f"❌ [删除用户] 失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@user_bp.route("/api/users/<int:user_id>/configs", methods=["GET"])
@login_required
def get_user_configs(user_id):
    """获取用户配置"""
    try:
        # 只能查看自己的配置，管理员可以查看所有
        if user_id != request.user_id and request.role != "admin":
            return jsonify({"success": False, "error": "无权限访问"}), 403

        sql = """
            SELECT id, config_key, config_value, config_type, description
            FROM user_configs WHERE user_id = %s
        """
        results = DbUtil.query_all(sql, (user_id,))

        configs = []
        sensitive_prefixes = ("app_", "access_token", "ai_api_key", "ai_quant_", "lb_", "longbridge_", "tiger_", "ib_")
        for row in results:
            config_key = row[1]
            if user_id != request.user_id and str(config_key).lower().startswith(sensitive_prefixes):
                continue
            configs.append(
                {
                    "id": row[0],
                    "config_key": config_key,
                    "config_value": row[2],
                    "config_type": row[3],
                    "description": row[4],
                }
            )

        return jsonify({"success": True, "data": configs})

    except Exception as e:
        print(f"❌ [用户配置] 获取失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@user_bp.route("/api/users/<int:user_id>/configs", methods=["PUT"])
@login_required
def update_user_configs(user_id):
    """更新用户配置"""
    try:
        # 只能更新自己的配置，管理员可以更新所有
        if user_id != request.user_id and request.role != "admin":
            return jsonify({"success": False, "error": "无权限访问"}), 403

        data = request.get_json()
        configs = data.get("configs", [])

        for config in configs:
            config_key = config.get("config_key")
            config_value = config.get("config_value")

            # 使用INSERT ... ON DUPLICATE KEY UPDATE
            sql = """
                INSERT INTO user_configs (user_id, config_key, config_value, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE config_value = VALUES(config_value), updated_at = NOW()
            """
            DbUtil.execute(sql, (user_id, config_key, config_value))

        return jsonify({"success": True, "message": "配置更新成功"})

    except Exception as e:
        print(f"❌ [更新配置] 失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
