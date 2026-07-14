import os
import sys
from datetime import datetime

# 添加父目录到路径，以便导入utils.DbUtil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.DbUtil import DbUtil as MySQLDbUtil
from utils.DbUtil import get_db_connection, get_db_cursor


class DbUtil:
    """
    兼容旧版接口，实际数据写入MySQL数据库
    从monitor.db迁移到MySQL
    """

    @staticmethod
    def add_web_log(content):
        """
        将扫描日志写入MySQL数据库（替代monitor.db）
        """
        try:
            MySQLDbUtil.add_web_log(content)
        except Exception as e:
            print(f"DB Error: {e}")

    @staticmethod
    def add_ai_decision(symbol, gemma, llama, deepseek, status, side, detail):
        """
        将AI决策记录写入MySQL数据库（替代monitor.db）
        """
        try:
            decision_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            MySQLDbUtil.add_ai_decision(decision_time, symbol, gemma, llama, deepseek, status, side, detail)
        except Exception as e:
            print(f"DB Error: {e}")

    @staticmethod
    def get_scan_logs(limit=50):
        """
        从MySQL获取扫描日志
        """
        try:
            return MySQLDbUtil.get_scan_logs(limit)
        except Exception as e:
            print(f"DB Error: {e}")
            return []

    @staticmethod
    def get_ai_decisions(limit=20):
        """
        从MySQL获取AI决策记录
        """
        try:
            return MySQLDbUtil.get_ai_decisions(limit)
        except Exception as e:
            print(f"DB Error: {e}")
            return []

    @staticmethod
    def get_db_connection():
        return get_db_connection()

    @staticmethod
    def get_db_cursor(dict_cursor=False):
        return get_db_cursor(dict_cursor=dict_cursor)

    @staticmethod
    def query_one(sql, params=None):
        return MySQLDbUtil.query_one(sql, params)

    @staticmethod
    def query_all(sql, params=None):
        return MySQLDbUtil.query_all(sql, params)

    @staticmethod
    def fetch_one(sql, params=None):
        return MySQLDbUtil.fetch_one(sql, params)

    @staticmethod
    def fetch_all(sql, params=None):
        return MySQLDbUtil.fetch_all(sql, params)

    @staticmethod
    def fetch_one_primary(sql, params=None):
        return MySQLDbUtil.fetch_one_primary(sql, params)

    @staticmethod
    def fetch_all_primary(sql, params=None):
        return MySQLDbUtil.fetch_all_primary(sql, params)

    @staticmethod
    def execute(sql, params=None):
        return MySQLDbUtil.execute(sql, params)

    @staticmethod
    def execute_sql(sql, params=None):
        return MySQLDbUtil.execute_sql(sql, params)

    @staticmethod
    def save_account_snapshot(net_assets, buy_power, market_value=0, today_pnl=0, today_pnl_percent=0):
        return MySQLDbUtil.save_account_snapshot(net_assets, buy_power, market_value, today_pnl, today_pnl_percent)

    @staticmethod
    def close_pool():
        return MySQLDbUtil.close_pool()
