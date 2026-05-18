"""
Redis客户端封装
提供连接池和常用操作
"""
import redis
import json
import pickle
from typing import Optional, Any, Union
from contextlib import contextmanager
import logging
import time
try:
    from redis.cluster import RedisCluster
except Exception:  # pragma: no cover - 兼容未安装 cluster 依赖的环境
    RedisCluster = None

from config.settings import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis客户端"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._pool = None
            cls._instance._client = None
        return cls._instance
    
    def __init__(self):
        # 初始化连接池
        if self._pool is None:
            self._init_pool()
        # 本地 fallback 用于没有 Redis 时
        if not hasattr(self, '_fallback'):
            self._fallback = {}
        if not hasattr(self, '_fallback_expiry'):
            self._fallback_expiry = {}
        if not hasattr(self, '_last_error_logged_at'):
            self._last_error_logged_at = {}
        # 提供 increment 方法，若 Redis 不可用则回退本地计数
        if not hasattr(self, 'increment'):
            def increment(key: str, amount: int = 1) -> int:
                """在 Redis 不可用时使用本地计数递增。"""
                try:
                    return self.client.incr(key, amount)
                except Exception as e:
                    self._log_unavailable('increment', e)
                    current = int(self._get_fallback_value(key, 0) or 0)
                    current += amount
                    self._store_fallback_value(key, current)
                    return current
            self.increment = increment

    def _log_unavailable(self, operation: str, error: Exception) -> None:
        """对 Redis 不可用错误做节流日志，避免刷屏。"""
        now = time.time()
        last_logged_at = self._last_error_logged_at.get(operation, 0)
        if now - last_logged_at < 60:
            return
        self._last_error_logged_at[operation] = now
        logger.warning(f"Redis {operation} 不可用，已降级到本地 fallback: {error}")

    def _cleanup_fallback(self, key: str) -> None:
        expire_at = self._fallback_expiry.get(key)
        if expire_at and expire_at <= time.time():
            self._fallback.pop(key, None)
            self._fallback_expiry.pop(key, None)

    def _store_fallback_value(self, key: str, value: Any, expire: Optional[int] = None) -> None:
        self._fallback[key] = value
        if expire:
            self._fallback_expiry[key] = time.time() + max(int(expire), 1)
        else:
            self._fallback_expiry.pop(key, None)

    def _get_fallback_value(self, key: str, default: Any = None) -> Any:
        self._cleanup_fallback(key)
        return self._fallback.get(key, default)
    
    def _init_pool(self):
        """初始化连接池"""
        try:
            config = settings.get_redis_config()
            if config.get('cluster_enabled'):
                if RedisCluster is None:
                    raise RuntimeError("当前环境未安装 RedisCluster 依赖")
                startup_nodes = []
                for node in str(config.get('cluster_nodes') or '').split(','):
                    node = node.strip()
                    if not node:
                        continue
                    host, _, port = node.partition(':')
                    startup_nodes.append({"host": host, "port": int(port or 6379)})
                if not startup_nodes:
                    startup_nodes.append({"host": config['host'], "port": config['port']})
                self._client = RedisCluster(
                    startup_nodes=startup_nodes,
                    password=config['password'] or None,
                    decode_responses=True
                )
                self._pool = None
                logger.info("Redis Cluster 初始化成功")
                return

            self._pool = redis.ConnectionPool(
                host=config['host'],
                port=config['port'],
                password=config['password'] or None,
                db=config['db'],
                decode_responses=True,
                max_connections=20
            )
            self._client = redis.Redis(connection_pool=self._pool)
            logger.info("Redis连接池初始化成功")
        except Exception as e:
            logger.error(f"Redis连接池初始化失败: {e}")
            raise
    
    @property
    def client(self) -> redis.Redis:
        """获取Redis客户端"""
        if self._client is None:
            self._init_pool()
        return self._client
    
    def ping(self) -> bool:
        """检查连接"""
        try:
            return self.client.ping()
        except Exception as e:
            self._log_unavailable('ping', e)
            return False
    
    # String操作
    def set(self, key: str, value: Union[str, int, float], expire: Optional[int] = None) -> bool:
        """设置值"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            return self.client.set(key, value, ex=expire)
        except Exception as e:
            self._log_unavailable('set', e)
            self._store_fallback_value(key, value, expire)
            return True

    @staticmethod
    def _scoped_key(scope: str, key: str) -> str:
        return f"{scope}:{key}"

    def get(self, key: str) -> Optional[str]:
        """获取值"""
        try:
            value = self.client.get(key)
            return value.decode('utf-8') if isinstance(value, bytes) else value
        except Exception as e:
            self._log_unavailable('get', e)
            value = self._get_fallback_value(key)
            return value.decode('utf-8') if isinstance(value, bytes) else value
    
    def get_json(self, key: str) -> Optional[Any]:
        """获取JSON值"""
        value = self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None

    def set_hot(self, key: str, value: Union[str, int, float, dict, list], expire: Optional[int] = 30) -> bool:
        """写入热数据缓存。"""
        return self.set(self._scoped_key('hot', key), value, expire=expire)

    def get_hot_json(self, key: str) -> Optional[Any]:
        """读取热数据缓存。"""
        return self.get_json(self._scoped_key('hot', key))

    def set_cold(self, key: str, value: Union[str, int, float, dict, list], expire: Optional[int] = 3600) -> bool:
        """写入冷数据缓存。"""
        return self.set(self._scoped_key('cold', key), value, expire=expire)

    def get_cold_json(self, key: str) -> Optional[Any]:
        """读取冷数据缓存。"""
        return self.get_json(self._scoped_key('cold', key))
    
    def delete(self, key: str) -> bool:
        """删除键"""
        try:
            return self.client.delete(key) > 0
        except Exception as e:
            self._log_unavailable('delete', e)
            existed = key in self._fallback
            self._fallback.pop(key, None)
            self._fallback_expiry.pop(key, None)
            return existed
    
    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        try:
            return self.client.exists(key) > 0
        except Exception as e:
            self._log_unavailable('exists', e)
            self._cleanup_fallback(key)
            return key in self._fallback
    
    def expire(self, key: str, seconds: int) -> bool:
        """设置过期时间"""
        try:
            return self.client.expire(key, seconds)
        except Exception as e:
            self._log_unavailable('expire', e)
            if key not in self._fallback:
                return False
            self._fallback_expiry[key] = time.time() + max(int(seconds), 1)
            return True
    
    # Hash操作
    def hset(self, key: str, field: str, value: Any) -> bool:
        """设置hash字段"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            return self.client.hset(key, field, value)
        except Exception as e:
            logger.error(f"Redis hset失败: {e}")
            return False
    
    def hget(self, key: str, field: str) -> Optional[str]:
        """获取hash字段"""
        try:
            value = self.client.hget(key, field)
            return value.decode('utf-8') if isinstance(value, bytes) else value
        except Exception as e:
            logger.error(f"Redis hget失败: {e}")
            return None
    
    def hgetall(self, key: str) -> dict:
        """获取所有hash字段"""
        try:
            result = self.client.hgetall(key)
            return {k.decode('utf-8') if isinstance(k, bytes) else k: 
                    v.decode('utf-8') if isinstance(v, bytes) else v 
                    for k, v in result.items()}
        except Exception as e:
            logger.error(f"Redis hgetall失败: {e}")
            return {}
    
    # List操作
    def lpush(self, key: str, value: Any) -> bool:
        """左侧推入列表"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            return self.client.lpush(key, value) > 0
        except Exception as e:
            logger.error(f"Redis lpush失败: {e}")
            return False
    
    def rpop(self, key: str) -> Optional[str]:
        """右侧弹出列表"""
        try:
            value = self.client.rpop(key)
            return value.decode('utf-8') if isinstance(value, bytes) else value
        except Exception as e:
            logger.error(f"Redis rpop失败: {e}")
            return None
    
    def llen(self, key: str) -> int:
        """获取列表长度"""
        try:
            return self.client.llen(key)
        except Exception as e:
            logger.error(f"Redis llen失败: {e}")
            return 0
    
    # Set操作
    def sadd(self, key: str, member: str) -> bool:
        """添加集合成员"""
        try:
            return self.client.sadd(key, member) > 0
        except Exception as e:
            logger.error(f"Redis sadd失败: {e}")
            return False
    
    def sismember(self, key: str, member: str) -> bool:
        """检查集合成员"""
        try:
            return self.client.sismember(key, member)
        except Exception as e:
            logger.error(f"Redis sismember失败: {e}")
            return False
    
    # 发布订阅
    def publish(self, channel: str, message: Any) -> bool:
        """发布消息"""
        try:
            if isinstance(message, (dict, list)):
                message = json.dumps(message, ensure_ascii=False)
            self.client.publish(channel, message)
            return True
        except Exception as e:
            logger.error(f"Redis publish失败: {e}")
            return False
    
    def close(self):
        """关闭连接"""
        if self._pool:
            self._pool.disconnect()
            logger.info("Redis连接池已关闭")


# 全局Redis客户端实例
redis_client = RedisClient()


@contextmanager
def redis_lock(lock_key: str, expire: int = 30):
    """
    Redis分布式锁上下文管理器
    使用示例：
        with redis_lock("my_lock"):
            # 执行需要加锁的操作
            pass
    """
    import uuid
    import time
    
    identifier = str(uuid.uuid4())
    lock_acquired = False
    
    try:
        # 尝试获取锁
        while not lock_acquired:
            lock_acquired = redis_client.client.set(
                lock_key, identifier, nx=True, ex=expire
            )
            if not lock_acquired:
                time.sleep(0.1)
        
        yield identifier
        
    finally:
        # 释放锁（只有锁的持有者才能释放）
        if lock_acquired:
            current_value = redis_client.client.get(lock_key)
            if current_value and current_value.decode('utf-8') == identifier:
                redis_client.client.delete(lock_key)
