import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler

class Logger:
    _instance = None
    _loggers = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @staticmethod
    def get_logger(name: str = 'app') -> logging.Logger:
        """获取或创建logger实例"""
        if name in Logger._loggers:
            return Logger._loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        
        # 避免重复添加handler
        if not logger.handlers:
            # 控制台handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
            
            # 文件handler
            log_dir = os.path.join(os.path.dirname(__file__), '../../logs')
            os.makedirs(log_dir, exist_ok=True)
            
            file_handler = RotatingFileHandler(
                os.path.join(log_dir, f'{name}.log'),
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        
        Logger._loggers[name] = logger
        return logger
    
    @staticmethod
    def log_ai_call(model: str, prompt: str, success: bool, error: str = None):
        """记录AI调用日志"""
        logger = Logger.get_logger('ai')
        if success:
            logger.info(f"[AI调用] 模型:{model} | 成功")
        else:
            logger.error(f"[AI调用] 模型:{model} | 失败 | 错误:{error}")
    
    @staticmethod
    def log_api_call(endpoint: str, method: str, status_code: int, duration: float):
        """记录API调用日志"""
        logger = Logger.get_logger('api')
        if status_code >= 400:
            logger.error(f"[API调用] {method} {endpoint} | 状态:{status_code} | 耗时:{duration:.2f}s")
        else:
            logger.info(f"[API调用] {method} {endpoint} | 状态:{status_code} | 耗时:{duration:.2f}s")
    
    @staticmethod
    def log_database_query(sql: str, success: bool, error: str = None):
        """记录数据库查询日志"""
        logger = Logger.get_logger('database')
        if success:
            logger.debug(f"[数据库] 查询成功 | SQL:{sql[:100]}...")
        else:
            logger.error(f"[数据库] 查询失败 | SQL:{sql[:100]}... | 错误:{error}")
    
    @staticmethod
    def log_business_event(event_type: str, symbol: str, details: str):
        """记录业务事件日志"""
        logger = Logger.get_logger('business')
        logger.info(f"[{event_type}] {symbol} | {details}")
    
    @staticmethod
    def log_error(component: str, error: Exception, context: str = None):
        """记录错误日志"""
        logger = Logger.get_logger('error')
        import traceback
        error_msg = f"[{component}] {type(error).__name__}: {str(error)}"
        if context:
            error_msg += f" | 上下文:{context}"
        logger.error(error_msg, exc_info=True)
        logger.error(traceback.format_exc())
