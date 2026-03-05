# MACD 量化交易系统

基于 MACD 指标的量化交易系统，采用命令行无头模式运行。

## 功能特性

- 📈 **MACD 策略**: 金叉/死叉信号、成交量确认、背离检测
- 🔄 **模拟交易**: 完整的模拟交易引擎，支持订单执行、持仓管理
- ⚠️ **风险管理**: 仓位控制、止盈止损、回撤控制
- 📊 **历史回测**: 支持历史数据回测，计算多种绩效指标
- 💾 **数据服务**: 支持 Tushare/AKShare 数据源，本地 SQLite 缓存
- 🖥️ **命令行接口**: 完整的 CLI 命令行操作

## 项目结构

```
quant-macd/
├── config/                 # 配置文件
│   └── default.yaml       # 默认配置
├── src/
│   ├── core/              # 核心模块
│   │   ├── models.py      # 数据模型
│   │   ├── engine.py      # 交易引擎
│   │   └── event_bus.py   # 事件总线
│   ├── strategy/          # 策略模块
│   │   ├── base.py        # 策略基类
│   │   └── macd.py        # MACD 策略
│   ├── broker/            # 执行器模块
│   │   ├── base.py        # 执行器接口
│   │   └── simulator.py   # 模拟执行器
│   ├── risk/              # 风控模块
│   │   └── manager.py     # 风控管理器
│   ├── data/              # 数据模块
│   │   ├── market.py      # 行情服务
│   │   ├── indicator.py   # 指标计算
│   │   └── portfolio.py   # 持仓管理
│   ├── backtest/          # 回测模块
│   │   ├── engine.py      # 回测引擎
│   │   └── metrics.py     # 绩效指标
│   ├── cli/               # 命令行模块
│   │   └── main.py        # CLI 入口
│   └── config/            # 配置管理
│       └── loader.py      # 配置加载
├── data/                  # 数据存储（gitignore）
├── logs/                  # 日志文件（gitignore）
├── output/                # 输出文件（gitignore）
├── requirements.txt       # 依赖列表
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置

```bash
# 复制环境变量配置
cp .env.example .env

# 编辑 .env 设置 API Token（如使用 Tushare）
vim .env
```

### 3. 使用

```bash
# 查看帮助
python -m src.main --help

# 同步数据
python -m src.main data sync --symbols 000001.SZ,600036.SH

# 运行回测
python -m src.main backtest --start 2024-01-01 --end 2024-12-31

# 启动实时交易（模拟模式）
python -m src.main run --config config/default.yaml

# 查看持仓报告
python -m src.main report positions

# 查看交易记录
python -m src.main report trades --days 7
```

## 命令详解

### run - 启动交易

```bash
python -m src.main run [OPTIONS]

Options:
  -c, --config PATH    配置文件路径 [default: config/default.yaml]
  -s, --symbols TEXT   交易标的，逗号分隔
  -m, --mode TEXT      交易模式: simulation|paper|live
  --dry-run           试运行，不执行实际交易
```

### backtest - 历史回测

```bash
python -m src.main backtest [OPTIONS]

Options:
  -s, --start DATE     开始日期 (YYYY-MM-DD)
  -e, --end DATE       结束日期 (YYYY-MM-DD)
  --symbols TEXT       回测标的
  --initial-capital    初始资金
  -o, --output PATH    输出目录
```

### data - 数据管理

```bash
# 同步数据
python -m src.main data sync --symbols 000001.SZ --days 365

# 查看数据信息
python -m src.main data info --symbol 000001.SZ

# 清理缓存
python -m src.main data clean --before 2024-01-01
```

### report - 报告查询

```bash
# 持仓报告
python -m src.main report positions

# 交易记录
python -m src.main report trades --days 30

# 每日汇总
python -m src.main report daily --start 2024-01-01
```

## 核心接口

### 策略接口

```python
from src.strategy.base import BaseStrategy

class MyStrategy(BaseStrategy):
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        pass
    
    def generate_signal(self, data: pd.DataFrame, context: StrategyContext) -> Signal:
        """生成交易信号"""
        pass
```

### 执行器接口

```python
from src.broker.base import BaseExecutor

class MyExecutor(BaseExecutor):
    def submit_order(self, order: Order) -> Order:
        """提交订单"""
        pass
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓"""
        pass
```

### 风控接口

```python
from src.risk.manager import RiskManager

risk_manager = RiskManager(config)
result = risk_manager.check_signal(signal, portfolio)
if result.approved:
    # 执行交易
    pass
```

## 配置说明

详见 `config/default.yaml`，主要配置项：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| engine.mode | 交易模式 | simulation |
| strategy.params.fast_period | MACD 快线周期 | 12 |
| strategy.params.slow_period | MACD 慢线周期 | 26 |
| risk.max_position_pct | 单票最大仓位 | 0.3 |
| risk.stop_loss_pct | 止损比例 | 0.05 |
| broker.initial_capital | 初始资金 | 1000000 |

## 开发计划

- [x] 核心数据模型
- [x] 事件驱动架构
- [x] MACD 策略实现
- [x] 模拟交易执行器
- [x] 风险管理模块
- [x] 数据服务（Tushare/AKShare）
- [x] 回测引擎
- [x] CLI 命令行接口
- [ ] 更多策略（RSI、布林带等）
- [ ] 实盘交易对接
- [ ] 策略优化工具

## 许可证

MIT License
# quant-system
