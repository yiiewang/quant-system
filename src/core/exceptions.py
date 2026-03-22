"""
统一异常体系

提供系统级的异常定义，便于错误处理和问题排查
"""
from typing import Optional, Dict, Any


class QuantSystemException(Exception):
    """
    量化系统基础异常
    
    所有自定义异常的基类
    """
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        初始化异常
        
        Args:
            message: 错误消息
            error_code: 错误代码
            details: 详细信息
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'error': self.error_code,
            'message': self.message,
            'details': self.details
        }
    
    def __str__(self) -> str:
        if self.details:
            return f"[{self.error_code}] {self.message} - {self.details}"
        return f"[{self.error_code}] {self.message}"


# ==================== 数据相关异常 ====================

class DataError(QuantSystemException):
    """数据相关错误基类"""
    pass


class DataFetchError(DataError):
    """数据获取异常"""
    
    def __init__(
        self,
        message: str = "数据获取失败",
        symbol: Optional[str] = None,
        source: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if symbol:
            details['symbol'] = symbol
        if source:
            details['source'] = source
        
        super().__init__(
            message=message,
            error_code="DATA_FETCH_ERROR",
            details=details
        )


class DataValidationError(DataError):
    """数据验证异常"""
    
    def __init__(
        self,
        message: str = "数据验证失败",
        field: Optional[str] = None,
        value: Optional[Any] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if field:
            details['field'] = field
        if value is not None:
            details['value'] = str(value)
        
        super().__init__(
            message=message,
            error_code="DATA_VALIDATION_ERROR",
            details=details
        )


class DataNotFoundError(DataError):
    """数据不存在异常"""
    
    def __init__(
        self,
        message: str = "数据不存在",
        symbol: Optional[str] = None,
        date: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if symbol:
            details['symbol'] = symbol
        if date:
            details['date'] = date
        
        super().__init__(
            message=message,
            error_code="DATA_NOT_FOUND",
            details=details
        )


class DataPersistenceError(DataError):
    """数据持久化异常"""
    
    def __init__(
        self,
        message: str = "数据持久化失败",
        table: Optional[str] = None,
        operation: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if table:
            details['table'] = table
        if operation:
            details['operation'] = operation
        
        super().__init__(
            message=message,
            error_code="DATA_PERSISTENCE_ERROR",
            details=details
        )


# ==================== 策略相关异常 ====================

class StrategyError(QuantSystemException):
    """策略相关错误基类"""
    pass


class StrategyNotFoundError(StrategyError):
    """策略不存在异常"""
    
    def __init__(
        self,
        message: str = "策略不存在",
        strategy_name: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if strategy_name:
            details['strategy_name'] = strategy_name
        
        super().__init__(
            message=message,
            error_code="STRATEGY_NOT_FOUND",
            details=details
        )


class StrategyExecutionError(StrategyError):
    """策略执行异常"""
    
    def __init__(
        self,
        message: str = "策略执行失败",
        strategy_name: Optional[str] = None,
        phase: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if strategy_name:
            details['strategy_name'] = strategy_name
        if phase:
            details['phase'] = phase
        
        super().__init__(
            message=message,
            error_code="STRATEGY_EXECUTION_ERROR",
            details=details
        )


class StrategyConfigError(StrategyError):
    """策略配置异常"""
    
    def __init__(
        self,
        message: str = "策略配置错误",
        config_key: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if config_key:
            details['config_key'] = config_key
        
        super().__init__(
            message=message,
            error_code="STRATEGY_CONFIG_ERROR",
            details=details
        )


# ==================== 交易相关异常 ====================

class TradingError(QuantSystemException):
    """交易相关错误基类"""
    pass


class OrderError(TradingError):
    """订单异常"""
    
    def __init__(
        self,
        message: str = "订单处理失败",
        order_id: Optional[str] = None,
        symbol: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if order_id:
            details['order_id'] = order_id
        if symbol:
            details['symbol'] = symbol
        
        super().__init__(
            message=message,
            error_code="ORDER_ERROR",
            details=details
        )


class InsufficientFundsError(TradingError):
    """资金不足异常"""
    
    def __init__(
        self,
        message: str = "资金不足",
        required: Optional[float] = None,
        available: Optional[float] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if required is not None:
            details['required'] = required
        if available is not None:
            details['available'] = available
        
        super().__init__(
            message=message,
            error_code="INSUFFICIENT_FUNDS",
            details=details
        )


# ==================== 风控相关异常 ====================

class RiskCheckError(QuantSystemException):
    """风控检查异常"""
    
    def __init__(
        self,
        message: str = "风控检查失败",
        risk_type: Optional[str] = None,
        limit: Optional[float] = None,
        actual: Optional[float] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if risk_type:
            details['risk_type'] = risk_type
        if limit is not None:
            details['limit'] = limit
        if actual is not None:
            details['actual'] = actual
        
        super().__init__(
            message=message,
            error_code="RISK_CHECK_FAILED",
            details=details
        )


# ==================== API 相关异常 ====================

class APIError(QuantSystemException):
    """API 相关错误基类"""
    pass


class AuthenticationError(APIError):
    """认证失败异常"""
    
    def __init__(
        self,
        message: str = "认证失败",
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
            details=kwargs.get('details', {})
        )


class AuthorizationError(APIError):
    """权限不足异常"""
    
    def __init__(
        self,
        message: str = "权限不足",
        required_role: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if required_role:
            details['required_role'] = required_role
        
        super().__init__(
            message=message,
            error_code="AUTHORIZATION_ERROR",
            details=details
        )


class RateLimitError(APIError):
    """请求限流异常"""
    
    def __init__(
        self,
        message: str = "请求过于频繁",
        retry_after: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if retry_after:
            details['retry_after'] = retry_after
        
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            details=details
        )


class ValidationError(APIError):
    """输入验证异常"""
    
    def __init__(
        self,
        message: str = "输入验证失败",
        field: Optional[str] = None,
        constraint: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if field:
            details['field'] = field
        if constraint:
            details['constraint'] = constraint
        
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            details=details
        )


# ==================== 配置相关异常 ====================

class ConfigError(QuantSystemException):
    """配置相关错误基类"""
    pass


class ConfigNotFoundError(ConfigError):
    """配置不存在异常"""
    
    def __init__(
        self,
        message: str = "配置不存在",
        config_key: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if config_key:
            details['config_key'] = config_key
        
        super().__init__(
            message=message,
            error_code="CONFIG_NOT_FOUND",
            details=details
        )


class ConfigValidationError(ConfigError):
    """配置验证异常"""
    
    def __init__(
        self,
        message: str = "配置验证失败",
        config_file: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if config_file:
            details['config_file'] = config_file
        
        super().__init__(
            message=message,
            error_code="CONFIG_VALIDATION_ERROR",
            details=details
        )


# ==================== 系统相关异常 ====================

class SystemError(QuantSystemException):
    """系统相关错误基类"""
    pass


class ConnectionError(SystemError):
    """连接异常"""
    
    def __init__(
        self,
        message: str = "连接失败",
        service: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if service:
            details['service'] = service
        
        super().__init__(
            message=message,
            error_code="CONNECTION_ERROR",
            details=details
        )


class TimeoutError(SystemError):
    """超时异常"""
    
    def __init__(
        self,
        message: str = "操作超时",
        operation: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if operation:
            details['operation'] = operation
        if timeout:
            details['timeout'] = timeout
        
        super().__init__(
            message=message,
            error_code="TIMEOUT_ERROR",
            details=details
        )


class ResourceExhaustedError(SystemError):
    """资源耗尽异常"""
    
    def __init__(
        self,
        message: str = "资源不足",
        resource_type: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if resource_type:
            details['resource_type'] = resource_type
        
        super().__init__(
            message=message,
            error_code="RESOURCE_EXHAUSTED",
            details=details
        )
