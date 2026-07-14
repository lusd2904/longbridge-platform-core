"""
宏观事件风控管理器 (Macro Event Risk Manager)
跟踪重要宏观经济事件（如非农数据、美联储决议、CPI等），
在事件前夕向交易系统发出“收紧风控”或“熔断”的信号，以保护已有利润。
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class MacroEventRiskManager:
    def __init__(self):
        # 模拟未来的高风险宏观事件时间表（实盘中应接入财经日历 API）
        # 结构：{ "YYYY-MM-DD": {"event": "FOMC", "severity": "HIGH"} }
        self.risk_calendar = {
            "2026-07-28": {"event": "FOMC Rate Decision", "severity": "HIGH"},
            "2026-08-07": {"event": "Non-Farm Payrolls", "severity": "MEDIUM"},
            "2026-08-13": {"event": "CPI Print", "severity": "HIGH"},
        }
        logger.info("MacroEventRiskManager initialized.")

    def get_current_risk_multiplier(self, current_date: datetime) -> float:
        """
        根据当前日期和即将到来的宏观事件，返回止损宽容度乘数。
        正常期为 1.0；高风险事件前 24 小时缩小为 0.5 (即止损线收紧一半)。
        """
        today_str = current_date.strftime("%Y-%m-%d")
        tomorrow_str = (current_date + timedelta(days=1)).strftime("%Y-%m-%d")
        
        # 检查今天或明天是否有高风险事件
        for check_date in [today_str, tomorrow_str]:
            if check_date in self.risk_calendar:
                event_info = self.risk_calendar[check_date]
                if event_info["severity"] == "HIGH":
                    logger.warning(f"⚠️ [宏观风控预警] 即将迎来高风险事件: {event_info['event']} ({check_date})。启动一级防御，全面收紧止损线！")
                    return 0.5
                elif event_info["severity"] == "MEDIUM":
                    logger.info(f"⚠️ [宏观风控提示] 即将迎来中风险事件: {event_info['event']} ({check_date})。轻微收紧止损线。")
                    return 0.8
        
        return 1.0  # 正常时期，不收紧止损

macro_risk_manager = MacroEventRiskManager()
