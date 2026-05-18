"""
API限流和熔断模块
保护系统免受过载和故障扩散
"""
import time
import logging
from typing import Dict, Optional, Callable, Any
from functools import wraps
from enum import Enum
import threading

from utils.redis_client import redis_client

logger = logging.getLogger(__name__)


class RateLimitStrategy(Enum):
    """限流策略"""
    FIXED_WINDOW = "fixed_window"      # 固定窗口
    SLIDING_WINDOW = "sliding_window"  # 滑动窗口
    TOKEN_BUCKET = "token_bucket"      # 令牌桶


class RateLimiter:
    """限流器"""
    
    def __init__(
        self,
        key_prefix: str = "rate_limit",
        strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW
    ):
        self.key_prefix = key_prefix
        self.strategy = strategy
        self.local_cache: Dict[str, Dict] = {}
        self.lock = threading.Lock()
        self._last_fallback_log_at = 0.0

    def _log_local_fallback(self, strategy: str, error: Exception) -> None:
        """Redis 不可用时，限流退化到本地缓存并节流日志。"""
        now = time.time()
        if now - self._last_fallback_log_at < 60:
            return
        self._last_fallback_log_at = now
        logger.warning(f"{strategy}限流降级到本地缓存: {error}")

    def _local_sliding_window_check(
        self,
        key: str,
        limit: int,
        window: int
    ) -> tuple[bool, Dict]:
        now = time.time()
        window_start = now - window
        cache_key = f"sliding:{key}"

        with self.lock:
            timestamps = self.local_cache.get(cache_key, {}).get("timestamps", [])
            timestamps = [ts for ts in timestamps if ts > window_start]
            current_count = len(timestamps)
            timestamps.append(now)
            self.local_cache[cache_key] = {"timestamps": timestamps}

        remaining = max(0, limit - current_count - 1)
        return current_count < limit, {
            "limit": limit,
            "remaining": remaining,
            "reset_time": int(now + window),
            "current": current_count + 1
        }
    
    def is_allowed(
        self,
        key: str,
        limit: int = 100,
        window: int = 60
    ) -> tuple[bool, Dict[str, Any]]:
        """
        检查是否允许请求
        
        Args:
            key: 限流键（如IP、用户ID）
            limit: 窗口期内最大请求数
            window: 窗口大小（秒）
        
        Returns:
            (是否允许, 限流信息)
        """
        full_key = f"{self.key_prefix}:{key}"
        
        if self.strategy == RateLimitStrategy.FIXED_WINDOW:
            return self._fixed_window_check(full_key, limit, window)
        elif self.strategy == RateLimitStrategy.SLIDING_WINDOW:
            return self._sliding_window_check(full_key, limit, window)
        elif self.strategy == RateLimitStrategy.TOKEN_BUCKET:
            return self._token_bucket_check(full_key, limit, window)
        
        return True, {}
    
    def _fixed_window_check(
        self,
        key: str,
        limit: int,
        window: int
    ) -> tuple[bool, Dict]:
        """固定窗口限流"""
        try:
            current_window = int(time.time()) // window
            window_key = f"{key}:{current_window}"
            
            # 使用Redis原子递增
            current_count = redis_client.increment(window_key, 1)
            
            # 设置过期时间
            if current_count == 1:
                redis_client.expire(window_key, window)
            
            remaining = max(0, limit - current_count)
            reset_time = (current_window + 1) * window
            
            return current_count <= limit, {
                "limit": limit,
                "remaining": remaining,
                "reset_time": reset_time,
                "current": current_count
            }
            
        except Exception as e:
            logger.error(f"限流检查失败: {e}")
            # 限流器故障时允许请求
            return True, {}
    
    def _sliding_window_check(
        self,
        key: str,
        limit: int,
        window: int
    ) -> tuple[bool, Dict]:
        """滑动窗口限流（简化版）"""
        try:
            now = time.time()
            window_start = now - window
            
            # 使用Redis Sorted Set
            # 移除窗口外的请求记录
            redis_client.client.zremrangebyscore(key, 0, window_start)
            
            # 获取当前窗口内的请求数
            current_count = redis_client.client.zcard(key)
            
            # 添加当前请求
            redis_client.client.zadd(key, {str(now): now})
            redis_client.expire(key, window)
            
            remaining = max(0, limit - current_count - 1)
            
            return current_count < limit, {
                "limit": limit,
                "remaining": remaining,
                "reset_time": int(now + window),
                "current": current_count + 1
            }
            
        except Exception as e:
            self._log_local_fallback("滑动窗口", e)
            return self._local_sliding_window_check(key, limit, window)
    
    def _token_bucket_check(
        self,
        key: str,
        limit: int,
        window: int
    ) -> tuple[bool, Dict]:
        """令牌桶限流"""
        try:
            bucket_key = f"{key}:bucket"
            last_update_key = f"{key}:last_update"
            
            # 获取当前令牌数和上次更新时间
            tokens = redis_client.get(bucket_key)
            last_update = redis_client.get(last_update_key)
            
            now = time.time()
            tokens = float(tokens) if tokens else limit
            last_update = float(last_update) if last_update else now
            
            # 计算新增令牌
            rate = limit / window  # 每秒产生的令牌数
            elapsed = now - last_update
            tokens = min(limit, tokens + elapsed * rate)
            
            # 判断是否允许请求
            if tokens >= 1:
                tokens -= 1
                allowed = True
            else:
                allowed = False
            
            # 更新Redis
            redis_client.set(bucket_key, tokens, expire=window)
            redis_client.set(last_update_key, now, expire=window)
            
            return allowed, {
                "limit": limit,
                "remaining": int(tokens),
                "reset_time": int(now + (1 - tokens) / rate) if tokens < 1 else int(now)
            }
            
        except Exception as e:
            logger.error(f"令牌桶限流检查失败: {e}")
            return True, {}


class CircuitBreaker:
    """熔断器"""
    
    class State(Enum):
        CLOSED = "closed"      # 关闭状态（正常）
        OPEN = "open"          # 打开状态（熔断）
        HALF_OPEN = "half_open"  # 半开状态（试探）
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.state = self.State.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.lock = threading.Lock()
    
    def can_execute(self) -> bool:
        """检查是否可以执行"""
        with self.lock:
            if self.state == self.State.CLOSED:
                return True
            
            elif self.state == self.State.OPEN:
                # 检查是否到达恢复时间
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = self.State.HALF_OPEN
                    self.success_count = 0
                    logger.info("熔断器进入半开状态")
                    return True
                return False
            
            elif self.state == self.State.HALF_OPEN:
                return self.success_count < self.half_open_max_calls
            
            return True
    
    def record_success(self):
        """记录成功"""
        with self.lock:
            if self.state == self.State.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.half_open_max_calls:
                    self.state = self.State.CLOSED
                    self.failure_count = 0
                    logger.info("熔断器关闭（恢复正常）")
            else:
                self.failure_count = 0
    
    def record_failure(self):
        """记录失败"""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == self.State.HALF_OPEN:
                self.state = self.State.OPEN
                logger.warning("熔断器打开（半开状态失败）")
            elif self.failure_count >= self.failure_threshold:
                self.state = self.State.OPEN
                logger.warning(f"熔断器打开（连续失败{self.failure_count}次）")
    
    def get_state(self) -> str:
        """获取当前状态"""
        return self.state.value


# 全局限流器实例
rate_limiter = RateLimiter()

# 熔断器存储
circuit_breakers: Dict[str, CircuitBreaker] = {}


def rate_limit(
    key_func: Optional[Callable] = None,
    limit: int = 100,
    window: int = 60,
    strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW
):
    """
    限流装饰器
    
    使用示例：
        @rate_limit(limit=10, window=60)
        def my_api():
            return "success"
        
        @rate_limit(key_func=lambda: request.remote_addr, limit=100)
        def api_by_ip():
            return "success"
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            # 生成限流键
            if key_func:
                key = key_func()
            else:
                key = f.__name__
            
            # 检查限流
            allowed, info = rate_limiter.is_allowed(key, limit, window)
            
            if not allowed:
                from flask import jsonify
                # 直接返回 (payload, status_code) 元组，保持兼容测试
                payload = {
                    "error": "请求过于频繁，请稍后再试",
                    "retry_after": info.get("reset_time", 60)
                }
                # 可选地返回自定义头信息（Flask 会接受三元组）
                headers = {
                    'X-RateLimit-Limit': str(info.get('limit', limit)),
                    'X-RateLimit-Remaining': str(info.get('remaining', 0)),
                    'X-RateLimit-Reset': str(info.get('reset_time', 0))
                }
                return jsonify(payload), 429, headers
            
            return f(*args, **kwargs)
        
        return wrapper
    return decorator


def circuit_breaker_protect(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: int = 60
):
    """
    熔断保护装饰器
    
    使用示例：
        @circuit_breaker_protect(name="external_api", failure_threshold=3)
        def call_external_api():
            return requests.get("https://api.example.com")
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            # 获取或创建熔断器
            if name not in circuit_breakers:
                circuit_breakers[name] = CircuitBreaker(
                    failure_threshold=failure_threshold,
                    recovery_timeout=recovery_timeout
                )
            
            breaker = circuit_breakers[name]
            
            # 检查是否可以执行
            if not breaker.can_execute():
                from flask import jsonify
                return jsonify({
                    "error": "服务暂时不可用，请稍后再试",
                    "circuit_breaker": breaker.get_state()
                }), 503
            
            try:
                result = f(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                raise e
        
        return wrapper
    return decorator
