"""
配置管理器
支持配置热更新，无需重启服务
"""

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from utils.DbUtil import DbUtil
from utils.LoggerUtil import get_logger

logger = get_logger(__name__)


@dataclass
class ConfigItem:
    """配置项"""

    key: str
    value: Any
    description: str = ""
    category: str = "general"
    is_editable: bool = True
    updated_at: datetime | None = None
    updated_by: str | None = None


class ConfigManager:
    """配置管理器"""

    def __init__(self, auto_reload: bool = True, reload_interval: int = 60):
        """
        初始化配置管理器

        Args:
            auto_reload: 是否自动重载配置
            reload_interval: 自动重载间隔（秒）
        """
        self.db = DbUtil()
        self._cache: dict[str, ConfigItem] = {}
        self._listeners: dict[str, list[Callable]] = {}
        self._lock = threading.RLock()
        self._last_reload = 0
        self._reload_interval = reload_interval
        self._auto_reload = auto_reload
        self._running = False
        self._reload_thread: threading.Thread | None = None

        # 确保表结构
        self._ensure_table()

        # 加载初始配置
        self.reload()

        # 启动自动重载线程
        if auto_reload:
            self._start_auto_reload()

    def _ensure_table(self):
        """确保配置表存在"""
        sql = """
        CREATE TABLE IF NOT EXISTS system_config (
            config_key VARCHAR(100) PRIMARY KEY,
            config_value TEXT NOT NULL,
            description VARCHAR(500),
            category VARCHAR(50) DEFAULT 'general',
            is_editable TINYINT(1) DEFAULT 1,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            updated_by VARCHAR(100),
            INDEX idx_category (category)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """

        try:
            self.db.execute(sql)

            # 初始化默认配置
            self._init_default_configs()

            logger.info("配置表检查完成")
        except Exception as e:
            logger.error(f"创建配置表失败: {e}")
            raise

    def _init_default_configs(self):
        """初始化默认配置"""
        default_configs = [
            # 交易配置
            ("trading.max_position_ratio", "0.2", "单只股票最大仓位比例", "trading", True),
            ("trading.max_total_positions", "10", "最大持仓数量", "trading", True),
            ("trading.stop_loss_percentage", "0.05", "止损比例", "trading", True),
            ("trading.trailing_stop_percentage", "0.08", "移动止损比例", "trading", True),
            ("trading.max_daily_loss_percentage", "0.03", "单日最大亏损比例", "trading", True),
            ("trading.max_daily_trades", "20", "单日最大交易次数", "trading", True),
            ("trading.max_single_order_value", "100000", "单笔最大订单金额", "trading", True),
            (
                "trading.min_single_order_value",
                "0",
                "单笔最小订单金额（0 表示不限制，美股允许 1 股委托）",
                "trading",
                True,
            ),
            # 扫描配置
            ("scan.batch_size", "25", "扫描批处理大小", "scan", True),
            ("scan.max_workers", "4", "扫描并发数", "scan", True),
            ("scan.cache_ttl", "600", "扫描结果缓存时间（秒）", "scan", True),
            # AI配置
            ("ai.gemma_model", "gemma3:4b", "Gemma模型名称", "ai", True),
            ("ai.llama_model", "llama3.1:8b", "Llama模型名称", "ai", True),
            ("ai.deepseek_model", "deepseek-r1:7b", "DeepSeek模型名称", "ai", True),
            ("ai.min_confidence", "0.6", "最小置信度", "ai", True),
            # 日志配置
            ("log.level", "INFO", "日志级别", "log", True),
            ("log.retention_days", "30", "日志保留天数", "log", True),
        ]

        for key, value, desc, category, editable in default_configs:
            # 检查是否已存在
            check_sql = "SELECT COUNT(*) as count FROM system_config WHERE config_key = %s"
            result = self.db.fetch_one(check_sql, (key,))

            if result and result["count"] == 0:
                insert_sql = """
                INSERT INTO system_config 
                (config_key, config_value, description, category, is_editable)
                VALUES (%s, %s, %s, %s, %s)
                """
                try:
                    self.db.execute(insert_sql, (key, value, desc, category, editable))
                    logger.info(f"初始化配置: {key} = {value}")
                except Exception as e:
                    logger.error(f"初始化配置失败 {key}: {e}")

    def _start_auto_reload(self):
        """启动自动重载线程"""
        self._running = True
        self._reload_thread = threading.Thread(target=self._reload_loop, daemon=True)
        self._reload_thread.start()
        logger.info("配置自动重载已启动")

    def _reload_loop(self):
        """重载循环"""
        while self._running:
            try:
                time.sleep(self._reload_interval)
                if self._running:
                    self.reload()
            except Exception as e:
                logger.error(f"配置自动重载出错: {e}")

    def stop_auto_reload(self):
        """停止自动重载"""
        self._running = False
        if self._reload_thread:
            self._reload_thread.join(timeout=5)
        logger.info("配置自动重载已停止")

    def reload(self):
        """重新加载配置"""
        with self._lock:
            try:
                sql = "SELECT * FROM system_config"
                rows = self.db.query_all(sql)

                new_cache = {}
                for row in rows:
                    key = row["config_key"]
                    value = self._parse_value(row["config_value"])

                    new_cache[key] = ConfigItem(
                        key=key,
                        value=value,
                        description=row.get("description", ""),
                        category=row.get("category", "general"),
                        is_editable=bool(row.get("is_editable", True)),
                        updated_at=row.get("updated_at"),
                        updated_by=row.get("updated_by"),
                    )

                # 检查变更并通知监听器
                self._notify_changes(self._cache, new_cache)

                self._cache = new_cache
                self._last_reload = time.time()

                logger.debug(f"配置已重载，共 {len(new_cache)} 项")

            except Exception as e:
                logger.error(f"重载配置失败: {e}")

    def _parse_value(self, value_str: str) -> Any:
        """解析配置值"""
        try:
            # 尝试解析为JSON
            return json.loads(value_str)
        except:
            # 作为字符串返回
            return value_str

    def _serialize_value(self, value: Any) -> str:
        """序列化配置值"""
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)

    def _notify_changes(self, old_cache: dict[str, ConfigItem], new_cache: dict[str, ConfigItem]):
        """通知配置变更"""
        for key, new_item in new_cache.items():
            if key in old_cache:
                old_item = old_cache[key]
                if old_item.value != new_item.value:
                    # 配置值变更
                    self._trigger_listeners(key, new_item.value, old_item.value)
            else:
                # 新增配置
                self._trigger_listeners(key, new_item.value, None)

    def _trigger_listeners(self, key: str, new_value: Any, old_value: Any):
        """触发监听器"""
        if key in self._listeners:
            for callback in self._listeners[key]:
                try:
                    callback(key, new_value, old_value)
                except Exception as e:
                    logger.error(f"配置监听器出错 {key}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值

        Args:
            key: 配置键
            default: 默认值

        Returns:
            配置值
        """
        with self._lock:
            if key in self._cache:
                return self._cache[key].value
            return default

    def get_int(self, key: str, default: int = 0) -> int:
        """获取整数配置"""
        value = self.get(key, default)
        try:
            return int(value)
        except:
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """获取浮点数配置"""
        value = self.get(key, default)
        try:
            return float(value)
        except:
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """获取布尔配置"""
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)

    def get_json(self, key: str, default: dict | None = None) -> dict | None:
        """获取JSON配置"""
        value = self.get(key, default)
        if isinstance(value, dict):
            return value
        return default

    def set(self, key: str, value: Any, updated_by: str | None = None) -> bool:
        """
        设置配置值

        Args:
            key: 配置键
            value: 配置值
            updated_by: 更新者

        Returns:
            是否成功
        """
        with self._lock:
            # 检查是否可编辑
            if key in self._cache and not self._cache[key].is_editable:
                logger.warning(f"配置项 {key} 不可编辑")
                return False

            value_str = self._serialize_value(value)

            sql = """
            INSERT INTO system_config 
            (config_key, config_value, updated_by)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
            config_value = VALUES(config_value),
            updated_by = VALUES(updated_by),
            updated_at = CURRENT_TIMESTAMP
            """

            try:
                self.db.execute(sql, (key, value_str, updated_by))

                # 更新缓存
                old_value = self._cache.get(key).value if key in self._cache else None
                self._cache[key] = ConfigItem(
                    key=key,
                    value=value,
                    description=self._cache.get(key, ConfigItem(key=key, value=value)).description,
                    category=self._cache.get(key, ConfigItem(key=key, value=value)).category,
                    is_editable=self._cache.get(key, ConfigItem(key=key, value=value, is_editable=True)).is_editable,
                    updated_at=datetime.now(),
                    updated_by=updated_by,
                )

                # 触发监听器
                self._trigger_listeners(key, value, old_value)

                logger.info(f"配置已更新: {key} = {value}")
                return True

            except Exception as e:
                logger.error(f"更新配置失败 {key}: {e}")
                return False

    def delete(self, key: str) -> bool:
        """
        删除配置

        Args:
            key: 配置键

        Returns:
            是否成功
        """
        with self._lock:
            if key in self._cache and not self._cache[key].is_editable:
                logger.warning(f"配置项 {key} 不可删除")
                return False

            sql = "DELETE FROM system_config WHERE config_key = %s"

            try:
                self.db.execute(sql, (key,))

                if key in self._cache:
                    old_value = self._cache[key].value
                    del self._cache[key]
                    self._trigger_listeners(key, None, old_value)

                logger.info(f"配置已删除: {key}")
                return True

            except Exception as e:
                logger.error(f"删除配置失败 {key}: {e}")
                return False

    def add_listener(self, key: str, callback: Callable):
        """
        添加配置变更监听器

        Args:
            key: 配置键
            callback: 回调函数(key, new_value, old_value)
        """
        with self._lock:
            if key not in self._listeners:
                self._listeners[key] = []
            self._listeners[key].append(callback)

    def remove_listener(self, key: str, callback: Callable):
        """移除配置变更监听器"""
        with self._lock:
            if key in self._listeners and callback in self._listeners[key]:
                self._listeners[key].remove(callback)

    def get_all(self, category: str | None = None) -> dict[str, ConfigItem]:
        """
        获取所有配置

        Args:
            category: 配置分类（可选）

        Returns:
            配置字典
        """
        with self._lock:
            if category:
                return {k: v for k, v in self._cache.items() if v.category == category}
            return dict(self._cache)

    def get_categories(self) -> list[str]:
        """获取所有配置分类"""
        with self._lock:
            categories = set(item.category for item in self._cache.values())
            return sorted(list(categories))

    def export_config(self) -> dict[str, Any]:
        """导出所有配置"""
        with self._lock:
            return {
                key: {
                    "value": item.value,
                    "description": item.description,
                    "category": item.category,
                    "is_editable": item.is_editable,
                }
                for key, item in self._cache.items()
            }

    def import_config(self, config_dict: dict[str, Any], updated_by: str | None = None):
        """
        导入配置

        Args:
            config_dict: 配置字典
            updated_by: 更新者
        """
        for key, data in config_dict.items():
            if isinstance(data, dict):
                value = data.get("value")
            else:
                value = data

            self.set(key, value, updated_by)


# 全局配置管理器实例
_config_manager = None


def get_config_manager(auto_reload: bool = True) -> ConfigManager:
    """获取全局配置管理器"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(auto_reload=auto_reload)
    return _config_manager


def get_config(key: str, default: Any = None) -> Any:
    """便捷函数：获取配置"""
    return get_config_manager().get(key, default)


def set_config(key: str, value: Any, updated_by: str | None = None) -> bool:
    """便捷函数：设置配置"""
    return get_config_manager().set(key, value, updated_by)
