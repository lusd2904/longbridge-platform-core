"""
数据库工具类 - 使用连接池和上下文管理器优化
"""
import pymysql
from pymysql.cursors import DictCursor
from pymysql.connections import Connection
from typing import Optional, Tuple, Any, Dict, List, Generator
from contextlib import contextmanager
import logging
import sys
import os
import threading

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.settings import settings

# 配置日志
logger = logging.getLogger(__name__)


class DatabasePool:
    """数据库连接池（简单实现）"""
    
    def __init__(self, config: Dict[str, Any], pool_size: int = 5, label: str = "write"):
        self.pool_size = pool_size
        self.config = dict(config)
        self.label = label
        self._pool: List[Connection] = []
        self._max_overflow = 10
        self._borrowed_count = 0
        self._lock = threading.Lock()
        
    def _create_connection(self) -> Connection:
        """创建新连接"""
        return pymysql.connect(**self.config)
    
    def get_connection(self) -> Connection:
        """获取连接"""
        with self._lock:
            while self._pool:
                conn = self._pool.pop()
                if conn.open:
                    self._borrowed_count += 1
                    return conn

            if self._borrowed_count >= (self.pool_size + self._max_overflow):
                raise Exception("连接池已满")

            self._borrowed_count += 1

        try:
            return self._create_connection()
        except Exception:
            with self._lock:
                self._borrowed_count = max(0, self._borrowed_count - 1)
            raise
    
    def release_connection(self, conn: Connection) -> None:
        """释放连接回池"""
        with self._lock:
            self._borrowed_count = max(0, self._borrowed_count - 1)
            if conn.open and len(self._pool) < self.pool_size:
                self._pool.append(conn)
                return

        if conn.open:
            try:
                conn.close()
            except Exception:
                logger.warning("关闭数据库连接失败", exc_info=True)
    
    def close_all(self) -> None:
        """关闭所有连接"""
        with self._lock:
            pool = list(self._pool)
            self._pool.clear()
            self._borrowed_count = 0

        for conn in pool:
            conn.close()


# 全局连接池实例
_pool_instances: Dict[str, DatabasePool] = {}


def get_pool(read_only: bool = False) -> DatabasePool:
    """获取连接池实例，读操作可走读库。"""
    label = "read" if read_only and settings.is_read_db_enabled() else "write"
    pool = _pool_instances.get(label)
    if pool is None:
        config = settings.get_db_read_config() if label == "read" else settings.get_db_config()
        pool = DatabasePool(config=config, pool_size=5, label=label)
        _pool_instances[label] = pool
    return pool


@contextmanager
def get_db_connection(read_only: bool = False) -> Generator[Connection, None, None]:
    """
    数据库连接上下文管理器
    使用示例：
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
    """
    conn = None
    pool: Optional[DatabasePool] = None
    try:
        try:
            pool = get_pool(read_only=read_only)
            conn = pool.get_connection()
        except Exception:
            if not read_only:
                raise
            logger.warning("读库连接失败，自动回退主库", exc_info=True)
            pool = get_pool(read_only=False)
            conn = pool.get_connection()
        yield conn
        if conn:
            conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"数据库操作失败: {e}")
        raise
    finally:
        if conn and pool:
            pool.release_connection(conn)


@contextmanager
def get_db_cursor(dict_cursor: bool = False, read_only: bool = False) -> Generator[Any, None, None]:
    """
    数据库游标上下文管理器
    使用示例：
        with get_db_cursor() as cursor:
            cursor.execute(sql)
            result = cursor.fetchall()
    """
    cursor_class = DictCursor if dict_cursor else None
    with get_db_connection(read_only=read_only) as conn:
        with conn.cursor(cursor_class) as cursor:
            yield cursor


class DbUtil:
    """数据库工具类"""
    
    # 保持向后兼容
    URL_CONFIG = settings.get_db_config()

    @staticmethod
    def add_web_log(content: str) -> None:
        """添加系统日志到system_logs表"""
        try:
            with get_db_cursor() as cursor:
                sql = "INSERT INTO system_logs (log_content) VALUES (%s)"
                cursor.execute(sql, (content,))
        except Exception as e:
            logger.error(f"添加系统日志失败: {e}")
            raise

    @staticmethod
    def add_scan_log(log_time: str, content: str) -> None:
        """添加扫描日志到scan_logs表"""
        try:
            with get_db_cursor() as cursor:
                sql = "INSERT INTO scan_logs (log_time, content) VALUES (%s, %s)"
                cursor.execute(sql, (log_time, content))
        except Exception as e:
            logger.error(f"添加扫描日志失败: {e}")
            raise

    @staticmethod
    def add_ai_decision(decision_time: str, symbol: str, gemma: str, llama: str, deepseek: str,
                        status: str, side: str, detail: str) -> None:
        """添加AI决策记录到ai_decisions表"""
        try:
            with get_db_cursor() as cursor:
                sql = """
                    INSERT INTO ai_decisions 
                    (decision_time, symbol, gemma, llama, deepseek, status, side, detail)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (decision_time, symbol, gemma, llama, deepseek, status, side, detail))
        except Exception as e:
            logger.error(f"添加AI决策记录失败: {e}")
            raise

    @staticmethod
    def get_scan_logs(limit: int = 50) -> List[Dict[str, Any]]:
        """获取扫描日志列表"""
        try:
            with get_db_cursor(dict_cursor=True) as cursor:
                sql = "SELECT log_time, content FROM scan_logs ORDER BY id DESC LIMIT %s"
                cursor.execute(sql, (limit,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取扫描日志失败: {e}")
            return []

    @staticmethod
    def get_ai_decisions(limit: int = 20) -> List[Dict[str, Any]]:
        """获取AI决策记录列表"""
        try:
            with get_db_cursor(dict_cursor=True) as cursor:
                sql = """
                    SELECT decision_time, symbol, gemma, llama, deepseek, status, side, detail
                    FROM ai_decisions ORDER BY id DESC LIMIT %s
                """
                cursor.execute(sql, (limit,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取AI决策记录失败: {e}")
            return []

    @staticmethod
    def save_account_snapshot(net_assets: float, buy_power: float, market_value: float = 0, 
                                today_pnl: float = 0, today_pnl_percent: float = 0) -> None:
        """保存账户快照"""
        try:
            with get_db_cursor() as cursor:
                sql = """
                    INSERT INTO account_snapshots 
                    (net_assets, buy_power, market_value, today_pnl, today_pnl_percent) 
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (net_assets, buy_power, market_value, today_pnl, today_pnl_percent))
        except Exception as e:
            logger.error(f"保存账户快照失败: {e}")
            raise

    @staticmethod
    def _ensure_user_asset_trend_table() -> None:
        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_asset_trends (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT NOT NULL DEFAULT 1,
                        trend_date DATE NOT NULL,
                        total_assets DECIMAL(18, 4) DEFAULT 0,
                        cash DECIMAL(18, 4) DEFAULT 0,
                        market_value DECIMAL(18, 4) DEFAULT 0,
                        today_pnl DECIMAL(18, 4) DEFAULT 0,
                        today_pnl_percent DECIMAL(10, 4) DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        UNIQUE KEY uniq_user_asset_trend (user_id, trend_date),
                        INDEX idx_user_asset_trend_date (user_id, trend_date)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
        except Exception as e:
            logger.error(f"初始化用户资产趋势表失败: {e}")
            raise
    
    @staticmethod
    def save_asset_trend(date: str, total_assets: float, cash: float, market_value: float, 
                         today_pnl: float, today_pnl_percent: float, user_id: int = 1) -> None:
        """保存资产趋势数据（日线）"""
        try:
            DbUtil._ensure_user_asset_trend_table()
            with get_db_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO user_asset_trends (
                        user_id, trend_date, total_assets, cash, market_value, today_pnl, today_pnl_percent
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        total_assets = VALUES(total_assets),
                        cash = VALUES(cash),
                        market_value = VALUES(market_value),
                        today_pnl = VALUES(today_pnl),
                        today_pnl_percent = VALUES(today_pnl_percent),
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, date, total_assets, cash, market_value, today_pnl, today_pnl_percent)
                )
        except Exception as e:
            logger.error(f"保存资产趋势失败: {e}")
            raise
    
    @staticmethod
    def get_asset_trend(days: int = 30, user_id: int = 1) -> List[Dict[str, Any]]:
        """获取资产趋势数据"""
        try:
            DbUtil._ensure_user_asset_trend_table()
            with get_db_cursor(dict_cursor=True) as cursor:
                sql = """
                    SELECT trend_date, total_assets, cash, market_value, today_pnl, today_pnl_percent
                    FROM user_asset_trends
                    WHERE user_id = %s
                      AND trend_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                    ORDER BY trend_date ASC
                """
                cursor.execute(sql, (user_id, days))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取资产趋势失败: {e}")
            return []
    
    @staticmethod
    def execute_sql(sql: str, params: Optional[Tuple[Any, ...]] = None) -> int:
        """
        执行SQL语句
        返回：影响的行数
        """
        try:
            with get_db_cursor() as cursor:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                return cursor.rowcount
        except Exception as e:
            logger.error(f"执行SQL失败: {e}, SQL: {sql[:100]}")
            raise
    
    @staticmethod
    def execute(sql: str, params: Optional[Tuple[Any, ...]] = None) -> int:
        """execute_sql的别名"""
        return DbUtil.execute_sql(sql, params)

    @staticmethod
    def execute_insert(sql: str, params: Optional[Tuple[Any, ...]] = None) -> int:
        """执行插入语句并返回 lastrowid。"""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    if params:
                        cursor.execute(sql, params)
                    else:
                        cursor.execute(sql)
                    return int(cursor.lastrowid or 0)
        except Exception as e:
            logger.error(f"执行插入失败: {e}, SQL: {sql[:100]}")
            raise
    
    @staticmethod
    def query_all(sql: str, params: Optional[Tuple[Any, ...]] = None) -> List[Tuple[Any, ...]]:
        """查询所有结果"""
        try:
            with get_db_cursor(read_only=True) as cursor:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"查询失败: {e}, SQL: {sql[:100]}")
            return []
    
    @staticmethod
    def query_one(sql: str, params: Optional[Tuple[Any, ...]] = None) -> Optional[Tuple[Any, ...]]:
        """查询单条结果"""
        try:
            with get_db_cursor(read_only=True) as cursor:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"查询失败: {e}, SQL: {sql[:100]}")
            return None

    @staticmethod
    def fetch_one(sql: str, params: Optional[Tuple[Any, ...]] = None) -> Optional[Dict[str, Any]]:
        """查询单条结果，返回字典格式"""
        try:
            with get_db_cursor(dict_cursor=True, read_only=True) as cursor:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"查询失败: {e}, SQL: {sql[:100]}")
            return None

    @staticmethod
    def fetch_all(sql: str, params: Optional[Tuple[Any, ...]] = None) -> List[Dict[str, Any]]:
        """查询所有结果，返回字典列表格式"""
        try:
            with get_db_cursor(dict_cursor=True, read_only=True) as cursor:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"查询失败: {e}, SQL: {sql[:100]}")
            return []

    @staticmethod
    def fetch_one_primary(sql: str, params: Optional[Tuple[Any, ...]] = None) -> Optional[Dict[str, Any]]:
        """强制走主库查询单条结果。"""
        try:
            with get_db_cursor(dict_cursor=True, read_only=False) as cursor:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"主库查询失败: {e}, SQL: {sql[:100]}")
            return None

    @staticmethod
    def fetch_all_primary(sql: str, params: Optional[Tuple[Any, ...]] = None) -> List[Dict[str, Any]]:
        """强制走主库查询多条结果。"""
        try:
            with get_db_cursor(dict_cursor=True, read_only=False) as cursor:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"主库查询失败: {e}, SQL: {sql[:100]}")
            return []

    @staticmethod
    def save_holding(symbol: str, current_price: float, avg_price: float, quantity: float) -> None:
        """保存持仓信息到positions表"""
        try:
            with get_db_cursor() as cursor:
                # 先检查是否已有该股票的记录
                check_sql = "SELECT symbol FROM positions WHERE symbol = %s"
                cursor.execute(check_sql, (symbol,))
                existing = cursor.fetchone()
                
                if existing:
                    # 更新已有记录
                    update_sql = """
                        UPDATE positions 
                        SET avg_price = %s, quantity = %s, current_price = %s, update_time = NOW()
                        WHERE symbol = %s
                    """
                    cursor.execute(update_sql, (avg_price, quantity, current_price, symbol))
                else:
                    # 插入新记录
                    insert_sql = """
                        INSERT INTO positions (symbol, avg_price, quantity, current_price)
                        VALUES (%s, %s, %s, %s)
                    """
                    cursor.execute(insert_sql, (symbol, avg_price, quantity, current_price))
        except Exception as e:
            logger.error(f"保存持仓信息失败: {e}")
            raise
    
    @staticmethod
    def close_pool() -> None:
        """关闭连接池（应用关闭时调用）"""
        global _pool_instances
        for pool in _pool_instances.values():
            pool.close_all()
        _pool_instances = {}
