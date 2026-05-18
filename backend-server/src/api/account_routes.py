"""
账户相关API路由
"""
from flask import Blueprint, request, jsonify
from utils.DbUtil import DbUtil
from api.auth_routes import login_required

account_bp = Blueprint('account', __name__)

@account_bp.route('/api/update_account', methods=['POST'])
@login_required
def update_account():
    """更新账户信息"""
    try:
        d = request.json
        if not d:
            return jsonify({"status": "error", "message": "No JSON data provided"}), 400
        
        required_fields = ['total', 'pnl', 'ratio', 'cash', 'mkt_val']
        for field in required_fields:
            if field not in d:
                return jsonify({"status": "error", "message": f"Missing required field: {field}"}), 400
        
        # 使用MySQL数据库
        DbUtil.save_account_snapshot(d['total'], d['cash'])
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
