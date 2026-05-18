"""
增强版交易引擎
集成风险管理、错误处理和结构化日志
"""
import time
import random
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from shared.longbridge import AdjustType, OrderSide, OrderType, TimeInForceType
from utils.MonitorLink import MonitorLink
from utils.LoggerUtil import get_logger, log_trade, log_error, log_risk_event
from core.RiskManager import RiskManager, RiskConfig, RiskLevel
from config.Config import AppConfig

logger = get_logger(__name__)


class TradeEngineEnhanced:
    """增强版交易引擎"""
    
    def __init__(self, tc, qc, risk_config: Optional[RiskConfig] = None):
        """
        初始化增强版交易引擎
        
        Args:
            tc: 交易上下文
            qc: 行情上下文
            risk_config: 风险控制配置
        """
        self.tc = tc
        self.qc = qc
        self.risk_manager = RiskManager(risk_config)
        self.daily_pnl = 0.0  # 当日盈亏
        
        logger.info("增强版交易引擎初始化完成")
    
    def _unpack(self, obj):
        """物理脱壳：安全转换 SDK 包装对象"""
        if obj is None:
            return 0.0
        val = getattr(obj, 'value', obj)
        try:
            return float(val)
        except:
            return 0.0
    
    def validate_order(self, side: str, symbol: str, quantity: int, price: float) -> Tuple[bool, str]:
        """
        验证订单参数
        
        Args:
            side: 买卖方向
            symbol: 股票代码
            quantity: 数量
            price: 价格
            
        Returns:
            (是否有效, 错误信息)
        """
        # 基本参数验证
        if not symbol or not isinstance(symbol, str):
            return False, "股票代码无效"
        
        if side not in ['BUY', 'SELL']:
            return False, f"无效的交易方向: {side}"
        
        if quantity <= 0:
            return False, f"交易数量必须大于0: {quantity}"
        
        if price <= 0:
            return False, f"交易价格必须大于0: {price}"
        
        order_value = quantity * price
        if order_value > self.risk_manager.config.max_single_order_value:
            return False, f"订单金额{order_value:.2f}超过最大限制"
        
        return True, "验证通过"
    
    def check_risk_before_order(self, 
                               side: str, 
                               symbol: str, 
                               quantity: int, 
                               price: float) -> Tuple[bool, str, RiskLevel]:
        """
        下单前风险检查
        
        Args:
            side: 买卖方向
            symbol: 股票代码
            quantity: 数量
            price: 价格
            
        Returns:
            (是否通过, 信息, 风险等级)
        """
        try:
            # 获取账户信息
            account_info = self.get_account_info()
            positions = self.get_positions()
            
            # 风险检查
            passed, message, risk_level = self.risk_manager.check_order_risk(
                symbol, side, quantity, price, account_info, positions
            )
            
            if not passed:
                log_risk_event(
                    logger, 'order_rejected', symbol, risk_level.value, message,
                    {'side': side, 'quantity': quantity, 'price': price}
                )
            
            return passed, message, risk_level
            
        except Exception as e:
            log_error(logger, e, {'context': 'risk_check', 'symbol': symbol})
            return False, f"风险检查失败: {str(e)}", RiskLevel.HIGH
    
    def buy(self, symbol: str, quantity: int, price: float, 
            order_type: str = "LIMIT") -> Dict[str, Any]:
        """
        买入股票（带风险控制和错误处理）
        
        Args:
            symbol: 股票代码
            quantity: 数量
            price: 价格
            order_type: 订单类型
            
        Returns:
            订单结果
        """
        try:
            # 1. 参数验证
            valid, error_msg = self.validate_order('BUY', symbol, quantity, price)
            if not valid:
                logger.error(f"买入参数验证失败: {error_msg}")
                return {'success': False, 'error': error_msg}
            
            # 2. 风险检查
            risk_passed, risk_msg, risk_level = self.check_risk_before_order('BUY', symbol, quantity, price)
            if not risk_passed:
                logger.warning(f"买入风险检查未通过: {risk_msg}")
                return {'success': False, 'error': risk_msg, 'risk_level': risk_level.value}
            
            # 3. 执行买入
            MonitorLink.log(f"🟢 [买入] {symbol} | 数量: {quantity} | 价格: ${price:.2f}")
            
            order_result = self._submit_order(
                symbol=symbol,
                side=OrderSide.Buy,
                quantity=quantity,
                price=price,
                order_type=order_type
            )
            
            # 4. 记录交易日志
            if order_result.get('success'):
                log_trade(
                    logger, symbol, 'BUY', quantity, price,
                    order_id=order_result.get('order_id'),
                    extra={'risk_level': risk_level.value}
                )
                
                # 更新风险管理器统计
                self.risk_manager.update_daily_stats(order_result)
            
            return order_result
            
        except Exception as e:
            error_msg = f"买入失败: {str(e)}"
            log_error(logger, e, {
                'context': 'buy_order',
                'symbol': symbol,
                'quantity': quantity,
                'price': price
            })
            return {'success': False, 'error': error_msg}
    
    def sell(self, symbol: str, quantity: int, price: float,
             order_type: str = "LIMIT") -> Dict[str, Any]:
        """
        卖出股票（带风险控制和错误处理）
        
        Args:
            symbol: 股票代码
            quantity: 数量
            price: 价格
            order_type: 订单类型
            
        Returns:
            订单结果
        """
        try:
            # 1. 参数验证
            valid, error_msg = self.validate_order('SELL', symbol, quantity, price)
            if not valid:
                logger.error(f"卖出参数验证失败: {error_msg}")
                return {'success': False, 'error': error_msg}
            
            # 2. 检查持仓
            positions = self.get_positions()
            position = next((p for p in positions if p['symbol'] == symbol), None)
            
            if not position:
                return {'success': False, 'error': f'未持有{symbol}'}
            
            if position['quantity'] < quantity:
                return {
                    'success': False, 
                    'error': f'持仓不足: 持有{position["quantity"]}, 尝试卖出{quantity}'
                }
            
            # 3. 风险检查
            risk_passed, risk_msg, risk_level = self.check_risk_before_order('SELL', symbol, quantity, price)
            if not risk_passed:
                logger.warning(f"卖出风险检查未通过: {risk_msg}")
            
            # 4. 执行卖出
            MonitorLink.log(f"🔴 [卖出] {symbol} | 数量: {quantity} | 价格: ${price:.2f}")
            
            order_result = self._submit_order(
                symbol=symbol,
                side=OrderSide.Sell,
                quantity=quantity,
                price=price,
                order_type=order_type
            )
            
            # 5. 记录交易日志
            if order_result.get('success'):
                # 计算盈亏
                entry_price = position.get('cost_price', price)
                realized_pnl = (price - entry_price) * quantity
                self.daily_pnl += realized_pnl
                
                log_trade(
                    logger, symbol, 'SELL', quantity, price,
                    order_id=order_result.get('order_id'),
                    extra={
                        'realized_pnl': realized_pnl,
                        'entry_price': entry_price,
                        'risk_level': risk_level.value
                    }
                )
                
                # 更新风险管理器统计
                order_result['realized_pnl'] = realized_pnl
                self.risk_manager.update_daily_stats(order_result)
                
                # 重置高点标记
                self.risk_manager.reset_high_water_mark(symbol)
            
            return order_result
            
        except Exception as e:
            error_msg = f"卖出失败: {str(e)}"
            log_error(logger, e, {
                'context': 'sell_order',
                'symbol': symbol,
                'quantity': quantity,
                'price': price
            })
            return {'success': False, 'error': error_msg}
    
    def _submit_order(self, symbol: str, side: OrderSide, quantity: int, 
                     price: float, order_type: str = "LIMIT") -> Dict[str, Any]:
        """
        提交订单到交易所
        
        Args:
            symbol: 股票代码
            side: 买卖方向
            quantity: 数量
            price: 价格
            order_type: 订单类型
            
        Returns:
            订单结果
        """
        try:
            # 转换订单类型
            if order_type == "MARKET":
                lb_order_type = OrderType.MO
            else:
                lb_order_type = OrderType.Limit
            
            # 提交订单
            response = self.tc.submit_order(
                symbol=symbol,
                order_type=lb_order_type,
                side=side,
                submitted_quantity=quantity,
                submitted_price=price if order_type != "MARKET" else None,
                time_in_force=TimeInForceType.Day
            )
            
            return {
                'success': True,
                'order_id': response.order_id,
                'status': response.status,
                'symbol': symbol,
                'side': side.name,
                'quantity': quantity,
                'price': price
            }
            
        except Exception as e:
            logger.error(f"提交订单失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def check_stop_loss(self, symbol: str, current_price: float) -> Tuple[bool, str, float]:
        """
        检查是否需要止损
        
        Args:
            symbol: 股票代码
            current_price: 当前价格
            
        Returns:
            (是否止损, 原因, 建议价格)
        """
        try:
            positions = self.get_positions()
            position = next((p for p in positions if p['symbol'] == symbol), None)
            
            if not position:
                return False, "无持仓", 0.0
            
            entry_price = position.get('cost_price', current_price)
            quantity = position.get('quantity', 0)
            
            should_stop, reason, stop_price = self.risk_manager.check_stop_loss(
                symbol, current_price, entry_price, quantity
            )
            
            if should_stop:
                log_risk_event(
                    logger, 'stop_loss', symbol, 'high', reason,
                    {'current_price': current_price, 'entry_price': entry_price, 'stop_price': stop_price}
                )
            
            return should_stop, reason, stop_price
            
        except Exception as e:
            log_error(logger, e, {'context': 'stop_loss_check', 'symbol': symbol})
            return False, f"止损检查失败: {str(e)}", 0.0
    
    def get_account_info(self) -> Dict[str, Any]:
        """获取账户信息"""
        try:
            acc_list = self.tc.account_balance()
            total_equity = 0.0
            total_cash = 0.0
            
            for acc in acc_list:
                balances = getattr(acc, 'balances', [acc])
                for b in balances:
                    total_cash += self._unpack(getattr(b, 'total_cash', 0.0))
                    total_equity += self._unpack(getattr(b, 'total_equity', 0.0))
            
            return {
                'total_equity': total_equity,
                'total_cash': total_cash,
                'buying_power': total_cash
            }
            
        except Exception as e:
            log_error(logger, e, {'context': 'get_account_info'})
            return {'total_equity': 0, 'total_cash': 0, 'buying_power': 0}
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """获取持仓列表"""
        try:
            positions = self.tc.stock_positions()
            result = []
            
            for pos in positions:
                symbol = getattr(pos, 'symbol', '')
                quantity = int(self._unpack(getattr(pos, 'quantity', 0)))
                cost_price = self._unpack(getattr(pos, 'cost_price', 0))
                market_price = self._unpack(getattr(pos, 'market_price', 0))
                market_value = quantity * market_price
                
                result.append({
                    'symbol': symbol,
                    'quantity': quantity,
                    'cost_price': cost_price,
                    'market_price': market_price,
                    'market_value': market_value
                })
            
            return result
            
        except Exception as e:
            log_error(logger, e, {'context': 'get_positions'})
            return []
    
    def get_risk_report(self) -> Dict[str, Any]:
        """获取风险报告"""
        report = self.risk_manager.get_risk_report()
        report['daily_pnl'] = self.daily_pnl
        return report
    
    def sync_market_data(self, symbols: List[str]) -> Tuple[Dict[str, float], float]:
        """
        同步市场数据
        
        Args:
            symbols: 股票代码列表
            
        Returns:
            (价格映射, 现金总额)
        """
        try:
            price_map = {}
            cash_total = 0.0
            
            # 获取账户现金
            acc_list = self.tc.account_balance()
            for acc in acc_list:
                balances = getattr(acc, 'balances', [acc])
                for b in balances:
                    cash_total += self._unpack(getattr(b, 'total_cash', 0.0))
            
            # 获取行情数据
            if symbols and self.qc:
                batch_size = 25
                for i in range(0, len(symbols), batch_size):
                    batch = symbols[i:i + batch_size]
                    try:
                        quotes = self.qc.quote(batch)
                        for q in quotes:
                            last_price = self._unpack(q.last_done)
                            prev_price = self._unpack(getattr(q, 'prev_close', 0))
                            
                            final_price = last_price if last_price > 0 else prev_price
                            if final_price > 0:
                                price_map[q.symbol] = final_price
                                
                    except Exception as e:
                        logger.error(f"获取行情失败: {e}")
                        continue
            
            return price_map, cash_total
            
        except Exception as e:
            log_error(logger, e, {'context': 'sync_market_data'})
            return {}, 0.0
