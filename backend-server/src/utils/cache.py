"""
缓存模块
基于Redis实现多级缓存
"""
import json
import hashlib
import pickle
from typing import Optional, Any, Callable
from functools import wraps
from datetime import datetime, timedelta
import logging

from utils.redis_client import redis_client

logger = logging.getLogger(__name__)


class Cache:
    """缓存管理器"""
    
    def __init__(self, prefix: str = "cache", default_expire: int = 300):
        self.prefix = prefix
        self.default_expire = default_expire
    
    def _make_key(self, key: str) -> str:
        """生成完整key"""
        return f"{self.prefix}:{key}"
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        full_key = self._make_key(key)
        value = redis_client.get_json(full_key)
        if value is not None:
            logger.debug(f"缓存命中: {key}")
        return value
    
    def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """设置缓存"""
        full_key = self._make_key(key)
        expire = expire or self.default_expire
        result = redis_client.set(full_key, value, expire=expire)
        if result:
            logger.debug(f"缓存设置: {key}, 过期时间: {expire}s")
        return result
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        full_key = self._make_key(key)
        return redis_client.delete(full_key)
    
    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        full_key = self._make_key(key)
        return redis_client.exists(full_key)
    
    def get_or_set(self, key: str, getter: Callable[[], Any], 
                   expire: Optional[int] = None) -> Any:
        """
        获取或设置缓存
        :param key: 缓存key
        :param getter: 获取数据的函数
        :param expire: 过期时间
        """
        value = self.get(key)
        if value is None:
            value = getter()
            if value is not None:
                self.set(key, value, expire)
        return value
    
    def increment(self, key: str, amount: int = 1) -> int:
        """原子递增"""
        full_key = self._make_key(key)
        try:
            return redis_client.client.incrby(full_key, amount)
        except Exception as e:
            logger.error(f"缓存递增失败: {e}")
            return 0
    
    def decrement(self, key: str, amount: int = 1) -> int:
        """原子递减"""
        full_key = self._make_key(key)
        try:
            return redis_client.client.decrby(full_key, amount)
        except Exception as e:
            logger.error(f"缓存递减失败: {e}")
            return 0
    
    def clear_pattern(self, pattern: str) -> int:
        """清除匹配pattern的缓存"""
        try:
            full_pattern = self._make_key(pattern)
            keys = redis_client.client.keys(full_pattern)
            if keys:
                return redis_client.client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"清除缓存失败: {e}")
            return 0


# 全局缓存实例
cache = Cache()


def cached(prefix: str = "cache", expire: int = 300, 
           key_func: Optional[Callable] = None):
    """
    缓存装饰器
    使用示例：
        @cached(prefix="stock", expire=60)
        def get_stock_price(symbol: str):
            return fetch_from_api(symbol)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # 默认使用函数名和参数生成key
                key_parts = [func.__name__]
                key_parts.extend(str(arg) for arg in args)
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = hashlib.md5(
                    ":".join(key_parts).encode()
                ).hexdigest()
            
            full_key = f"{prefix}:{cache_key}"
            
            # 尝试从缓存获取
            result = redis_client.get_json(full_key)
            if result is not None:
                logger.debug(f"缓存命中: {func.__name__}")
                return result
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 缓存结果
            if result is not None:
                redis_client.set(full_key, result, expire=expire)
                logger.debug(f"缓存设置: {func.__name__}, 过期: {expire}s")
            
            return result
        
        # 添加清除缓存的方法
        def clear_cache(*args, **kwargs):
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                key_parts = [func.__name__]
                key_parts.extend(str(arg) for arg in args)
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = hashlib.md5(
                    ":".join(key_parts).encode()
                ).hexdigest()
            
            full_key = f"{prefix}:{cache_key}"
            redis_client.delete(full_key)
        
        wrapper.clear_cache = clear_cache
        return wrapper
    return decorator


def clear_cache_pattern(pattern: str):
    """清除匹配pattern的缓存"""
    return cache.clear_pattern(pattern)


# 业务相关缓存函数
class StockCache:
    """股票相关缓存"""
    
    @staticmethod
    def get_price_key(symbol: str) -> str:
        return f"stock:price:{symbol}"
    
    @staticmethod
    def cache_price(symbol: str, price: float, expire: int = 60):
        """缓存股价"""
        key = StockCache.get_price_key(symbol)
        redis_client.set(key, {"price": price, "time": datetime.now().isoformat()}, expire)
    
    @staticmethod
    def get_price(symbol: str) -> Optional[dict]:
        """获取缓存的股价"""
        key = StockCache.get_price_key(symbol)
        return redis_client.get_json(key)
    
    @staticmethod
    def get_indicator_key(symbol: str) -> str:
        return f"stock:indicator:{symbol}"
    
    @staticmethod
    def cache_indicators(symbol: str, indicators: dict, expire: int = 300):
        """缓存技术指标"""
        key = StockCache.get_indicator_key(symbol)
        redis_client.set(key, indicators, expire)
    
    @staticmethod
    def get_indicators(symbol: str) -> Optional[dict]:
        """获取缓存的技术指标"""
        key = StockCache.get_indicator_key(symbol)
        return redis_client.get_json(key)


class AICache:
    """AI分析相关缓存"""
    
    @staticmethod
    def get_analysis_key(symbol: str, model: str = "combined") -> str:
        return f"ai:analysis:{model}:{symbol}"
    
    @staticmethod
    def cache_analysis(symbol: str, result: dict, model: str = "combined", expire: int = 1800):
        """缓存AI分析结果"""
        key = AICache.get_analysis_key(symbol, model)
        redis_client.set(key, result, expire)
    
    @staticmethod
    def get_analysis(symbol: str, model: str = "combined") -> Optional[dict]:
        """获取缓存的AI分析结果"""
        key = AICache.get_analysis_key(symbol, model)
        return redis_client.get_json(key)
    
    @staticmethod
    def clear_analysis(symbol: str):
        """清除股票的AI分析缓存"""
        pattern = f"ai:analysis:*:{symbol}"
        cache.clear_pattern(pattern)


class AccountCache:
    """账户相关缓存"""
    
    @staticmethod
    def get_account_key(account_id: str = "default") -> str:
        return f"account:info:{account_id}"
    
    @staticmethod
    def cache_account_info(info: dict, account_id: str = "default", expire: int = 60):
        """缓存账户信息"""
        key = AccountCache.get_account_key(account_id)
        redis_client.set(key, info, expire)
    
    @staticmethod
    def get_account_info(account_id: str = "default") -> Optional[dict]:
        """获取缓存的账户信息"""
        key = AccountCache.get_account_key(account_id)
        return redis_client.get_json(key)
