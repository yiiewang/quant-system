"""
回测引擎
提供策略历史回测功能
"""
from typing import Dict, Any, List, Callable, Optional
from datetime import datetime, timedelta
import pandas as pd
import logging

from src.core.models import Signal, SignalType, Order, OrderSide, OrderType
from src.broker.simulator import SimulatedExecutor
from src.risk.manager import RiskManager, RiskConfig
from src.strategy.base import BaseStrategy, StrategyContext
from .metrics import MetricsCalculator, BacktestResult

logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    回测引擎
    
    提供策略历史回测功能，支持:
    - 单标的/多标的回测
    - 自定义手续费和滑点
    - 详细的回测指标计算
    
    Usage:
        engine = BacktestEngine(
            strategy=MACDStrategy(),
            symbols=['000001.SZ'],
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            initial_capital=100000
        )
        
        result = engine.run()
        print(result.total_return)
    """
    
    def __init__(self,
                 strategy: BaseStrategy,
                 symbols: List[str],
                 start_date: datetime,
                 end_date: datetime,
                 initial_capital: float = 100000,
                 commission: float = 0.0003,
                 slippage: float = 0.001,
                 risk_config: RiskConfig = None):
        """
        初始化回测引擎
        
        Args:
            strategy: 策略实例
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            initial_capital: 初始资金
            commission: 手续费率
            slippage: 滑点
            risk_config: 风控配置
        """
        self.strategy = strategy
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        
        # 初始化组件
        self.executor = SimulatedExecutor(
            initial_capital=initial_capital,
            commission_rate=commission,
            slippage=slippage
        )
        self.risk_manager = RiskManager(risk_config or RiskConfig())
        self.metrics_calc = MetricsCalculator()
        
        # 回测数据
        self._market_data: Dict[str, pd.DataFrame] = {}
        self._equity_curve: List[Dict] = []
        self._trades: List[Dict] = []
        self._signals: List[Dict] = []
        
        logger.info(
            f"初始化回测引擎: {symbols}, "
            f"{start_date.date()} ~ {end_date.date()}, "
            f"资金={initial_capital}"
        )
    
    def load_data(self, data_loader: Callable = None) -> None:
        """
        加载回测数据
        
        Args:
            data_loader: 自定义数据加载函数
        """
        if data_loader:
            for symbol in self.symbols:
                self._market_data[symbol] = data_loader(
                    symbol, self.start_date, self.end_date
                )
        else:
            # 使用默认数据服务
            from src.data.market import MarketDataService, DataSource
            service = MarketDataService(source=DataSource.LOCAL)
            
            for symbol in self.symbols:
                data = service.get_history(symbol, self.start_date, self.end_date)
                if not data.empty:
                    self._market_data[symbol] = data
                    logger.info(f"加载数据: {symbol}, {len(data)} 条")
                else:
                    logger.warning(f"无数据: {symbol}")
    
    def run(self, progress_callback: Callable = None) -> BacktestResult:
        """
        运行回测
        
        Args:
            progress_callback: 进度回调函数
        
        Returns:
            BacktestResult: 回测结果
        """
        logger.info("开始回测...")
        
        # 加载数据（如果尚未加载）
        if not self._market_data:
            self.load_data()
        
        # 验证数据
        if not self._market_data:
            raise ValueError("无回测数据")
        
        # 初始化策略
        self.strategy.initialize()
        
        # 获取所有交易日期
        all_dates = self._get_all_dates()
        total_days = len(all_dates)
        
        logger.info(f"回测区间: {total_days} 个交易日")
        
        # 按日期遍历
        for i, current_date in enumerate(all_dates):
            # 每个标的处理
            for symbol in self.symbols:
                self._process_bar(symbol, current_date)
            
            # 记录权益
            self._record_equity(current_date)
            
            # 进度回调
            if progress_callback and i % 10 == 0:
                progress = (i + 1) / total_days * 100
                progress_callback(progress)
        
        # 计算指标
        result = self._calculate_result()
        
        logger.info(f"回测完成: 总收益率={result.total_return:.2%}")
        
        return result
    
    def _process_bar(self, symbol: str, current_date: datetime) -> None:
        """
        处理单根 K 线
        
        Args:
            symbol: 股票代码
            current_date: 当前日期
        """
        data = self._market_data.get(symbol)
        if data is None or data.empty:
            return
        
        # 获取截止当前日期的数据
        mask = data['date'] <= current_date
        available_data = data[mask].copy()
        
        if len(available_data) < 60:  # 数据不足
            return
        
        # 获取当日价格
        current_bar = available_data.iloc[-1]
        current_price = current_bar['close']
        
        # 更新执行器价格
        self.executor.update_price(symbol, current_price)
        
        # 计算指标
        available_data = self.strategy.calculate_indicators(available_data)
        
        # 构建上下文
        portfolio = self.executor.get_portfolio()
        position = portfolio.get_position(symbol)
        
        context = StrategyContext(
            symbol=symbol,
            portfolio=portfolio,
            position=position,
            timestamp=current_date,
            params=self.strategy.params
        )
        
        # 生成信号
        signal = self.strategy.generate_signal(available_data, context)
        
        # 记录信号
        if signal.signal_type != SignalType.HOLD:
            self._signals.append({
                'date': current_date,
                'symbol': symbol,
                'type': signal.signal_type.name,
                'price': signal.price,
                'reason': signal.reason
            })
        
        # 处理信号
        self._process_signal(signal, portfolio)
        
        # 检查止盈止损
        if position and position.quantity > 0:
            self._check_exit(symbol, position, current_price)
    
    def _process_signal(self, signal: Signal, portfolio) -> None:
        """处理交易信号"""
        if signal.signal_type == SignalType.HOLD:
            return
        
        # 风控检查
        result = self.risk_manager.check_signal(signal, portfolio)
        if not result.passed:
            return
        
        # 创建订单
        if signal.signal_type == SignalType.BUY:
            quantity = self.risk_manager.calculate_position_size(signal, portfolio)
            if quantity <= 0:
                return
            
            order = Order(
                symbol=signal.symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=quantity,
                price=signal.price
            )
        else:
            position = portfolio.get_position(signal.symbol)
            if not position or position.quantity <= 0:
                return
            
            order = Order(
                symbol=signal.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=position.quantity,
                price=signal.price
            )
        
        # 执行订单
        result = self.executor.submit_order(order)
        
        if result.is_filled:
            self._trades.append({
                'date': signal.timestamp,
                'symbol': signal.symbol,
                'side': result.side.value,
                'quantity': result.filled_quantity,
                'price': result.filled_price,
                'commission': result.commission,
                'reason': signal.reason
            })
    
    def _check_exit(self, symbol: str, position, current_price: float) -> None:
        """检查止盈止损"""
        portfolio = self.executor.get_portfolio()
        
        if self.risk_manager.check_stop_loss(position, current_price):
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                price=current_price,
                reason="止损"
            )
            self._process_signal(signal, portfolio)
        
        elif self.risk_manager.check_take_profit(position, current_price):
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                price=current_price,
                reason="止盈"
            )
            self._process_signal(signal, portfolio)
    
    def _record_equity(self, date: datetime) -> None:
        """记录权益曲线"""
        portfolio = self.executor.get_portfolio()
        
        self._equity_curve.append({
            'date': date,
            'total_value': portfolio.total_value,
            'cash': portfolio.cash,
            'position_value': portfolio.position_value,
            'daily_pnl': portfolio.daily_pnl
        })
    
    def _get_all_dates(self) -> List[datetime]:
        """获取所有交易日期"""
        all_dates = set()
        
        for data in self._market_data.values():
            dates = data['date'].tolist()
            all_dates.update(dates)
        
        # 过滤日期范围
        all_dates = [d for d in all_dates 
                    if self.start_date <= d <= self.end_date]
        
        return sorted(all_dates)
    
    def _calculate_result(self) -> BacktestResult:
        """计算回测结果"""
        equity_df = pd.DataFrame(self._equity_curve)
        
        if equity_df.empty:
            return BacktestResult()
        
        # 使用指标计算器
        return self.metrics_calc.calculate(
            equity_curve=equity_df,
            trades=self._trades,
            initial_capital=self.initial_capital,
            risk_free_rate=0.03
        )
    
    def get_equity_curve(self) -> pd.DataFrame:
        """获取权益曲线"""
        return pd.DataFrame(self._equity_curve)
    
    def get_trades(self) -> pd.DataFrame:
        """获取交易记录"""
        return pd.DataFrame(self._trades)
    
    def get_signals(self) -> pd.DataFrame:
        """获取信号记录"""
        return pd.DataFrame(self._signals)
