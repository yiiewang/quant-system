# API 参考文档

本节提供量化交易系统的完整 API 参考文档，包括核心接口、数据模型、配置参数等。

## 目录

- [核心模块](#核心模块)
- [数据模型](#数据模型)
- [策略接口](#策略接口)
- [执行器接口](#执行器接口)
- [风控接口](#风控接口)
- [数据接口](#数据接口)
- [配置参数](#配置参数)

---

## 核心模块

### TradingEngine

交易引擎是系统的核心协调器。

```python
class TradingEngine:
    """交易引擎"""
    
    def __init__(self, config: Dict[str, Any])
    def add_strategy(self, strategy: BaseStrategy) -> None
    def add_symbols(self, symbols: List[str]) -> None
    def set_broker(self, broker: BaseExecutor) -> None
    def set_risk_manager(self, risk_manager: RiskManager) -> None
    def run_backtest(self, start_date: str, end_date: str) -> BacktestResult
    def run_monitor(self, symbols: List[str]) -> None
    def run_analyze(self, symbols: List[str]) -> None
```

**主要方法**:

- `add_strategy()`: 添加交易策略
- `run_backtest()`: 运行历史回测
- `run_monitor()`: 启动实时监控
- `run_analyze()`: 运行策略分析

### EventBus

事件总线实现模块间通信。

```python
class EventBus:
    """事件总线"""
    
    def subscribe(self, event_type: Type[Event], handler: Callable) -> None
    def unsubscribe(self, event_type: Type[Event], handler: Callable) -> None
    def publish(self, event: Event) -> None
    def clear() -> None
```

---

## 数据模型

### Signal

交易信号模型。

```python
@dataclass
class Signal:
    """交易信号"""
    symbol: str
    signal_type: SignalType
    price: float
    strength: float
    reason: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
```

**字段说明**:
- `symbol`: 交易标的代码
- `signal_type`: 信号类型 (BUY/SELL/HOLD)
- `price`: 信号价格
- `strength`: 信号强度 (0-1)
- `reason`: 信号原因
- `metadata`: 附加信息

### Order

订单模型。

```python
@dataclass
class Order:
    """订单"""
    order_id: str
    symbol: str
    order_type: OrderType
    direction: Direction
    quantity: int
    price: Optional[float]
    status: OrderStatus
    created_at: datetime
    updated_at: datetime
    filled_quantity: int = 0
    filled_price: float = 0.0
    commission: float = 0.0
    message: str = ""
```

### Position

持仓模型。

```python
@dataclass
class Position:
    """持仓"""
    symbol: str
    quantity: int
    avg_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    
    def update_price(self, current_price: float) -> None
    @property
    def profit_pct(self) -> float
```

### Portfolio

投资组合模型。

```python
@dataclass
class Portfolio:
    """投资组合"""
    initial_capital: float
    current_capital: float
    cash: float
    positions: Dict[str, Position]
    
    @property
    def total_value(self) -> float
    @property
    def total_pnl(self) -> float
    @property
    def total_pnl_pct(self) -> float
    @property
    def position_count(self) -> int
```

### Trade

成交记录模型。

```python
@dataclass
class Trade:
    """成交记录"""
    trade_id: str
    order_id: str
    symbol: str
    direction: Direction
    quantity: int
    price: float
    commission: float
    timestamp: datetime
```

---

## 策略接口

### BaseStrategy

策略基类，所有策略的父类。

```python
class BaseStrategy:
    """策略基类"""
    
    name: str
    version: str
    author: str
    description: str
    
    @classmethod
    def default_params(cls) -> Dict[str, Any]
    
    @classmethod
    def param_schema(cls) -> Dict[str, Any]
    
    def __init__(self, params: Optional[Dict[str, Any]] = None)
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame
    
    def generate_signal(self, data: pd.DataFrame, context: StrategyContext) -> Signal
    
    def analyze_status(self, data: pd.DataFrame, symbol: str) -> AnalysisResult
    
    def validate_data(self, data: pd.DataFrame) -> bool
    
    def should_notify(self, signal: Signal, last_signal: Optional[Signal] = None) -> bool
```

**必需方法**:
- `calculate_indicators()`: 计算技术指标
- `generate_signal()`: 生成交易信号

**可选方法**:
- `analyze_status()`: 分析当前状态
- `validate_data()`: 验证数据有效性
- `should_notify()`: 判断是否需要通知

### StrategyContext

策略上下文，提供运行时信息。

```python
@dataclass
class StrategyContext:
    """策略上下文"""
    symbol: str
    position: Optional[Position]
    portfolio: Portfolio
    current_time: datetime
    data_frequency: str = "daily"
```

### AnalysisResult

策略分析结果。

```python
@dataclass
class AnalysisResult:
    """分析结果"""
    symbol: str
    timestamp: datetime
    status: str
    action: str
    reason: str
    confidence: float
    indicators: Dict[str, Any] = field(default_factory=dict)
```

---

## 执行器接口

### BaseExecutor

执行器基类。

```python
class BaseExecutor:
    """执行器基类"""
    
    def submit_order(self, order: Order) -> Order
    
    def cancel_order(self, order_id: str) -> bool
    
    def get_position(self, symbol: str) -> Optional[Position]
    
    def get_account(self) -> Dict[str, Any]
    
    def get_open_orders(self) -> List[Order]
    
    def get_trade_history(self, symbol: Optional[str] = None) -> List[Trade]
```

### SimulatorBroker

模拟执行器。

```python
class SimulatorBroker(BaseExecutor):
    """模拟执行器"""
    
    def __init__(self, 
                 initial_capital: float,
                 commission_rate: float = 0.0003,
                 slippage_rate: float = 0.001)
    
    def set_market_data(self, symbol: str, data: pd.DataFrame) -> None
    
    def reset(self, initial_capital: float) -> None
    
    def get_portfolio(self) -> Portfolio
```

---

## 风控接口

### RiskManager

风控管理器。

```python
class RiskManager:
    """风控管理器"""
    
    def __init__(self, config: Dict[str, Any])
    
    def check_signal(self, signal: Signal, portfolio: Portfolio) -> RiskResult
    
    def check_order(self, order: Order, portfolio: Portfolio) -> RiskResult
    
    def check_position(self, position: Position, portfolio: Portfolio) -> List[RiskAlert]
```

### RiskResult

风控检查结果。

```python
@dataclass
class RiskResult:
    """风控检查结果"""
    approved: bool
    reason: str
    risk_level: RiskLevel
    suggestions: List[str]
    risk_metrics: Dict[str, float] = field(default_factory=dict)
```

### RiskAlert

风险预警。

```python
@dataclass
class RiskAlert:
    """风险预警"""
    alert_type: str
    message: str
    severity: RiskLevel
    timestamp: datetime
    symbol: Optional[str] = None
    current_value: Optional[float] = None
    threshold: Optional[float] = None
```

---

## 数据接口

### MarketDataService

市场数据服务。

```python
class MarketDataService:
    """市场数据服务"""
    
    def __init__(self, config: Dict[str, Any])
    
    def get_historical_data(self, 
                           symbol: str,
                           start_date: str,
                           end_date: str,
                           frequency: str = "daily") -> pd.DataFrame
    
    def get_latest_data(self, symbols: List[str]) -> Dict[str, pd.Series]
    
    def subscribe_realtime(self, symbols: List[str], callback: Callable) -> None
    
    def get_stock_info(self, symbol: str) -> Dict[str, Any]
    
    def sync_data(self, symbols: List[str], days: int = 365) -> None
```

### IndicatorService

技术指标服务。

```python
class IndicatorService:
    """技术指标服务"""
    
    def calculate_macd(self, data: pd.DataFrame, 
                      fast_period: int = 12,
                      slow_period: int = 26,
                      signal_period: int = 9) -> pd.DataFrame
    
    def calculate_rsi(self, data: pd.DataFrame, period: int = 14) -> pd.Series
    
    def calculate_bollinger_bands(self, data: pd.DataFrame,
                                  period: int = 20,
                                  std_dev: float = 2.0) -> pd.DataFrame
    
    def calculate_ema(self, data: pd.Series, period: int) -> pd.Series
    
    def calculate_sma(self, data: pd.Series, period: int) -> pd.Series
```

---

## 配置参数

### 系统配置

```yaml
# config/default.yaml
system:
  log_level: INFO
  data_dir: data
  output_dir: output
  timezone: Asia/Shanghai

database:
  type: sqlite
  path: data/market.db
```

### 策略配置

```yaml
# src/strategy/configs/macd.yaml
strategy:
  name: "MACD"
  class: "src.strategy.macd.MACDStrategy"
  params:
    fast_period: 12
    slow_period: 26
    signal_period: 9
    volume_confirm: true
    volume_ratio: 1.3
    min_data_length: 60
```

### 风控配置

```yaml
risk:
  max_position_pct: 0.3        # 单票最大仓位
  max_total_position: 0.8      # 最大总仓位
  max_position_count: 10       # 最大持仓数量
  stop_loss_pct: 0.05          # 止损比例
  take_profit_pct: 0.15        # 止盈比例
  max_drawdown: 0.2            # 最大回撤
  max_daily_loss: 0.05         # 最大日亏损
  min_order_value: 1000        # 最小订单价值
  max_order_value: 100000      # 最大订单价值
```

### 执行器配置

```yaml
broker:
  type: simulator
  initial_capital: 1000000
  commission_rate: 0.0003      # 手续费率
  slippage_rate: 0.001         # 滑点率
  min_commission: 5.0          # 最小手续费
```

### 通知配置

```yaml
notification:
  enabled: false
  email:
    enabled: false
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
    username: "your-email@gmail.com"
    password: "your-password"
    recipients: ["recipient@example.com"]
  webhook:
    enabled: false
    url: "https://your-webhook-url.com"
```

---

## 工具函数

### 信号创建函数

```python
from src.strategy.base import create_buy_signal, create_sell_signal, create_hold_signal

# 创建买入信号
buy_signal = create_buy_signal(
    symbol="000001.SZ",
    price=10.50,
    strength=0.8,
    reason="金叉买入",
    **metadata
)

# 创建卖出信号
sell_signal = create_sell_signal(
    symbol="000001.SZ",
    price=12.30,
    strength=0.9,
    reason="止盈",
    **metadata
)

# 创建持有信号
hold_signal = create_hold_signal(
    symbol="000001.SZ",
    price=11.20,
    reason="观望"
)
```

### 配置加载函数

```python
from src.config.loader import load_config, load_strategy_config

# 加载系统配置
system_config = load_config("config/default.yaml")

# 加载策略配置
strategy_config = load_strategy_config("src/strategy/configs/macd.yaml")
```

### 回测结果分析

```python
from src.core.metrics import MetricsCalculator

# 创建分析器
calculator = MetricsCalculator()

# 计算绩效指标
metrics = calculator.calculate_metrics(trades, portfolio, benchmark_returns)

# 获取详细报告
report = calculator.generate_detailed_report()
```

---

## 错误处理

### 常见异常类型

```python
# 数据相关异常
class DataError(Exception): pass
class InsufficientDataError(DataError): pass
class InvalidDataError(DataError): pass

# 策略相关异常
class StrategyError(Exception): pass
class InvalidParameterError(StrategyError): pass
class StrategyInitializationError(StrategyError): pass

# 执行相关异常
class ExecutionError(Exception): pass
class OrderExecutionError(ExecutionError): pass
class InsufficientFundsError(ExecutionError): pass

# 风控相关异常
class RiskError(Exception): pass
class RiskLimitExceededError(RiskError): pass
class RiskCheckError(RiskError): pass
```

### 异常处理示例

```python
try:
    result = engine.run_backtest(start_date, end_date)
except InsufficientDataError as e:
    logger.error(f"数据不足: {e}")
except InvalidParameterError as e:
    logger.error(f"参数错误: {e}")
except Exception as e:
    logger.error(f"未知错误: {e}")
    raise
```

---

## 性能优化

### 缓存配置

```python
# 指标缓存
@lru_cache(maxsize=128)
def calculate_rsi_cached(data_hash: str, period: int) -> pd.Series:
    # RSI 计算逻辑
    pass

# 数据缓存
from functools import cached_property

class CachedDataService:
    @cached_property
    def market_data(self) -> pd.DataFrame:
        # 延迟加载市场数据
        return self._load_market_data()
```

### 并发处理

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def process_multiple_symbols(symbols: List[str]):
    """并发处理多个股票"""
    with ThreadPoolExecutor() as executor:
        tasks = []
        for symbol in symbols:
            task = asyncio.get_event_loop().run_in_executor(
                executor, process_symbol, symbol
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        return results
```

---

本 API 参考文档提供了系统的完整接口说明，开发者可以基于这些接口开发自定义策略、执行器和扩展功能。