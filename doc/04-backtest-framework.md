# 回测框架设计

## 1. 回测流程

```
┌─────────────────────────────────────────────────────────────────┐
│                        回测流程                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. 参数配置                                                     │
│     - 标的、时间范围、初始资金                                    │
│     - 策略参数（MACD: 12/26/9）                                   │
│     - 交易成本（佣金、印花税、滑点）                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. 数据加载                                                     │
│     - 加载历史 K 线数据                                          │
│     - 数据清洗与预处理                                           │
│     - 计算技术指标                                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. 逐 K 线回放                                                  │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │  for each bar:                                          │ │
│     │    1. 更新行情数据                                       │ │
│     │    2. 策略计算 → 生成信号                                │ │
│     │    3. 风控检查                                           │ │
│     │    4. 模拟成交                                           │ │
│     │    5. 更新持仓 & 净值                                    │ │
│     └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. 结果统计                                                     │
│     - 计算收益指标                                               │
│     - 计算风险指标                                               │
│     - 生成交易记录                                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. 可视化 & 报告                                                │
│     - 净值曲线                                                   │
│     - 买卖点标记                                                 │
│     - 回测报告                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 回测引擎实现

```python
# backtest/engine.py

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Callable, Optional
from datetime import datetime
from decimal import Decimal

@dataclass
class BacktestConfig:
    """回测配置"""
    symbol: str                              # 交易标的
    start_date: str                          # 开始日期
    end_date: str                            # 结束日期
    initial_capital: float = 100000          # 初始资金
    commission_rate: float = 0.0003          # 佣金率
    stamp_tax: float = 0.001                 # 印花税（卖出）
    slippage: float = 0.001                  # 滑点
    min_commission: float = 5                # 最低佣金

@dataclass
class BacktestResult:
    """回测结果"""
    # 基础指标
    total_return: float = 0                  # 总收益率
    annual_return: float = 0                 # 年化收益率
    max_drawdown: float = 0                  # 最大回撤
    sharpe_ratio: float = 0                  # 夏普比率
    sortino_ratio: float = 0                 # 索提诺比率
    calmar_ratio: float = 0                  # 卡玛比率
    
    # 交易统计
    total_trades: int = 0                    # 总交易次数
    win_trades: int = 0                      # 盈利次数
    loss_trades: int = 0                     # 亏损次数
    win_rate: float = 0                      # 胜率
    profit_factor: float = 0                 # 盈亏比
    avg_profit: float = 0                    # 平均盈利
    avg_loss: float = 0                      # 平均亏损
    max_consecutive_wins: int = 0            # 最大连胜
    max_consecutive_losses: int = 0          # 最大连亏
    
    # 持仓统计
    avg_holding_period: float = 0            # 平均持仓天数
    max_holding_period: int = 0              # 最长持仓天数
    
    # 详细数据
    equity_curve: pd.Series = None           # 净值曲线
    trades: List[Dict] = field(default_factory=list)  # 交易记录
    daily_returns: pd.Series = None          # 日收益率

class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.data: pd.DataFrame = None
        self.strategy = None
        
        # 状态变量
        self.capital = config.initial_capital
        self.position = 0
        self.avg_price = 0
        self.equity_history = []
        self.trades = []
        self.signals = []
    
    def load_data(self, data: pd.DataFrame) -> None:
        """加载数据"""
        self.data = data.copy()
        self.data.sort_index(inplace=True)
    
    def set_strategy(self, strategy) -> None:
        """设置策略"""
        self.strategy = strategy
    
    def run(self) -> BacktestResult:
        """运行回测"""
        if self.data is None or self.strategy is None:
            raise ValueError("请先加载数据和设置策略")
        
        # 计算技术指标
        self.data = self.strategy.calculate_indicators(self.data)
        
        # 逐 K 线回放
        for i in range(len(self.data)):
            bar = self.data.iloc[i]
            history = self.data.iloc[:i+1]
            
            # 生成信号
            signal = self.strategy.generate_signal(history)
            self.signals.append(signal)
            
            # 执行交易
            self._execute_signal(signal, bar)
            
            # 记录净值
            equity = self._calculate_equity(bar['close'])
            self.equity_history.append({
                'date': bar.name,
                'equity': equity,
                'capital': self.capital,
                'position': self.position,
                'position_value': self.position * bar['close']
            })
        
        # 计算结果
        return self._calculate_result()
    
    def _execute_signal(self, signal, bar) -> None:
        """执行交易信号"""
        price = bar['close']
        
        if signal.signal_type.value == 1 and self.position == 0:  # 买入
            # 计算可买数量（考虑手续费）
            available = self.capital * 0.99  # 预留1%
            quantity = int(available / price / 100) * 100  # 整手交易
            
            if quantity > 0:
                # 计算成本
                cost = quantity * price
                commission = max(cost * self.config.commission_rate, self.config.min_commission)
                slippage_cost = cost * self.config.slippage
                
                total_cost = cost + commission + slippage_cost
                
                if total_cost <= self.capital:
                    self.capital -= total_cost
                    self.position = quantity
                    self.avg_price = price * (1 + self.config.slippage)
                    
                    self.trades.append({
                        'date': bar.name,
                        'side': 'buy',
                        'price': self.avg_price,
                        'quantity': quantity,
                        'cost': total_cost,
                        'commission': commission,
                        'reason': signal.reason
                    })
        
        elif signal.signal_type.value == -1 and self.position > 0:  # 卖出
            sell_price = price * (1 - self.config.slippage)
            revenue = self.position * sell_price
            
            # 佣金 + 印花税
            commission = max(revenue * self.config.commission_rate, self.config.min_commission)
            stamp_tax = revenue * self.config.stamp_tax
            
            net_revenue = revenue - commission - stamp_tax
            pnl = net_revenue - self.position * self.avg_price
            
            self.capital += net_revenue
            
            self.trades.append({
                'date': bar.name,
                'side': 'sell',
                'price': sell_price,
                'quantity': self.position,
                'revenue': net_revenue,
                'commission': commission + stamp_tax,
                'pnl': pnl,
                'return': pnl / (self.position * self.avg_price),
                'reason': signal.reason
            })
            
            self.position = 0
            self.avg_price = 0
    
    def _calculate_equity(self, current_price: float) -> float:
        """计算当前净值"""
        position_value = self.position * current_price
        return self.capital + position_value
    
    def _calculate_result(self) -> BacktestResult:
        """计算回测结果"""
        result = BacktestResult()
        
        # 净值曲线
        equity_df = pd.DataFrame(self.equity_history)
        equity_df.set_index('date', inplace=True)
        result.equity_curve = equity_df['equity']
        
        # 日收益率
        result.daily_returns = result.equity_curve.pct_change().dropna()
        
        # 总收益率
        result.total_return = (result.equity_curve.iloc[-1] / self.config.initial_capital - 1)
        
        # 年化收益率
        days = (result.equity_curve.index[-1] - result.equity_curve.index[0]).days
        result.annual_return = (1 + result.total_return) ** (365 / days) - 1 if days > 0 else 0
        
        # 最大回撤
        rolling_max = result.equity_curve.cummax()
        drawdown = (result.equity_curve - rolling_max) / rolling_max
        result.max_drawdown = drawdown.min()
        
        # 夏普比率（假设无风险利率 3%）
        risk_free_rate = 0.03 / 252
        excess_returns = result.daily_returns - risk_free_rate
        result.sharpe_ratio = np.sqrt(252) * excess_returns.mean() / excess_returns.std() if excess_returns.std() > 0 else 0
        
        # 索提诺比率
        downside_returns = result.daily_returns[result.daily_returns < 0]
        downside_std = downside_returns.std()
        result.sortino_ratio = np.sqrt(252) * excess_returns.mean() / downside_std if downside_std > 0 else 0
        
        # 卡玛比率
        result.calmar_ratio = result.annual_return / abs(result.max_drawdown) if result.max_drawdown != 0 else 0
        
        # 交易统计
        result.trades = self.trades
        sell_trades = [t for t in self.trades if t['side'] == 'sell']
        result.total_trades = len(sell_trades)
        
        if result.total_trades > 0:
            profits = [t['pnl'] for t in sell_trades if t['pnl'] > 0]
            losses = [t['pnl'] for t in sell_trades if t['pnl'] <= 0]
            
            result.win_trades = len(profits)
            result.loss_trades = len(losses)
            result.win_rate = result.win_trades / result.total_trades
            
            result.avg_profit = np.mean(profits) if profits else 0
            result.avg_loss = np.mean(losses) if losses else 0
            
            total_profit = sum(profits)
            total_loss = abs(sum(losses))
            result.profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        return result
```

## 3. 评估指标详解

### 3.1 收益指标

| 指标 | 公式 | 说明 |
|------|------|------|
| **总收益率** | `(最终净值 - 初始资金) / 初始资金` | 回测期间总收益 |
| **年化收益率** | `(1 + 总收益率)^(365/天数) - 1` | 折算为年度收益 |
| **基准收益** | `(期末价格 - 期初价格) / 期初价格` | 买入持有收益 |
| **超额收益** | `年化收益 - 基准年化收益` | Alpha |

### 3.2 风险指标

| 指标 | 公式 | 说明 |
|------|------|------|
| **最大回撤** | `max((峰值 - 谷值) / 峰值)` | 最大亏损幅度 |
| **波动率** | `std(日收益率) × √252` | 年化波动率 |
| **下行波动率** | `std(负收益率) × √252` | 只考虑亏损的波动 |
| **VaR(95%)** | `日收益率的5%分位数` | 95%置信度最大损失 |

### 3.3 风险调整收益

| 指标 | 公式 | 优秀值 |
|------|------|--------|
| **夏普比率** | `(年化收益 - 无风险利率) / 年化波动率` | > 1 |
| **索提诺比率** | `(年化收益 - 无风险利率) / 下行波动率` | > 1.5 |
| **卡玛比率** | `年化收益 / 最大回撤绝对值` | > 1 |
| **信息比率** | `超额收益 / 跟踪误差` | > 0.5 |

### 3.4 交易统计

| 指标 | 公式 | 参考值 |
|------|------|--------|
| **胜率** | `盈利次数 / 总交易次数` | > 40% |
| **盈亏比** | `平均盈利 / 平均亏损绝对值` | > 1.5 |
| **利润因子** | `总盈利 / 总亏损绝对值` | > 1.5 |
| **期望值** | `胜率 × 平均盈利 - (1-胜率) × 平均亏损` | > 0 |

## 4. 可视化

```python
# backtest/visualization.py

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

class BacktestVisualizer:
    """回测可视化"""
    
    def __init__(self, result: BacktestResult, data: pd.DataFrame):
        self.result = result
        self.data = data
    
    def plot_equity_curve(self, figsize=(14, 6)):
        """绘制净值曲线"""
        fig, ax = plt.subplots(figsize=figsize)
        
        # 净值曲线
        self.result.equity_curve.plot(ax=ax, label='策略净值', linewidth=2)
        
        # 基准（买入持有）
        benchmark = self.data['close'] / self.data['close'].iloc[0] * self.result.equity_curve.iloc[0]
        benchmark.plot(ax=ax, label='基准（买入持有）', linewidth=1, alpha=0.7)
        
        ax.set_title('净值曲线', fontsize=14)
        ax.set_xlabel('日期')
        ax.set_ylabel('净值')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        return fig
    
    def plot_drawdown(self, figsize=(14, 4)):
        """绘制回撤曲线"""
        fig, ax = plt.subplots(figsize=figsize)
        
        rolling_max = self.result.equity_curve.cummax()
        drawdown = (self.result.equity_curve - rolling_max) / rolling_max * 100
        
        ax.fill_between(drawdown.index, drawdown.values, 0, color='red', alpha=0.3)
        ax.plot(drawdown.index, drawdown.values, color='red', linewidth=1)
        
        ax.set_title('回撤曲线', fontsize=14)
        ax.set_xlabel('日期')
        ax.set_ylabel('回撤 (%)')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        return fig
    
    def plot_trades(self, figsize=(14, 8)):
        """绘制买卖点"""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, height_ratios=[3, 1], sharex=True)
        
        # 价格和买卖点
        ax1.plot(self.data.index, self.data['close'], label='价格', linewidth=1)
        
        # 买入点
        buys = [t for t in self.result.trades if t['side'] == 'buy']
        for trade in buys:
            ax1.scatter(trade['date'], trade['price'], color='green', marker='^', s=100, zorder=5)
        
        # 卖出点
        sells = [t for t in self.result.trades if t['side'] == 'sell']
        for trade in sells:
            ax1.scatter(trade['date'], trade['price'], color='red', marker='v', s=100, zorder=5)
        
        ax1.set_title('交易信号', fontsize=14)
        ax1.set_ylabel('价格')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # MACD 指标
        ax2.bar(self.data.index, self.data['macd_hist'], color=['red' if x < 0 else 'green' for x in self.data['macd_hist']], alpha=0.6)
        ax2.plot(self.data.index, self.data['dif'], label='DIF', linewidth=1)
        ax2.plot(self.data.index, self.data['dea'], label='DEA', linewidth=1)
        ax2.axhline(y=0, color='gray', linestyle='--', linewidth=0.5)
        
        ax2.set_xlabel('日期')
        ax2.set_ylabel('MACD')
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        return fig
    
    def generate_report(self) -> str:
        """生成文本报告"""
        r = self.result
        
        report = f"""
╔══════════════════════════════════════════════════════════════╗
║                      MACD 策略回测报告                        ║
╠══════════════════════════════════════════════════════════════╣
║ 回测区间: {self.data.index[0].strftime('%Y-%m-%d')} ~ {self.data.index[-1].strftime('%Y-%m-%d')}
║ 初始资金: {100000:,.2f}
╠══════════════════════════════════════════════════════════════╣
║                         收益指标                              ║
╠──────────────────────────────────────────────────────────────╣
║ 总收益率:      {r.total_return*100:>8.2f}%
║ 年化收益率:    {r.annual_return*100:>8.2f}%
║ 最大回撤:      {r.max_drawdown*100:>8.2f}%
╠──────────────────────────────────────────────────────────────╣
║                       风险调整收益                            ║
╠──────────────────────────────────────────────────────────────╣
║ 夏普比率:      {r.sharpe_ratio:>8.2f}
║ 索提诺比率:    {r.sortino_ratio:>8.2f}
║ 卡玛比率:      {r.calmar_ratio:>8.2f}
╠──────────────────────────────────────────────────────────────╣
║                         交易统计                              ║
╠──────────────────────────────────────────────────────────────╣
║ 总交易次数:    {r.total_trades:>8d}
║ 盈利次数:      {r.win_trades:>8d}
║ 亏损次数:      {r.loss_trades:>8d}
║ 胜率:          {r.win_rate*100:>8.2f}%
║ 盈亏比:        {r.profit_factor:>8.2f}
║ 平均盈利:      {r.avg_profit:>8.2f}
║ 平均亏损:      {r.avg_loss:>8.2f}
╚══════════════════════════════════════════════════════════════╝
"""
        return report
```

## 5. 使用示例

```python
# main.py

from backtest.engine import BacktestEngine, BacktestConfig
from strategy.macd import MACDStrategy
from backtest.visualization import BacktestVisualizer
from data.loader import load_stock_data

# 1. 配置回测参数
config = BacktestConfig(
    symbol='000001.SZ',
    start_date='2020-01-01',
    end_date='2025-12-31',
    initial_capital=100000,
    commission_rate=0.0003,
    stamp_tax=0.001,
    slippage=0.001
)

# 2. 加载数据
data = load_stock_data(config.symbol, config.start_date, config.end_date)

# 3. 创建策略
strategy = MACDStrategy({
    'fast_period': 12,
    'slow_period': 26,
    'signal_period': 9,
    'zero_line_filter': True
})

# 4. 运行回测
engine = BacktestEngine(config)
engine.load_data(data)
engine.set_strategy(strategy)
result = engine.run()

# 5. 可视化
viz = BacktestVisualizer(result, engine.data)
viz.plot_equity_curve()
viz.plot_drawdown()
viz.plot_trades()

# 6. 打印报告
print(viz.generate_report())
```
