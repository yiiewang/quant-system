"""
核心数据模型
定义系统中使用的所有数据结构
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional, Callable
import pandas as pd

# 导入 Frequency 用于验证
from src.data import Frequency


# ==================== 引擎模式 ====================

class EngineMode(Enum):
    """引擎运行模式"""
    BACKTEST = "backtest"    # 回测模式：历史数据重放，模拟交易计算收益
    LIVE = "live"            # 实时模式：实时数据运行策略，发送信号通知
    ANALYZE = "analyze"      # 分析模式：一次性分析当前状态


# ==================== 引擎相关 ====================

class EngineState(Enum):
    """引擎状态"""
    IDLE = "idle"           # 空闲
    RUNNING = "running"     # 运行中
    PAUSED = "paused"       # 暂停
    STOPPED = "stopped"     # 已停止
    ERROR = "error"         # 错误


@dataclass
class EngineConfig:
    """
    引擎配置

    Attributes:
        mode: 运行模式 (BACKTEST/LIVE/ANALYZE)
        symbols: 交易标的列表
        strategy_name: 策略名称
        strategy_params: 策略参数（由外部配置传入，Engine 负责创建策略实例）
        initial_capital: 初始资金
        poll_interval: 行情轮询间隔（秒）
        frequency: 数据频率 (1min/5min/15min/30min/60min/daily/weekly/monthly)
        data_source: 数据源 (可选，None 表示自动选择)
        max_positions: 最大持仓数量
        enable_risk_check: 是否启用风控检查
        commission: 手续费率
        slippage: 滑点率
    """
    mode: EngineMode = EngineMode.LIVE
    symbols: List[str] = field(default_factory=list)
    strategy_name: str = "macd"
    strategy_config: Optional[str] = None
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    initial_capital: float = 100000.0
    poll_interval: int = 60
    frequency: str = Frequency.DAILY  # 数据频率
    data_source: Optional[str] = None  # 数据源 (None=自动选择)
    max_positions: int = 10
    enable_risk_check: bool = True
    commission: float = 0.0003
    slippage: float = 0.001
    start_date: Optional[str] = None  # 回测开始日期
    end_date: Optional[str] = None  # 回测结束日期
    notify: bool = False  # 是否启用通知
    days: int = 60  # 分析模式历史天数
    data_service: Any = None  # 注入的数据服务实例（Runner统一初始化）
# ==================== 信号相关 ====================

class SignalType(Enum):
    """信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class Signal:
    """交易信号"""
    symbol: str
    signal_type: SignalType
    price: float
    reason: str = ""
    strength: float = 1.0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'signal_type': self.signal_type.value,
            'price': self.price,
            'strength': self.strength,
            'reason': self.reason,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }


# ==================== 订单相关 ====================

class OrderType(Enum):
    """订单类型"""
    MARKET = "market"           # 市价单
    LIMIT = "limit"             # 限价单
    STOP = "stop"               # 止损单


class OrderSide(Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"         # 待执行
    SUBMITTED = "submitted"     # 已提交
    FILLED = "filled"           # 已成交
    CANCELLED = "cancelled"     # 已取消
    REJECTED = "rejected"       # 已拒绝


@dataclass
class Order:
    """订单"""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float
    order_id: str = field(default_factory=lambda: __import__('uuid').uuid4().hex[:8].upper())
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    filled_price: float = 0.0
    commission: float = 0.0
    message: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    # 向后兼容
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def is_active(self) -> bool:
        """订单是否仍可操作"""
        return self.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'order_id': self.order_id,
            'symbol': self.symbol,
            'side': self.side.value,
            'order_type': self.order_type.value,
            'quantity': self.quantity,
            'price': self.price,
            'status': self.status.value,
            'filled_quantity': self.filled_quantity,
            'filled_price': self.filled_price,
            'commission': self.commission,
            'message': self.message,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class OrderResult:
    """订单执行结果（向后兼容保留）"""
    symbol: str
    side: OrderSide
    quantity: int
    filled_quantity: int
    filled_price: float
    commission: float
    is_filled: bool
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'side': self.side.value,
            'quantity': self.quantity,
            'filled_quantity': self.filled_quantity,
            'filled_price': self.filled_price,
            'commission': self.commission,
            'is_filled': self.is_filled,
            'message': self.message,
            'timestamp': self.timestamp.isoformat()
        }


# ==================== 持仓相关 ====================

@dataclass
class Position:
    """持仓信息"""
    symbol: str
    quantity: int
    avg_cost: float
    current_price: float = 0.0
    realized_pnl: float = 0.0

    def update_price(self, price: float) -> None:
        """更新当前价格"""
        self.current_price = price

    @property
    def market_value(self) -> float:
        """市值"""
        return self.quantity * self.current_price
    
    @property
    def unrealized_pnl(self) -> float:
        """未实现盈亏"""
        return (self.current_price - self.avg_cost) * self.quantity
    
    @property
    def unrealized_pnl_pct(self) -> float:
        """未实现盈亏百分比"""
        if self.avg_cost == 0:
            return 0.0
        return (self.current_price - self.avg_cost) / self.avg_cost

    @property
    def profit_pct(self) -> float:
        """盈亏百分比（unrealized_pnl_pct 别名）"""
        return self.unrealized_pnl_pct


@dataclass
class Portfolio:
    """投资组合"""
    cash: float = 0.0
    total_value: float = 0.0
    position_value: float = 0.0
    daily_pnl: float = 0.0
    positions: Dict[str, 'Position'] = field(default_factory=dict)
    total_pnl: float = 0.0
    initial_capital: float = 0.0

    def get_position(self, symbol: str) -> Optional['Position']:
        """获取持仓"""
        pos = self.positions.get(symbol)
        return pos if (pos and pos.quantity > 0) else None

    def has_position(self, symbol: str) -> bool:
        """是否有持仓"""
        pos = self.positions.get(symbol)
        return pos is not None and pos.quantity > 0

    @property
    def position_count(self) -> int:
        """持仓数量"""
        return sum(1 for p in self.positions.values() if p.quantity > 0)

    def update_position(self, symbol: str, quantity: int, price: float) -> None:
        """更新持仓"""
        if quantity == 0:
            if symbol in self.positions:
                del self.positions[symbol]
            return

        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol, quantity, price)
        else:
            pos = self.positions[symbol]
            new_qty = pos.quantity + quantity
            if new_qty == 0:
                del self.positions[symbol]
            else:
                total_cost = pos.quantity * pos.avg_cost + quantity * price
                pos.quantity = new_qty
                pos.avg_cost = total_cost / new_qty

        self._recalculate()

    def _recalculate(self) -> None:
        """重新计算总市值"""
        self.position_value = sum(p.market_value for p in self.positions.values() if p.quantity > 0)
        self.total_value = self.cash + self.position_value

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'cash': self.cash,
            'total_value': self.total_value,
            'position_value': self.position_value,
            'daily_pnl': self.daily_pnl,
            'positions': {
                symbol: {
                    'quantity': p.quantity,
                    'avg_cost': p.avg_cost,
                    'current_price': p.current_price,
                    'market_value': p.market_value,
                    'unrealized_pnl': p.unrealized_pnl,
                    'unrealized_pnl_pct': p.unrealized_pnl_pct
                }
                for symbol, p in self.positions.items() if p.quantity > 0
            }
        }


# ==================== 回测结果 ====================




# ==================== 策略决策 ====================

@dataclass
class StrategyDecision:
    """
    策略决策结果
    
    统一的策略输出，包含交易信号和分析信息。
    """
    symbol: str
    signal_type: SignalType  # BUY/SELL/HOLD
    price: float = 0.0
    
    # 分析信息
    status: str = ""  # 市场状态描述，如 "多头趋势"
    action: str = ""  # 建议操作，如 "买入"/"卖出"/"观望"
    reason: str = ""  # 详细理由
    indicators: Dict[str, Any] = field(default_factory=dict)  # 关键指标值
    
    # 通用字段
    confidence: float = 1.0  # 置信度 0-1
    strength: float = 1.0  # 信号强度
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def hold(cls, symbol: str, reason: str = "") -> 'StrategyDecision':
        """创建持有决策"""
        return cls(
            symbol=symbol,
            signal_type=SignalType.HOLD,
            status="观望",
            action="持有",
            reason=reason
        )
    
    @classmethod
    def buy(cls, symbol: str, price: float, reason: str = "", 
            status: str = "", indicators: Optional[Dict] = None) -> 'StrategyDecision':
        """创建买入决策"""
        return cls(
            symbol=symbol,
            signal_type=SignalType.BUY,
            price=price,
            status=status or "买入信号",
            action="买入",
            reason=reason,
            indicators=indicators or {}
        )
    
    @classmethod
    def sell(cls, symbol: str, price: float, reason: str = "",
             status: str = "", indicators: Optional[Dict] = None) -> 'StrategyDecision':
        """创建卖出决策"""
        return cls(
            symbol=symbol,
            signal_type=SignalType.SELL,
            price=price,
            status=status or "卖出信号",
            action="卖出",
            reason=reason,
            indicators=indicators or {}
        )


# ==================== 交易记录 ====================

@dataclass
class Trade:
    """成交记录"""
    symbol: str
    side: OrderSide  # 买入/卖出
    price: float
    quantity: int
    trade_id: str = field(default_factory=lambda: __import__('uuid').uuid4().hex[:8].upper())
    order_id: Optional[str] = None
    amount: float = 0.0   # 成交金额（可选，price*quantity）
    commission: float = 0.0  # 手续费
    timestamp: Optional[datetime] = field(default_factory=datetime.now)


# ==================== 策略上下文 ====================
# 从公共模块导入，避免循环导入和类型不兼容
from src.common import StrategyContext

# ==================== 通知相关 ====================

@dataclass
class NotifyMessage:
    """通知消息"""
    title: str
    content: str
    message_type: str = "signal"  # signal, alert, summary
    symbol: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseNotifier:
    """通知器基类"""
    
    def send_signal(self, symbol: str, signal_type: str, price: float, 
                    reason: str, indicators: Optional[Dict[str, Any]] = None,
                    additional_info: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        """发送交易信号通知"""
        raise NotImplementedError
    
    def send_alert(self, title: str, message: str) -> bool:
        """发送告警通知"""
        raise NotImplementedError
    
    def send_daily_summary(self, portfolio_value: float, daily_pnl: float,
                          positions: List[Dict], signals: List[Dict]) -> bool:
        """发送每日汇总"""
        raise NotImplementedError


# ==================== 分析结果 ====================

@dataclass  
class AnalysisResult:
    """分析结果"""
    symbol: str
    signal_type: str
    price: float
    reason: str = ""
    indicators: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
