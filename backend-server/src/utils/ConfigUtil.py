"""
配置管理工具类
从数据库读取配置，支持缓存机制
"""

import json
from typing import Any

from utils.DbUtil import DbUtil


class ConfigUtil:
    """配置管理工具类"""

    # 配置缓存
    _config_cache = {}

    @staticmethod
    def get_config(user_id: int, key: str, default: Any = None) -> Any:
        """
        获取配置

        Args:
            user_id: 用户ID
            key: 配置键
            default: 默认值

        Returns:
            配置值
        """
        # 构建缓存键
        cache_key = f"{user_id}:{key}"

        # 检查缓存
        if cache_key in ConfigUtil._config_cache:
            return ConfigUtil._config_cache[cache_key]

        # 从数据库读取
        try:
            sql = "SELECT config_value FROM configs WHERE user_id = %s AND config_key = %s"
            result = DbUtil.query_one(sql, (user_id, key))

            if result:
                value = result[0]
                # 尝试解析 JSON
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass
                # 缓存结果
                ConfigUtil._config_cache[cache_key] = value
                return value
        except Exception as e:
            print(f"❌ [配置] 读取失败: {e}")

        return default

    @staticmethod
    def set_config(user_id: int, key: str, value: Any, description: str = None) -> bool:
        """
        设置配置

        Args:
            user_id: 用户ID
            key: 配置键
            value: 配置值
            description: 配置描述

        Returns:
            是否成功
        """
        try:
            # 序列化值
            if not isinstance(value, (str, int, float, bool, type(None))):
                value = json.dumps(value)
            else:
                value = str(value)

            # 插入或更新配置
            sql = """
                INSERT INTO configs (user_id, config_key, config_value, description)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    config_value = %s,
                    description = %s
            """
            DbUtil.execute(sql, (user_id, key, value, description, value, description))

            # 清除缓存
            cache_key = f"{user_id}:{key}"
            if cache_key in ConfigUtil._config_cache:
                del ConfigUtil._config_cache[cache_key]

            return True
        except Exception as e:
            print(f"❌ [配置] 设置失败: {e}")
            return False

    @staticmethod
    def get_all_configs(user_id: int) -> dict:
        """
        获取用户的所有配置

        Args:
            user_id: 用户ID

        Returns:
            配置字典
        """
        configs = {}
        try:
            sql = "SELECT config_key, config_value FROM configs WHERE user_id = %s"
            results = DbUtil.query_all(sql, (user_id,))

            for key, value in results:
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass
                configs[key] = value
        except Exception as e:
            print(f"❌ [配置] 获取所有配置失败: {e}")

        return configs

    @staticmethod
    def clear_cache(user_id: int = None):
        """
        清除缓存

        Args:
            user_id: 用户ID，None 表示清除所有缓存
        """
        if user_id:
            # 清除指定用户的缓存
            keys_to_remove = []
            for key in ConfigUtil._config_cache:
                if key.startswith(f"{user_id}:"):
                    keys_to_remove.append(key)
            for key in keys_to_remove:
                del ConfigUtil._config_cache[key]
        else:
            # 清除所有缓存
            ConfigUtil._config_cache.clear()
