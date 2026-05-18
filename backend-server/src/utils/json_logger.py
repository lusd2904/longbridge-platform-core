"""
JSON Logger Configuration
提供统一的JSON格式日志输出
"""
import os
import logging
import json
import time
import traceback
from datetime import datetime
from typing import Dict, Any, Optional
import threading

# 线程本地存储，用于跟踪traceID
_thread_local = threading.local()


class JSONFormatter(logging.Formatter):
    """
    JSON日志格式化器
    输出格式：{"timestamp": "...", "level": "INFO", "logger": "...", "message": "...", "trace_id": "...", ...}
    """

    def __init__(self, service_name: str = None):
        """
        初始化JSON格式化器

        Args:
            service_name: 服务名称，用于标识日志来源
        """
        super().__init__()
        self.service_name = service_name or "unknown"

    def format(self, record: logging.LogRecord) -> str:
        """
        格式化日志记录为JSON

        Args:
            record: 日志记录对象

        Returns:
            JSON字符串
        """
        # 创建日志字典
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "service": self.service_name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # 添加trace_id（如果可用）
        trace_id = get_trace_id()
        if trace_id:
            log_entry["trace_id"] = trace_id

        # 添加异常信息（如果有）
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info)
            }

        # 添加额外字段
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_json_logger(
    name: str = __name__,
    level: int = logging.INFO,
    service_name: str = None,
    enable_console: bool = True,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    配置JSON格式的日志记录器

    Args:
        name: 日志记录器名称
        level: 日志级别
        service_name: 服务名称
        enable_console: 是否输出到控制台
        log_file: 日志文件路径（可选）

    Returns:
        配置好的日志记录器
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 清除现有的handlers
    logger.handlers.clear()

    # 创建JSON格式化器
    formatter = JSONFormatter(service_name=service_name)

    # 控制台handler
    if enable_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # 文件handler
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # 避免向父logger传播
    logger.propagate = False

    return logger


def set_trace_id(trace_id: str):
    """
    设置当前线程的traceID

    Args:
        trace_id: 追踪ID
    """
    _thread_local.trace_id = trace_id


def get_trace_id() -> Optional[str]:
    """
    获取当前线程的traceID

    Returns:
        traceID字符串，如果未设置则返回None
    """
    return getattr(_thread_local, 'trace_id', None)


def clear_trace_id():
    """清除当前线程的traceID"""
    if hasattr(_thread_local, 'trace_id'):
        del _thread_local.trace_id


def get_logger(name: str = __name__) -> logging.Logger:
    """
    获取已配置的logger

    Args:
        name: logger名称

    Returns:
        Logger实例
    """
    return logging.getLogger(name)


# 便捷的装饰器，用于自动管理traceID
def with_trace_id(trace_id_func=None):
    """
    装饰器，用于自动设置和清理traceID

    Args:
        trace_id_func: 返回traceID的函数，如果未提供则使用第一个参数作为trace_id
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # 尝试获取trace_id
            trace_id = None
            if trace_id_func:
                trace_id = trace_id_func(*args, **kwargs)
            elif args:
                # 使用第一个参数作为trace_id（假设是请求对象）
                trace_id = getattr(args[0], 'trace_id', None) or getattr(args[0], 'id', None)

            if trace_id:
                set_trace_id(trace_id)

            try:
                return func(*args, **kwargs)
            finally:
                clear_trace_id()

        return wrapper
    return decorator


# 颜色输出辅助函数（用于开发环境的可读性）
def colorize_json_log(json_str: str) -> str:
    """
    为JSON日志添加ANSI颜色（仅在终端中有效）

    Args:
        json_str: JSON字符串

    Returns:
        带颜色的JSON字符串
    """
    try:
        data = json.loads(json_str)
        level = data.get('level', 'INFO')

        # 不同级别的颜色
        colors = {
            'DEBUG': '\033[36m',      # 青色
            'INFO': '\033[32m',       # 绿色
            'WARNING': '\033[33m',    # 黄色
            'ERROR': '\033[31m',      # 红色
            'CRITICAL': '\033[35m',   # 紫色
        }
        reset = '\033[0m'
        color = colors.get(level, '')

        return color + json_str + reset
    except:
        return json_str
