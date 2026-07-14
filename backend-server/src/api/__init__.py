"""
API模块初始化
"""

import time
import uuid

from flask import Flask, g, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from config.settings import settings
from database.DbUtil import DbUtil
from utils.json_logger import clear_trace_id, get_logger, set_trace_id
from utils.redis_client import redis_client
from utils.websocket import init_websocket

api_logger = get_logger("api.gateway")


def create_app():
    """创建Flask应用"""
    app = Flask(__name__)

    cors_origins = settings.get_cors_origins()
    cors_kwargs = {"resources": {r"/api/*": {"origins": cors_origins}}}
    if cors_origins != "*":
        cors_kwargs["supports_credentials"] = True
    CORS(app, **cors_kwargs)

    @app.before_request
    def attach_request_context():
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        g.request_id = request_id
        g.request_started_at = time.perf_counter()
        set_trace_id(request_id)

    @app.after_request
    def enrich_response(response):
        request_id = getattr(g, "request_id", None)
        started_at = getattr(g, "request_started_at", None)
        duration_ms = ((time.perf_counter() - started_at) * 1000) if started_at is not None else None

        if request_id:
            response.headers["X-Request-ID"] = request_id
        if duration_ms is not None:
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

        try:
            api_logger.info(
                "request.completed",
                extra={
                    "extra_fields": {
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.path,
                        "status_code": response.status_code,
                        "duration_ms": round(duration_ms or 0, 2),
                        "remote_addr": request.headers.get("X-Forwarded-For", request.remote_addr),
                    }
                },
            )
        finally:
            clear_trace_id()

        return response

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc):
        return jsonify(
            {"success": False, "error": exc.description, "request_id": getattr(g, "request_id", None)}
        ), exc.code or 500

    @app.errorhandler(Exception)
    def handle_unexpected_exception(exc):
        api_logger.exception(
            "request.failed",
            extra={
                "extra_fields": {
                    "request_id": getattr(g, "request_id", None),
                    "method": request.method,
                    "path": request.path,
                }
            },
        )
        payload = {"success": False, "error": "服务器内部错误", "request_id": getattr(g, "request_id", None)}
        if settings.is_development():
            payload["detail"] = str(exc)
        return jsonify(payload), 500

    # 注册蓝图
    from .account_routes import account_bp
    from .ai_routes import ai_bp
    from .auth_routes import auth_bp
    from .broker_routes import broker_bp
    from .data_routes import data_bp
    from .log_routes import log_bp
    from .platform_routes import platform_bp
    from .scan_routes import scan_bp
    from .trade_routes import trade_bp
    from .user_routes import user_bp

    app.register_blueprint(log_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(trade_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(broker_bp)
    app.register_blueprint(scan_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(platform_bp)
    init_websocket(app)

    # 健康检查端点
    @app.route("/api/health", methods=["GET"])
    def health_check():
        """健康检查"""
        health = {
            "status": "healthy",
            "services": {},
            "environment": settings.APP_ENV,
            "request_id": getattr(g, "request_id", None),
        }

        # 检查MySQL
        try:
            with DbUtil.get_db_cursor() as cursor:
                cursor.execute("SELECT 1")
                health["services"]["mysql"] = "connected"
        except Exception as e:
            health["services"]["mysql"] = f"error: {str(e)}"
            health["status"] = "unhealthy"

        # 检查Redis
        try:
            if redis_client.ping():
                health["services"]["redis"] = "connected"
            else:
                health["services"]["redis"] = "disconnected"
                if health["status"] != "unhealthy":
                    health["status"] = "degraded"
        except Exception as e:
            health["services"]["redis"] = f"error: {str(e)}"
            if health["status"] != "unhealthy":
                health["status"] = "degraded"

        status_code = 503 if health["status"] == "unhealthy" else 200
        return jsonify(health), status_code

    # 就绪检查端点
    @app.route("/api/ready", methods=["GET"])
    def readiness_check():
        """就绪检查"""
        try:
            # 检查数据库连接
            with DbUtil.get_db_cursor() as cursor:
                cursor.execute("SELECT 1")

            return jsonify({"ready": True, "request_id": getattr(g, "request_id", None)}), 200
        except Exception as e:
            return jsonify({"ready": False, "error": str(e), "request_id": getattr(g, "request_id", None)}), 503

    return app
