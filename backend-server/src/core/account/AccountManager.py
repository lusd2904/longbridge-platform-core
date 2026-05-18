"""
账户管理模块
负责账户信息更新、持仓记录等功能
"""
from utils.MonitorLink import MonitorLink
from utils.DbUtil import DbUtil

class AccountManager:
    @staticmethod
    def update_account_info(total, pnl, ratio, cash, mkt_val):
        """更新账户信息到数据库"""
        try:
            # 提取数值部分，移除货币符号和逗号
            def extract_value(value):
                if isinstance(value, str):
                    # 移除货币符号、逗号和加号
                    value = value.replace('$', '').replace(',', '').replace('+', '')
                    try:
                        return float(value)
                    except:
                        return 0.0
                return value
            
            # 提取数值
            total_val = extract_value(total)
            cash_val = extract_value(cash)
            mkt_val_float = extract_value(mkt_val)
            pnl_val = extract_value(pnl)
            
            # 计算盈亏百分比
            pnl_percent = 0.0
            if total_val > 0 and mkt_val_float > 0:
                pnl_percent = (pnl_val / mkt_val_float * 100) if mkt_val_float > 0 else 0.0
            
            # 保存账户快照
            DbUtil.save_account_snapshot(total_val, cash_val, mkt_val_float, pnl_val, pnl_percent)
            
            # 保存资产趋势（日线）
            from datetime import datetime
            today = datetime.now().strftime('%Y-%m-%d')
            DbUtil.save_asset_trend(today, total_val, cash_val, mkt_val_float, pnl_val, pnl_percent)
            
            MonitorLink.log(f"✅ [Web] 账户信息已更新到数据库 | 总资产:${total_val:.2f} | 持仓市值:${mkt_val_float:.2f} | 今日盈亏:{pnl_val:+.2f}")
        except Exception as e:
            MonitorLink.log(f"⚠️ [Web] 账户信息更新异常: {str(e)[:100]}")
    
    @staticmethod
    def log_holding_to_db(symbol, price, cost, pnl, pnl_ratio, qty):
        """将持仓信息记录到数据库"""
        try:
            # 保存到positions表
            DbUtil.save_holding(symbol, price, cost, qty)
            DbUtil.add_web_log(f"持仓: {symbol} | 现价:{price:.2f} | 成本:{cost:.2f} | 盈亏:{pnl:+.2f} ({pnl_ratio:+.2f}%)")
        except Exception as e:
            MonitorLink.log(f"⚠️ [Web] 记录持仓信息异常: {str(e)[:100]}")
    
    @staticmethod
    def check_positions(holds, max_positions=5):
        """检查持仓数量，返回当前持仓数和是否已满"""
        current_positions = len(holds)
        is_full = current_positions >= max_positions
        MonitorLink.log(f"📊 [仓位] 当前持仓: {current_positions}只 | 最大持仓: {max_positions}只")
        return current_positions, is_full
