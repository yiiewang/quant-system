"""
回测指标计算
提供各类绩效指标的计算功能
"""
from typing import List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """
    回测结果
    
    包含所有回测指标
    """
    # 基础信息
    start_date: datetime = None
    end_date: datetime = None
    trading_days: int = 0
    initial_capital: float = 0
    final_capital: float = 0
    
    # 收益指标
    total_return: float = 0          # 总收益率
    annual_return: float = 0         # 年化收益率
    benchmark_return: float = 0      # 基准收益率
    alpha: float = 0                 # 超额收益
    
    # 风险指标
    max_drawdown: float = 0          # 最大回撤
    max_drawdown_duration: int = 0   # 最大回撤持续天数
    volatility: float = 0            # 波动率
    downside_vol: float = 0          # 下行波动率
    
    # 风险调整收益
    sharpe_ratio: float = 0          # 夏普比率
    sortino_ratio: float = 0         # 索提诺比率
    calmar_ratio: float = 0          # 卡玛比率
    
    # 交易统计
    trade_count: int = 0             # 交易次数
    win_count: int = 0               # 盈利次数
    lose_count: int = 0              # 亏损次数
    win_rate: float = 0              # 胜率
    profit_factor: float = 0         # 盈亏比
    avg_profit: float = 0            # 平均盈利
    avg_loss: float = 0              # 平均亏损
    avg_holding_days: float = 0      # 平均持仓天数
    max_consecutive_wins: int = 0    # 最大连胜
    max_consecutive_losses: int = 0  # 最大连亏
    
    # 详细数据
    equity_curve: pd.DataFrame = None
    trades: List[Dict] = field(default_factory=list)
    monthly_returns: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'trading_days': self.trading_days,
            'initial_capital': self.initial_capital,
            'final_capital': self.final_capital,
            'total_return': self.total_return,
            'annual_return': self.annual_return,
            'benchmark_return': self.benchmark_return,
            'alpha': self.alpha,
            'max_drawdown': self.max_drawdown,
            'max_drawdown_duration': self.max_drawdown_duration,
            'volatility': self.volatility,
            'downside_vol': self.downside_vol,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'calmar_ratio': self.calmar_ratio,
            'trade_count': self.trade_count,
            'win_count': self.win_count,
            'lose_count': self.lose_count,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'avg_profit': self.avg_profit,
            'avg_loss': self.avg_loss,
            'avg_holding_days': self.avg_holding_days,
            'max_consecutive_wins': self.max_consecutive_wins,
            'max_consecutive_losses': self.max_consecutive_losses,
            'monthly_returns': self.monthly_returns,
        }
    
    def summary(self) -> str:
        """生成文本摘要"""
        return f"""
╔══════════════════════════════════════════════════════════════╗
║                        回测结果报告                           ║
╠══════════════════════════════════════════════════════════════╣
║  📈 收益指标                                                  ║
║  ├─ 总收益率:      {self.total_return:>10.2%}                 ║
║  ├─ 年化收益率:    {self.annual_return:>10.2%}                ║
║  └─ 超额收益:      {self.alpha:>10.2%}                        ║
╠══════════════════════════════════════════════════════════════╣
║  📉 风险指标                                                  ║
║  ├─ 最大回撤:      {self.max_drawdown:>10.2%}                 ║
║  ├─ 波动率:        {self.volatility:>10.2%}                   ║
║  └─ 下行波动率:    {self.downside_vol:>10.2%}                 ║
╠══════════════════════════════════════════════════════════════╣
║  📊 风险调整收益                                              ║
║  ├─ 夏普比率:      {self.sharpe_ratio:>10.2f}                 ║
║  ├─ 索提诺比率:    {self.sortino_ratio:>10.2f}                ║
║  └─ 卡玛比率:      {self.calmar_ratio:>10.2f}                 ║
╠══════════════════════════════════════════════════════════════╣
║  🔄 交易统计                                                  ║
║  ├─ 交易次数:      {self.trade_count:>10}                     ║
║  ├─ 胜率:          {self.win_rate:>10.2%}                     ║
║  ├─ 盈亏比:        {self.profit_factor:>10.2f}                ║
║  └─ 平均持仓天数:  {self.avg_holding_days:>10.1f}             ║
╚══════════════════════════════════════════════════════════════╝
"""


class MetricsCalculator:
    """
    指标计算器
    
    计算各类回测绩效指标
    """
    
    def calculate(self, equity_curve: pd.DataFrame,
                  trades: List[Dict],
                  initial_capital: float,
                  risk_free_rate: float = 0.03) -> BacktestResult:
        """
        计算所有指标
        
        Args:
            equity_curve: 权益曲线
            trades: 交易记录
            initial_capital: 初始资金
            risk_free_rate: 无风险利率
        
        Returns:
            BacktestResult: 回测结果
        """
        result = BacktestResult()
        
        if equity_curve.empty:
            return result
        
        # 基础信息
        result.start_date = equity_curve['date'].iloc[0]
        result.end_date = equity_curve['date'].iloc[-1]
        result.trading_days = len(equity_curve)
        result.initial_capital = initial_capital
        result.final_capital = equity_curve['total_value'].iloc[-1]
        result.equity_curve = equity_curve
        result.trades = trades
        
        # 计算收益率序列
        equity_curve['returns'] = equity_curve['total_value'].pct_change().fillna(0)
        
        # 收益指标
        result.total_return = (result.final_capital - initial_capital) / initial_capital
        result.annual_return = self._calculate_annual_return(
            result.total_return, result.trading_days
        )
        
        # 风险指标
        result.volatility = self._calculate_volatility(equity_curve['returns'])
        result.downside_vol = self._calculate_downside_volatility(equity_curve['returns'])
        result.max_drawdown, result.max_drawdown_duration = self._calculate_max_drawdown(
            equity_curve['total_value']
        )
        
        # 风险调整收益
        result.sharpe_ratio = self._calculate_sharpe_ratio(
            result.annual_return, result.volatility, risk_free_rate
        )
        result.sortino_ratio = self._calculate_sortino_ratio(
            result.annual_return, result.downside_vol, risk_free_rate
        )
        result.calmar_ratio = self._calculate_calmar_ratio(
            result.annual_return, result.max_drawdown
        )
        
        # 交易统计
        trade_stats = self._calculate_trade_stats(trades)
        result.trade_count = trade_stats['trade_count']
        result.win_count = trade_stats['win_count']
        result.lose_count = trade_stats['lose_count']
        result.win_rate = trade_stats['win_rate']
        result.profit_factor = trade_stats['profit_factor']
        result.avg_profit = trade_stats['avg_profit']
        result.avg_loss = trade_stats['avg_loss']
        result.max_consecutive_wins = trade_stats['max_consecutive_wins']
        result.max_consecutive_losses = trade_stats['max_consecutive_losses']
        
        # 月度收益
        result.monthly_returns = self._calculate_monthly_returns(equity_curve)
        
        return result
    
    def _calculate_annual_return(self, total_return: float, trading_days: int) -> float:
        """计算年化收益率"""
        if trading_days <= 0:
            return 0
        years = trading_days / 252  # 假设一年252个交易日
        return (1 + total_return) ** (1 / years) - 1
    
    def _calculate_volatility(self, returns: pd.Series) -> float:
        """计算年化波动率"""
        if len(returns) < 2:
            return 0
        return returns.std() * np.sqrt(252)
    
    def _calculate_downside_volatility(self, returns: pd.Series) -> float:
        """计算下行波动率"""
        if len(returns) < 2:
            return 0
        negative_returns = returns[returns < 0]
        if len(negative_returns) < 2:
            return 0
        return negative_returns.std() * np.sqrt(252)
    
    def _calculate_max_drawdown(self, equity: pd.Series) -> tuple:
        """
        计算最大回撤
        
        Returns:
            tuple: (最大回撤比例, 最大回撤持续天数)
        """
        if len(equity) < 2:
            return 0, 0
        
        # 计算累计最高点
        peak = equity.expanding().max()
        
        # 计算回撤
        drawdown = (equity - peak) / peak
        
        # 最大回撤
        max_dd = drawdown.min()
        
        # 最大回撤持续天数
        in_drawdown = drawdown < 0
        duration = 0
        max_duration = 0
        
        for is_dd in in_drawdown:
            if is_dd:
                duration += 1
                max_duration = max(max_duration, duration)
            else:
                duration = 0
        
        return abs(max_dd), max_duration
    
    def _calculate_sharpe_ratio(self, annual_return: float, 
                                volatility: float,
                                risk_free_rate: float) -> float:
        """计算夏普比率"""
        if volatility == 0:
            return 0
        return (annual_return - risk_free_rate) / volatility
    
    def _calculate_sortino_ratio(self, annual_return: float,
                                 downside_vol: float,
                                 risk_free_rate: float) -> float:
        """计算索提诺比率"""
        if downside_vol == 0:
            return 0
        return (annual_return - risk_free_rate) / downside_vol
    
    def _calculate_calmar_ratio(self, annual_return: float,
                                max_drawdown: float) -> float:
        """计算卡玛比率"""
        if max_drawdown == 0:
            return 0
        return annual_return / max_drawdown
    
    def _calculate_trade_stats(self, trades: List[Dict]) -> Dict:
        """计算交易统计（通过买卖配对计算每笔盈亏）"""
        stats = {
            'trade_count': 0,
            'win_count': 0,
            'lose_count': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'avg_profit': 0,
            'avg_loss': 0,
            'max_consecutive_wins': 0,
            'max_consecutive_losses': 0,
        }

        if not trades:
            return stats

        # 按标的分组，配对买卖计算盈亏
        from collections import defaultdict
        buy_queue: dict = defaultdict(list)  # symbol -> [buy_trade, ...]
        pnls = []

        for trade in trades:
            side = trade.get('side', '')
            symbol = trade.get('symbol', '')
            price = trade.get('price', 0)
            quantity = trade.get('quantity', 0)

            if side == 'buy':
                buy_queue[symbol].append({'price': price, 'quantity': quantity})
            elif side == 'sell' and buy_queue[symbol]:
                buy = buy_queue[symbol].pop(0)
                pnl = (price - buy['price']) * min(quantity, buy['quantity'])
                pnls.append(pnl)

        stats['trade_count'] = len(pnls)
        if stats['trade_count'] == 0:
            return stats

        profits = [p for p in pnls if p > 0]
        losses = [abs(p) for p in pnls if p < 0]

        stats['win_count'] = len(profits)
        stats['lose_count'] = len(losses)
        stats['win_rate'] = stats['win_count'] / stats['trade_count']

        stats['avg_profit'] = sum(profits) / len(profits) if profits else 0
        stats['avg_loss'] = sum(losses) / len(losses) if losses else 0

        total_profit = sum(profits)
        total_loss = sum(losses)
        stats['profit_factor'] = total_profit / total_loss if total_loss > 0 else float('inf')

        # 计算最大连胜/连亏
        max_wins = max_losses = cur_wins = cur_losses = 0
        for p in pnls:
            if p > 0:
                cur_wins += 1
                cur_losses = 0
            else:
                cur_losses += 1
                cur_wins = 0
            max_wins = max(max_wins, cur_wins)
            max_losses = max(max_losses, cur_losses)

        stats['max_consecutive_wins'] = max_wins
        stats['max_consecutive_losses'] = max_losses

        return stats
    
    def _calculate_monthly_returns(self, equity_curve: pd.DataFrame) -> Dict[str, float]:
        """计算月度收益"""
        if equity_curve.empty:
            return {}
        
        df = equity_curve.copy()
        df['date'] = pd.to_datetime(df['date'])
        df['month'] = df['date'].dt.to_period('M')
        
        monthly = df.groupby('month')['total_value'].agg(['first', 'last'])
        monthly['return'] = (monthly['last'] - monthly['first']) / monthly['first']
        
        return {str(k): v for k, v in monthly['return'].items()}
