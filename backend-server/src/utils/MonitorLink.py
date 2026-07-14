import os
import re
from datetime import datetime

import requests

from utils.DbUtil import DbUtil
from utils.logger import Logger


class MonitorLink:
    API_BASE = os.getenv("MONITOR_LINK_API_BASE", "http://127.0.0.1:5001/api")

    @staticmethod
    def _resolve_api_base():
        raw_value = str(os.getenv("MONITOR_LINK_API_BASE", MonitorLink.API_BASE) or "").strip()
        if raw_value.lower() in {"", "0", "false", "off", "none", "disabled"}:
            return None
        return raw_value.rstrip("/")

    @staticmethod
    def _post(path, payload, timeout):
        """向前端监控接口发送数据，忽略本机代理配置。"""
        api_base = MonitorLink._resolve_api_base()
        if not api_base:
            return None
        session = requests.Session()
        session.trust_env = False
        return session.post(f"{api_base}{path}", json=payload, timeout=timeout)

    @staticmethod
    def log(content):
        # 添加时间戳到content中
        timestamp = datetime.now().strftime("%H:%M:%S")
        content_with_timestamp = f"[{timestamp}] {content}"

        # 保存到数据库
        try:
            DbUtil.add_web_log(content_with_timestamp)
        except Exception as e:
            Logger.log_error("MonitorLink", e, "写入系统日志失败，已忽略")

        # 发送到前端
        try:
            MonitorLink._post("/log_scan", {"content": content_with_timestamp}, timeout=1)
        except Exception as e:
            Logger.log_error("MonitorLink", e, "发送日志到前端失败")

        # 打印到控制台
        clean_content = re.sub(r"<[^>]+>", "", content)
        print(f"[{timestamp}] {clean_content}")

        # 记录到日志文件
        logger = Logger.get_logger("monitor")
        logger.info(clean_content)

    @staticmethod
    def post_ai_ui(symbol, gemma, llama, deepseek, status, side, price, cost):
        """物理解决网页现价/盈亏显示"""
        pnl = float(price) - float(cost)
        detail = f"{float(price):.2f}|{float(cost):.2f}|{pnl:.2f}"
        payload = {
            "symbol": symbol,
            "gemma": gemma,
            "llama": llama,
            "deepseek": deepseek,
            "status": status,
            "side": side,
            "detail": detail,
        }
        try:
            MonitorLink._post("/log_ai", payload, timeout=2)
            Logger.log_business_event("AI分析", symbol, f"状态:{status} | 价格:{price} | 成本:{cost}")
        except Exception as e:
            Logger.log_error("MonitorLink", e, f"发送AI分析结果到前端失败: {symbol}")
