# 量化交易系统 (Quantitative Trading System)

一个专业、模块化的量化交易框架，支持多种策略、完整的风控体系和灵活的回测功能。

## ✨ 特性

- 🚀 **模块化架构**: 策略、数据、风控、执行器完全解耦
- 📈 **多种策略**: MACD 日线、周线、多周期共振策略
- ⚡ **事件驱动**: 高性能事件总线，支持实时处理
- 🛡️ **完整风控**: 仓位控制、止盈止损、回撤管理
- 📊 **专业回测**: 详细绩效分析，多维度评估
- 🖥️ **命令行工具**: 完整的 CLI，支持脚本化操作
- 💾 **数据管理**: 多数据源支持，本地缓存优化

## 🏗️ 系统架构

```
quant-system/
├── src/                    # 源代码
│   ├── core/              # 核心框架
│   │   ├── models.py      # 数据模型
│   │   ├── engine.py      # 交易引擎
│   │   └── event_bus.py   # 事件总线
│   ├── strategy/          # 策略模块
│   │   ├── base.py        # 策略基类
│   │   ├── registry.py    # 策略注册
│   │   ├── macd.py        # MACD 日线策略
│   │   ├── macd_weekly.py # MACD 周线策略
│   │   └── macd_multi_timeframe.py # 多周期策略
│   ├── broker/            # 执行器模块
│   │   ├── base.py        # 执行器接口
│   │   └── simulator.py   # 模拟执行器
│   ├── risk/              # 风控模块
│   │   └── manager.py     # 风控管理器
│   ├── data/              # 数据模块
│   │   ├── market.py      # 市场数据
│   │   ├── indicator.py   # 技术指标
│   │   └── portfolio.py   # 投资组合
│   ├── backtest/          # 回测模块
│   │   ├── engine.py      # 回测引擎
│   │   └── metrics.py     # 绩效计算
│   ├── runner/            # 运行器
│   │   └── application.py # 应用运行器
│   ├── cli/               # 命令行工具
│   │   └── main.py        # CLI 入口
│   ├── config/            # 配置管理
│   │   └── loader.py      # 配置加载器
│   └── notification/      # 通知模块
│       ├── base.py        # 通知基类
│       ├── email_notifier.py # 邮件通知
│       └── webhook_notifier.py # Webhook 通知
├── config/                # 系统配置
│   └── default.yaml       # 默认配置
├── docs/                  # 文档
│   ├── architecture.md    # 系统架构
│   ├── strategies/        # 策略文档
│   ├── api/              # API 文档
│   └── examples/         # 使用示例
├── tests/                 # 测试代码
├── data/                  # 数据存储
├── output/                # 输出结果
└── notebooks/            # Jupyter 笔记本
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd quant-system

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置设置

```bash
# 复制环境配置
cp .env.example .env

# 编辑配置文件（可选）
vim config/default.yaml
```

### 3. 数据准备

```bash
# 同步股票数据
python -m src.cli.main data sync --symbols 002050.SZ --days 365
```

### 4. 运行回测

```bash
# 基础回测（MACD 日线策略）
python -m src.cli.main backtest \
  --start 2023-01-01 \
  --end 2025-12-31 \
  --symbols 002050.SZ \
  --strategy macd \
  --initial-capital 1000000

# 周线策略回测
python -m src.cli.main backtest \
  --start 2023-01-01 \
  --end 2025-12-31 \
  --symbols 002050.SZ \
  --strategy weekly \
  --initial-capital 1000000

# 多周期策略回测
python -m src.cli.main backtest \
  --start 2023-01-01 \
  --end 2025-12-31 \
  --symbols 002050.SZ \
  --strategy multi_timeframe \
  --initial-capital 1000000
```

## 📋 命令参考

### 数据管理

```bash
# 同步数据
python -m src.cli.main data sync --symbols 000001.SZ,600036.SH

# 数据信息
python -m src.cli.main data info --symbol 000001.SZ

# 清理数据
python -m src.cli.main data clean --before 2024-01-01
```

### 策略运行

```bash
# 回测模式
python -m src.cli.main backtest [OPTIONS]

# 实时监控模式
python -m src.cli.main monitor --symbols 002050.SZ

# 分析模式
python -m src.cli.main analyze --symbols 002050.SZ
```

### 报告查询

```bash
# 持仓报告
python -m src.cli.main report positions

# 交易记录
python -m src.cli.main report trades --days 30

# 绩效报告
python -m src.cli.main report performance --symbol 002050.SZ
```

## 🎯 策略说明

### MACD 日线策略
- **适用场景**: 短线交易，日内到数日持仓
- **信号逻辑**: 日线 MACD 金叉买入，死叉卖出
- **优势**: 信号频繁，捕捉短期波动
- **风险**: 容易受噪音影响，需要严格止损

### MACD 周线策略  
- **适用场景**: 中线趋势交易，数周到数月持仓
- **信号逻辑**: 周线 MACD 金叉买入，死叉卖出
- **优势**: 过滤日常噪音，捕捉中期趋势
- **风险**: 信号稀少，可能错过短期机会

### 多周期共振策略
- **适用场景**: 趋势跟踪，多时间框架确认
- **信号逻辑**: 日线+周线+月线多周期信号共振
- **优势**: 信号质量高，假信号少
- **风险**: 机会较少，持仓周期较长

## ⚙️ 配置参数

### 策略参数
```yaml
strategy:
  macd:
    fast_period: 12      # MACD 快线周期
    slow_period: 26      # MACD 慢线周期
    signal_period: 9     # MACD 信号线周期
    volume_confirm: true # 成交量确认
```

### 风控参数
```yaml
risk:
  max_position_pct: 0.3    # 单票最大仓位
  max_total_position: 0.8  # 最大总仓位
  stop_loss_pct: 0.05      # 止损比例
  take_profit_pct: 0.15    # 止盈比例
  max_drawdown: 0.2         # 最大回撤
```

### 执行参数
```yaml
broker:
  initial_capital: 1000000  # 初始资金
  commission_rate: 0.0003  # 手续费率
  slippage_rate: 0.001      # 滑点率
```

## 📊 回测指标

系统提供完整的回测绩效分析：

- **收益指标**: 总收益率、年化收益率、夏普比率
- **风险指标**: 最大回撤、波动率、VaR
- **交易指标**: 交易次数、胜率、盈亏比
- **其他指标**: 卡尔马比率、索提诺比率、最大连续盈利/亏损

## 🧪 开发测试

```bash
# 运行所有测试
python -m pytest tests/

# 运行特定测试
python -m pytest tests/test_strategy.py

# 生成覆盖率报告
python -m pytest --cov=src tests/
```

## 📚 文档

- [系统架构](docs/architecture.md) - 详细的系统设计
- [策略开发指南](docs/strategy-development.md) - 如何开发新策略
- [API 参考](docs/api/) - 完整的 API 文档
- [使用示例](docs/examples/) - 实用代码示例

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 📞 联系方式

如有问题或建议，请通过以下方式联系：

- 提交 Issue: [GitHub Issues](https://github.com/your-repo/issues)
- 邮箱: your-email@example.com

---

**免责声明**: 本系统仅用于研究和教育目的，不构成投资建议。使用本系统进行实盘交易存在风险，请谨慎使用。