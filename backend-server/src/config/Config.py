import os
from typing import Any

from utils.ConfigUtil import ConfigUtil


class AppConfig:
    """应用配置类"""

    _INT_KEYS = {
        "AI_TIMEOUT",
        "AI_LOCAL_TIMEOUT",
        "NUM_THREAD",
        "NUM_PREDICT",
        "RSI_OVER_BUY",
        "RSI_OVER_SELL",
        "SCAN_INTERVAL",
        "CANCEL_ORDER_THRESHOLD_SECONDS",
        "RECOMMENDATION_REFRESH_INTERVAL",
        "MARKET_INSIGHT_REFRESH_INTERVAL",
        "POSITION_MONITOR_INTERVAL",
        "AI_QUANT_INTERVAL",
        "AI_QUANT_CONFIDENCE_THRESHOLD",
        "AI_QUANT_MAX_BUY_AMOUNT",
        "HISTORICAL_DATA_SYNC_HOUR",
        "HISTORICAL_DATA_SYNC_MINUTE",
        "HISTORICAL_DATA_LOOKBACK_DAYS",
        "HISTORICAL_DATA_MAX_SYMBOLS",
    }
    _FLOAT_KEYS = {"TEMPERATURE"}
    _STRING_KEYS = {"AI_REASONING_EFFORT", "AI_SCAN_REASONING_EFFORT"}
    _BOOL_KEYS = {
        "ENABLE_CANCEL_STRATEGY",
        "MARKET_INSIGHT_ENABLED",
        "AI_QUANT_TRADING_ENABLED",
        "AI_QUANT_AUTO_EXECUTE",
        "HISTORICAL_DATA_SYNC_ENABLED",
    }

    # 默认配置（当数据库中不存在时使用）
    _default_config = {
        # Longbridge API 配置
        "APP_KEY": "",
        "APP_SECRET": "",
        "ACCESS_TOKEN": "",
        # AI 配置
        "AI_PROVIDER": "nvidia",
        "AI_FALLBACK_PROVIDER": "",
        "AI_BASE_URL": "https://integrate.api.nvidia.com/v1",
        "AI_URL": "https://integrate.api.nvidia.com/v1/chat/completions",
        "AI_API_STYLE": "openai-chat-completions",
        "AI_LOCAL_URL": "http://127.0.0.1:11434/api/generate",
        "AI_LOCAL_MODEL": "gemma3:12b",
        "AI_MODEL": "gpt-5.5",
        "AI_MODEL_SCAN_PULSE": "gpt-5.4",
        "AI_MODEL_SCAN_FAST": "gpt-5.4",
        "AI_MODEL_SCAN_RISK": "gpt-5.4",
        "AI_MODEL_SCAN_FINAL": "gpt-5.5",
        "AI_MODEL_TREND_BATCH": "gpt-5.4",
        "AI_MODEL_RECOMMEND_BRIEF": "gpt-5.4",
        "AI_MODEL_RECOMMEND_SUMMARY": "gpt-5.5",
        "AI_MODEL_VISION": "gpt-5.4",
        "AI_REASONING_EFFORT": "medium",
        "AI_SCAN_REASONING_EFFORT": "high",
        "AI_API_KEY": "",
        "AI_TIMEOUT": 8,
        "AI_LOCAL_TIMEOUT": 45,
        "NUM_THREAD": 4,
        "TEMPERATURE": 0.2,
        "NUM_PREDICT": 360,
        # 策略与路径
        "RSI_OVER_BUY": 70,
        "RSI_OVER_SELL": 30,
        "SCAN_INTERVAL": 600,
        "RECOMMENDATION_REFRESH_INTERVAL": 1800,
        "MARKET_INSIGHT_REFRESH_INTERVAL": 900,
        "MARKET_INSIGHT_ENABLED": True,
        "POSITION_MONITOR_INTERVAL": 300,
        "AI_QUANT_INTERVAL": 900,
        "AI_QUANT_CONFIDENCE_THRESHOLD": 72,
        "AI_QUANT_MAX_BUY_AMOUNT": 2000,
        "AI_QUANT_TRADING_ENABLED": False,
        "AI_QUANT_AUTO_EXECUTE": False,
        "HISTORICAL_DATA_SYNC_ENABLED": True,
        "HISTORICAL_DATA_SYNC_HOUR": 7,
        "HISTORICAL_DATA_SYNC_MINUTE": 10,
        "HISTORICAL_DATA_LOOKBACK_DAYS": 420,
        "HISTORICAL_DATA_MAX_SYMBOLS": 240,
        "HISTORICAL_BACKFILL_START_DATE": "2020-01-01",
        # 撤单策略配置
        "ENABLE_CANCEL_STRATEGY": True,
        "CANCEL_ORDER_THRESHOLD_SECONDS": 300,
    }

    @classmethod
    def get(cls, key: str, user_id: int = 1, default: Any = None) -> Any:
        """
        获取配置值

        优先级：环境变量 > 数据库 > 默认值

        Args:
            key: 配置键
            user_id: 用户ID，默认为管理员
            default: 默认值

        Returns:
            配置值
        """
        # 1. 从环境变量获取（优先级最高）
        env_key = f"LONGBRIDGE_{key.upper()}"
        value = os.environ.get(env_key)

        if value is not None:
            # 环境变量存在，进行类型转换
            if key in cls._INT_KEYS:
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    pass  # 转换失败，继续尝试其他来源
            elif key in cls._FLOAT_KEYS:
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    pass  # 转换失败，继续尝试其他来源
            elif key in cls._BOOL_KEYS:
                if isinstance(value, str):
                    value = value.lower() == "true"
            return value

        # 2. 从数据库获取
        value = ConfigUtil.get_config(user_id, key.lower(), None)

        # 3. 如果数据库中不存在，使用默认值
        if value is None:
            value = cls._default_config.get(key, default)

        # 类型转换
        if key in cls._INT_KEYS:
            try:
                value = int(value)
            except (ValueError, TypeError):
                value = cls._default_config.get(key, default)
        elif key in cls._FLOAT_KEYS:
            try:
                value = float(value)
            except (ValueError, TypeError):
                value = cls._default_config.get(key, default)
        elif key in cls._BOOL_KEYS:
            if isinstance(value, str):
                value = value.lower() == "true"

        return value

    @classmethod
    def set(cls, key: str, value: Any, user_id: int = 1, description: str = None) -> bool:
        """
        设置配置值

        Args:
            key: 配置键
            value: 配置值
            user_id: 用户ID，默认为管理员
            description: 配置描述

        Returns:
            是否成功
        """
        return ConfigUtil.set_config(user_id, key.lower(), value, description)

    @classmethod
    def get_all(cls, user_id: int = 1) -> dict:
        """
        获取所有配置

        Args:
            user_id: 用户ID，默认为管理员

        Returns:
            配置字典
        """
        configs = ConfigUtil.get_all_configs(user_id)

        # 合并默认配置
        for key, default_value in cls._default_config.items():
            if key.lower() not in configs:
                configs[key.lower()] = default_value

        # 检查环境变量，覆盖配置
        for key in cls._default_config:
            env_key = f"LONGBRIDGE_{key.upper()}"
            env_value = os.environ.get(env_key)
            if env_value is not None:
                configs[key.lower()] = env_value

        return configs


# 为了保持向后兼容，创建默认实例
# 注意：这些值会在运行时从数据库读取
APP_KEY = AppConfig.get("APP_KEY")
APP_SECRET = AppConfig.get("APP_SECRET")
ACCESS_TOKEN = AppConfig.get("ACCESS_TOKEN")
AI_PROVIDER = AppConfig.get("AI_PROVIDER")
AI_FALLBACK_PROVIDER = AppConfig.get("AI_FALLBACK_PROVIDER")
AI_BASE_URL = AppConfig.get("AI_BASE_URL")
AI_URL = AppConfig.get("AI_URL")
AI_LOCAL_URL = AppConfig.get("AI_LOCAL_URL")
AI_LOCAL_MODEL = AppConfig.get("AI_LOCAL_MODEL")
AI_MODEL = AppConfig.get("AI_MODEL")
AI_MODEL_SCAN_PULSE = AppConfig.get("AI_MODEL_SCAN_PULSE")
AI_MODEL_SCAN_FAST = AppConfig.get("AI_MODEL_SCAN_FAST")
AI_MODEL_SCAN_RISK = AppConfig.get("AI_MODEL_SCAN_RISK")
AI_MODEL_SCAN_FINAL = AppConfig.get("AI_MODEL_SCAN_FINAL")
AI_MODEL_TREND_BATCH = AppConfig.get("AI_MODEL_TREND_BATCH")
AI_MODEL_RECOMMEND_BRIEF = AppConfig.get("AI_MODEL_RECOMMEND_BRIEF")
AI_MODEL_RECOMMEND_SUMMARY = AppConfig.get("AI_MODEL_RECOMMEND_SUMMARY")
AI_MODEL_VISION = AppConfig.get("AI_MODEL_VISION")
AI_REASONING_EFFORT = AppConfig.get("AI_REASONING_EFFORT")
AI_SCAN_REASONING_EFFORT = AppConfig.get("AI_SCAN_REASONING_EFFORT")
AI_API_KEY = AppConfig.get("AI_API_KEY")
AI_TIMEOUT = AppConfig.get("AI_TIMEOUT")
AI_LOCAL_TIMEOUT = AppConfig.get("AI_LOCAL_TIMEOUT")
NUM_THREAD = AppConfig.get("NUM_THREAD")
TEMPERATURE = AppConfig.get("TEMPERATURE")
NUM_PREDICT = AppConfig.get("NUM_PREDICT")
RSI_OVER_BUY = AppConfig.get("RSI_OVER_BUY")
RSI_OVER_SELL = AppConfig.get("RSI_OVER_SELL")
SCAN_INTERVAL = AppConfig.get("SCAN_INTERVAL")
RECOMMENDATION_REFRESH_INTERVAL = AppConfig.get("RECOMMENDATION_REFRESH_INTERVAL")
MARKET_INSIGHT_REFRESH_INTERVAL = AppConfig.get("MARKET_INSIGHT_REFRESH_INTERVAL")
MARKET_INSIGHT_ENABLED = AppConfig.get("MARKET_INSIGHT_ENABLED")
POSITION_MONITOR_INTERVAL = AppConfig.get("POSITION_MONITOR_INTERVAL")
AI_QUANT_INTERVAL = AppConfig.get("AI_QUANT_INTERVAL")
AI_QUANT_CONFIDENCE_THRESHOLD = AppConfig.get("AI_QUANT_CONFIDENCE_THRESHOLD")
AI_QUANT_MAX_BUY_AMOUNT = AppConfig.get("AI_QUANT_MAX_BUY_AMOUNT")
AI_QUANT_TRADING_ENABLED = AppConfig.get("AI_QUANT_TRADING_ENABLED")
AI_QUANT_AUTO_EXECUTE = AppConfig.get("AI_QUANT_AUTO_EXECUTE")
HISTORICAL_DATA_SYNC_ENABLED = AppConfig.get("HISTORICAL_DATA_SYNC_ENABLED")
HISTORICAL_DATA_SYNC_HOUR = AppConfig.get("HISTORICAL_DATA_SYNC_HOUR")
HISTORICAL_DATA_SYNC_MINUTE = AppConfig.get("HISTORICAL_DATA_SYNC_MINUTE")
HISTORICAL_DATA_LOOKBACK_DAYS = AppConfig.get("HISTORICAL_DATA_LOOKBACK_DAYS")
HISTORICAL_DATA_MAX_SYMBOLS = AppConfig.get("HISTORICAL_DATA_MAX_SYMBOLS")
HISTORICAL_BACKFILL_START_DATE = AppConfig.get("HISTORICAL_BACKFILL_START_DATE")
ENABLE_CANCEL_STRATEGY = AppConfig.get("ENABLE_CANCEL_STRATEGY")
CANCEL_ORDER_THRESHOLD_SECONDS = AppConfig.get("CANCEL_ORDER_THRESHOLD_SECONDS")
