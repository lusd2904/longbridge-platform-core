"""
风险管理模块
提供止损、仓位控制、单日最大亏损限制等功能
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskConfig:
    """风险控制配置"""

    # 仓位控制
    max_position_ratio: float = 0.2  # 单只股票最大仓位比例（占总资金）
    max_total_positions: int = 10  # 最大持仓数量

    # 止损设置
    stop_loss_percentage: float = 0.05  # 止损比例（5%）
    trailing_stop_percentage: float = 0.08  # 移动止损比例（8%）

    # 单日限制
    max_daily_loss_percentage: float = 0.03  # 单日最大亏损比例（3%）
    max_daily_trades: int = 20  # 单日最大交易次数

    # 单笔交易限制
    max_single_order_value: float = 100000  # 单笔最大订单金额
    min_single_order_value: float = 0  # 单笔最小订单金额；美股允许 1 股小额委托

    # 风险敞口
    max_sector_exposure: float = 0.4  # 单个行业最大敞口
    max_market_exposure: float = 0.9  # 总体市场敞口


class RiskManager:
    """风险管理器"""

    def __init__(self, config: RiskConfig | None = None):
        """
        初始化风险管理器

        Args:
            config: 风险控制配置，如未提供则使用默认配置
        """
        self.config = config or RiskConfig()
        self.daily_stats = {"date": datetime.now().date(), "total_loss": 0.0, "trade_count": 0, "orders": []}
        self.position_high_water_marks = {}  # 持仓高点标记（用于移动止损）

    def check_order_risk(
        self, symbol: str, side: str, quantity: int, price: float, account_info: dict, positions: list[dict]
    ) -> tuple[bool, str, RiskLevel]:
        """
        检查订单风险

        Args:
            symbol: 股票代码
            side: 买卖方向（BUY/SELL）
            quantity: 数量
            price: 价格
            account_info: 账户信息
            positions: 当前持仓列表

        Returns:
            (是否通过, 风险信息, 风险等级)
        """
        order_value = quantity * price
        total_equity = account_info.get("total_equity", 0)

        # 1. 检查单笔订单金额限制
        if order_value > self.config.max_single_order_value:
            return False, f"订单金额{order_value:.2f}超过限制{self.config.max_single_order_value}", RiskLevel.HIGH

        if self.config.min_single_order_value > 0 and order_value < self.config.min_single_order_value:
            return False, f"订单金额{order_value:.2f}低于最小限制{self.config.min_single_order_value}", RiskLevel.MEDIUM

        # 2. 检查单日交易次数
        if self.daily_stats["trade_count"] >= self.config.max_daily_trades:
            return False, f"单日交易次数已达上限{self.config.max_daily_trades}", RiskLevel.HIGH

        # 3. 检查单日亏损限制
        if abs(self.daily_stats["total_loss"]) >= total_equity * self.config.max_daily_loss_percentage:
            return False, f"单日亏损已达上限{self.config.max_daily_loss_percentage*100}%", RiskLevel.CRITICAL

        # 4. 买入时检查仓位限制
        if side == "BUY":
            # 检查单只股票仓位
            existing_position = next((p for p in positions if p["symbol"] == symbol), None)
            existing_value = existing_position["market_value"] if existing_position else 0
            new_position_value = existing_value + order_value

            if new_position_value > total_equity * self.config.max_position_ratio:
                max_allowed = total_equity * self.config.max_position_ratio - existing_value
                return False, f"仓位将超过限制，最大可买入{max_allowed:.2f}", RiskLevel.HIGH

            # 检查总持仓数量
            if len(positions) >= self.config.max_total_positions and not existing_position:
                return False, f"持仓数量已达上限{self.config.max_total_positions}", RiskLevel.MEDIUM

        return True, "风险检查通过", RiskLevel.LOW

    def check_stop_loss(
        self, symbol: str, current_price: float, entry_price: float, position_quantity: int
    ) -> tuple[bool, str, float]:
        """
        检查是否需要止损

        Args:
            symbol: 股票代码
            current_price: 当前价格
            entry_price: 入场价格
            position_quantity: 持仓数量

        Returns:
            (是否止损, 止损原因, 建议卖出价格)
        """
        if position_quantity <= 0 or entry_price <= 0:
            return False, "无持仓", 0.0

        loss_percentage = (current_price - entry_price) / entry_price

        # 1. 固定止损检查
        if loss_percentage <= -self.config.stop_loss_percentage:
            stop_price = entry_price * (1 - self.config.stop_loss_percentage)
            return True, f"触发固定止损（亏损{abs(loss_percentage)*100:.2f}%）", stop_price

        # 2. 移动止损检查
        if symbol in self.position_high_water_marks:
            high_price = self.position_high_water_marks[symbol]
            drawdown = (high_price - current_price) / high_price

            if drawdown >= self.config.trailing_stop_percentage:
                stop_price = high_price * (1 - self.config.trailing_stop_percentage)
                return True, f"触发移动止损（从高点回撤{drawdown*100:.2f}%）", stop_price

            # 更新高点
            if current_price > high_price:
                self.position_high_water_marks[symbol] = current_price
        else:
            # 初始化高点
            self.position_high_water_marks[symbol] = max(entry_price, current_price)

        return False, "未触发止损", 0.0

    def update_daily_stats(self, order_result: dict):
        """
        更新每日统计

        Args:
            order_result: 订单执行结果
        """
        today = datetime.now().date()

        # 重置每日统计（新的一天）
        if today != self.daily_stats["date"]:
            self.daily_stats = {"date": today, "total_loss": 0.0, "trade_count": 0, "orders": []}

        # 更新统计
        self.daily_stats["trade_count"] += 1
        self.daily_stats["orders"].append({"time": datetime.now(), "result": order_result})

        # 计算盈亏（简化版，实际需要根据成交结果计算）
        if "realized_pnl" in order_result:
            self.daily_stats["total_loss"] += order_result["realized_pnl"]

    def calculate_position_size(
        self, symbol: str, price: float, account_equity: float, risk_per_trade: float = 0.02
    ) -> int:
        """
        计算建议仓位大小

        Args:
            symbol: 股票代码
            price: 当前价格
            account_equity: 账户总资产
            risk_per_trade: 单笔交易风险比例（默认2%）

        Returns:
            建议买入数量
        """
        # 基于风险的头寸计算
        max_risk_amount = account_equity * risk_per_trade
        stop_loss_distance = price * self.config.stop_loss_percentage

        if stop_loss_distance <= 0:
            return 0

        position_by_risk = int(max_risk_amount / stop_loss_distance)

        # 基于仓位限制的头寸计算
        max_position_value = account_equity * self.config.max_position_ratio
        position_by_limit = int(max_position_value / price)

        # 取较小值
        suggested_quantity = min(position_by_risk, position_by_limit)

        logger.info(
            f"仓位计算 - {symbol}: 基于风险={position_by_risk}, 基于限制={position_by_limit}, 建议={suggested_quantity}"
        )

        return suggested_quantity

    def get_risk_report(self) -> dict:
        """
        获取风险报告

        Returns:
            风险报告字典
        """
        today = datetime.now().date()

        # 检查是否需要重置
        if today != self.daily_stats["date"]:
            self.daily_stats = {"date": today, "total_loss": 0.0, "trade_count": 0, "orders": []}

        return {
            "date": self.daily_stats["date"].isoformat(),
            "daily_loss": self.daily_stats["total_loss"],
            "daily_trade_count": self.daily_stats["trade_count"],
            "max_daily_loss_pct": self.config.max_daily_loss_percentage * 100,
            "max_daily_trades": self.config.max_daily_trades,
            "position_high_water_marks": self.position_high_water_marks,
            "config": {
                "stop_loss_pct": self.config.stop_loss_percentage * 100,
                "trailing_stop_pct": self.config.trailing_stop_percentage * 100,
                "max_position_ratio": self.config.max_position_ratio * 100,
            },
        }

    def reset_high_water_mark(self, symbol: str):
        """
        重置持仓高点标记

        Args:
            symbol: 股票代码
        """
        if symbol in self.position_high_water_marks:
            del self.position_high_water_marks[symbol]
            logger.info(f"重置{symbol}的高点标记")


# 全局风险管理器实例
_risk_manager = None


def get_risk_manager(config: RiskConfig | None = None) -> RiskManager:
    """
    获取全局风险管理器实例（单例模式）

    Args:
        config: 风险控制配置

    Returns:
        RiskManager实例
    """
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager(config)
    return _risk_manager
