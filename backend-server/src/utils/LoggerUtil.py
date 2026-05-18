"""
结构化日志工具
提供统一的日志记录格式和级别管理
"""
import logging
import json
import sys
import os
from datetime import datetime
from typing import Dict, Any, Optional
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from enum import Enum


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StructuredLogFormatter(logging.Formatter):
    """结构化日志格式化器"""
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'thread': record.thread,
            'process': record.process
        }
        
        # 添加额外字段
        if hasattr(record, 'extra_data'):
            log_data.update(record.extra_data)
        
        # 添加异常信息
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False, default=str)


class ColoredConsoleFormatter(logging.Formatter):
    """带颜色的控制台日志格式化器"""
    
    # ANSI颜色代码
    COLORS = {
        'DEBUG': '\033[36m',     # 青色
        'INFO': '\033[32m',      # 绿色
        'WARNING': '\033[33m',   # 黄色
        'ERROR': '\033[31m',     # 红色
        'CRITICAL': '\033[35m',  # 紫色
        'RESET': '\033[0m'       # 重置
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        level = f"{color}[{record.levelname}]{reset}"
        
        return f"{timestamp} {level} [{record.name}] {record.getMessage()}"


class LoggerUtil:
    """日志工具类"""
    
    _loggers: Dict[str, logging.Logger] = {}
    _log_dir: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    
    @classmethod
    def setup_logging(cls,
                     log_level: str = "INFO",
                     log_to_file: bool = True,
                     log_to_console: bool = True,
                     max_bytes: int = 10 * 1024 * 1024,  # 10MB
                     backup_count: int = 5) -> None:
        """
        设置日志配置
        
        Args:
            log_level: 日志级别
            log_to_file: 是否写入文件
            log_to_console: 是否输出到控制台
            max_bytes: 单个日志文件最大大小
            backup_count: 备份文件数量
        """
        # 创建日志目录
        if log_to_file and not os.path.exists(cls._log_dir):
            os.makedirs(cls._log_dir)
        
        # 根日志器配置
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level.upper()))
        
        # 清除现有处理器
        root_logger.handlers.clear()
        
        # 控制台处理器
        if log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.DEBUG)
            console_formatter = ColoredConsoleFormatter()
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)
        
        # 文件处理器
        if log_to_file:
            # 结构化日志文件（JSON格式）
            structured_log_path = os.path.join(cls._log_dir, 'structured.log')
            structured_handler = RotatingFileHandler(
                structured_log_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            structured_handler.setLevel(logging.DEBUG)
            structured_formatter = StructuredLogFormatter()
            structured_handler.setFormatter(structured_formatter)
            root_logger.addHandler(structured_handler)
            
            # 普通日志文件（可读格式）
            app_log_path = os.path.join(cls._log_dir, 'app.log')
            app_handler = RotatingFileHandler(
                app_log_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            app_handler.setLevel(logging.DEBUG)
            app_formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            app_handler.setFormatter(app_formatter)
            root_logger.addHandler(app_handler)
            
            # 错误日志文件（单独记录错误）
            error_log_path = os.path.join(cls._log_dir, 'error.log')
            error_handler = RotatingFileHandler(
                error_log_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(structured_formatter)
            root_logger.addHandler(error_handler)
        
        # 设置第三方库日志级别
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('requests').setLevel(logging.WARNING)
        
        cls.get_logger(__name__).info("日志系统初始化完成")
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """
        获取日志器
        
        Args:
            name: 日志器名称
            
        Returns:
            Logger实例
        """
        if name not in cls._loggers:
            logger = logging.getLogger(name)
            cls._loggers[name] = logger
        return cls._loggers[name]
    
    @classmethod
    def log_with_context(cls,
                        logger: logging.Logger,
                        level: str,
                        message: str,
                        extra_data: Optional[Dict[str, Any]] = None) -> None:
        """
        带上下文的日志记录
        
        Args:
            logger: 日志器
            level: 日志级别
            message: 日志消息
            extra_data: 额外数据
        """
        extra = {'extra_data': extra_data or {}}
        log_func = getattr(logger, level.lower())
        log_func(message, extra=extra)


# 便捷函数
def get_logger(name: str) -> logging.Logger:
    """获取日志器"""
    return LoggerUtil.get_logger(name)


def log_trade(logger: logging.Logger,
              symbol: str,
              action: str,
              quantity: int,
              price: float,
              order_id: Optional[str] = None,
              extra: Optional[Dict[str, Any]] = None) -> None:
    """
    记录交易日志
    
    Args:
        logger: 日志器
        symbol: 股票代码
        action: 动作（BUY/SELL）
        quantity: 数量
        price: 价格
        order_id: 订单ID
        extra: 额外信息
    """
    data = {
        'event_type': 'trade',
        'symbol': symbol,
        'action': action,
        'quantity': quantity,
        'price': price,
        'total_value': quantity * price,
        'order_id': order_id
    }
    if extra:
        data.update(extra)
    
    LoggerUtil.log_with_context(logger, 'INFO', f"交易执行: {action} {symbol}", data)


def log_scan(logger: logging.Logger,
             symbol: str,
             score: int,
            indicators: Dict[str, Any],
             extra: Optional[Dict[str, Any]] = None) -> None:
    """
    记录扫描日志
    
    Args:
        logger: 日志器
        symbol: 股票代码
        score: 评分
        indicators: 指标数据
        extra: 额外信息
    """
    data = {
        'event_type': 'scan',
        'symbol': symbol,
        'score': score,
        'indicators': indicators
    }
    if extra:
        data.update(extra)
    
    LoggerUtil.log_with_context(logger, 'INFO', f"扫描完成: {symbol}", data)


def log_ai_decision(logger: logging.Logger,
                   symbol: str,
                   decision: str,
                   confidence: float,
                   models_used: list,
                   extra: Optional[Dict[str, Any]] = None) -> None:
    """
    记录AI决策日志
    
    Args:
        logger: 日志器
        symbol: 股票代码
        decision: 决策结果
        confidence: 置信度
        models_used: 使用的模型列表
        extra: 额外信息
    """
    data = {
        'event_type': 'ai_decision',
        'symbol': symbol,
        'decision': decision,
        'confidence': confidence,
        'models_used': models_used
    }
    if extra:
        data.update(extra)
    
    LoggerUtil.log_with_context(logger, 'INFO', f"AI决策: {symbol} -> {decision}", data)


def log_risk_event(logger: logging.Logger,
                   event_type: str,
                   symbol: str,
                   risk_level: str,
                   message: str,
                   extra: Optional[Dict[str, Any]] = None) -> None:
    """
    记录风险事件日志
    
    Args:
        logger: 日志器
        event_type: 事件类型（stop_loss/risk_limit/etc）
        symbol: 股票代码
        risk_level: 风险等级
        message: 风险信息
        extra: 额外信息
    """
    data = {
        'event_type': 'risk',
        'risk_event_type': event_type,
        'symbol': symbol,
        'risk_level': risk_level,
        'message': message
    }
    if extra:
        data.update(extra)
    
    LoggerUtil.log_with_context(logger, 'WARNING', f"风险事件: {message}", data)


def log_error(logger: logging.Logger,
              error: Exception,
              context: Optional[Dict[str, Any]] = None) -> None:
    """
    记录错误日志
    
    Args:
        logger: 日志器
        error: 异常对象
        context: 上下文信息
    """
    data = {
        'event_type': 'error',
        'error_type': type(error).__name__,
        'error_message': str(error),
        'context': context or {}
    }
    
    LoggerUtil.log_with_context(logger, 'ERROR', f"错误: {str(error)}", data)


# 初始化日志（在应用启动时调用）
def init_logging(log_level: str = "INFO"):
    """初始化日志系统"""
    LoggerUtil.setup_logging(log_level=log_level)
