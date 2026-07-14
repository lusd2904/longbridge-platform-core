"""
交易执行模块
负责执行交易、计算手续费、仓位控制等功能
"""

from utils.MonitorLink import MonitorLink


class TradeExecutor:
    @staticmethod
    def execute_trade(engine, verdict, target, stock_data, holds, cash, max_positions=5):
        """执行交易"""
        commission_per_trade = 2.0  # 每次交易手续费2美元
        current_positions = len(holds)

        if verdict == "BUY":
            # 仓位控制：确保持仓不超过5只股票
            if current_positions >= max_positions:
                MonitorLink.log(f"⚠️ [仓位] 已达到最大持仓数 {max_positions}只，跳过买入 {target}")
                return False

            # 资金管理：考虑手续费成本
            available_cash = cash - commission_per_trade
            if available_cash <= 0:
                MonitorLink.log(f"⚠️ [资金] 现金不足，无法买入 {target}")
                return False

            # 买入用现金的 10%
            buy_amount = cash * 0.1
            # 考虑手续费后的实际买入金额
            actual_buy_amount = buy_amount - commission_per_trade
            if actual_buy_amount <= 0:
                MonitorLink.log(f"⚠️ [资金] 买入金额过小，无法买入 {target}")
                return False

            curr_p = stock_data["price"]
            qty = int(actual_buy_amount / curr_p)
            if qty > 0:
                MonitorLink.log(
                    f"💰 [买入] {target} | 价格: ${curr_p:.2f} | 数量: {qty} | 成本: ${actual_buy_amount:.2f} | 手续费: ${commission_per_trade:.2f}"
                )
                engine.execute_order(target, verdict, qty, curr_p)
                return True
            else:
                MonitorLink.log(f"⚠️ [资金] 计算数量为0，无法买入 {target}")
                return False

        elif verdict == "SELL" and target in holds:
            # 卖出则清空
            qty = holds[target]["qty"]
            if qty > 0:
                curr_p = stock_data["price"]
                # 计算卖出金额（扣除手续费）
                sell_amount = curr_p * qty - commission_per_trade
                MonitorLink.log(
                    f"💰 [卖出] {target} | 价格: ${curr_p:.2f} | 数量: {qty} | 收入: ${sell_amount:.2f} | 手续费: ${commission_per_trade:.2f}"
                )
                engine.execute_order(target, verdict, qty, curr_p)
                return True

        return False
