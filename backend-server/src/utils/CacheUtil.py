"""
缓存工具模块
提供内存缓存和Redis缓存支持
"""

import hashlib
import json
import time
from collections.abc import Callable
from functools import wraps
from typing import Any


class MemoryCache:
    """内存缓存"""

    def __init__(self, default_ttl: int = 300):
        """
        初始化内存缓存

        Args:
            default_ttl: 默认过期时间（秒）
        """
        self._cache: dict[str, dict[str, Any]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        """
        获取缓存值

        Args:
            key: 缓存键

        Returns:
            缓存值或None
        """
        if key not in self._cache:
            return None

        item = self._cache[key]

        # 检查是否过期
        if item["expire_at"] < time.time():
            del self._cache[key]
            return None

        return item["value"]

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None使用默认值
        """
        expire_at = time.time() + (ttl if ttl is not None else self._default_ttl)
        self._cache[key] = {"value": value, "expire_at": expire_at, "created_at": time.time()}

    def delete(self, key: str) -> bool:
        """
        删除缓存

        Args:
            key: 缓存键

        Returns:
            是否成功删除
        """
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()

    def keys(self, pattern: str | None = None) -> list:
        """
        获取缓存键列表

        Args:
            pattern: 匹配模式（简单字符串匹配）

        Returns:
            键列表
        """
        if pattern is None:
            return list(self._cache.keys())

        return [k for k in self._cache.keys() if pattern in k]

    def cleanup(self) -> int:
        """
        清理过期缓存

        Returns:
            清理的条目数
        """
        now = time.time()
        expired_keys = [k for k, v in self._cache.items() if v["expire_at"] < now]

        for key in expired_keys:
            del self._cache[key]

        return len(expired_keys)

    def get_stats(self) -> dict[str, Any]:
        """
        获取缓存统计

        Returns:
            统计信息
        """
        total = len(self._cache)
        expired = sum(1 for v in self._cache.values() if v["expire_at"] < time.time())

        return {"total_keys": total, "expired_keys": expired, "valid_keys": total - expired}


class StockDataCache:
    """股票数据专用缓存"""

    def __init__(self):
        """初始化股票数据缓存"""
        self._price_cache = MemoryCache(default_ttl=60)  # 价格缓存60秒
        self._indicator_cache = MemoryCache(default_ttl=300)  # 指标缓存5分钟
        self._scan_result_cache = MemoryCache(default_ttl=600)  # 扫描结果缓存10分钟
        self._kline_cache = MemoryCache(default_ttl=3600)  # K线缓存1小时

    def get_price(self, symbol: str) -> float | None:
        """获取缓存价格"""
        return self._price_cache.get(f"price:{symbol}")

    def set_price(self, symbol: str, price: float) -> None:
        """设置缓存价格"""
        self._price_cache.set(f"price:{symbol}", price)

    def get_indicator(self, symbol: str, indicator_type: str) -> Any | None:
        """获取缓存指标"""
        return self._indicator_cache.get(f"indicator:{symbol}:{indicator_type}")

    def set_indicator(self, symbol: str, indicator_type: str, value: Any, ttl: int = 300) -> None:
        """设置缓存指标"""
        self._indicator_cache.set(f"indicator:{symbol}:{indicator_type}", value, ttl)

    def get_scan_result(self, cache_key: str) -> Any | None:
        """获取缓存扫描结果"""
        return self._scan_result_cache.get(f"scan:{cache_key}")

    def set_scan_result(self, cache_key: str, result: Any, ttl: int = 600) -> None:
        """设置缓存扫描结果"""
        self._scan_result_cache.set(f"scan:{cache_key}", result, ttl)

    def get_kline(self, symbol: str, period: str) -> list | None:
        """获取缓存K线数据"""
        return self._kline_cache.get(f"kline:{symbol}:{period}")

    def set_kline(self, symbol: str, period: str, data: list) -> None:
        """设置缓存K线数据"""
        self._kline_cache.set(f"kline:{symbol}:{period}", data)

    def invalidate_symbol(self, symbol: str) -> None:
        """使某只股票的所有缓存失效"""
        # 清理价格缓存
        self._price_cache.delete(f"price:{symbol}")

        # 清理指标缓存
        for key in self._indicator_cache.keys(f":{symbol}:"):
            self._indicator_cache.delete(key)

        # 清理K线缓存
        for key in self._kline_cache.keys(f":{symbol}:"):
            self._kline_cache.delete(key)

    def clear_all(self) -> None:
        """清空所有缓存"""
        self._price_cache.clear()
        self._indicator_cache.clear()
        self._scan_result_cache.clear()
        self._kline_cache.clear()

    def get_stats(self) -> dict[str, Any]:
        """获取缓存统计"""
        return {
            "price_cache": self._price_cache.get_stats(),
            "indicator_cache": self._indicator_cache.get_stats(),
            "scan_result_cache": self._scan_result_cache.get_stats(),
            "kline_cache": self._kline_cache.get_stats(),
        }


# 全局缓存实例
_memory_cache = MemoryCache()
_stock_cache = StockDataCache()


def get_memory_cache() -> MemoryCache:
    """获取全局内存缓存"""
    return _memory_cache


def get_stock_cache() -> StockDataCache:
    """获取股票数据缓存"""
    return _stock_cache


def cached(ttl: int = 300, key_prefix: str = ""):
    """
    缓存装饰器

    Args:
        ttl: 缓存过期时间（秒）
        key_prefix: 缓存键前缀

    Returns:
        装饰器函数
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix}:{func.__name__}:"
            cache_key += hashlib.md5(json.dumps({"args": args, "kwargs": kwargs}, default=str).encode()).hexdigest()

            # 尝试从缓存获取
            cached_value = _memory_cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # 执行函数
            result = func(*args, **kwargs)

            # 存入缓存
            _memory_cache.set(cache_key, result, ttl)

            return result

        return wrapper

    return decorator


def generate_cache_key(*args, **kwargs) -> str:
    """
    生成缓存键

    Args:
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        缓存键字符串
    """
    key_data = {"args": args, "kwargs": kwargs}
    return hashlib.md5(json.dumps(key_data, default=str, sort_keys=True).encode()).hexdigest()


class BatchProcessor:
    """批量处理器"""

    def __init__(self, batch_size: int = 100, max_workers: int = 4):
        """
        初始化批量处理器

        Args:
            batch_size: 批处理大小
            max_workers: 最大并发数
        """
        self.batch_size = batch_size
        self.max_workers = max_workers

    def process(self, items: list, process_func: Callable, *args, **kwargs) -> list:
        """
        批量处理

        Args:
            items: 待处理项列表
            process_func: 处理函数
            *args, **kwargs: 传递给处理函数的参数

        Returns:
            处理结果列表
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = []

        # 分批处理
        for i in range(0, len(items), self.batch_size):
            batch = items[i : i + self.batch_size]

            # 使用线程池并发处理
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(process_func, item, *args, **kwargs): item for item in batch}

                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        results.append({"item": item, "error": str(e), "success": False})

        return results

    def process_with_progress(
        self, items: list, process_func: Callable, progress_callback: Callable | None = None, *args, **kwargs
    ) -> list:
        """
        带进度回调的批量处理

        Args:
            items: 待处理项列表
            process_func: 处理函数
            progress_callback: 进度回调函数(current, total)
            *args, **kwargs: 传递给处理函数的参数

        Returns:
            处理结果列表
        """
        results = []
        total = len(items)
        processed = 0

        for i in range(0, total, self.batch_size):
            batch = items[i : i + self.batch_size]
            batch_results = self.process(batch, process_func, *args, **kwargs)
            results.extend(batch_results)

            processed += len(batch)

            if progress_callback:
                progress_callback(processed, total)

        return results
