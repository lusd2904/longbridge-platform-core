"""
老虎国际证券API客户端
封装Tiger Open API的常用功能
"""
import logging
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from utils.DbUtil import DbUtil
from utils.LoggerUtil import get_logger, log_trade, log_error
from utils.crypto import decrypt, encrypt
from core.broker.BrokerInterface import AccountInfo, Position, Order, Quote

logger = get_logger(__name__)

# 尝试导入tigeropen
try:
    from tigeropen.tiger_open_client import TigerOpenClient
    from tigeropen.tiger_open_config import get_client_config
    from tigeropen.common.consts import Market, Language
    from tigeropen.quote.quote_client import QuoteClient
    from tigeropen.trade.trade_client import TradeClient
    from tigeropen.common.exceptions import ApiException
    TIGER_SDK_AVAILABLE = True
except ImportError as e:
    logger.warning(f"tigeropen SDK导入失败: {e}")
    TIGER_SDK_AVAILABLE = False


@dataclass
class TigerAccountConfig:
    """老虎证券账户配置"""
    tiger_id: str
    account: str
    license: str
    private_key_pk1: str
    private_key_pk8: str
    env: str = "PROD"
    
    @classmethod
    def from_db_record(cls, record: Dict) -> 'TigerAccountConfig':
        """从数据库记录创建配置"""
        return cls(
            tiger_id=decrypt(record.get('tiger_id', '')),
            account=decrypt(record.get('tiger_account', '')),
            license=decrypt(record.get('tiger_license', '')),
            private_key_pk1=decrypt(record.get('tiger_private_key_pk1', '')),
            private_key_pk8=decrypt(record.get('tiger_private_key_pk8', '')),
            env=record.get('tiger_env', 'PROD')
        )


class TigerBrokerAPI:
    """老虎证券API客户端"""
    
    def __init__(self, account_id: Optional[int] = None):
        """
        初始化老虎证券API客户端
        
        Args:
            account_id: 券商账户ID，如未提供则使用默认账户
        """
        self.db = DbUtil()
        self.account_id = account_id
        self.config: Optional[TigerAccountConfig] = None
        
        # API客户端
        self.client: Optional[TigerOpenClient] = None
        self.quote_client: Optional[QuoteClient] = None
        self.trade_client: Optional[TradeClient] = None
        
        # 加载配置
        self._load_config()
    
    def _load_config(self):
        """从数据库加载配置"""
        try:
            if self.account_id:
                sql = """
                SELECT * FROM broker_accounts 
                WHERE id = %s AND broker_type = 'tiger' AND is_active = 1
                """
                record = self.db.fetch_one(sql, (self.account_id,))
            else:
                # 获取默认的老虎证券账户
                sql = """
                SELECT * FROM broker_accounts 
                WHERE broker_type = 'tiger' AND is_active = 1
                ORDER BY is_default DESC, id ASC
                LIMIT 1
                """
                record = self.db.fetch_one(sql)

            if record:
                logger.info(f"老虎证券数据库记录: {record}")
                self.config = TigerAccountConfig.from_db_record(record)
                self.account_id = record.get('id')
                logger.info(f"已加载老虎证券配置: tiger_id={self.config.tiger_id}, account={self.config.account}")
            else:
                logger.warning(f"未找到老虎证券配置, account_id={self.account_id}")

        except Exception as e:
            logger.error(f"加载老虎证券配置失败: {e}")
            raise
    
    def connect(self) -> bool:
        """
        连接老虎证券API
        
        Returns:
            是否连接成功
        """
        if not TIGER_SDK_AVAILABLE:
            logger.error("tigeropen SDK未安装")
            return False
        
        if not self.config:
            logger.error("老虎证券配置未加载")
            return False
        
        try:
            # 写入临时私钥文件
            import tempfile
            import os
            
            # 将Base64编码的私钥转换为PEM格式
            private_key_content = self.config.private_key_pk1
            
            # 检查是否已经是PEM格式
            if not private_key_content.startswith('-----BEGIN'):
                # 需要包装成PEM格式
                # PKCS#1格式
                pem_content = "-----BEGIN RSA PRIVATE KEY-----\n"
                # 每64字符一行
                for i in range(0, len(private_key_content), 64):
                    pem_content += private_key_content[i:i+64] + "\n"
                pem_content += "-----END RSA PRIVATE KEY-----\n"
            else:
                pem_content = private_key_content
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
                f.write(pem_content)
                temp_key_path = f.name
            
            logger.info(f"私钥文件已创建: {temp_key_path}")
            
            try:
                # 创建客户端配置
                self.client_config = get_client_config(
                    private_key_path=temp_key_path,
                    tiger_id=self.config.tiger_id,
                    account=self.config.account
                )
                
                # 创建行情客户端 - 使用client_config，启用行情权限抢占
                self.quote_client = QuoteClient(self.client_config, logger=logger, is_grab_permission=True)
                
                # 显式执行行情权限抢占
                try:
                    self.quote_client.grab_quote_permission()
                    logger.info("老虎证券行情权限抢占成功")
                except Exception as e:
                    logger.warning(f"行情权限抢占失败（可能已抢占）: {e}")
                
                # 创建交易客户端 - 使用client_config
                self.trade_client = TradeClient(self.client_config, logger=logger)
                
                # 测试连接 - 获取资产信息
                assets = self.trade_client.get_assets()
                logger.info(f"老虎证券连接测试成功，获取到资产信息: {assets}")
                
                logger.info("老虎证券API连接成功")
                self._log_connection('connect', 'success')
                return True
            finally:
                # 删除临时文件
                os.unlink(temp_key_path)
            
        except Exception as e:
            logger.error(f"老虎证券API连接失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._log_connection('connect', 'failed', str(e))
            return False
    
    def disconnect(self):
        """断开连接"""
        self.quote_client = None
        self.trade_client = None
        self.client_config = None
        logger.info("老虎证券API已断开")
        self._log_connection('disconnect', 'success')
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.trade_client is not None and self.quote_client is not None
    
    def _ensure_connected(self):
        """确保已连接"""
        if not self.is_connected():
            if not self.connect():
                raise ConnectionError("老虎证券API未连接")
    
    def _log_connection(self, action: str, status: str, message: str = ''):
        """记录连接日志"""
        try:
            sql = """
            INSERT INTO broker_connection_logs 
            (broker_account_id, action, status, message)
            VALUES (%s, %s, %s, %s)
            """
            self.db.execute(sql, (self.account_id, action, status, message))
        except Exception as e:
            logger.error(f"记录连接日志失败: {e}")
    
    # ==================== 行情接口 ====================
    
    def get_quote(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        获取行情数据
        
        Args:
            symbols: 股票代码列表
            
        Returns:
            行情数据字典
        """
        self._ensure_connected()
        
        try:
            # 调用Tiger API获取行情
            quotes = self.quote_client.get_stock_briefs(symbols=symbols)
            
            result = {}
            for quote in quotes:
                symbol = getattr(quote, 'symbol', '')
                result[symbol] = {
                    'symbol': symbol,
                    'last_price': float(getattr(quote, 'latest_price', 0)),
                    'prev_close': float(getattr(quote, 'prev_close', 0)),
                    'open': float(getattr(quote, 'open', 0)),
                    'high': float(getattr(quote, 'high', 0)),
                    'low': float(getattr(quote, 'low', 0)),
                    'volume': int(getattr(quote, 'volume', 0)),
                    'timestamp': datetime.now()
                }
            
            return result
            
        except Exception as e:
            logger.error(f"获取行情失败: {e}")
            self._log_connection('query', 'failed', f'get_quote: {e}')
            raise
    
    def get_klines(self, symbol: str, period: str = 'day', limit: int = 100) -> List[Dict]:
        """
        获取K线数据
        
        Args:
            symbol: 股票代码
            period: 周期 (day/week/month)
            limit: 数量限制
            
        Returns:
            K线数据列表
        """
        self._ensure_connected()
        
        try:
            # 转换周期
            period_map = {
                'day': 'day',
                'week': 'week',
                'month': 'month'
            }
            tiger_period = period_map.get(period, 'day')
            
            # 获取K线
            klines = self.quote_client.get_klines(
                symbols=[symbol],
                period=tiger_period,
                limit=limit
            )
            
            result = []
            for k in klines:
                result.append({
                    'symbol': symbol,
                    'timestamp': getattr(k, 'time', None),
                    'open': float(getattr(k, 'open', 0)),
                    'high': float(getattr(k, 'high', 0)),
                    'low': float(getattr(k, 'low', 0)),
                    'close': float(getattr(k, 'close', 0)),
                    'volume': int(getattr(k, 'volume', 0))
                })
            
            return result
            
        except Exception as e:
            logger.error(f"获取K线失败: {e}")
            raise
    
    # ==================== 交易接口 ====================
    
    def get_positions(self) -> List[Position]:
        """
        获取持仓列表
        
        Returns:
            持仓列表
        """
        self._ensure_connected()
        
        try:
            positions = self.trade_client.get_positions(account=self.config.account)
            
            result = []
            for pos in positions:
                result.append(Position(
                    symbol=getattr(pos, 'symbol', ''),
                    quantity=int(getattr(pos, 'quantity', 0)),
                    average_cost=float(getattr(pos, 'average_cost', 0)),
                    market_price=float(getattr(pos, 'market_price', 0)),
                    market_value=float(getattr(pos, 'market_value', 0)),
                    unrealized_pnl=float(getattr(pos, 'unrealized_pnl', 0)),
                    realized_pnl=float(getattr(pos, 'realized_pnl', 0)),
                    name=getattr(pos, 'symbol', '')
                ))
            
            return result
            
        except Exception as e:
            logger.error(f"获取持仓失败: {e}")
            self._log_connection('query', 'failed', f'get_positions: {e}')
            raise
    
    def get_account_info(self) -> 'AccountInfo':
        """
        获取账户信息
        
        Returns:
            账户信息对象
        """
        self._ensure_connected()
        
        try:
            # 使用get_assets获取账户资产信息
            logger.info(f"正在获取老虎证券账户资产信息, account={self.config.account}")
            accounts = self.trade_client.get_assets(account=self.config.account)
            logger.info(f"获取到账户资产信息: {accounts}")
            
            # 获取第一个账户的资产信息
            if accounts and len(accounts) > 0:
                portfolio_account = accounts[0]
                logger.info(f"PortfolioAccount: {portfolio_account}")
                summary = getattr(portfolio_account, 'summary', None)
                logger.info(f"Summary: {summary}")
                
                if summary:
                    cash = float(getattr(summary, 'cash', 0))
                    buying_power = float(getattr(summary, 'buying_power', 0))
                    gross_position_value = float(getattr(summary, 'gross_position_value', 0))
                    net_liquidation = float(getattr(summary, 'net_liquidation', 0))
                    
                    # 检查是否有无穷大值
                    import math
                    if math.isinf(gross_position_value) or math.isnan(gross_position_value):
                        logger.warning(f"持仓市值为无穷大或NaN: {gross_position_value}，设置为0")
                        gross_position_value = 0.0
                    if math.isinf(net_liquidation) or math.isnan(net_liquidation):
                        logger.warning(f"总资产为无穷大或NaN: {net_liquidation}，设置为cash值")
                        net_liquidation = cash
                    
                    logger.info(f"账户数据: cash={cash}, buying_power={buying_power}, "
                              f"market_value={gross_position_value}, total_equity={net_liquidation}")
                    
                    return AccountInfo(
                        account_id=self.config.account,
                        currency=getattr(summary, 'currency', 'USD'),
                        cash=cash,
                        market_value=gross_position_value,
                        total_equity=net_liquidation,
                        buying_power=buying_power
                    )
                else:
                    logger.warning("无法获取summary信息")
            else:
                logger.warning(f"无法获取账户资产信息，accounts={accounts}")
            
            # 如果无法获取资产信息，返回默认值
            logger.warning("返回默认账户信息")
            return AccountInfo(
                account_id=self.config.account,
                currency='USD',
                cash=0.0,
                market_value=0.0,
                total_equity=0.0,
                buying_power=0.0
            )
            
        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._log_connection('query', 'failed', f'get_account_info: {e}')
            raise
    
    def place_order(self, 
                   symbol: str, 
                   action: str, 
                   quantity: int, 
                   order_type: str = 'LIMIT',
                   price: Optional[float] = None,
                   time_in_force: str = 'DAY') -> Dict[str, Any]:
        """
        下单
        
        Args:
            symbol: 股票代码
            action: 动作 (BUY/SELL)
            quantity: 数量
            order_type: 订单类型 (LIMIT/MARKET)
            price: 价格（限价单需要）
            time_in_force: 有效期 (DAY/GTC)
            
        Returns:
            订单结果
        """
        self._ensure_connected()
        
        try:
            # 转换订单类型
            from tigeropen.common.const import OrderType, OrderSide, TimeInForce
            
            side = OrderSide.BUY if action == 'BUY' else OrderSide.SELL
            
            if order_type == 'MARKET':
                order_type_enum = OrderType.MKT
            else:
                order_type_enum = OrderType.LMT
            
            if time_in_force == 'GTC':
                tif = TimeInForce.GTC
            else:
                tif = TimeInForce.DAY
            
            # 提交订单
            order = self.trade_client.place_order(
                account=self.config.account,
                symbol=symbol,
                side=side,
                order_type=order_type_enum,
                quantity=quantity,
                price=price,
                time_in_force=tif
            )
            
            result = {
                'order_id': getattr(order, 'order_id', ''),
                'status': getattr(order, 'status', ''),
                'symbol': symbol,
                'action': action,
                'quantity': quantity,
                'price': price,
                'message': '订单提交成功'
            }
            
            # 记录交易日志
            log_trade(logger, symbol, action, quantity, price or 0, 
                     order_id=result['order_id'])
            
            self._log_connection('trade', 'success', f'place_order: {symbol} {action}')
            
            return result
            
        except Exception as e:
            logger.error(f"下单失败: {e}")
            self._log_connection('trade', 'failed', f'place_order: {e}')
            raise
    
    def cancel_order(self, order_id: str) -> bool:
        """
        撤单
        
        Args:
            order_id: 订单ID
            
        Returns:
            是否成功
        """
        self._ensure_connected()
        
        try:
            self.trade_client.cancel_order(account=self.config.account, order_id=order_id)
            logger.info(f"订单已撤销: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"撤单失败: {e}")
            return False
    
    def get_orders(self, status: Optional[str] = None) -> List[Order]:
        """
        获取订单列表
        
        Args:
            status: 订单状态过滤
            
        Returns:
            订单列表
        """
        self._ensure_connected()
        
        try:
            orders = self.trade_client.get_orders(account=self.config.account)
            
            result = []
            for o in orders:
                order = Order(
                    order_id=getattr(o, 'order_id', ''),
                    symbol=getattr(o, 'symbol', ''),
                    action=getattr(o, 'side', ''),
                    order_type=getattr(o, 'order_type', ''),
                    quantity=int(getattr(o, 'quantity', 0)),
                    filled_quantity=int(getattr(o, 'filled_quantity', 0)),
                    price=float(
                        getattr(
                            o,
                            'price',
                            getattr(o, 'submitted_price', getattr(o, 'limit_price', 0))
                        ) or 0
                    ),
                    status=getattr(o, 'status', ''),
                    create_time=getattr(o, 'create_time', datetime.now())
                )
                
                if status is None or order.status == status:
                    result.append(order)
            
            return result
            
        except Exception as e:
            logger.error(f"获取订单列表失败: {e}")
            raise
    
    # ==================== 静态方法 ====================
    
    @staticmethod
    def save_config(
        config: Dict[str, str],
        user_id: int = 1,
        is_default: bool = False,
        account_row_id: Optional[int] = None
    ) -> int:
        """
        保存配置到数据库
        
        Args:
            config: 配置字典
            user_id: 用户ID
            is_default: 是否为默认账户
            
        Returns:
            账户ID
        """
        db = DbUtil()
        
        try:
            if account_row_id:
                existing = db.fetch_one(
                    """
                    SELECT id, account_id, tiger_id, tiger_account, tiger_license,
                           tiger_private_key_pk1, tiger_private_key_pk8, tiger_env
                    FROM broker_accounts
                    WHERE id = %s AND user_id = %s AND broker_type = 'tiger' AND is_active = 1
                    LIMIT 1
                    """,
                    (account_row_id, user_id)
                )
                if not existing:
                    raise ValueError('券商账户不存在或不属于当前用户')

                account_value = str(config.get('account') or existing.get('account_id') or '').strip()
                tiger_id = str(config.get('tiger_id') or '').strip()
                license_value = str(config.get('license') or '').strip()
                private_key_pk1 = str(config.get('private_key_pk1') or '').strip()
                private_key_pk8 = str(config.get('private_key_pk8') or '').strip()
                env_value = str(config.get('env') or existing.get('tiger_env') or 'PROD').strip().upper()

                sql = """
                UPDATE broker_accounts
                SET account_id = %s,
                    tiger_id = %s,
                    tiger_account = %s,
                    tiger_license = %s,
                    tiger_private_key_pk1 = %s,
                    tiger_private_key_pk8 = %s,
                    tiger_env = %s,
                    is_default = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s
                """
                params = (
                    account_value,
                    encrypt(tiger_id) if tiger_id else (existing.get('tiger_id') or ''),
                    encrypt(account_value) if account_value else (existing.get('tiger_account') or ''),
                    encrypt(license_value) if license_value else (existing.get('tiger_license') or ''),
                    encrypt(private_key_pk1) if private_key_pk1 else (existing.get('tiger_private_key_pk1') or ''),
                    encrypt(private_key_pk8) if private_key_pk8 else (existing.get('tiger_private_key_pk8') or ''),
                    env_value or 'PROD',
                    1 if is_default else 0,
                    account_row_id,
                    user_id
                )
                db.execute(sql, params)
                logger.info("老虎证券配置已更新，账户ID: %s", account_row_id)
                return int(account_row_id)

            sql = """
            INSERT INTO broker_accounts
            (user_id, broker_type, broker_name, account_id,
             tiger_id, tiger_account, tiger_license,
             tiger_private_key_pk1, tiger_private_key_pk8, tiger_env,
             is_default, is_active)
            VALUES (%s, 'tiger', '老虎证券', %s, %s, %s, %s, %s, %s, %s, %s, 1)
            """

            params = (
                user_id,
                config.get('account', ''),
                encrypt(config.get('tiger_id', '')),
                encrypt(config.get('account', '')),
                encrypt(config.get('license', '')),
                encrypt(config.get('private_key_pk1', '')),
                encrypt(config.get('private_key_pk8', '')),
                config.get('env', 'PROD'),
                1 if is_default else 0
            )

            account_id = db.execute_insert(sql, params)
            logger.info("老虎证券配置已保存，账户ID: %s", account_id)
            return account_id
        except Exception as e:
            logger.error(f"保存老虎证券配置失败: {e}")
            raise


# 便捷函数
def get_tiger_api(account_id: Optional[int] = None) -> TigerBrokerAPI:
    """获取老虎证券API实例"""
    return TigerBrokerAPI(account_id)
