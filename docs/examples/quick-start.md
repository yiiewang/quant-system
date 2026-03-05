# 快速开始示例

本文档提供了量化交易系统的快速入门示例，帮助用户快速上手使用系统。

## 1. 环境准备

### 1.1 安装系统

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

### 1.2 配置系统

```bash
# 复制环境配置
cp .env.example .env

# 编辑配置文件
vim config/default.yaml
```

## 2. 数据管理

### 2.1 同步股票数据

```bash
# 同步单只股票数据
python -m src.cli.main data sync --symbols 002050.SZ --days 365

# 同步多只股票数据
python -m src.cli.main data sync --symbols "002050.SZ,000001.SZ,600036.SH" --days 365

# 同步指定时间范围数据
python -m src.cli.main data sync --symbols 002050.SZ --start 2023-01-01 --end 2024-12-31
```

### 2.2 查看数据信息

```bash
# 查看股票数据信息
python -m src.cli.main data info --symbol 002050.SZ

# 查看数据库信息
python -m src.cli.main data info --stats
```

### 2.3 数据清理

```bash
# 清理过期数据
python -m src.cli.main data clean --before 2023-01-01

# 清理指定股票数据
python -m src.cli.main data clean --symbols 002050.SZ
```

## 3. 策略回测

### 3.1 MACD 日线策略回测

```bash
# 基础回测
python -m src.cli.main backtest \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --symbols 002050.SZ \
  --strategy macd \
  --initial-capital 1000000

# 指定输出目录
python -m src.cli.main backtest \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --symbols 002050.SZ \
  --strategy macd \
  --initial-capital 1000000 \
  --output output/backtest/macd_2023
```

### 3.2 MACD 周线策略回测

```bash
python -m src.cli.main backtest \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --symbols 002050.SZ \
  --strategy weekly \
  --initial-capital 1000000
```

### 3.3 多周期策略回测

```bash
python -m src.cli.main backtest \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --symbols 002050.SZ \
  --strategy multi_timeframe \
  --initial-capital 1000000
```

### 3.4 多股票回测

```bash
python -m src.cli.main backtest \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --symbols "002050.SZ,000001.SZ,600036.SH" \
  --strategy macd \
  --initial-capital 1000000
```

## 4. 实时监控

### 4.1 单股票监控

```bash
# 监控单只股票
python -m src.cli.main monitor --symbols 002050.SZ

# 指定策略监控
python -m src.cli.main monitor --symbols 002050.SZ --strategy weekly
```

### 4.2 多股票监控

```bash
python -m src.cli.main monitor --symbols "002050.SZ,000001.SZ,600036.SH"
```

### 4.3 配置文件监控

```bash
# 使用配置文件启动监控
python -m src.cli.main monitor --config config/monitor.yaml
```

## 5. 策略分析

### 5.1 单股票分析

```bash
# 分析当前状态
python -m src.cli.main analyze --symbols 002050.SZ

# 使用指定策略分析
python -m src.cli.main analyze --symbols 002050.SZ --strategy weekly
```

### 5.2 批量分析

```bash
python -m src.cli.main analyze --symbols "002050.SZ,000001.SZ,600036.SH"
```

## 6. 报告查询

### 6.1 持仓报告

```bash
# 查看当前持仓
python -m src.cli.main report positions

# 查看指定股票持仓
python -m src.cli.main report positions --symbol 002050.SZ
```

### 6.2 交易记录

```bash
# 查看最近30天交易记录
python -m src.cli.main report trades --days 30

# 查看指定时间范围交易记录
python -m src.cli.main report trades --start 2023-01-01 --end 2024-12-31

# 查看指定股票交易记录
python -m src.cli.main report trades --symbol 002050.SZ
```

### 6.3 绩效报告

```bash
# 查看整体绩效
python -m src.cli.main report performance

# 查看指定股票绩效
python -m src.cli.main report performance --symbol 002050.SZ

# 查看策略绩效
python -m src.cli.main report performance --strategy macd
```

### 6.4 每日汇总

```bash
# 查看最近7天汇总
python -m src.cli.main report daily --days 7

# 查看指定时间范围汇总
python -m src.cli.main report daily --start 2023-01-01 --end 2024-12-31
```

## 7. 配置使用

### 7.1 策略参数配置

创建自定义策略配置文件 `config/my_strategy.yaml`:

```yaml
strategy:
  name: "MyMACD"
  class: "src.strategy.macd.MACDStrategy"
  params:
    fast_period: 10
    slow_period: 30
    signal_period: 8
    volume_confirm: true
    volume_ratio: 1.5
    min_data_length: 50

risk:
  max_position_pct: 0.25
  stop_loss_pct: 0.03
  take_profit_pct: 0.20

broker:
  initial_capital: 2000000
  commission_rate: 0.0002
```

使用自定义配置:

```bash
python -m src.cli.main backtest \
  --config config/my_strategy.yaml \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --symbols 002050.SZ
```

### 7.2 监控配置

创建监控配置文件 `config/monitor.yaml`:

```yaml
symbols:
  - 002050.SZ
  - 000001.SZ
  - 600036.SH

strategy: weekly

notification:
  enabled: true
  email:
    enabled: true
    recipients:
      - user@example.com

risk:
  max_drawdown: 0.15
  alerts:
    - type: drawdown
      threshold: 0.1
    - type: position_loss
      threshold: 0.05
```

## 8. Python API 使用

### 8.1 基础回测

```python
from src.config.loader import load_config
from src.core.engine import TradingEngine
from src.strategy.macd import MACDStrategy
from src.broker.simulator import SimulatorBroker
from src.risk.manager import RiskManager

# 加载配置
config = load_config("config/default.yaml")

# 创建引擎
engine = TradingEngine(config)

# 设置策略
strategy = MACDStrategy()
engine.add_strategy(strategy)

# 设置执行器
broker = SimulatorBroker(initial_capital=1000000)
engine.set_broker(broker)

# 设置风控
risk_manager = RiskManager(config['risk'])
engine.set_risk_manager(risk_manager)

# 添加股票
engine.add_symbols(["002050.SZ"])

# 运行回测
result = engine.run_backtest("2023-01-01", "2024-12-31")

# 输出结果
print(f"总收益率: {result.total_return:.2%}")
print(f"夏普比率: {result.sharpe_ratio:.2f}")
```

### 8.2 多策略回测

```python
from src.strategy.macd import MACDStrategy
from src.strategy.macd_weekly import WeeklyMACDStrategy

# 创建多个策略
strategies = [
    MACDStrategy({'fast_period': 12, 'slow_period': 26}),
    WeeklyMACDStrategy({'fast_period': 10, 'slow_period': 30})
]

# 分别运行回测
for strategy in strategies:
    engine = TradingEngine(config)
    engine.add_strategy(strategy)
    engine.add_symbols(["002050.SZ"])
    
    result = engine.run_backtest("2023-01-01", "2024-12-31")
    
    print(f"{strategy.name} 回测结果:")
    print(f"  总收益率: {result.total_return:.2%}")
    print(f"  最大回撤: {result.max_drawdown:.2%}")
    print(f"  交易次数: {result.trade_count}")
```

### 8.3 自定义指标

```python
import pandas as pd
import numpy as np

def calculate_custom_indicator(data: pd.DataFrame, period: int = 20):
    """计算自定义指标"""
    df = data.copy()
    
    # 计算价格动量
    df['momentum'] = df['close'].pct_change(periods=period)
    
    # 计算波动率
    df['volatility'] = df['close'].pct_change().rolling(period).std()
    
    # 计算相对强弱
    df['relative_strength'] = df['close'] / df['close'].rolling(period).mean()
    
    # 计算自定义信号
    df['signal'] = 0
    df.loc[df['momentum'] > 0, 'signal'] = 1
    df.loc[df['momentum'] < 0, 'signal'] = -1
    
    return df

# 使用自定义指标
data = pd.read_csv('data/002050.SZ_daily.csv', parse_dates=['date'], index_col='date')
enhanced_data = calculate_custom_indicator(data)

print(enhanced_data.tail())
```

### 8.4 策略组合

```python
from src.core.engine import TradingEngine
from src.strategy.macd import MACDStrategy
from src.strategy.macd_weekly import WeeklyMACDStrategy

class CombinedStrategy:
    """组合策略"""
    
    def __init__(self):
        self.macd_strategy = MACDStrategy()
        self.weekly_strategy = WeeklyMACDStrategy()
    
    def generate_combined_signal(self, data, context):
        """生成组合信号"""
        macd_signal = self.macd_strategy.generate_signal(data, context)
        weekly_signal = self.weekly_strategy.generate_signal(data, context)
        
        # 信号组合逻辑
        if macd_signal.signal_type == SignalType.BUY and weekly_signal.signal_type == SignalType.BUY:
            return create_buy_signal(
                symbol=context.symbol,
                price=data['close'].iloc[-1],
                strength=1.0,
                reason="双策略共振买入"
            )
        elif macd_signal.signal_type == SignalType.SELL or weekly_signal.signal_type == SignalType.SELL:
            return create_sell_signal(
                symbol=context.symbol,
                price=data['close'].iloc[-1],
                strength=0.8,
                reason="任一策略卖出"
            )
        else:
            return create_hold_signal(
                symbol=context.symbol,
                price=data['close'].iloc[-1],
                reason="无明确信号"
            )

# 使用组合策略
combined = CombinedStrategy()
# 在回测中使用...
```

## 9. 数据分析

### 9.1 回测结果分析

```python
import pandas as pd
import matplotlib.pyplot as plt

# 读取回测结果
trades = pd.read_csv('output/backtest/trades.csv')
equity = pd.read_csv('output/backtest/equity_curve.csv')

# 绘制权益曲线
plt.figure(figsize=(12, 6))
plt.plot(equity['date'], equity['total_value'])
plt.title('权益曲线')
plt.xlabel('日期')
plt.ylabel('总资产')
plt.xticks(rotation=45)
plt.grid(True)
plt.show()

# 分析交易记录
print(f"总交易次数: {len(trades)}")
print(f"盈利交易: {len(trades[trades['side'] == 'sell'])}")

# 计算月度收益
equity['monthly_return'] = equity['total_value'].pct_change(21) * 100
monthly_stats = equity.groupby(equity['date'].str[:7])['monthly_return'].mean()
print("\n月度收益统计:")
print(monthly_stats)
```

### 9.2 策略对比

```python
def compare_strategies(results_dict):
    """比较多个策略的回测结果"""
    
    comparison_data = []
    for strategy_name, result in results_dict.items():
        comparison_data.append({
            'Strategy': strategy_name,
            'Total Return': f"{result.total_return:.2%}",
            'Annual Return': f"{result.annual_return:.2%}",
            'Max Drawdown': f"{result.max_drawdown:.2%}",
            'Sharpe Ratio': f"{result.sharpe_ratio:.2f}",
            'Trade Count': result.trade_count,
            'Win Rate': f"{result.win_rate:.2%}"
        })
    
    df = pd.DataFrame(comparison_data)
    print(df.to_string(index=False))
    
    return df

# 使用示例
results = {
    'MACD Daily': macd_result,
    'MACD Weekly': weekly_result,
    'Multi Timeframe': multi_result
}

comparison = compare_strategies(results)
```

## 10. 实用脚本

### 10.1 批量回测脚本

```python
#!/usr/bin/env python3
# batch_backtest.py

import argparse
import yaml
from src.core.engine import TradingEngine
from src.strategy.macd import MACDStrategy

def batch_backtest(symbols_file, config_file):
    """批量回测脚本"""
    
    # 读取股票列表
    with open(symbols_file, 'r') as f:
        symbols = [line.strip() for line in f if line.strip()]
    
    # 读取配置
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    results = []
    
    for symbol in symbols:
        print(f"回测 {symbol}...")
        
        engine = TradingEngine(config)
        engine.add_strategy(MACDStrategy())
        engine.add_symbols([symbol])
        
        try:
            result = engine.run_backtest("2023-01-01", "2024-12-31")
            results.append({
                'symbol': symbol,
                'total_return': result.total_return,
                'sharpe_ratio': result.sharpe_ratio,
                'max_drawdown': result.max_drawdown,
                'trade_count': result.trade_count
            })
        except Exception as e:
            print(f"回测 {symbol} 失败: {e}")
    
    # 保存结果
    df = pd.DataFrame(results)
    df.to_csv('batch_backtest_results.csv', index=False)
    print("批量回测完成，结果已保存到 batch_backtest_results.csv")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='批量回测')
    parser.add_argument('--symbols', required=True, help='股票列表文件')
    parser.add_argument('--config', default='config/default.yaml', help='配置文件')
    args = parser.parse_args()
    
    batch_backtest(args.symbols, args.config)
```

### 10.2 数据监控脚本

```python
#!/usr/bin/env python3
# data_monitor.py

import time
import requests
from src.data.market import MarketDataService

def monitor_data_quality():
    """监控数据质量"""
    
    service = MarketDataService()
    
    while True:
        try:
            # 检查最新数据
            symbols = ["002050.SZ", "000001.SZ", "600036.SH"]
            
            for symbol in symbols:
                latest_data = service.get_latest_data([symbol])
                if symbol in latest_data:
                    latest = latest_data[symbol]
                    print(f"{symbol}: 最新数据 {latest['date']}, 价格 {latest['close']}")
                else:
                    print(f"{symbol}: 无最新数据")
            
            print("=" * 50)
            time.sleep(60)  # 每分钟检查一次
            
        except Exception as e:
            print(f"监控出错: {e}")
            time.sleep(60)

if __name__ == "__main__":
    monitor_data_quality()
```

通过这些示例，用户可以快速掌握量化交易系统的使用方法，并根据需求进行定制和扩展。