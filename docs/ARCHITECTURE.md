# quant-macd 项目架构全景

## 一、项目目录结构

```
quant-macd/
├── config/default.yaml            # 系统配置（日志、存储、报告）
├── src/                           # 核心源码
│   ├── main.py                    # 入口：加载 .env + 调用 CLI
│   ├── cli/main.py                # Click CLI 命令定义
│   ├── config/loader.py           # 两层配置加载器
│   ├── core/
│   │   ├── models.py              # 数据模型（Signal, Order, Position, Portfolio...）
│   │   ├── engine.py              # TradingEngine（实时交易主循环）
│   │   └── event_bus.py           # 事件总线（发布-订阅解耦）
│   ├── strategy/
│   │   ├── base.py                # 策略基类 BaseStrategy + StrategyContext
│   │   ├── registry.py            # 策略注册表（单例）
│   │   ├── macd.py                # MACD 日线策略
│   │   ├── macd_weekly.py         # MACD 周线策略
│   │   ├── macd_multi_timeframe.py # 多周期共振策略（月+周+日）
│   │   └── configs/*.yaml         # 各策略专属参数配置
│   ├── runner/
│   │   ├── base.py                # BaseRunner（通用执行流程）
│   │   ├── analyze.py             # AnalyzeRunner（一次性分析）
│   │   ├── monitor.py             # MonitorRunner（循环监控+通知）
│   │   └── backtest.py            # BacktestRunner（历史回测）
│   ├── backtest/
│   │   ├── engine.py              # 回测引擎（逐日遍历 K 线）
│   │   └── metrics.py             # 绩效指标计算
│   ├── broker/
│   │   ├── base.py                # BaseExecutor（抽象）
│   │   └── simulator.py           # SimulatedExecutor（模拟撮合）
│   ├── risk/manager.py            # 7项风控规则 + 自定义扩展
│   ├── data/
│   │   ├── market.py              # 3个数据源 Provider + SQLite 缓存
│   │   ├── indicator.py           # 技术指标计算器
│   │   └── portfolio.py           # 持仓管理
│   └── notification/
│       ├── email_notifier.py      # SMTP 邮件
│       └── webhook_notifier.py    # 企业微信/钉钉/飞书
├── data/market.db                 # SQLite 行情缓存（gitignored）
├── output/                        # 图表、权益曲线、交易记录
├── logs/                          # 日志
└── tests/                         # 单元测试
```

## 二、架构分层

```
┌─────────────────────────────────────────────────────────┐
│                    CLI 层 (cli/main.py)                  │
│  strategy | run | backtest | analyze | monitor | data    │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                   Runner 层 (runner/)                     │
│   AnalyzeRunner  │  MonitorRunner  │  BacktestRunner     │
│              统一: 初始化策略 + 数据服务 + 通知器          │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                   策略层 (strategy/)                      │
│   BaseStrategy → MACDStrategy / WeeklyMACD / MultiTF     │
│   StrategyRegistry（注册表，按名称查找）                    │
│   接口: calculate_indicators → generate_signal → analyze  │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│              核心框架层 (core/ + backtest/ + broker/)      │
│   TradingEngine (实时)  │  BacktestEngine (回测)          │
│   SimulatedExecutor     │  RiskManager (7项风控)          │
│   EventBus (发布-订阅)                                    │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                基础设施层 (data/ + config/ + notification/)│
│   MarketDataService (Tushare/AKShare/BaoStock → SQLite)  │
│   IndicatorCalculator (MACD/RSI/KDJ/ATR/布林带)          │
│   ConfigLoader (SystemConfig + StrategyConfig → Config)   │
│   EmailNotifier / WebhookNotifier                         │
└─────────────────────────────────────────────────────────┘
```

## 三、初始化流程

以推荐的 `strategy` 统一命令为例：

```bash
python -m src.main strategy --strategy-config src/strategy/configs/macd.yaml -m analyze
```

```
1. src/main.py
   ├── load_dotenv()                       # 加载 .env（TUSHARE_TOKEN, SMTP 等）
   └── cli()                               # 进入 Click CLI

2. cli() → strategy_cmd()
   ├── _ensure_strategies_registered()      # 确保策略已注册
   │   └── import src.strategy              # 触发 __init__.py
   │       ├── registry.register('macd', MACDStrategy)
   │       ├── registry.register('multi_timeframe', MultiTimeframeMACDStrategy)
   │       └── registry.register('weekly', WeeklyMACDStrategy)
   │
   ├── load_system_config()                 # 加载 config/default.yaml → SystemConfig
   │
   ├── load_config(strategy_config_path)    # 加载策略配置
   │   ├── _load_yaml()                     # 读取 YAML
   │   ├── _substitute_env_vars()           # ${VAR:-default} 替换
   │   └── Config.from_system_and_strategy()# 合并系统+策略配置
   │
   ├── RunParams(mode, symbols, ...).merge_with_config(config)
   │   └── 优先级: CLI参数 > YAML配置 > 代码默认值
   │
   └── runner_cls(config, params).run()     # 根据 mode 选择 Runner
       ↓
```

## 四、运行时流程（4种模式）

### 4.1 Analyze（分析模式）— 一次性执行

```
AnalyzeRunner.run()
  ├── _init_strategy()          → registry.create('macd', params) → MACDStrategy
  ├── _init_data_service()      → MarketDataService(source=baostock)
  └── execute()
       └── for symbol in symbols:
            ├── data_service.get_history(symbol, start, end)
            │   └── SQLite 有缓存 → 直接返回; 无 → 远程拉取 → 存库
            ├── strategy.calculate_indicators(data)
            │   └── 计算 EMA → MACD(DIF) → Signal(DEA) → Histogram → 量比 → 金叉/死叉标记
            ├── strategy.analyze_status(data, symbol)
            │   └── 返回 AnalysisResult(状态, 建议操作, 置信度, 分析理由, 关键指标)
            └── 控制台输出分析结果
```

### 4.2 Monitor（监控模式）— 持续循环

```
MonitorRunner.run() → execute()
  └── while True:
       └── for symbol in symbols:
            ├── get_history → calculate_indicators → analyze_status
            ├── generate_signal(data, context) → Signal(type, price, strength, reason)
            ├── should_notify(signal, last_signal)
            │   └── 信号类型发生变化时触发
            └── if 需通知 → notifier.send(symbol, signal_type, price, reason)
       sleep(interval)
```

### 4.3 Backtest（回测模式）— 历史验证

```
BacktestRunner.run() → execute()
  ├── 创建 BacktestEngine(strategy, symbols, start, end, capital)
  │   ├── SimulatedExecutor(capital, commission=0.0003, slippage=0.002)
  │   └── RiskManager(max_position=0.3, stop_loss=8%, take_profit=25%)
  │
  └── engine.run()
       ├── load_data()                     # 从 SQLite 加载历史数据
       ├── strategy.initialize()           # 参数验证 + on_start()
       └── for date in 所有交易日:
            └── for symbol in symbols:
                 ├── 截取[0..当日]的数据窗口
                 ├── executor.update_price(symbol, close)
                 ├── strategy.calculate_indicators(data)
                 ├── strategy.generate_signal(data, context)
                 │
                 ├── if BUY:
                 │    ├── risk_manager.check_signal()      # 7项风控检查
                 │    ├── risk_manager.calculate_position_size()
                 │    └── executor.submit_order(BUY)       # 模拟成交
                 ├── if SELL:
                 │    └── executor.submit_order(SELL)
                 │
                 ├── check_stop_loss / check_take_profit   # 止盈止损
                 └── record_equity()                       # 记录净值
       │
       └── metrics.calculate() → BacktestResult
            (总收益率, 年化收益, 最大回撤, 夏普比率, 胜率, 交易次数)
```

### 4.4 Run（实时交易引擎）— 生产交易

```
TradingEngine(config).start()
  ├── _initialize_components()
  │   ├── registry.create(strategy) → strategy.initialize()
  │   ├── SimulatedExecutor(capital)
  │   ├── RiskManager(config)
  │   └── MarketDataService(LOCAL)
  │
  └── _run_loop()
       └── while not stop:
            ├── if 非交易时间 → sleep(10); continue
            └── _tick()
                 └── for symbol in symbols:
                      ├── data_service.get_latest(symbol, lookback=100)
                      ├── calculate_indicators → generate_signal
                      ├── event_bus.emit(BAR_RECEIVED)
                      ├── if 非 HOLD → _process_signal()
                      │    ├── event_bus.emit(SIGNAL_GENERATED)
                      │    ├── risk_manager.check → calculate_size
                      │    ├── executor.submit_order()
                      │    └── event_bus.emit(ORDER_FILLED / REJECTED)
                      └── check_exit_conditions(止损/止盈)
            sleep(poll_interval)
```

## 五、配置体系

| 层级 | 文件 | 内容 | 优先级 |
|------|------|------|--------|
| **CLI 参数** | 命令行 `--symbols`, `-m` 等 | 运行时覆盖 | **最高** |
| **策略配置** | `src/strategy/configs/*.yaml` | 策略参数、风控、费用、数据源、通知 | 中 |
| **系统配置** | `config/default.yaml` | 日志、存储路径、报告格式 | 低 |
| **代码默认** | 各类 `__init__` 默认参数 | fallback | **最低** |

环境变量通过 `${VAR:-default}` 语法在 YAML 中引用，由 `_substitute_env_vars()` 在加载时替换。

## 六、核心设计特点

1. **框架与策略分离** — 新增策略只需实现 4 个方法：`calculate_indicators()`, `generate_signal()`, `analyze_status()`, `should_notify()`
2. **策略注册表** — 单例 `StrategyRegistry`，按名称创建策略实例（目前硬编码注册）
3. **Runner 模式** — `BaseRunner` 统一封装了"初始化策略+数据服务+通知器"的公共逻辑，3 个子类实现不同执行策略
4. **事件驱动** — `EventBus` 发布-订阅，解耦引擎/策略/风控/通知之间的通信
5. **多数据源自动降级** — Tushare(付费) → AKShare(免费) → BaoStock(免费)，统一存入 SQLite
6. **7 项内置风控** — 单票仓位/总仓位/持仓数量/日亏损/回撤/订单金额/现金检查，支持自定义规则扩展

## 七、关键接口定义

### 7.1 策略接口 (BaseStrategy)

```python
class BaseStrategy(ABC):
    """策略基类 - 定义框架与策略之间的契约"""

    @abstractmethod
    def calculate_indicators(self, data: DataFrame) -> DataFrame:
        """计算技术指标 (框架调用)"""
        pass

    @abstractmethod
    def generate_signal(self, data: DataFrame, context: StrategyContext) -> Signal:
        """生成交易信号 (框架调用)"""
        pass

    @abstractmethod
    def analyze_status(self, data: DataFrame) -> AnalysisResult:
        """
        分析当前状态 (框架调用)

        返回:
            - status: 当前状态 (如: 空头/多头/震荡)
            - action: 建议操作 (如: 买入/卖出/观望)
            - reason: 分析理由
            - indicators: 关键指标值
            - confidence: 置信度 (0-1)
        """
        pass

    def should_notify(self, signal: Signal, last_signal: Optional[Signal]) -> bool:
        """
        决定是否发送通知 (策略可覆盖)

        默认: 信号类型变化时通知
        策略可自定义更复杂的通知逻辑
        """
        if last_signal is None:
            return signal.signal_type != SignalType.HOLD
        return signal.signal_type != last_signal.signal_type
```

### 7.2 分析结果 (AnalysisResult)

```python
@dataclass
class AnalysisResult:
    """策略分析结果"""
    symbol: str                          # 股票代码
    timestamp: datetime                  # 分析时间
    status: str                          # 当前状态
    action: str                          # 建议操作
    reason: str                          # 分析理由
    indicators: Dict[str, Any]           # 关键指标
    confidence: float                    # 置信度 (0-1)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 7.3 通知服务接口 (Notifier)

```python
class BaseNotifier(ABC):
    """通知服务基类 - 框架提供"""

    @abstractmethod
    def send(self, message: NotifyMessage) -> bool:
        """发送通知"""
        pass

    @abstractmethod
    def send_signal(self, signal: Signal, analysis: AnalysisResult) -> bool:
        """发送交易信号通知"""
        pass

    @abstractmethod
    def send_daily_summary(self, summary: DailySummary) -> bool:
        """发送每日汇总"""
        pass
```
