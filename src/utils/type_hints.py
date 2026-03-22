"""
类型注解辅助模块

提供常用的类型注解和类型检查工具
"""
from typing import (
    TypeVar, Generic, Callable, Optional, List, Dict, Any, 
    Union, Tuple, Type, Protocol, runtime_checkable
)
from datetime import datetime
from decimal import Decimal
import pandas as pd
import numpy as np


# ==================== 基础类型别名 ====================

# 数值类型
Number = Union[int, float, Decimal]

# 字符串类型
Symbol = str  # 股票代码
DateStr = str  # 日期字符串 (YYYY-MM-DD)
DateTimeStr = str  # 日期时间字符串 (YYYY-MM-DD HH:MM:SS)

# 价格和数量
Price = float
Quantity = int
Amount = float

# Pandas 类型
DataFrame = pd.DataFrame
Series = pd.Series

# ==================== 泛型类型变量 ====================

T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')


# ==================== 协议（Protocol）====================

@runtime_checkable
class DataProvider(Protocol):
    """数据提供者协议"""
    
    def fetch(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> pd.DataFrame:
        """获取数据"""
        ...


@runtime_checkable
class Strategy(Protocol):
    """策略协议"""
    
    def on_bar(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理行情数据"""
        ...
    
    def on_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理逐笔数据"""
        ...


@runtime_checkable
class RiskManager(Protocol):
    """风控管理器协议"""
    
    def check_order(self, order: Dict[str, Any]) -> bool:
        """检查订单"""
        ...
    
    def check_position(self, position: Dict[str, Any]) -> bool:
        """检查持仓"""
        ...


# ==================== 通用类型 ====================

class Result(Generic[T]):
    """
    通用结果类型
    
    用于函数返回值，支持成功和错误状态
    
    Usage:
        def divide(a: float, b: float) -> Result[float]:
            if b == 0:
                return Result.error("除数不能为 0")
            return Result.success(a / b)
        
        result = divide(10, 2)
        if result.is_success():
            print(result.value)  # 5.0
        else:
            print(result.error)  # None
    """
    
    def __init__(
        self,
        value: Optional[T] = None,
        error: Optional[str] = None,
        success: bool = True
    ):
        self._value = value
        self._error = error
        self._success = success
    
    @classmethod
    def success(cls, value: T) -> 'Result[T]':
        """创建成功结果"""
        return cls(value=value, success=True)
    
    @classmethod
    def error(cls, error: str) -> 'Result[T]':
        """创建错误结果"""
        return cls(error=error, success=False)
    
    def is_success(self) -> bool:
        """是否成功"""
        return self._success
    
    def is_error(self) -> bool:
        """是否失败"""
        return not self._success
    
    @property
    def value(self) -> Optional[T]:
        """获取值（成功时）"""
        if not self._success:
            raise ValueError("无法获取失败结果的值")
        return self._value
    
    @property
    def error(self) -> Optional[str]:
        """获取错误信息（失败时）"""
        if self._success:
            raise ValueError("无法获取成功结果的错误信息")
        return self._error
    
    def unwrap(self, default: Optional[T] = None) -> Optional[T]:
        """
        获取值或默认值
        
        Args:
            default: 失败时返回的默认值
        
        Returns:
            成功时返回值，失败时返回默认值
        """
        if self._success:
            return self._value
        return default


# ==================== 回调类型 ====================

# 基础回调
Callback = Callable[..., None]

# 事件回调
EventCallback = Callable[[Dict[str, Any]], None]

# 异步回调
AsyncCallback = Callable[..., Any]  # 可以是协程

# 数据回调
DataCallback = Callable[[pd.DataFrame], None]

# 策略回调
StrategyCallback = Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]


# ==================== 订单和持仓类型 ====================

class OrderSide:
    """订单方向"""
    BUY = 'buy'
    SELL = 'sell'


class OrderType:
    """订单类型"""
    MARKET = 'market'
    LIMIT = 'limit'
    STOP = 'stop'
    STOP_LIMIT = 'stop_limit'


class OrderStatus:
    """订单状态"""
    PENDING = 'pending'
    SUBMITTED = 'submitted'
    FILLED = 'filled'
    PARTIAL = 'partial'
    CANCELLED = 'cancelled'
    REJECTED = 'rejected'


class PositionSide:
    """持仓方向"""
    LONG = 'long'
    SHORT = 'short'


# ==================== 数据结构类型 ====================

# 订单数据
OrderData = Dict[str, Any]

# 持仓数据
PositionData = Dict[str, Any]

# 账户数据
AccountData = Dict[str, Any]

# 行情数据
BarData = Dict[str, Any]

# 逐笔数据
TickData = Dict[str, Any]

# 交易信号
SignalData = Dict[str, Any]


# ==================== 类型检查工具 ====================

def check_type(value: Any, expected_type: Type) -> bool:
    """
    检查值是否符合预期类型
    
    Args:
        value: 待检查的值
        expected_type: 预期类型
    
    Returns:
        bool: 是否符合类型
    
    Usage:
        check_type(42, int)  # True
        check_type("hello", str)  # True
        check_type([1, 2, 3], List[int])  # True
    """
    try:
        # 对于基本类型
        if expected_type in (int, float, str, bool, bytes):
            return isinstance(value, expected_type)
        
        # 对于复杂类型（使用 typing 模块）
        from typing import get_origin, get_args
        
        origin = get_origin(expected_type)
        args = get_args(expected_type)
        
        if origin is None:
            # 简单类型
            return isinstance(value, expected_type)
        
        # 处理 List, Dict 等容器类型
        if origin is list:
            if not isinstance(value, list):
                return False
            if args:
                element_type = args[0]
                return all(check_type(item, element_type) for item in value)
            return True
        
        if origin is dict:
            if not isinstance(value, dict):
                return False
            if args and len(args) == 2:
                key_type, value_type = args
                return all(
                    check_type(k, key_type) and check_type(v, value_type)
                    for k, v in value.items()
                )
            return True
        
        if origin is Union:
            return any(check_type(value, t) for t in args)
        
        # 其他情况，使用 isinstance
        return isinstance(value, expected_type)
        
    except Exception:
        return False


def validate_dataframe(
    df: pd.DataFrame,
    required_columns: Optional[List[str]] = None,
    column_types: Optional[Dict[str, Type]] = None
) -> bool:
    """
    验证 DataFrame 结构
    
    Args:
        df: 待验证的 DataFrame
        required_columns: 必需的列
        column_types: 列类型要求
    
    Returns:
        bool: 是否符合要求
    """
    if not isinstance(df, pd.DataFrame):
        return False
    
    if df.empty:
        return False
    
    # 检查必需列
    if required_columns:
        for col in required_columns:
            if col not in df.columns:
                return False
    
    # 检查列类型
    if column_types:
        for col, expected_type in column_types.items():
            if col not in df.columns:
                continue
            
            # 检查数据类型
            actual_type = df[col].dtype
            if expected_type == str:
                if not pd.api.types.is_string_dtype(actual_type):
                    return False
            elif expected_type == int:
                if not pd.api.types.is_integer_dtype(actual_type):
                    return False
            elif expected_type == float:
                if not pd.api.types.is_float_dtype(actual_type):
                    return False
            elif expected_type == datetime:
                if not pd.api.types.is_datetime64_any_dtype(actual_type):
                    return False
    
    return True


def enforce_types(func: Callable) -> Callable:
    """
    类型强制装饰器（运行时类型检查）
    
    Usage:
        @enforce_types
        def process_data(
            symbol: str,
            prices: List[float]
        ) -> Dict[str, float]:
            return {'symbol': symbol, 'avg': sum(prices) / len(prices)}
    """
    import functools
    from typing import get_type_hints
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # 获取类型提示
        hints = get_type_hints(func)
        
        # 检查参数类型
        sig = functools.signature(func)
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()
        
        for param_name, param_value in bound_args.arguments.items():
            if param_name in hints and param_name != 'return':
                expected_type = hints[param_name]
                if not check_type(param_value, expected_type):
                    raise TypeError(
                        f"参数 '{param_name}' 类型错误: "
                        f"预期 {expected_type}, 实际 {type(param_value)}"
                    )
        
        # 执行函数
        result = func(*args, **kwargs)
        
        # 检查返回值类型
        if 'return' in hints:
            expected_return = hints['return']
            if not check_type(result, expected_return):
                raise TypeError(
                    f"返回值类型错误: "
                    f"预期 {expected_return}, 实际 {type(result)}"
                )
        
        return result
    
    return wrapper
