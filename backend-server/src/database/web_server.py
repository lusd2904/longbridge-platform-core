"""
监控数据API服务 - 已迁移到MySQL
此文件保留用于兼容，实际数据存储在MySQL数据库中
"""
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, request, jsonify
from flask_cors import CORS
from utils.DbUtil import DbUtil

app = Flask(__name__)
CORS(app)

@app.route('/api/log_scan', methods=['POST'])
def log_scan():
    """记录扫描日志到MySQL"""
    content = request.json.get('content')
    try:
        from datetime import datetime
        log_time = datetime.now().strftime('%H:%M:%S')
        DbUtil.add_scan_log(log_time, content)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/log_ai', methods=['POST'])
def log_ai():
    """记录AI决策到MySQL"""
    d = request.json
    try:
        from datetime import datetime
        decision_time = datetime.now().strftime('%H:%M:%S')
        DbUtil.add_ai_decision(
            decision_time,
            d['symbol'],
            d['gemma'],
            d['llama'],
            d['deepseek'],
            d['status'],
            d['side'],
            d['detail']
        )
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/update_account', methods=['POST'])
def update_account():
    """更新账户快照到MySQL"""
    d = request.json
    try:
        # 解析数值（去掉$和%符号）
        total = float(d['total'].replace('$', '').replace(',', ''))
        pnl = float(d['pnl'].replace('$', '').replace(',', '').replace('+', ''))
        ratio = float(d['ratio'].replace('%', ''))
        cash = float(d['cash'].replace('$', '').replace(',', ''))
        mkt_val = float(d['mkt_val'].replace('$', '').replace(',', ''))

        DbUtil.save_account_snapshot(total, cash, mkt_val, pnl, ratio)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/get_data')
def get_data():
    """从MySQL获取监控数据"""
    try:
        scans = DbUtil.get_scan_logs(50)
        ais = DbUtil.get_ai_decisions(20)

        # 格式化扫描日志
        formatted_scans = [{"time": s['log_time'], "content": s['content']} for s in scans]

        # 格式化AI决策
        formatted_ais = [{
            "time": a['decision_time'],
            "symbol": a['symbol'],
            "gemma": a['gemma'],
            "llama": a['llama'],
            "deepseek": a['deepseek'],
            "status": a['status'],
            "side": a['side'],
            "detail": a['detail']
        } for a in ais]

        # 获取最新账户快照
        account_data = DbUtil.fetch_one("""
            SELECT net_assets, today_pnl, today_pnl_percent, cash, market_value
            FROM account_snapshots ORDER BY id DESC LIMIT 1
        """)

        if account_data:
            acc = (
                f"${account_data['net_assets']:,.2f}",
                f"{'+' if account_data['today_pnl'] >= 0 else ''}${account_data['today_pnl']:,.2f}",
                f"{account_data['today_pnl_percent']:+.2f}%",
                f"${account_data['cash']:,.2f}",
                f"${account_data['market_value']:,.2f}"
            )
        else:
            acc = ("$0.00", "+$0.00", "0.00%", "$0.00", "$0.00")

        return jsonify({"scans": formatted_scans, "ais": formatted_ais, "account": acc})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    print("✅ 监控数据API服务已启动（使用MySQL数据库）")
    app.run(host='0.0.0.0', port=5001)
