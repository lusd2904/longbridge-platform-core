"""
券商接口抽象层
提供统一的券商接口，支持多券商切换
"""
import logging
import importlib
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from utils.DbUtil import DbUtil
from utils.LoggerUtil import get_logger
from utils.rate_limiter import CircuitBreaker, circuit_breakers

logger = get_logger(__name__)


class BrokerType(Enum):
    """券商类型"""
    LONGBRIDGE = "longbridge"
    TIGER = "tiger"
    INTERACTIVE_BROKERS = "interactive_brokers"
    EASTMONEY = "eastmoney"
    SOOCHOW = "soochow"


@dataclass(frozen=True)
class BrokerProviderSpec:
    """券商适配器注册信息。"""
    broker_type: str
    display_name: str
    adapter_path: Optional[str] = None
    implemented: bool = True
    capabilities: List[str] = field(default_factory=list)
    markets: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class Position:
    """统一持仓数据结构"""
    symbol: str
    quantity: int
    average_cost: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    name: str = ''


@dataclass
class Order:
    """统一订单数据结构"""
    order_id: str
    symbol: str
    action: str  # BUY/SELL
    order_type: str
    quantity: int
    filled_quantity: int
    price: float
    status: str
    create_time: datetime


@dataclass
class AccountInfo:
    """统一账户信息结构"""
    account_id: str
    currency: str
    cash: float
    market_value: float
    total_equity: float
    buying_power: float
    maintenance_margin: float = 0.0


@dataclass
class Quote:
    """统一行情数据结构"""
    symbol: str
    last_price: float
    prev_close: float
    open: float
    high: float
    low: float
    volume: int
    timestamp: datetime
    change: float = 0.0  # 涨跌额
    change_percent: float = 0.0  # 涨跌幅百分比


class BaseBrokerAPI(ABC):
    """券商API基类"""
    
    def __init__(self, account_id: int):
        """
        初始化券商API
        
        Args:
            account_id: 券商账户ID
        """
        self.account_id = account_id
        self.db = DbUtil()
        self.is_connected = False
    
    @abstractmethod
    def connect(self) -> bool:
        """连接API"""
        pass
    
    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass
    
    @abstractmethod
    def get_quote(self, symbols: List[str]) -> Dict[str, Quote]:
        """获取行情"""
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Position]:
        """获取持仓"""
        pass
    
    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        """获取账户信息"""
        pass
    
    @abstractmethod
    def place_order(self, symbol: str, action: str, quantity: int,
                   order_type: str = 'LIMIT', price: Optional[float] = None,
                   time_in_force: str = 'DAY') -> Dict[str, Any]:
        """下单"""
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        pass
    
    @abstractmethod
    def get_orders(self, status: Optional[str] = None) -> List[Order]:
        """获取订单列表"""
        pass
    
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


class BrokerManager:
    """券商管理器"""

    PROVIDER_REGISTRY: Dict[str, BrokerProviderSpec] = {
        BrokerType.LONGBRIDGE.value: BrokerProviderSpec(
            broker_type=BrokerType.LONGBRIDGE.value,
            display_name="长桥证券",
            adapter_path="core.broker.LongbridgeAPI:LongbridgeAPI",
            capabilities=["quote", "positions", "orders", "account"],
            markets=["US", "HK", "CN"],
            notes="当前主通道，已支持实时持仓和交易。"
        ),
        BrokerType.TIGER.value: BrokerProviderSpec(
            broker_type=BrokerType.TIGER.value,
            display_name="老虎证券",
            adapter_path="core.broker.TigerBrokerAPI:TigerBrokerAPI",
            capabilities=["quote", "positions", "orders", "account"],
            markets=["US", "HK", "CN"],
            notes="已接入账号与行情能力。"
        ),
        BrokerType.INTERACTIVE_BROKERS.value: BrokerProviderSpec(
            broker_type=BrokerType.INTERACTIVE_BROKERS.value,
            display_name="盈透证券",
            implemented=False,
            capabilities=["quote", "positions", "orders", "account"],
            markets=["US", "HK", "CN"],
            notes="已预留适配器注册位。"
        ),
        BrokerType.EASTMONEY.value: BrokerProviderSpec(
            broker_type=BrokerType.EASTMONEY.value,
            display_name="东方财富",
            implemented=False,
            capabilities=["quote"],
            markets=["CN"],
            notes="作为国内券商接入预留，待补充认证和委托适配。"
        ),
        BrokerType.SOOCHOW.value: BrokerProviderSpec(
            broker_type=BrokerType.SOOCHOW.value,
            display_name="东吴证券",
            implemented=False,
            capabilities=["quote"],
            markets=["CN"],
            notes="作为国内券商接入预留，待补充交易接口适配。"
        )
    }
    
    def __init__(self):
        """初始化券商管理器"""
        self.db = DbUtil()
        self._brokers: Dict[int, BaseBrokerAPI] = {}
        self._default_broker_ids: Dict[int, Optional[int]] = {}

    @classmethod
    def list_supported_brokers(cls) -> List[Dict[str, Any]]:
        """返回当前系统已登记的券商适配器。"""
        items: List[Dict[str, Any]] = []
        for broker_type, spec in cls.PROVIDER_REGISTRY.items():
            breaker = circuit_breakers.setdefault(
                f"broker:{broker_type}",
                CircuitBreaker(failure_threshold=4, recovery_timeout=45, half_open_max_calls=2)
            )
            items.append({
                "brokerType": broker_type,
                "name": spec.display_name,
                "implemented": spec.implemented,
                "capabilities": spec.capabilities,
                "markets": spec.markets,
                "notes": spec.notes,
                "circuitState": breaker.get_state()
            })
        return items

    @staticmethod
    def _import_adapter(adapter_path: str):
        module_name, _, class_name = adapter_path.partition(':')
        module = importlib.import_module(module_name)
        return getattr(module, class_name)
    
    def get_broker(self, account_id: Optional[int] = None, user_id: Optional[int] = None) -> Optional[BaseBrokerAPI]:
        """
        获取券商API实例
        
        Args:
            account_id: 券商账户ID，None则使用默认账户
            user_id: 用户ID，指定后会校验账户归属
            
        Returns:
            券商API实例
        """
        # 如果未指定账户ID，使用默认账户
        if account_id is None:
            account_id = self._get_default_account_id(user_id=user_id)
        
        if account_id is None:
            logger.error("未找到可用的券商账户")
            return None

        if user_id is not None and not self.account_belongs_to_user(account_id, user_id):
            logger.error("账户不属于当前用户: account_id=%s user_id=%s", account_id, user_id)
            return None
        
        # 检查缓存
        if account_id in self._brokers:
            return self._brokers[account_id]
        
        # 创建新的API实例
        broker = self._create_broker(account_id, user_id=user_id)
        if broker:
            self._brokers[account_id] = broker
        
        return broker
    
    def _get_default_account_id(self, user_id: Optional[int] = None) -> Optional[int]:
        """获取默认账户ID"""
        if user_id is not None and self._default_broker_ids.get(user_id):
            return self._default_broker_ids.get(user_id)
        
        try:
            if user_id is not None:
                sql = """
                SELECT id FROM broker_accounts 
                WHERE user_id = %s AND is_default = 1 AND is_active = 1
                LIMIT 1
                """
                record = self.db.fetch_one(sql, (user_id,))
            else:
                sql = """
                SELECT id FROM broker_accounts 
                WHERE is_default = 1 AND is_active = 1
                LIMIT 1
                """
                record = self.db.fetch_one(sql)

            if record:
                if user_id is not None:
                    self._default_broker_ids[user_id] = record['id']
                return record['id']

            # 如果没有默认账户，使用第一个激活账户
            if user_id is not None:
                sql = """
                SELECT id FROM broker_accounts 
                WHERE user_id = %s AND is_active = 1
                ORDER BY id ASC
                LIMIT 1
                """
                record = self.db.fetch_one(sql, (user_id,))
            else:
                sql = """
                SELECT id FROM broker_accounts 
                WHERE is_active = 1
                ORDER BY id ASC
                LIMIT 1
                """
                record = self.db.fetch_one(sql)

            if record:
                if user_id is not None:
                    self._default_broker_ids[user_id] = record['id']
                return record['id']
                
        except Exception as e:
            logger.error(f"获取默认账户失败: {e}")
        
        return None
    
    def _create_broker(self, account_id: int, user_id: Optional[int] = None) -> Optional[BaseBrokerAPI]:
        """
        创建券商API实例
        
        Args:
            account_id: 账户ID
            user_id: 用户ID
            
        Returns:
            券商API实例
        """
        try:
            # 查询账户类型
            if user_id is not None:
                sql = """
                SELECT broker_type FROM broker_accounts 
                WHERE id = %s AND user_id = %s AND is_active = 1
                """
                record = self.db.fetch_one(sql, (account_id, user_id))
            else:
                sql = """
                SELECT broker_type FROM broker_accounts 
                WHERE id = %s AND is_active = 1
                """
                record = self.db.fetch_one(sql, (account_id,))

            if not record:
                logger.error(f"未找到券商账户: {account_id}")
                return None

            broker_type = record['broker_type']
            spec = self.PROVIDER_REGISTRY.get(broker_type)
            if not spec:
                logger.error(f"未知的券商类型: {broker_type}")
                return None

            if not spec.implemented or not spec.adapter_path:
                logger.warning("券商适配器尚未实现: %s", broker_type)
                return None

            breaker = circuit_breakers.setdefault(
                f"broker:{broker_type}",
                CircuitBreaker(failure_threshold=4, recovery_timeout=45, half_open_max_calls=2)
            )
            if not breaker.can_execute():
                logger.warning("券商适配器处于熔断状态: %s", broker_type)
                return None

            adapter_cls = self._import_adapter(spec.adapter_path)
            broker = adapter_cls(account_id)
            breaker.record_success()
            return broker
                
        except Exception as e:
            if 'broker_type' in locals():
                breaker = circuit_breakers.setdefault(
                    f"broker:{broker_type}",
                    CircuitBreaker(failure_threshold=4, recovery_timeout=45, half_open_max_calls=2)
                )
                breaker.record_failure()
            logger.error(f"创建券商API失败: {e}")
            return None

    def account_belongs_to_user(self, account_id: int, user_id: int) -> bool:
        """校验账户是否归属于指定用户。"""
        try:
            row = self.db.fetch_one(
                """
                SELECT id
                FROM broker_accounts
                WHERE id = %s AND user_id = %s AND is_active = 1
                LIMIT 1
                """,
                (account_id, user_id)
            )
            return bool(row)
        except Exception as e:
            logger.error(f"校验账户归属失败: {e}")
            return False

    def list_user_ids_with_accounts(self) -> List[int]:
        """列出拥有激活券商账户的用户。"""
        try:
            rows = self.db.query_all(
                """
                SELECT DISTINCT user_id
                FROM broker_accounts
                WHERE is_active = 1
                ORDER BY user_id ASC
                """
            )
            return [int(row[0]) for row in rows if row and row[0] is not None]
        except Exception as e:
            logger.error(f"列出券商账户用户失败: {e}")
            return []
    
    def list_accounts(self, user_id: int = 1, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """
        列出券商账户
        
        Args:
            user_id: 用户ID
            include_inactive: 是否包含已删除/停用账户
            
        Returns:
            账户列表
        """
        try:
            sql = """
            SELECT id, broker_type, broker_name, account_id, 
                   is_default, is_active, created_at
            FROM broker_accounts 
            WHERE user_id = %s
              AND (%s = 1 OR is_active = 1)
            ORDER BY is_default DESC, id ASC
            """
            rows = self.db.query_all(sql, (user_id, 1 if include_inactive else 0))
            # 将元组转换为字典
            accounts = []
            for row in rows:
                accounts.append({
                    'id': row[0],
                    'broker_type': row[1],
                    'broker_name': row[2],
                    'account_id': row[3],
                    'is_default': row[4],
                    'is_active': row[5],
                    'created_at': row[6]
                })
            return accounts
        except Exception as e:
            logger.error(f"列出券商账户失败: {e}")
            return []
    
    def set_default_account(self, account_id: int, user_id: Optional[int] = None) -> bool:
        """
        设置默认账户
        
        Args:
            account_id: 账户ID
            user_id: 用户ID
            
        Returns:
            是否成功
        """
        try:
            if user_id is not None and not self.account_belongs_to_user(account_id, user_id):
                logger.error("设置默认账户失败，账户不属于当前用户: account_id=%s user_id=%s", account_id, user_id)
                return False

            # 先清除所有默认标记
            if user_id is not None:
                sql1 = """
                UPDATE broker_accounts 
                SET is_default = 0 
                WHERE user_id = %s AND is_default = 1
                """
                self.db.execute(sql1, (user_id,))
            else:
                sql1 = """
                UPDATE broker_accounts 
                SET is_default = 0 
                WHERE is_default = 1
                """
                self.db.execute(sql1)
            
            # 设置新的默认账户
            if user_id is not None:
                sql2 = """
                UPDATE broker_accounts 
                SET is_default = 1 
                WHERE id = %s AND user_id = %s
                """
                self.db.execute(sql2, (account_id, user_id))
                self._default_broker_ids[user_id] = account_id
            else:
                sql2 = """
                UPDATE broker_accounts 
                SET is_default = 1 
                WHERE id = %s
                """
                self.db.execute(sql2, (account_id,))
            
            logger.info(f"默认券商账户已设置为: {account_id}")
            return True
            
        except Exception as e:
            logger.error(f"设置默认账户失败: {e}")
            return False
    
    def switch_broker(self, account_id: int) -> Optional[BaseBrokerAPI]:
        """
        切换券商
        
        Args:
            account_id: 目标账户ID
            
        Returns:
            新的券商API实例
        """
        # 断开当前连接
        if account_id in self._brokers:
            self._brokers[account_id].disconnect()
            del self._brokers[account_id]
        
        # 创建新连接
        return self.get_broker(account_id)


# 全局券商管理器实例
_broker_manager = None

def get_broker_manager() -> BrokerManager:
    """获取全局券商管理器"""
    global _broker_manager
    if _broker_manager is None:
        _broker_manager = BrokerManager()
    return _broker_manager


def get_broker(account_id: Optional[int] = None, user_id: Optional[int] = None) -> Optional[BaseBrokerAPI]:
    """便捷函数：获取券商API"""
    return get_broker_manager().get_broker(account_id, user_id=user_id)
