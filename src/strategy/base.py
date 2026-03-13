"""
策略基类
定义策略接口规范，所有策略必须继承此类
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd
import logging

from src.core.models import Signal, SignalType, Position, Portfolio, AnalysisResult

if TYPE_CHECKING:
    from src.data.market import MarketDataService
    from src.risk.manager import RiskManager
    from src.broker.simulator import SimulatedExecutor

logger = logging.getLogger(__name__)


@dataclass
class StrategyDeps:
    """
    策略依赖注入容器

    由 Engine 在 initialize() 时传入，策略可在 on_start() 中按需使用。
    所有字段均为可选，策略应做 None 判断后再使用。

    Attributes:
        data_service: 数据服务，可用于预热指标、加载历史数据
        risk_manager: 风控管理器，可用于查询仓位限制等
        executor:     执行器，可用于查询初始资金等
    """
    data_service: Optional['MarketDataService'] = None
    risk_manager: Optional['RiskManager'] = None
    executor: Optional['SimulatedExecutor'] = None


@dataclass
class StrategyContext:
    """
    策略上下文
    
    包含策略执行所需的环境信息
    
    Attributes:
        symbol: 当前处理的股票代码
        portfolio: 投资组合
        position: 当前持仓
        timestamp: 当前时间
        params: 策略参数
    """
    symbol: str
    portfolio: Portfolio
    position: Optional[Position] = None
    timestamp: datetime = field(default_factory=datetime.now)
    params: Dict[str, Any] = field(default_factory=dict)


class BaseStrategy(ABC):
    """
    策略基类
    
    所有交易策略必须继承此类并实现抽象方法
    
    Usage:
        class MyStrategy(BaseStrategy):
            name = "MyStrategy"
            version = "1.0.0"
            
            @classmethod
            def default_params(cls) -> Dict[str, Any]:
                return {'period': 20}
            
            def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
                data['ma'] = data['close'].rolling(self.params['period']).mean()
                return data
            
            def generate_signal(self, data: pd.DataFrame, context: StrategyContext) -> Signal:
                # 策略逻辑
                pass
    """
    
    # 策略元信息（子类应覆盖）
    name: str = "BaseStrategy"
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    
    def __init__(self, params: Dict[str, Any] = None):
        """
        初始化策略
        
        Args:
            params: 策略参数，会与默认参数合并
        """
        self.params = {**self.default_params(), **(params or {})}
        self._indicators: Dict[str, Any] = {}
        self._state: Dict[str, Any] = {}
        self._initialized = False
        self._deps: Optional[StrategyDeps] = None  # 由 initialize() 注入

        logger.info(f"初始化策略: {self.name} v{self.version}")
        logger.debug(f"策略参数: {self.params}")
    
    @property
    def min_bars(self) -> int:
        """
        策略所需最小 K 线数量（warmup 期）

        回测循环在可用数据根数 < min_bars 时跳过该 bar，
        避免指标计算基于不足数据产生 NaN 噪声信号。

        默认从 params['min_data_length'] 读取；子类可直接覆盖此 property。
        """
        return int(self.params.get('min_data_length', 60))

    @classmethod
    def default_params(cls) -> Dict[str, Any]:
        """
        默认参数
        
        子类应覆盖此方法返回策略的默认参数
        
        Returns:
            Dict[str, Any]: 参数字典
        """
        return {}
    
    @classmethod
    def param_schema(cls) -> Dict[str, Any]:
        """
        参数模式定义
        
        用于参数验证和UI自动生成
        
        Returns:
            Dict[str, Any]: 参数模式
        
        Example:
            return {
                'period': {
                    'type': 'int',
                    'default': 20,
                    'min': 5,
                    'max': 200,
                    'description': '计算周期'
                }
            }
        """
        return {}
    
    @abstractmethod
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        计算技术指标
        
        在生成信号前调用，用于计算策略所需的技术指标
        
        Args:
            data: OHLCV 数据，包含以下列:
                - date/timestamp: 日期/时间
                - open: 开盘价
                - high: 最高价
                - low: 最低价
                - close: 收盘价
                - volume: 成交量
        
        Returns:
            pd.DataFrame: 添加指标列后的数据
        
        Example:
            def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
                data['ma20'] = data['close'].rolling(20).mean()
                data['ma60'] = data['close'].rolling(60).mean()
                return data
        """
        pass
    
    @abstractmethod
    def generate_signal(self, data: pd.DataFrame, context: StrategyContext) -> Signal:
        """
        生成交易信号
        
        根据计算好的指标数据生成交易信号
        
        Args:
            data: 包含指标的 OHLCV 数据
            context: 策略上下文（包含持仓、组合等信息）
        
        Returns:
            Signal: 交易信号对象
        """
        pass
    
    @abstractmethod
    def analyze_status(self, data: pd.DataFrame, symbol: str) -> AnalysisResult:
        """
        分析当前市场状态 (策略实现)
        
        框架在 analyze 和 monitor 模式中调用此方法。
        策略需要返回当前的市场状态、建议操作和分析理由。
        
        Args:
            data: 包含指标的 OHLCV 数据 (已调用 calculate_indicators)
            symbol: 股票代码
        
        Returns:
            AnalysisResult: 分析结果，包含:
                - status: 当前状态 (如: "多头趋势"/"空头趋势"/"震荡")
                - action: 建议操作 (如: "买入"/"卖出"/"观望")
                - reason: 详细分析理由
                - indicators: 关键指标值
                - confidence: 置信度 (0.0-1.0)
        """
        pass
    
    def should_notify(self, signal: Signal, last_signal: Optional[Signal] = None) -> bool:
        """
        决定是否发送通知 (策略可覆盖)
        
        框架在 monitor 模式中调用此方法决定是否触发通知。
        默认逻辑：信号类型发生变化时通知。
        策略可覆盖此方法实现更复杂的通知逻辑。
        
        Args:
            signal: 当前信号
            last_signal: 上一次信号 (首次为 None)
        
        Returns:
            bool: 是否应该发送通知
        """
        if last_signal is None:
            return signal.signal_type != SignalType.HOLD
        return signal.signal_type != last_signal.signal_type
    
    def validate_data(self, data: pd.DataFrame) -> bool:
        """
        验证数据有效性
        
        Args:
            data: 待验证的数据
        
        Returns:
            bool: 数据是否有效
        """
        if data is None or data.empty:
            logger.warning("数据为空")
            return False
        
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing = [col for col in required_columns if col not in data.columns]
        
        if missing:
            logger.warning(f"缺少必要列: {missing}")
            return False
        
        return True
    
    def validate_params(self) -> bool:
        """
        验证参数有效性
        
        Returns:
            bool: 参数是否有效
        """
        schema = self.param_schema()
        
        for param_name, rules in schema.items():
            if param_name not in self.params:
                if 'default' in rules:
                    self.params[param_name] = rules['default']
                else:
                    logger.error(f"缺少必要参数: {param_name}")
                    return False
            
            value = self.params[param_name]
            
            # 类型检查
            if 'type' in rules:
                expected_type = rules['type']
                if expected_type == 'int' and not isinstance(value, int):
                    logger.error(f"参数类型错误: {param_name} 应为 int")
                    return False
                elif expected_type == 'float' and not isinstance(value, (int, float)):
                    logger.error(f"参数类型错误: {param_name} 应为 float")
                    return False
            
            # 范围检查
            if 'min' in rules and value < rules['min']:
                logger.error(f"参数超出范围: {param_name} < {rules['min']}")
                return False
            if 'max' in rules and value > rules['max']:
                logger.error(f"参数超出范围: {param_name} > {rules['max']}")
                return False
        
        return True
    
    def initialize(self, deps: Optional[StrategyDeps] = None) -> None:
        """
        策略初始化

        在策略开始运行前由 Engine 调用。

        Args:
            deps: 依赖注入容器（Engine 传入 DataService / RiskManager / Executor）。
                  单独测试策略时可不传（默认 None）。
        """
        if self._initialized:
            return
        
        if not self.validate_params():
            raise ValueError("参数验证失败")

        self._deps = deps or StrategyDeps()
        self.on_start(self._deps)
        self._initialized = True
        logger.info(f"策略 {self.name} 初始化完成")
    
    def on_start(self, deps: StrategyDeps) -> None:
        """
        策略启动回调

        子类可覆盖此方法执行启动时的初始化操作，如数据预热、加载模型等。

        Args:
            deps: 依赖注入容器，包含 data_service / risk_manager / executor，
                  使用前应做 None 判断（单测场景下可能为空）。
        """
        pass
    
    def on_stop(self) -> None:
        """
        策略停止回调
        
        子类可覆盖此方法执行停止时的清理操作
        """
        pass
    
    def on_bar(self, bar: Dict[str, Any], context: StrategyContext) -> Optional[Signal]:
        """
        K线回调
        
        每收到一根新K线时调用（可选实现）
        
        Args:
            bar: 当前K线数据
            context: 策略上下文
        
        Returns:
            Optional[Signal]: 交易信号，无信号返回 None
        """
        return None
    
    def on_order_filled(self, order: Any) -> None:
        """
        订单成交回调
        
        订单成交时调用，可用于更新策略状态
        
        Args:
            order: 成交的订单
        """
        pass
    
    def on_position_changed(self, position: Position) -> None:
        """
        持仓变化回调
        
        持仓发生变化时调用
        
        Args:
            position: 变化后的持仓
        """
        pass
    
    def get_indicator(self, name: str) -> Any:
        """
        获取已计算的指标
        
        Args:
            name: 指标名称
        
        Returns:
            Any: 指标值
        """
        return self._indicators.get(name)
    
    def set_indicator(self, name: str, value: Any) -> None:
        """
        设置指标值
        
        Args:
            name: 指标名称
            value: 指标值
        """
        self._indicators[name] = value
    
    def get_state(self, key: str, default: Any = None) -> Any:
        """
        获取策略状态
        
        Args:
            key: 状态键
            default: 默认值
        
        Returns:
            Any: 状态值
        """
        return self._state.get(key, default)
    
    def set_state(self, key: str, value: Any) -> None:
        """
        设置策略状态
        
        Args:
            key: 状态键
            value: 状态值
        """
        self._state[key] = value
    
    def reset(self) -> None:
        """重置策略状态"""
        self._indicators.clear()
        self._state.clear()
        self._initialized = False
    
    def get_info(self) -> Dict[str, Any]:
        """
        获取策略信息
        
        Returns:
            Dict[str, Any]: 策略信息字典
        """
        return {
            'name': self.name,
            'version': self.version,
            'author': self.author,
            'description': self.description,
            'params': self.params,
            'initialized': self._initialized,
        }
    
    def __repr__(self) -> str:
        return f"{self.name}(v{self.version}, params={self.params})"


def create_hold_signal(symbol: str, price: float, reason: str = "") -> Signal:
    """
    创建持有信号的便捷函数
    
    Args:
        symbol: 股票代码
        price: 当前价格
        reason: 原因
    
    Returns:
        Signal: 持有信号
    """
    return Signal(
        symbol=symbol,
        signal_type=SignalType.HOLD,
        price=price,
        reason=reason
    )


def create_buy_signal(symbol: str, price: float, strength: float = 1.0, 
                      reason: str = "", **metadata) -> Signal:
    """
    创建买入信号的便捷函数
    
    Args:
        symbol: 股票代码
        price: 当前价格
        strength: 信号强度
        reason: 原因
        **metadata: 额外元数据
    
    Returns:
        Signal: 买入信号
    """
    return Signal(
        symbol=symbol,
        signal_type=SignalType.BUY,
        price=price,
        strength=strength,
        reason=reason,
        metadata=metadata
    )


def create_sell_signal(symbol: str, price: float, strength: float = 1.0,
                       reason: str = "", **metadata) -> Signal:
    """
    创建卖出信号的便捷函数
    
    Args:
        symbol: 股票代码
        price: 当前价格
        strength: 信号强度
        reason: 原因
        **metadata: 额外元数据
    
    Returns:
        Signal: 卖出信号
    """
    return Signal(
        symbol=symbol,
        signal_type=SignalType.SELL,
        price=price,
        strength=strength,
        reason=reason,
        metadata=metadata
    )
