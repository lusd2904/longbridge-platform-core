"""
长桥证券API适配器
适配长桥证券SDK到统一接口
"""
import logging
import threading
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from .BrokerInterface import BaseBrokerAPI, Position, Order, AccountInfo, Quote
from shared.longbridge import (
    QuoteContext,
    TradeContext,
    build_quote_context_from_cli,
    build_trade_context_from_cli,
    invalidate_quote_context,
    invalidate_trade_context,
)
from utils.DbUtil import DbUtil
from utils.LoggerUtil import get_logger, log_trade
from utils.kafka_bus import kafka_bus
from utils.rate_limiter import CircuitBreaker, circuit_breakers
from utils.redis_client import redis_client

logger = get_logger(__name__)


def _to_float(value: Any) -> float:
    """安全转换长桥 SDK 数值对象。"""
    if value is None:
        return 0.0

    try:
        return float(getattr(value, 'value', value))
    except (TypeError, ValueError):
        return 0.0


def _enum_name(value: Any, default: str = "") -> str:
    """兼容 SDK 枚举、字符串和普通对象的名称提取。"""
    if value is None:
        return default

    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name

    raw = str(value).strip()
    if not raw:
        return default
    if "." in raw:
        raw = raw.split(".")[-1]
    return raw or default

# 尝试导入长桥SDK
try:
    LONGBRIDGE_SDK_AVAILABLE = True
except ImportError:
    logger.warning("longbridge SDK未安装，长桥证券功能将不可用")
    LONGBRIDGE_SDK_AVAILABLE = False
    # 定义占位符类以避免错误
    class Config:
        def __init__(self, *args, **kwargs):
            pass
    class TradeContext:
        def __init__(self, *args, **kwargs):
            pass
    class QuoteContext:
        def __init__(self, *args, **kwargs):
            pass


@dataclass
class LongbridgeConfig:
    """长桥证券配置"""
    account_id: str = ''  # 长桥账户ID
    
    @classmethod
    def from_db_record(cls, record: Dict) -> 'LongbridgeConfig':
        """从数据库记录创建配置"""
        return cls(account_id=record.get('account_id', ''))


class LongbridgeAPI(BaseBrokerAPI):
    """长桥证券API适配器"""
    _request_lock = threading.Lock()
    _last_request_at = 0.0
    _min_interval_seconds = 0.35
    _metrics_lock = threading.Lock()
    _observability = {
        "tradeContextAttachCount": 0,
        "quoteContextAttachCount": 0,
        "quoteFallbackCount": 0,
        "contextRefreshCount": 0,
        "lastError": "",
        "lastErrorAt": "",
        "lastErrorAccountId": None,
        "lastSuccessAt": "",
        "lastSuccessOperation": ""
    }
    
    def __init__(self, account_id: int):
        """
        初始化长桥证券API
        
        Args:
            account_id: 券商账户ID
        """
        super().__init__(account_id)
        self.config: Optional[LongbridgeConfig] = None
        self.trade_context: Optional[TradeContext] = None
        self.quote_context: Optional[QuoteContext] = None
        
        # 加载配置
        self._load_config()

    @classmethod
    def _increment_metric(cls, key: str, amount: int = 1) -> None:
        with cls._metrics_lock:
            cls._observability[key] = int(cls._observability.get(key, 0) or 0) + amount

    @classmethod
    def _record_error(cls, message: Any, account_id: Optional[int] = None) -> None:
        with cls._metrics_lock:
            cls._observability["lastError"] = str(message or "")
            cls._observability["lastErrorAt"] = datetime.now().isoformat()
            cls._observability["lastErrorAccountId"] = account_id

    @classmethod
    def _record_success(cls, operation: str) -> None:
        with cls._metrics_lock:
            cls._observability["lastSuccessAt"] = datetime.now().isoformat()
            cls._observability["lastSuccessOperation"] = str(operation or "")

    @classmethod
    def get_observability_snapshot(cls) -> Dict[str, Any]:
        with cls._metrics_lock:
            return dict(cls._observability)

    def _invalidate_context_cache(self, include_quote: bool = True) -> None:
        if not self.config:
            return

        self._increment_metric("contextRefreshCount")

        invalidate_trade_context()
        if include_quote:
            invalidate_quote_context()

    def _attach_trade_context(self, *, force_refresh: bool = False) -> TradeContext:
        if not self.config:
            raise RuntimeError("长桥证券配置未加载")
        if force_refresh:
            self._invalidate_context_cache(include_quote=False)

        self.trade_context = build_trade_context_from_cli()
        self.is_connected = self.trade_context is not None
        if not self.trade_context:
            raise RuntimeError("长桥交易上下文初始化失败")
        self._increment_metric("tradeContextAttachCount")
        self._record_success("attach_trade_context")
        return self.trade_context

    def _attach_quote_context(self, *, force_refresh: bool = False) -> QuoteContext:
        if not self.config:
            raise RuntimeError("长桥证券配置未加载")
        if force_refresh:
            invalidate_quote_context()

        self.quote_context = build_quote_context_from_cli()
        if not self.quote_context:
            raise RuntimeError("长桥行情上下文初始化失败")
        self._increment_metric("quoteContextAttachCount")
        self._record_success("attach_quote_context")
        return self.quote_context
    
    def _load_config(self):
        """从数据库加载配置"""
        try:
            sql = """
            SELECT * FROM broker_accounts 
            WHERE id = %s AND broker_type = 'longbridge' AND is_active = 1
            """
            record = self.db.fetch_one(sql, (self.account_id,))

            if record:
                self.config = LongbridgeConfig.from_db_record(record)
                logger.info("已加载长桥证券配置")
            else:
                logger.warning(f"未找到长桥证券配置, account_id={self.account_id}")

        except Exception as e:
            logger.error(f"加载长桥证券配置失败: {e}")
            raise
    
    def connect(self) -> bool:
        """
        连接长桥证券API
        
        Returns:
            是否连接成功
        """
        if not LONGBRIDGE_SDK_AVAILABLE:
            logger.error("longbridge SDK未安装")
            return False
        
        if not self.config:
            logger.error("长桥证券配置未加载")
            return False

        if self.is_connected and self.trade_context is not None:
            return True

        try:
            self._attach_trade_context()
            logger.info("长桥证券API连接成功")
            self._log_connection('connect', 'success')
            return True

        except Exception as first_error:
            self._record_error(first_error, self.account_id)
            logger.warning("长桥证券API首次连接失败，准备刷新上下文重试: %s", first_error)
            try:
                self._attach_trade_context(force_refresh=True)
                logger.info("长桥证券API刷新上下文后连接成功")
                self._log_connection('connect', 'success', 'reconnected_after_refresh')
                return True
            except Exception as retry_error:
                self.trade_context = None
                self.quote_context = None
                self.is_connected = False
                self._record_error(retry_error, self.account_id)
                logger.error(f"长桥证券API连接失败: {retry_error}")
                self._log_connection('connect', 'failed', str(retry_error))
                return False
    
    def disconnect(self):
        """断开连接"""
        self.trade_context = None
        self.quote_context = None
        self.is_connected = False
        logger.info("长桥证券API已断开")
        self._log_connection('disconnect', 'success')
    
    def _ensure_connected(self):
        """确保已连接"""
        if not self.is_connected or self.trade_context is None:
            if not self.connect():
                raise ConnectionError("长桥证券API未连接")

    def _ensure_quote_context(self) -> QuoteContext:
        self._ensure_connected()
        if self.quote_context is None:
            try:
                return self._attach_quote_context()
            except Exception as first_error:
                logger.warning("长桥行情上下文初始化失败，准备刷新重试: %s", first_error)
                return self._attach_quote_context(force_refresh=True)
        return self.quote_context

    @classmethod
    def _throttle_request(cls):
        with cls._request_lock:
            now = time.time()
            elapsed = now - cls._last_request_at
            if elapsed < cls._min_interval_seconds:
                time.sleep(cls._min_interval_seconds - elapsed)
            cls._last_request_at = time.time()

    def _breaker(self, operation: str, failure_threshold: int = 4, recovery_timeout: int = 45) -> CircuitBreaker:
        return circuit_breakers.setdefault(
            f"broker:longbridge:{operation}:{self.account_id}",
            CircuitBreaker(
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                half_open_max_calls=2
            )
        )

    def _execute_with_resilience(self, operation: str, func, fallback=None):
        breaker = self._breaker(operation)
        if not breaker.can_execute():
            logger.warning("长桥 %s 处于熔断降级状态，account_id=%s", operation, self.account_id)
            self._record_error(f"breaker_open:{operation}", self.account_id)
            if fallback:
                return fallback()
            raise RuntimeError(f"长桥 {operation} 当前处于熔断状态")

        try:
            result = func()
            breaker.record_success()
            self._record_success(operation)
            return result
        except Exception as exc:
            breaker.record_failure()
            self._record_error(exc, self.account_id)
            if fallback:
                return fallback()
            raise

    @staticmethod
    def _quote_to_cache_payload(quote: Quote) -> Dict[str, Any]:
        return {
            "symbol": quote.symbol,
            "last_price": quote.last_price,
            "prev_close": quote.prev_close,
            "open": quote.open,
            "high": quote.high,
            "low": quote.low,
            "volume": quote.volume,
            "change": quote.change,
            "change_percent": quote.change_percent,
            "timestamp": quote.timestamp.isoformat() if quote.timestamp else None
        }

    @staticmethod
    def _quote_from_cache(symbol: str, payload: Dict[str, Any]) -> Quote:
        timestamp_raw = payload.get("timestamp")
        try:
            timestamp = datetime.fromisoformat(timestamp_raw) if timestamp_raw else datetime.now()
        except Exception:
            timestamp = datetime.now()

        return Quote(
            symbol=symbol,
            last_price=float(payload.get("last_price", 0) or 0),
            prev_close=float(payload.get("prev_close", 0) or 0),
            open=float(payload.get("open", 0) or 0),
            high=float(payload.get("high", 0) or 0),
            low=float(payload.get("low", 0) or 0),
            volume=int(payload.get("volume", 0) or 0),
            timestamp=timestamp,
            change=float(payload.get("change", 0) or 0),
            change_percent=float(payload.get("change_percent", 0) or 0)
        )

    @staticmethod
    def _position_to_cache_payload(position: Position) -> Dict[str, Any]:
        return {
            "symbol": position.symbol,
            "quantity": position.quantity,
            "average_cost": position.average_cost,
            "market_price": position.market_price,
            "market_value": position.market_value,
            "unrealized_pnl": position.unrealized_pnl,
            "realized_pnl": position.realized_pnl,
            "name": position.name
        }

    @staticmethod
    def _position_from_cache(payload: Dict[str, Any]) -> Position:
        return Position(
            symbol=str(payload.get("symbol") or ""),
            quantity=int(payload.get("quantity", 0) or 0),
            average_cost=float(payload.get("average_cost", 0) or 0),
            market_price=float(payload.get("market_price", 0) or 0),
            market_value=float(payload.get("market_value", 0) or 0),
            unrealized_pnl=float(payload.get("unrealized_pnl", 0) or 0),
            realized_pnl=float(payload.get("realized_pnl", 0) or 0),
            name=str(payload.get("name") or "")
        )

    @staticmethod
    def _account_to_cache_payload(account_info: AccountInfo) -> Dict[str, Any]:
        return {
            "account_id": account_info.account_id,
            "currency": account_info.currency,
            "cash": account_info.cash,
            "market_value": account_info.market_value,
            "total_equity": account_info.total_equity,
            "buying_power": account_info.buying_power,
            "maintenance_margin": account_info.maintenance_margin
        }

    @staticmethod
    def _account_from_cache(payload: Dict[str, Any]) -> AccountInfo:
        return AccountInfo(
            account_id=str(payload.get("account_id") or ""),
            currency=str(payload.get("currency") or "USD"),
            cash=float(payload.get("cash", 0) or 0),
            market_value=float(payload.get("market_value", 0) or 0),
            total_equity=float(payload.get("total_equity", 0) or 0),
            buying_power=float(payload.get("buying_power", 0) or 0),
            maintenance_margin=float(payload.get("maintenance_margin", 0) or 0)
        )

    def _load_cached_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        cached: Dict[str, Quote] = {}
        for symbol in symbols:
            payload = redis_client.get_hot_json(f"quote:{symbol}")
            if isinstance(payload, dict):
                cached[symbol] = self._quote_from_cache(symbol, payload)
        return cached

    def _load_cached_positions(self) -> List[Position]:
        payload = redis_client.get_hot_json(f"broker:{self.account_id}:positions")
        if not isinstance(payload, list):
            return []
        return [self._position_from_cache(item) for item in payload if isinstance(item, dict)]

    def _load_cached_account_info(self) -> Optional[AccountInfo]:
        payload = redis_client.get_hot_json(f"broker:{self.account_id}:account")
        if not isinstance(payload, dict):
            return None
        return self._account_from_cache(payload)
    
    def get_quote(self, symbols: List[str]) -> Dict[str, Quote]:
        """
        获取行情数据
        
        Args:
            symbols: 股票代码列表
            
        Returns:
            行情数据字典
        """
        if not symbols or not isinstance(symbols, list):
            logger.error("股票代码列表不能为空")
            return {}

        unique_symbols = list(dict.fromkeys([str(item or '').strip().upper() for item in symbols if str(item or '').strip()]))
        if not unique_symbols:
            return {}

        def fallback():
            cached = self._load_cached_quotes(unique_symbols)
            if cached:
                logger.warning("长桥行情已降级到缓存数据: %s", unique_symbols)
                self._increment_metric("quoteFallbackCount")
            return cached

        def fetch():
            self._ensure_connected()
            quote_context = self._ensure_quote_context()
            self._throttle_request()
            quotes = quote_context.quote(unique_symbols)

            result = {}
            for q in quotes:
                symbol = q.symbol
                last_price = _to_float(getattr(q, 'last_done', 0))
                prev_close = _to_float(getattr(q, 'prev_close', 0))
                open_price = _to_float(getattr(q, 'open', 0))
                high = _to_float(getattr(q, 'high', 0))
                low = _to_float(getattr(q, 'low', 0))
                volume = int(_to_float(getattr(q, 'volume', 0)))
                change = 0.0
                change_percent = 0.0
                if prev_close > 0:
                    change = last_price - prev_close
                    change_percent = (change / prev_close) * 100

                quote = Quote(
                    symbol=symbol,
                    last_price=last_price,
                    prev_close=prev_close,
                    open=open_price,
                    high=high,
                    low=low,
                    volume=volume,
                    timestamp=datetime.now(),
                    change=change,
                    change_percent=change_percent
                )
                result[symbol] = quote
                redis_client.set_hot(f"quote:{symbol}", self._quote_to_cache_payload(quote), expire=15)

            if result:
                kafka_bus.publish_market_quotes(
                    account_id=self.account_id,
                    quotes=[self._quote_to_cache_payload(item) for item in result.values()]
                )

            missing_symbols = [s for s in unique_symbols if s not in result]
            if missing_symbols:
                logger.warning("以下股票未获取到行情: %s", missing_symbols)
            return result

        try:
            return self._execute_with_resilience('quote', fetch, fallback=fallback)
        except Exception as e:
            logger.error(f"获取行情失败: {e}")
            self._log_connection('query', 'failed', f'get_quote: {e}')
            return fallback()
    
    def get_positions(self) -> List[Position]:
        """
        获取持仓列表
        
        Returns:
            持仓列表
        """
        def fallback():
            cached = self._load_cached_positions()
            if cached:
                logger.warning("长桥持仓已降级到缓存数据: account_id=%s", self.account_id)
            return cached

        def fetch():
            self._ensure_connected()
            self._throttle_request()
            response = self.trade_context.stock_positions()

            result = []
            symbols = []
            if hasattr(response, 'channels'):
                for channel in response.channels:
                    if hasattr(channel, 'positions'):
                        for pos in channel.positions:
                            symbols.append(getattr(pos, 'symbol', ''))

            quotes = {}
            if symbols:
                try:
                    quote_context = self._ensure_quote_context()
                    self._throttle_request()
                    quote_response = quote_context.quote(symbols)
                    for q in quote_response:
                        symbol = getattr(q, 'symbol', '')
                        last_done = getattr(q, 'last_done', None)
                        quotes[symbol] = _to_float(last_done)
                except Exception as e:
                    logger.warning(f"获取持仓实时行情失败: {e}")

            if hasattr(response, 'channels'):
                for channel in response.channels:
                    if hasattr(channel, 'positions'):
                        for pos in channel.positions:
                            symbol = getattr(pos, 'symbol', '')
                            quantity = int(_to_float(getattr(pos, 'quantity', 0)))
                            cost_price = _to_float(getattr(pos, 'cost_price', 0))
                            symbol_name = getattr(pos, 'symbol_name', symbol)
                            market_price = quotes.get(symbol, cost_price)
                            market_value = quantity * market_price
                            unrealized_pnl = (market_price - cost_price) * quantity

                            result.append(Position(
                                symbol=symbol,
                                quantity=quantity,
                                average_cost=cost_price,
                                market_price=market_price,
                                market_value=market_value,
                                unrealized_pnl=unrealized_pnl,
                                realized_pnl=0.0,
                                name=symbol_name
                            ))
            else:
                logger.warning(f"未知的持仓响应格式: {type(response)}")

            redis_client.set_hot(
                f"broker:{self.account_id}:positions",
                [self._position_to_cache_payload(item) for item in result],
                expire=20
            )
            return result

        try:
            return self._execute_with_resilience('positions', fetch, fallback=fallback)
        except Exception as e:
            logger.error(f"获取持仓失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._log_connection('query', 'failed', f'get_positions: {e}')
            return fallback()
    
    def get_account_info(self) -> AccountInfo:
        """
        获取账户信息
        
        Returns:
            账户信息
        """
        def fallback():
            cached = self._load_cached_account_info()
            if cached:
                logger.warning("长桥账户信息已降级到缓存数据: account_id=%s", self.account_id)
                return cached
            raise RuntimeError("当前没有可用的长桥账户缓存")

        def fetch():
            self._ensure_connected()
            self._throttle_request()
            logger.info(f"正在获取长桥账户余额, account_id={self.account_id}")
            acc_list = self.trade_context.account_balance()

            usd_cash = 0.0
            usd_available_cash = 0.0
            usd_frozen_cash = 0.0
            total_equity = 0.0
            maintenance_margin = 0.0

            for acc in acc_list:
                total_equity = max(total_equity, _to_float(getattr(acc, 'net_assets', 0)))
                maintenance_margin = max(maintenance_margin, _to_float(getattr(acc, 'maintenance_margin', 0)))
                cash_infos = getattr(acc, 'cash_infos', [])
                for cash_info in cash_infos:
                    if getattr(cash_info, 'currency', '') == 'USD':
                        usd_available_cash = _to_float(getattr(cash_info, 'available_cash', 0))
                        usd_frozen_cash = _to_float(getattr(cash_info, 'frozen_cash', 0))
                        usd_cash = usd_available_cash + usd_frozen_cash

            positions = self.get_positions()
            market_value = sum(p.market_value for p in positions)
            if total_equity <= 0:
                total_equity = usd_cash + market_value

            account_id = self.config.account_id if self.config and self.config.account_id else str(self.account_id)
            account_info = AccountInfo(
                account_id=account_id,
                currency='USD',
                cash=usd_cash,
                market_value=market_value,
                total_equity=total_equity,
                buying_power=usd_available_cash,
                maintenance_margin=maintenance_margin
            )
            redis_client.set_hot(
                f"broker:{self.account_id}:account",
                self._account_to_cache_payload(account_info),
                expire=20
            )
            return account_info

        try:
            return self._execute_with_resilience('account', fetch, fallback=fallback)
        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._log_connection('query', 'failed', f'get_account_info: {e}')
            return fallback()
    
    def place_order(self, symbol: str, action: str, quantity: int,
                   order_type: str = 'LIMIT', price: Optional[float] = None,
                   time_in_force: str = 'DAY') -> Dict[str, Any]:
        """
        下单
        
        Args:
            symbol: 股票代码
            action: 动作 (BUY/SELL)
            quantity: 数量
            order_type: 订单类型
            price: 价格
            time_in_force: 有效期
            
        Returns:
            订单结果
        """
        def submit():
            self._ensure_connected()
            self._throttle_request()
            side = OrderSide.Buy if action == 'BUY' else OrderSide.Sell
            lb_order_type = OrderType.MO if order_type == 'MARKET' else OrderType.Limit

            response = self.trade_context.submit_order(
                symbol=symbol,
                order_type=lb_order_type,
                side=side,
                submitted_quantity=quantity,
                submitted_price=price if order_type != 'MARKET' else None,
                time_in_force=TimeInForceType.Day
            )

            order_id = str(getattr(response, 'order_id', '') or '')
            status = _enum_name(
                getattr(response, 'status', None),
                default='SUBMITTED'
            )
            result = {
                'order_id': order_id,
                'status': status,
                'symbol': symbol,
                'action': action,
                'quantity': quantity,
                'price': price,
                'message': '订单提交成功'
            }
            log_trade(logger, symbol, action, quantity, price or 0, order_id=result['order_id'])
            self._log_connection('trade', 'success', f'place_order: {symbol} {action}')
            return result

        try:
            return self._execute_with_resilience('trade', submit)
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
        def submit():
            self._ensure_connected()
            self._throttle_request()
            self.trade_context.cancel_order(order_id)
            logger.info(f"订单已撤销: {order_id}")
            self._log_connection('trade', 'success', f'cancel_order: {order_id}')
            return True

        try:
            return bool(self._execute_with_resilience('trade', submit))
        except Exception as e:
            logger.error(f"撤单失败: {e}")
            self._log_connection('trade', 'failed', f'cancel_order: {e}')
            return False
    
    def get_orders(self, status: Optional[str] = None) -> List[Order]:
        """
        获取订单列表
        
        Args:
            status: 状态过滤
            
        Returns:
            订单列表
        """
        def fetch():
            self._ensure_connected()
            self._throttle_request()
            return self.trade_context.today_orders() or []

        try:
            orders = self._execute_with_resilience('orders', fetch, fallback=lambda: [])
            result = []
            for o in orders:
                side_text = str(getattr(o, 'side', '')).split('.')[-1].upper()
                action = 'BUY' if 'BUY' in side_text else 'SELL'
                order_type = str(getattr(o, 'order_type', '')).split('.')[-1].upper()
                status_text = str(getattr(o, 'status', '')).split('.')[-1]
                create_time = getattr(o, 'submitted_at', None) or getattr(o, 'updated_at', None) or datetime.now()
                order = Order(
                    order_id=getattr(o, 'order_id', ''),
                    symbol=getattr(o, 'symbol', ''),
                    action=action,
                    order_type=order_type or 'LIMIT',
                    quantity=int(_to_float(getattr(o, 'quantity', 0))),
                    filled_quantity=int(_to_float(getattr(o, 'executed_quantity', getattr(o, 'filled_quantity', 0)))),
                    price=_to_float(getattr(o, 'price', getattr(o, 'submitted_price', 0))),
                    status=status_text or 'Unknown',
                    create_time=create_time if isinstance(create_time, datetime) else datetime.now()
                )
                
                if status is None or str(order.status).upper() == str(status).upper():
                    result.append(order)
            
            return result
            
        except Exception as e:
            logger.error(f"获取订单列表失败: {e}")
            raise
    
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
            is_default: 是否为默认
            
        Returns:
            账户ID
        """
        db = DbUtil()
        
        try:
            if account_row_id:
                existing = db.fetch_one(
                    """
                    SELECT id, account_id
                    FROM broker_accounts
                    WHERE id = %s AND user_id = %s AND broker_type = 'longbridge' AND is_active = 1
                    LIMIT 1
                    """,
                    (account_row_id, user_id)
                )
                if not existing:
                    raise ValueError('券商账户不存在或不属于当前用户')

                account_value = str(config.get('account') or existing.get('account_id') or '').strip()

                sql = """
                UPDATE broker_accounts
                SET account_id = %s,
                    longbridge_app_key = '',
                    longbridge_app_secret = '',
                    longbridge_access_token = '',
                    is_default = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s
                """
                params = (
                    account_value,
                    1 if is_default else 0,
                    account_row_id,
                    user_id
                )
                db.execute(sql, params)
                logger.info("长桥证券配置已更新，账户ID: %s", account_row_id)
                return int(account_row_id)

            sql = """
            INSERT INTO broker_accounts
            (user_id, broker_type, broker_name, account_id, is_default, is_active)
            VALUES (%s, 'longbridge', '长桥证券', %s, %s, 1)
            """

            params = (
                user_id,
                config.get('account', ''),
                1 if is_default else 0
            )

            account_id = db.execute_insert(sql, params)
            logger.info("长桥证券配置已保存，账户ID: %s", account_id)
            return account_id
        except Exception as e:
            logger.error(f"保存长桥证券配置失败: {e}")
            raise
