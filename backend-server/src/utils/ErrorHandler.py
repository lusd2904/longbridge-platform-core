"""
错误处理工具
提供统一的错误处理和重试机制
"""
import functools
import time
import logging
from typing import Callable, Any, Optional, Type, Tuple
from utils.LoggerUtil import get_logger, log_error

logger = get_logger(__name__)


class APIError(Exception):
    """API调用错误"""
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class NetworkError(Exception):
    """网络错误"""
    pass


class ValidationError(Exception):
    """数据验证错误"""
    pass


class RiskLimitError(Exception):
    """风险控制限制错误"""
    pass


def retry_on_error(max_retries: int = 3,
                   delay: float = 1.0,
                   backoff: float = 2.0,
                   exceptions: Tuple[Type[Exception], ...] = (Exception,),
                   on_retry: Optional[Callable] = None) -> Callable:
    """
    错误重试装饰器
    
    Args:
        max_retries: 最大重试次数
        delay: 初始延迟时间（秒）
        backoff: 延迟增长倍数
        exceptions: 需要捕获的异常类型
        on_retry: 重试时的回调函数
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        logger.warning(
                            f"{func.__name__} 第{attempt + 1}次尝试失败: {e}, "
                            f"{current_delay}秒后重试..."
                        )
                        
                        if on_retry:
                            try:
                                on_retry(attempt, e, *args, **kwargs)
                            except Exception as callback_error:
                                logger.error(f"重试回调函数出错: {callback_error}")
                        
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"{func.__name__} 重试{max_retries}次后仍然失败")
            
            # 所有重试都失败了
            raise last_exception
        
        return wrapper
    return decorator


def handle_api_error(default_return: Any = None,
                     log_level: str = "ERROR",
                     error_message: Optional[str] = None) -> Callable:
    """
    API错误处理装饰器
    
    Args:
        default_return: 出错时的默认返回值
        log_level: 日志级别
        error_message: 自定义错误消息
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
                
            except APIError as e:
                msg = error_message or f"API错误: {e}"
                if log_level == "ERROR":
                    logger.error(msg)
                elif log_level == "WARNING":
                    logger.warning(msg)
                
                log_error(logger, e, {
                    'context': 'api_error',
                    'function': func.__name__,
                    'status_code': e.status_code
                })
                
                return default_return
                
            except NetworkError as e:
                msg = error_message or f"网络错误: {e}"
                logger.error(msg)
                
                log_error(logger, e, {
                    'context': 'network_error',
                    'function': func.__name__
                })
                
                return default_return
                
            except Exception as e:
                msg = error_message or f"未预期的错误: {e}"
                logger.error(msg)
                
                log_error(logger, e, {
                    'context': 'unexpected_error',
                    'function': func.__name__
                })
                
                return default_return
        
        return wrapper
    return decorator


def safe_execute(func: Callable, 
                 default_return: Any = None,
                 error_handler: Optional[Callable] = None,
                 *args, **kwargs) -> Any:
    """
    安全执行函数
    
    Args:
        func: 要执行的函数
        default_return: 出错时的默认返回值
        error_handler: 错误处理回调
        *args, **kwargs: 函数参数
        
    Returns:
        函数返回值或默认值
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"执行{func.__name__}时出错: {e}")
        
        if error_handler:
            try:
                error_handler(e, *args, **kwargs)
            except Exception as handler_error:
                logger.error(f"错误处理函数出错: {handler_error}")
        
        return default_return


class CircuitBreaker:
    """熔断器模式"""
    
    def __init__(self, 
                 failure_threshold: int = 5,
                 recovery_timeout: float = 60.0,
                 expected_exception: Type[Exception] = Exception):
        """
        初始化熔断器
        
        Args:
            failure_threshold: 失败次数阈值
            recovery_timeout: 恢复超时时间（秒）
            expected_exception: 预期的异常类型
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def can_execute(self) -> bool:
        """检查是否可以执行"""
        if self.state == "CLOSED":
            return True
        
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info("熔断器进入半开状态，尝试恢复")
                return True
            return False
        
        return True  # HALF_OPEN
    
    def record_success(self):
        """记录成功"""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def record_failure(self):
        """记录失败"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.error(f"熔断器打开，失败次数: {self.failure_count}")
    
    def __call__(self, func: Callable) -> Callable:
        """作为装饰器使用"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if not self.can_execute():
                raise NetworkError(f"熔断器打开，服务暂时不可用")
            
            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
                
            except self.expected_exception as e:
                self.record_failure()
                raise e
        
        return wrapper


# 全局熔断器实例
_api_circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)
_db_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)


def with_api_circuit_breaker(func: Callable) -> Callable:
    """API熔断器装饰器"""
    return _api_circuit_breaker(func)


def with_db_circuit_breaker(func: Callable) -> Callable:
    """数据库熔断器装饰器"""
    return _db_circuit_breaker(func)


def validate_input(validator: Callable, error_msg: str = "输入验证失败") -> Callable:
    """
    输入验证装饰器
    
    Args:
        validator: 验证函数
        error_msg: 错误消息
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if not validator(*args, **kwargs):
                raise ValidationError(error_msg)
            return func(*args, **kwargs)
        return wrapper
    return decorator


# 常用验证函数
def validate_symbol(symbol: str) -> bool:
    """验证股票代码"""
    return bool(symbol and isinstance(symbol, str) and len(symbol) <= 20)


def validate_price(price: float) -> bool:
    """验证价格"""
    return isinstance(price, (int, float)) and price > 0


def validate_quantity(quantity: int) -> bool:
    """验证数量"""
    return isinstance(quantity, int) and quantity > 0
