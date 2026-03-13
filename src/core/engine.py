"""
统一的交易引擎
支持多种运行模式：回测、实盘、模拟、分析、监控
"""
from typing import Dict, Any, Optional, List, Callable, TYPE_CHECKING
from datetime import datetime, time, timedelta
from enum import Enum
import time as time_module
import logging
import threading

import pandas as pd

if TYPE_CHECKING:
    from src.strategy.base import BaseStrategy

from .models import (
    EngineState, EngineConfig, Signal, SignalType, Order, OrderSide, OrderType,
    Portfolio, AnalysisResult, StrategyContext, EngineMode
)
from .metrics import BacktestResult
from .event_bus import EventBus, EventType, get_event_bus

logger = logging.getLogger(__name__)


class TradingEngine:
    """
    统一的交易引擎
    
    支持多种运行模式:
    - BACKTEST: 回测模式 - 在历史数据上运行策略
    - LIVE: 实盘模式 - 真实交易
    - PAPER: 模拟模式 - 实时数据但模拟交易
    - ANALYZE: 分析模式 - 一次性分析当前状态
    - MONITOR: 监控模式 - 循环监控并发送通知
    
    Usage:
        engine = TradingEngine(config)
        result = engine.run_backtest(start_date, end_date)
        # 或
        engine.run_live()
        # 或
        engine.run_monitor(symbols, interval=60)
    """
    
    def __init__(self, config: EngineConfig, event_bus: EventBus = None):
        """
        初始化交易引擎
        
        Args:
            config: 引擎配置
            event_bus: 事件总线（可选，默认使用全局实例）
        """
        self.config = config
        self.state = EngineState.IDLE
        self.event_bus = event_bus or get_event_bus()
        self.mode: Optional[EngineMode] = None
        
        # 核心组件（延迟初始化）
        self._strategy = None
        self._executor = None
        self._risk_manager = None
        self._data_service = None
        
        # 回测专用数据
        self._backtest_data: Dict[str, 'pd.DataFrame'] = {}
        self._equity_curve: List[Dict] = []
        self._trades: List[Dict] = []
        self._signals: List[Dict] = []
        
        # 运行时状态
        self._stop_flag = threading.Event()
        self._last_tick_time: Dict[str, datetime] = {}
        
        logger.info(f"初始化交易引擎: {config.symbols}, strategy={config.strategy_name}")
    
    def run_backtest(self, start_date: datetime, end_date: datetime,
                     progress_callback: Optional[Callable[[float], None]] = None) -> BacktestResult:
        """
        回测模式：在历史数据上运行策略
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            progress_callback: 进度回调函数 (0-100)
        
        Returns:
            BacktestResult: 回测结果
        """
        self.mode = EngineMode.BACKTEST
        logger.info("=" * 50)
        logger.info("回测模式启动")
        logger.info("=" * 50)
        
        try:
            # 初始化组件
            self._initialize_components()
            
            # 更新状态
            self.state = EngineState.RUNNING
            self._stop_flag.clear()
            
            # 发送启动事件
            self.event_bus.emit(
                EventType.ENGINE_STARTED,
                mode="backtest",
                timestamp=datetime.now(),
                config=self.config.__dict__
            )
            
            # 加载回测数据
            self._load_backtest_data(start_date, end_date)
            
            # 运行回测循环
            result = self._run_backtest_loop(progress_callback)
            
            # 发送停止事件
            self.event_bus.emit(EventType.ENGINE_STOPPED, timestamp=datetime.now())
            
            return result
            
        except Exception as e:
            self.state = EngineState.ERROR
            logger.error(f"回测失败: {e}")
            self.event_bus.emit(EventType.ENGINE_ERROR, error=str(e))
            raise
    
    def run_live(self):
        """
        实盘模式：真实交易
        
        注意：当前版本暂不支持实盘模式
        """
        raise NotImplementedError("实盘模式暂未实现")
    
    def run_paper(self):
        """
        模拟模式：实时数据但模拟交易
        """
        self.mode = EngineMode.PAPER
        logger.info("=" * 50)
        logger.info("模拟模式启动")
        logger.info("=" * 50)
        
        try:
            # 初始化组件
            self._initialize_components()
            
            # 更新状态
            self.state = EngineState.RUNNING
            self._stop_flag.clear()
            
            # 发送启动事件
            self.event_bus.emit(
                EventType.ENGINE_STARTED,
                mode="paper",
                timestamp=datetime.now(),
                config=self.config.__dict__
            )
            
            # 运行主循环
            self._run_loop()
            
            # 发送停止事件
            self.event_bus.emit(EventType.ENGINE_STOPPED, timestamp=datetime.now())
            
        except Exception as e:
            self.state = EngineState.ERROR
            logger.error(f"模拟模式失败: {e}")
            self.event_bus.emit(EventType.ENGINE_ERROR, error=str(e))
            raise
    
    def run_analyze(self, symbol: str, days: int = 60) -> Dict[str, Any]:
        """
        分析模式：一次性分析当前状态
        
        Args:
            symbol: 分析标的
            days: 回溯天数
        
        Returns:
            分析结果字典
        """
        self.mode = EngineMode.ANALYZE
        logger.info(f"分析 {symbol} (最近 {days} 天)")
        
        try:
            # 初始化组件
            self._initialize_components()
            
            # 获取数据
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            data = self._data_service.get_history(symbol, start_date, end_date)
            if data is None or data.empty:
                return {'error': f'无法获取 {symbol} 的数据'}
            
            # 计算指标
            data = self._strategy.calculate_indicators(data)
            
            # 构建上下文
            portfolio = Portfolio(cash=0, total_value=0)
            context = StrategyContext(symbol=symbol, portfolio=portfolio)
            
            # 分析状态
            result = self._strategy.analyze_status(data, symbol)
            
            return {
                'symbol': symbol,
                'status': result.status,
                'action': result.action,
                'confidence': result.confidence,
                'reason': result.reason,
                'indicators': result.indicators,
                'current_price': data['close'].iloc[-1] if not data.empty else 0
            }
            
        except Exception as e:
            logger.error(f"分析失败: {e}")
            return {'error': str(e)}
    
    def run_monitor(self, symbols: List[str], interval: int = 60,
                    notify_callback: Optional[Callable] = None):
        """
        监控模式：循环监控并发送通知
        
        Args:
            symbols: 监控标的列表
            interval: 检查间隔（秒）
            notify_callback: 通知回调函数
        """
        self.mode = EngineMode.MONITOR
        self.config.symbols = symbols
        self.config.poll_interval = interval
        
        logger.info("=" * 50)
        logger.info("监控模式启动")
        logger.info(f"监控标的: {symbols}")
        logger.info(f"检查间隔: {interval}s")
        logger.info("=" * 50)
        
        try:
            # 初始化组件
            self._initialize_components()
            
            # 更新状态
            self.state = EngineState.RUNNING
            self._stop_flag.clear()
            
            # 发送启动事件
            self.event_bus.emit(
                EventType.ENGINE_STARTED,
                mode="monitor",
                timestamp=datetime.now(),
                config=self.config.__dict__
            )
            
            # 运行监控循环
            self._run_monitor_loop(notify_callback)
            
            # 发送停止事件
            self.event_bus.emit(EventType.ENGINE_STOPPED, timestamp=datetime.now())
            
        except Exception as e:
            self.state = EngineState.ERROR
            logger.error(f"监控模式失败: {e}")
            self.event_bus.emit(EventType.ENGINE_ERROR, error=str(e))
            raise
    
    def stop(self) -> None:
        """
        停止引擎
        
        安全停止交易循环并清理资源
        """
        if self.state not in (EngineState.RUNNING, EngineState.PAUSED):
            return
        
        logger.info("正在停止交易引擎...")
        
        # 设置停止标志
        self._stop_flag.set()
        self.state = EngineState.STOPPED
        
        # 取消所有待执行订单
        if self._executor:
            cancelled = self._executor.cancel_all_orders()
            if cancelled:
                logger.info(f"已取消 {cancelled} 个待执行订单")
        
        # 发送停止事件
        self.event_bus.emit(EventType.ENGINE_STOPPED, timestamp=datetime.now())
        
        logger.info("交易引擎已停止")
    
    def pause(self) -> None:
        """暂停引擎"""
        if self.state == EngineState.RUNNING:
            self.state = EngineState.PAUSED
            self.event_bus.emit(EventType.ENGINE_PAUSED, timestamp=datetime.now())
            logger.info("交易引擎已暂停")
    
    def resume(self) -> None:
        """恢复引擎"""
        if self.state == EngineState.PAUSED:
            self.state = EngineState.RUNNING
            self.event_bus.emit(EventType.ENGINE_RESUMED, timestamp=datetime.now())
            logger.info("交易引擎已恢复")
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取引擎状态
        
        Returns:
            Dict: 状态信息
        """
        portfolio = self._executor.get_portfolio() if self._executor else None
        
        return {
            'state': self.state.value,
            'mode': self.mode.value if self.mode else None,
            'symbols': self.config.symbols,
            'strategy': self.config.strategy_name,
            'portfolio': portfolio.to_dict() if portfolio else None,
        }
    
    def _initialize_components(self) -> None:
        """初始化所有组件"""
        logger.info("初始化组件...")

        # 策略：优先使用外部注入（Runner 已传入带 yaml params 的实例）
        # 仅在未注入时才自行创建（Engine 独立使用时的 fallback）
        if self._strategy is None:
            from src.strategy.registry import get_registry
            import src.strategy  # noqa: F401 - 确保内置策略已注册
            registry = get_registry()
            self._strategy = registry.create(self.config.strategy_name)
            logger.info(f"策略由 Engine 创建（fallback）: {self._strategy.name}")
        else:
            logger.info(f"策略由外部注入，跳过创建: {self._strategy.name}")

        self._strategy.initialize()
        logger.info(f"策略已初始化: {self._strategy.name}")
        
        # 初始化执行器
        from src.broker.simulator import SimulatedExecutor
        if self.mode == EngineMode.BACKTEST:
            self._executor = SimulatedExecutor(
                initial_capital=self.config.initial_capital,
                commission_rate=self.config.commission,
                slippage=self.config.slippage
            )
        elif self.mode == EngineMode.PAPER:
            self._executor = SimulatedExecutor(
                initial_capital=self.config.initial_capital,
                commission_rate=self.config.commission,
                slippage=self.config.slippage
            )
        else:
            raise NotImplementedError(f"实盘模式暂未实现: {self.mode}")
        logger.info(f"执行器已初始化: {self.mode.value} 模式")
        
        # 初始化风控
        from src.risk.manager import RiskManager, RiskConfig
        self._risk_manager = RiskManager(RiskConfig())
        logger.info("风控管理器已初始化")
        
        # 初始化数据服务
        from src.data.market import MarketDataService, DataSource
        if self.mode == EngineMode.BACKTEST:
            self._data_service = MarketDataService(source=DataSource.LOCAL)
        else:
            self._data_service = MarketDataService(source=DataSource.BAOSTOCK)
        logger.info("数据服务已初始化")
    
    def _load_backtest_data(self, start_date: datetime, end_date: datetime) -> None:
        """加载回测数据"""
        logger.info("加载回测数据...")
        
        for symbol in self.config.symbols:
            data = self._data_service.get_history(symbol, start_date, end_date)
            if data is not None and not data.empty:
                self._backtest_data[symbol] = data
                logger.info(f"  {symbol}: {len(data)} 条数据")
            else:
                logger.warning(f"  {symbol}: 无数据")
    
    def _run_backtest_loop(self, progress_callback: Optional[Callable[[float], None]] = None) -> BacktestResult:
        """运行回测循环"""
        logger.info("开始回测...")
        
        # 获取所有交易日期
        all_dates = self._get_all_dates()
        total_days = len(all_dates)
        
        logger.info(f"回测区间: {total_days} 个交易日")
        
        # 按日期遍历
        for i, current_date in enumerate(all_dates):
            if self._stop_flag.is_set():
                break
            
            # 每个标的处理
            for symbol in self.config.symbols:
                self._process_bar(symbol, current_date, is_backtest=True)
            
            # 记录权益
            self._record_equity(current_date)
            
            # 进度回调
            if progress_callback and i % 10 == 0:
                progress = (i + 1) / total_days * 100
                progress_callback(progress)
        
        # 计算结果
        result = self._calculate_backtest_result()
        
        logger.info(f"回测完成: 总收益率={result.total_return:.2%}")
        
        return result
    
    def _run_loop(self) -> None:
        """主交易循环（模拟/实盘模式）"""
        while not self._stop_flag.is_set():
            # 检查状态
            if self.state == EngineState.PAUSED:
                time_module.sleep(1)
                continue
            
            if self.state != EngineState.RUNNING:
                break
            
            # 检查交易时间
            if not self._is_trading_time():
                logger.debug("非交易时间，等待中...")
                time_module.sleep(10)
                continue
            
            try:
                # 执行一次 tick
                self._tick()
            except Exception as e:
                logger.error(f"Tick 异常: {e}")
                self.event_bus.emit(EventType.ENGINE_ERROR, error=str(e))
            
            # 等待下次轮询
            time_module.sleep(self.config.poll_interval)
    
    def _run_monitor_loop(self, notify_callback: Optional[Callable] = None) -> None:
        """监控循环"""
        last_signals = {}
        
        while not self._stop_flag.is_set():
            try:
                now = datetime.now()
                logger.info(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 检查中...")
                
                for symbol in self.config.symbols:
                    try:
                        self._monitor_symbol(symbol, last_signals, notify_callback)
                    except Exception as e:
                        logger.error(f"  {symbol}: 处理失败 - {e}")
                
                time_module.sleep(self.config.poll_interval)
                
            except KeyboardInterrupt:
                break
    
    def _monitor_symbol(self, symbol: str, last_signals: Dict,
                        notify_callback: Optional[Callable] = None) -> None:
        """监控单个标的"""
        end_date = datetime.now()
        start_date = end_date - time_module.timedelta(days=60)
        
        data = self._data_service.get_history(symbol, start_date, end_date)
        
        if data is None or data.empty:
            logger.info(f"  {symbol}: 无法获取数据")
            return
        
        # 计算指标
        data = self._strategy.calculate_indicators(data)
        
        # 分析状态
        analysis = self._strategy.analyze_status(data, symbol)
        
        logger.info(
            f"  {symbol}: "
            f"状态={analysis.status}, "
            f"建议={analysis.action}, "
            f"置信度={analysis.confidence:.0%}"
        )
        
        # 生成信号用于通知判断
        portfolio = Portfolio(cash=0, total_value=0)
        context = StrategyContext(symbol=symbol, portfolio=portfolio)
        signal = self._strategy.generate_signal(data, context)
        
        # 策略决定是否通知
        last_signal = last_signals.get(symbol)
        if self._strategy.should_notify(signal, last_signal):
            logger.info(f"  >>> {symbol} 信号变化: {signal.signal_type.name} - {signal.reason}")
            
            # 发送事件
            self.event_bus.emit(
                EventType.SIGNAL_GENERATED,
                signal=signal.to_dict(),
                mode='monitor'
            )
            
            # 调用通知回调
            if notify_callback:
                notify_callback({
                    'symbol': symbol,
                    'signal_type': signal.signal_type.name,
                    'price': signal.price,
                    'reason': signal.reason,
                    'indicators': analysis.indicators,
                })
        
        last_signals[symbol] = signal
    
    def _tick(self) -> None:
        """
        单次交易循环（模拟/实盘模式）
        
        对每个标的执行: 获取数据 -> 计算指标 -> 生成信号 -> 处理信号
        """
        for symbol in self.config.symbols:
            try:
                self._process_symbol(symbol)
            except Exception as e:
                logger.error(f"处理 {symbol} 异常: {e}")
    
    def _process_symbol(self, symbol: str) -> None:
        """
        处理单个标的（模拟/实盘模式）
        
        Args:
            symbol: 股票代码
        """
        # 获取行情数据
        data = self._data_service.get_latest(symbol, lookback=100)
        
        if data.empty:
            logger.warning(f"无法获取 {symbol} 行情数据")
            return
        
        # 更新价格缓存
        current_price = data['close'].iloc[-1]
        self._executor.update_price(symbol, current_price)
        
        # 计算指标
        data = self._strategy.calculate_indicators(data)
        
        # 构建策略上下文
        portfolio = self._executor.get_portfolio()
        position = portfolio.get_position(symbol)
        
        context = StrategyContext(
            symbol=symbol,
            portfolio=portfolio,
            position=position,
            params=self._strategy.params
        )
        
        # 生成信号
        signal = self._strategy.generate_signal(data, context)
        
        # 发送数据更新事件
        self.event_bus.emit(
            EventType.BAR_RECEIVED,
            symbol=symbol,
            price=current_price,
            signal_type=signal.signal_type.name
        )
        
        # 记录 tick 时间
        self._last_tick_time[symbol] = datetime.now()
        
        # 处理非 HOLD 信号
        if signal.signal_type != SignalType.HOLD:
            self._process_signal(signal)
        
        # 检查止盈止损
        if position and position.quantity > 0:
            self._check_exit_conditions(symbol, position, current_price)
    
    def _process_bar(self, symbol: str, current_date: datetime, is_backtest: bool = False) -> None:
        """
        处理单根 K 线（回测模式）
        
        Args:
            symbol: 股票代码
            current_date: 当前日期
            is_backtest: 是否为回测模式
        """
        data = self._backtest_data.get(symbol)
        if data is None or data.empty:
            return
        
        # 获取截止当前日期的数据
        mask = data['date'] <= current_date
        available_data = data[mask].copy()
        
        if len(available_data) < self._strategy.min_bars:  # 数据不足（warmup 期）
            return
        
        # 获取当日价格
        current_bar = available_data.iloc[-1]
        current_price = current_bar['close']
        
        # 更新执行器价格
        self._executor.update_price(symbol, current_price)
        
        # 计算指标
        available_data = self._strategy.calculate_indicators(available_data)
        
        # 构建上下文
        portfolio = self._executor.get_portfolio()
        position = portfolio.get_position(symbol)
        
        context = StrategyContext(
            symbol=symbol,
            portfolio=portfolio,
            position=position,
            timestamp=current_date,
            params=self._strategy.params
        )
        
        # 生成信号
        signal = self._strategy.generate_signal(available_data, context)
        
        # 记录信号
        if is_backtest and signal.signal_type != SignalType.HOLD:
            self._signals.append({
                'date': current_date,
                'symbol': symbol,
                'type': signal.signal_type.name,
                'price': signal.price,
                'reason': signal.reason
            })
        
        # 处理信号
        self._process_signal(signal, is_backtest)
        
        # 检查止盈止损
        if position and position.quantity > 0:
            self._check_exit(symbol, position, current_price)
    
    def _process_signal(self, signal: Signal, is_backtest: bool = False) -> Optional[Order]:
        """
        处理交易信号
        
        Args:
            signal: 交易信号
            is_backtest: 是否为回测模式
        
        Returns:
            Optional[OrderResult]: 执行的订单结果
        """
        if signal.signal_type == SignalType.HOLD:
            return None
        
        logger.info(f"收到信号: {signal.symbol} {signal.signal_type.name} @ {signal.price:.2f}")
        
        # 发送信号事件
        self.event_bus.emit(
            EventType.SIGNAL_GENERATED,
            signal=signal.to_dict(),
            mode=self.mode.value if self.mode else 'unknown'
        )
        
        # 风控检查
        if self.config.enable_risk_check:
            portfolio = self._executor.get_portfolio()
            result = self._risk_manager.check_signal(signal, portfolio)
            
            if not result.passed:
                logger.warning(f"风控拦截: {result.message}")
                self.event_bus.emit(
                    EventType.SIGNAL_REJECTED,
                    signal=signal.to_dict(),
                    reason=result.message
                )
                return None
        
        # 创建订单
        order = self._create_order(signal)
        
        if order is None:
            return None
        
        # 执行订单
        executed_order = self._executor.submit_order(order)
        
        # 检查订单是否成交（订单状态为 FILLED）
        from src.core.models import OrderStatus
        if executed_order.status == OrderStatus.FILLED:
            logger.info(f"订单成交: {executed_order.symbol} {executed_order.side.value} "
                       f"{executed_order.quantity}@{executed_order.price:.2f}")
            
            self.event_bus.emit(
                EventType.ORDER_FILLED,
                order=executed_order.to_dict()
            )
            
            # 回测记录
            if is_backtest:
                self._trades.append({
                    'date': signal.timestamp,
                    'symbol': signal.symbol,
                    'side': executed_order.side.value,
                    'quantity': executed_order.filled_quantity,
                    'price': executed_order.filled_price,
                    'reason': signal.reason
                })
            
            # 更新风控统计
            if executed_order.side == OrderSide.SELL:
                pnl = (executed_order.filled_price - signal.price) * executed_order.filled_quantity
                self._risk_manager.update_daily_pnl(pnl)
        else:
            logger.warning(f"订单未成交: {executed_order.status.value}")
            self.event_bus.emit(
                EventType.ORDER_REJECTED,
                order=executed_order.to_dict()
            )
        
        return executed_order
    
    def _create_order(self, signal: Signal) -> Optional[Order]:
        """
        根据信号创建订单
        
        Args:
            signal: 交易信号
        
        Returns:
            Optional[Order]: 订单对象
        """
        portfolio = self._executor.get_portfolio()
        
        if signal.signal_type == SignalType.BUY:
            # 计算买入数量
            quantity = self._risk_manager.calculate_position_size(signal, portfolio)
            
            if quantity <= 0:
                logger.info(f"计算仓位为 0，跳过买入: {signal.symbol}")
                return None
            
            return Order(
                symbol=signal.symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=quantity,
                price=signal.price
            )
        
        elif signal.signal_type == SignalType.SELL:
            # 获取持仓数量
            position = portfolio.get_position(signal.symbol)
            
            if not position or position.quantity <= 0:
                logger.warning(f"无持仓可卖: {signal.symbol}")
                return None
            
            return Order(
                symbol=signal.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=position.quantity,
                price=signal.price
            )
        
        return None
    
    def _check_exit_conditions(self, symbol: str, position, current_price: float) -> None:
        """
        检查退出条件（止盈止损）- 模拟/实盘模式
        
        Args:
            symbol: 股票代码
            position: 当前持仓
            current_price: 当前价格
        """
        # 检查止损
        if self._risk_manager.check_stop_loss(position, current_price):
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                price=current_price,
                reason="止损触发",
                strength=1.0
            )
            self._process_signal(signal)
            return
        
        # 检查止盈
        if self._risk_manager.check_take_profit(position, current_price):
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                price=current_price,
                reason="止盈触发",
                strength=1.0
            )
            self._process_signal(signal)
    
    def _check_exit(self, symbol: str, position, current_price: float) -> None:
        """
        检查退出条件（止盈止损）- 回测模式
        
        Args:
            symbol: 股票代码
            position: 当前持仓
            current_price: 当前价格
        """
        portfolio = self._executor.get_portfolio()
        
        if self._risk_manager.check_stop_loss(position, current_price):
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                price=current_price,
                reason="止损",
                strength=1.0
            )
            self._process_signal(signal, is_backtest=True)
        
        elif self._risk_manager.check_take_profit(position, current_price):
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                price=current_price,
                reason="止盈",
                strength=1.0
            )
            self._process_signal(signal, is_backtest=True)
    
    def _record_equity(self, date: datetime) -> None:
        """记录权益曲线"""
        portfolio = self._executor.get_portfolio()
        
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
        
        for data in self._backtest_data.values():
            dates = data['date'].tolist()
            all_dates.update(dates)
        
        return sorted(list(all_dates))
    
    def _calculate_backtest_result(self) -> BacktestResult:
        """计算回测结果"""
        from .metrics import MetricsCalculator
        
        equity_df = pd.DataFrame(self._equity_curve)
        
        if equity_df.empty:
            return BacktestResult()
        
        # 使用指标计算器
        metrics_calc = MetricsCalculator()
        result = metrics_calc.calculate(
            equity_curve=equity_df,
            trades=self._trades,
            initial_capital=self.config.initial_capital,
            risk_free_rate=0.03
        )
        
        # 直接返回 BacktestResult
        return result
    
    def _is_trading_time(self) -> bool:
        """
        检查是否在交易时间内
        
        Returns:
            bool: 是否在交易时间
        """
        now = datetime.now()
        current_time = now.time()
        
        # A股交易时间: 9:30-11:30, 13:00-15:00
        morning_start = time(9, 30)
        morning_end = time(11, 30)
        afternoon_start = time(13, 0)
        afternoon_end = time(15, 0)
        
        is_morning = morning_start <= current_time <= morning_end
        is_afternoon = afternoon_start <= current_time <= afternoon_end
        
        # 检查是否工作日（简化：只检查周一到周五）
        is_weekday = now.weekday() < 5
        
        return is_weekday and (is_morning or is_afternoon)
    
    def get_equity_curve(self) -> pd.DataFrame:
        """获取权益曲线"""
        return pd.DataFrame(self._equity_curve)
    
    def get_trades(self) -> pd.DataFrame:
        """获取交易记录"""
        return pd.DataFrame(self._trades)
    
    def get_signals(self) -> pd.DataFrame:
        """获取信号记录"""
        return pd.DataFrame(self._signals)
