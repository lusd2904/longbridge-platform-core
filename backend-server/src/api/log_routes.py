"""
日志相关API路由
"""

from flask import Blueprint, jsonify, request

from utils.DbUtil import DbUtil

log_bp = Blueprint("log", __name__)


@log_bp.route("/api/log_scan", methods=["POST"])
def log_scan():
    """记录扫描日志 - 内部接口，不需要鉴权"""
    # MonitorLink.log 已经在调用端完成了数据库写入，这里只保留轻量确认，
    # 避免高频 AI 日志再次写库造成连接池拥堵。
    return jsonify({"status": "ok"})


@log_bp.route("/api/log_ai", methods=["POST"])
def log_ai():
    """记录AI决策日志 - 内部接口，不需要鉴权"""
    d = request.json
    DbUtil.add_web_log(
        f"[AI决策] {d['symbol']} | Gemma:{d['gemma']} | Llama:{d['llama']} | DeepSeek:{d['deepseek']} | 状态:{d['status']}"
    )
    return jsonify({"status": "ok"})
