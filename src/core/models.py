"""
核心数据模型定义
定义交易系统中使用的基础数据结构
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod


# ==================== 信号相关 ====================

class SignalType(Enum):
    """信号类型"""
    BUY = 1      # 买入信号
    SELL = -1    # 卖出信号
    HOLD = 0     # 持有/观望


@dataclass
class Signal:
    """
    交易信号
    
    Attributes:
        symbol: 股票代码
        signal_type: 信号类型 (BUY/SELL/HOLD)
        price: 当前价格
        timestamp: 信号生成时间
        strength: 信号强度 (0.0-1.0)，用于仓位计算
        reason: 信号生成原因描述
        metadata: 额外元数据（如指标值等）
    """
    symbol: str
    signal_type: SignalType
    price: float
    timestamp: datetime = field(default_factory=datetime.now)
    strength: float = 1.0
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """验证数据"""
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError(f"信号强度必须在 0.0-1.0 之间，当前值: {self.strength}")
        if self.price <= 0:
            raise ValueError(f"价格必须为正数，当前值: {self.price}")
    
    def is_buy(self) -> bool:
        """是否为买入信号"""
        return self.signal_type == SignalType.BUY
    
    def is_sell(self) -> bool:
        """是否为卖出信号"""
        return self.signal_type == SignalType.SELL
    
    def is_hold(self) -> bool:
        """是否为持有信号"""
        return self.signal_type == SignalType.HOLD
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'signal_type': self.signal_type.name,
            'price': self.price,
            'timestamp': self.timestamp.isoformat(),
            'strength': self.strength,
            'reason': self.reason,
            'metadata': self.metadata,
        }


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
        symbols: 交易标的列表
        strategy_name: 策略名称
        mode: 运行模式 (paper=模拟, live=实盘)
        initial_capital: 初始资金
        poll_interval: 行情轮询间隔（秒）
        max_positions: 最大持仓数量
        enable_risk_check: 是否启用风控检查
    """
    symbols: List[str]
    strategy_name: str = "macd"
    mode: str = "paper"
    initial_capital: float = 100000.0
    poll_interval: int = 60
    max_positions: int = 10
    enable_risk_check: bool = True
    
    def __post_init__(self):
        """验证配置"""
        if not self.symbols:
            raise ValueError("交易标的列表不能为空")
        if self.mode not in ("paper", "live"):
            raise ValueError(f"运行模式必须是 paper 或 live，当前值: {self.mode}")
        if self.initial_capital <= 0:
            raise ValueError(f"初始资金必须为正数，当前值: {self.initial_capital}")
        if self.poll_interval < 1:
            raise ValueError(f"轮询间隔必须 >= 1 秒，当前值: {self.poll_interval}")


# ==================== 订单相关 ====================

class OrderType(Enum):
    """订单类型"""
    MARKET = "market"           # 市价单
    LIMIT = "limit"             # 限价单
    STOP = "stop"               # 止损单
    STOP_LIMIT = "stop_limit"   # 止损限价单


class OrderSide(Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"         # 待提交
    SUBMITTED = "submitted"     # 已提交
    PARTIAL = "partial"         # 部分成交
    FILLED = "filled"           # 完全成交
    CANCELLED = "cancelled"     # 已取消
    REJECTED = "rejected"       # 被拒绝


@dataclass
class Order:
    """
    订单对象
    
    Attributes:
        symbol: 股票代码
        side: 买/卖方向
        order_type: 订单类型
        quantity: 数量（股）
        price: 限价单价格
        stop_price: 止损价格
        order_id: 订单ID
        status: 订单状态
        filled_quantity: 已成交数量
        filled_price: 成交均价
        commission: 手续费
        created_at: 创建时间
        updated_at: 更新时间
        message: 状态信息
    """
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    order_id: str = ""
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0
    filled_price: float = 0
    commission: float = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    message: str = ""
    
    def __post_init__(self):
        """初始化订单ID"""
        import uuid
        if not self.order_id:
            self.order_id = str(uuid.uuid4())[:8].upper()
    
    @property
    def is_filled(self) -> bool:
        """是否已完全成交"""
        return self.status == OrderStatus.FILLED
    
    @property
    def is_active(self) -> bool:
        """是否为活动订单"""
        return self.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL)
    
    @property
    def unfilled_quantity(self) -> float:
        """未成交数量"""
        return self.quantity - self.filled_quantity
    
    @property
    def filled_value(self) -> float:
        """成交金额"""
        return self.filled_quantity * self.filled_price
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'order_id': self.order_id,
            'symbol': self.symbol,
            'side': self.side.value,
            'order_type': self.order_type.value,
            'quantity': self.quantity,
            'price': self.price,
            'stop_price': self.stop_price,
            'status': self.status.value,
            'filled_quantity': self.filled_quantity,
            'filled_price': self.filled_price,
            'commission': self.commission,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'message': self.message,
        }


# ==================== 持仓相关 ====================

@dataclass
class Position:
    """
    持仓对象
    
    Attributes:
        symbol: 股票代码
        quantity: 持仓数量
        avg_cost: 持仓成本
        current_price: 当前价格
        unrealized_pnl: 浮动盈亏
        realized_pnl: 已实现盈亏
        created_at: 建仓时间
    """
    symbol: str
    quantity: float
    avg_cost: float
    current_price: float = 0
    unrealized_pnl: float = 0
    realized_pnl: float = 0
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def market_value(self) -> float:
        """市值"""
        return self.quantity * self.current_price
    
    @property
    def cost_value(self) -> float:
        """成本值"""
        return self.quantity * self.avg_cost
    
    @property
    def profit_pct(self) -> float:
        """盈亏比例"""
        if self.avg_cost == 0:
            return 0
        return (self.current_price - self.avg_cost) / self.avg_cost
    
    def update_price(self, price: float) -> None:
        """更新当前价格"""
        self.current_price = price
        self.unrealized_pnl = (price - self.avg_cost) * self.quantity
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'quantity': self.quantity,
            'avg_cost': self.avg_cost,
            'current_price': self.current_price,
            'market_value': self.market_value,
            'unrealized_pnl': self.unrealized_pnl,
            'realized_pnl': self.realized_pnl,
            'profit_pct': self.profit_pct,
            'created_at': self.created_at.isoformat(),
        }


@dataclass
class Portfolio:
    """
    投资组合
    
    Attributes:
        cash: 可用现金
        total_value: 总资产
        positions: 持仓字典
        daily_pnl: 当日盈亏
        total_pnl: 累计盈亏
        initial_capital: 初始资金
    """
    cash: float
    total_value: float
    positions: Dict[str, Position] = field(default_factory=dict)
    daily_pnl: float = 0
    total_pnl: float = 0
    initial_capital: float = 0
    
    @property
    def position_value(self) -> float:
        """持仓总市值"""
        return sum(p.market_value for p in self.positions.values())
    
    @property
    def position_count(self) -> int:
        """持仓数量"""
        return len(self.positions)
    
    @property
    def total_return(self) -> float:
        """总收益率"""
        if self.initial_capital == 0:
            return 0
        return (self.total_value - self.initial_capital) / self.initial_capital
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """获取指定持仓"""
        return self.positions.get(symbol)
    
    def has_position(self, symbol: str) -> bool:
        """是否持有某股票"""
        return symbol in self.positions and self.positions[symbol].quantity > 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'cash': self.cash,
            'total_value': self.total_value,
            'position_value': self.position_value,
            'position_count': self.position_count,
            'daily_pnl': self.daily_pnl,
            'total_pnl': self.total_pnl,
            'total_return': self.total_return,
            'positions': {s: p.to_dict() for s, p in self.positions.items()},
        }


# ==================== 交易记录 ====================

@dataclass
class Trade:
    """
    成交记录
    
    Attributes:
        trade_id: 成交ID
        order_id: 关联订单ID
        symbol: 股票代码
        side: 买/卖方向
        quantity: 成交数量
        price: 成交价格
        commission: 手续费
        timestamp: 成交时间
        strategy: 策略名称
    """
    trade_id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float = 0
    timestamp: datetime = field(default_factory=datetime.now)
    strategy: str = ""
    
    def __post_init__(self):
        """初始化"""
        import uuid
        if not self.trade_id:
            self.trade_id = str(uuid.uuid4())[:8].upper()
    
    @property
    def amount(self) -> float:
        """成交金额"""
        return self.quantity * self.price
    
    @property
    def net_amount(self) -> float:
        """净成交金额（扣除手续费）"""
        if self.side == OrderSide.BUY:
            return self.amount + self.commission
        return self.amount - self.commission
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'trade_id': self.trade_id,
            'order_id': self.order_id,
            'symbol': self.symbol,
            'side': self.side.value,
            'quantity': self.quantity,
            'price': self.price,
            'amount': self.amount,
            'commission': self.commission,
            'timestamp': self.timestamp.isoformat(),
            'strategy': self.strategy,
        }


# ==================== K线数据 ====================

@dataclass
class Bar:
    """
    K线数据
    
    Attributes:
        symbol: 股票代码
        timestamp: 时间
        open: 开盘价
        high: 最高价
        low: 最低价
        close: 收盘价
        volume: 成交量
        amount: 成交额
    """
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float = 0
    
    @property
    def typical_price(self) -> float:
        """典型价格 (H+L+C)/3"""
        return (self.high + self.low + self.close) / 3
    
    @property
    def range(self) -> float:
        """振幅"""
        return self.high - self.low
    
    @property
    def range_pct(self) -> float:
        """振幅比例"""
        if self.open == 0:
            return 0
        return self.range / self.open
    
    @property
    def change(self) -> float:
        """涨跌额"""
        return self.close - self.open
    
    @property
    def change_pct(self) -> float:
        """涨跌幅"""
        if self.open == 0:
            return 0
        return self.change / self.open
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'amount': self.amount,
        }


# ==================== 分析结果 ====================

@dataclass
class AnalysisResult:
    """
    策略分析结果
    
    由策略的 analyze_status() 方法返回，
    框架层负责格式化输出和决定是否发送通知。
    
    Attributes:
        symbol: 股票代码
        timestamp: 分析时间
        status: 当前状态描述 (如: "多头趋势"/"空头趋势"/"震荡")
        action: 建议操作 (如: "买入"/"卖出"/"观望"/"持有")
        reason: 分析理由
        indicators: 关键指标值
        confidence: 置信度 (0.0-1.0)
        metadata: 额外元数据
    """
    symbol: str
    timestamp: datetime
    status: str
    action: str
    reason: str
    indicators: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"置信度必须在 0.0-1.0 之间，当前值: {self.confidence}")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'status': self.status,
            'action': self.action,
            'reason': self.reason,
            'indicators': self.indicators,
            'confidence': self.confidence,
            'metadata': self.metadata,
        }


# ==================== 通知消息 ====================

@dataclass
class NotifyMessage:
    """
    通知消息
    
    框架层通知服务使用的统一消息格式。
    
    Attributes:
        title: 消息标题
        content: 消息内容 (纯文本)
        html_content: HTML 格式内容 (可选)
        level: 消息级别 (info/warning/alert)
        metadata: 额外元数据
    """
    title: str
    content: str
    html_content: str = ""
    level: str = "info"
    metadata: Dict[str, Any] = field(default_factory=dict)


# ==================== 通知服务基类 ====================

class BaseNotifier(ABC):
    """
    通知服务基类 (框架层)
    
    定义通知渠道的统一接口，具体实现由各通知渠道提供。
    框架负责调用通知，策略通过 should_notify() 决定是否通知。
    """
    
    @abstractmethod
    def send(self, message: NotifyMessage) -> bool:
        """
        发送通用通知消息
        
        Args:
            message: 通知消息对象
        
        Returns:
            bool: 是否发送成功
        """
        pass
    
    @abstractmethod
    def send_signal(self, signal: 'Signal', analysis: AnalysisResult) -> bool:
        """
        发送交易信号通知
        
        Args:
            signal: 交易信号
            analysis: 策略分析结果
        
        Returns:
            bool: 是否发送成功
        """
        pass
    
    @abstractmethod
    def send_daily_summary(self, summary: Dict[str, Any]) -> bool:
        """
        发送每日汇总
        
        Args:
            summary: 汇总数据字典
        
        Returns:
            bool: 是否发送成功
        """
        pass
