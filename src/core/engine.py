"""
交易引擎
核心调度模块，协调各组件完成交易流程
"""
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, time
from enum import Enum
import time as time_module
import logging
import threading

from .models import EngineState, EngineConfig, Signal, SignalType, Order, OrderSide, OrderType
from .event_bus import EventBus, EventType, get_event_bus

logger = logging.getLogger(__name__)


class TradingEngine:
    """
    交易引擎
    
    负责:
    1. 协调策略、执行器、风控等模块
    2. 驱动交易循环
    3. 处理信号和订单
    
    Usage:
        config = EngineConfig(
            symbols=['000001.SZ'],
            strategy_name='macd',
            mode='paper'
        )
        
        engine = TradingEngine(config)
        engine.start()  # 启动交易
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
        
        # 核心组件（延迟初始化）
        self._strategy = None
        self._executor = None
        self._risk_manager = None
        self._data_service = None
        
        # 运行时状态
        self._stop_flag = threading.Event()
        self._last_tick_time: Dict[str, datetime] = {}
        
        logger.info(f"初始化交易引擎: {config.symbols}, strategy={config.strategy_name}")
    
    def start(self) -> None:
        """
        启动引擎
        
        初始化组件并开始交易循环
        """
        if self.state == EngineState.RUNNING:
            logger.warning("引擎已在运行中")
            return
        
        logger.info("=" * 50)
        logger.info("启动交易引擎")
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
                timestamp=datetime.now(),
                config=self.config.__dict__
            )
            
            logger.info("引擎启动成功，进入交易循环")
            
            # 运行主循环
            self._run_loop()
            
        except Exception as e:
            self.state = EngineState.ERROR
            logger.error(f"引擎启动失败: {e}")
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
            'symbols': self.config.symbols,
            'strategy': self.config.strategy_name,
            'mode': self.config.mode,
            'portfolio': portfolio.to_dict() if portfolio else None,
            'last_tick': {s: t.isoformat() for s, t in self._last_tick_time.items()},
        }
    
    def process_signal(self, signal: Signal) -> Optional[Order]:
        """
        手动处理信号
        
        Args:
            signal: 交易信号
        
        Returns:
            Optional[Order]: 执行的订单
        """
        return self._process_signal(signal)
    
    def _initialize_components(self) -> None:
        """初始化所有组件"""
        logger.info("初始化组件...")
        
        # 通过注册表加载策略
        from src.strategy.registry import get_registry
        import src.strategy  # noqa: F401 - 确保内置策略已注册
        
        registry = get_registry()
        self._strategy = registry.create(self.config.strategy_name)
        self._strategy.initialize()
        logger.info(f"策略已加载: {self._strategy.name}")
        
        # 初始化执行器
        from src.broker.simulator import SimulatedExecutor
        if self.config.mode == 'paper':
            self._executor = SimulatedExecutor(
                initial_capital=self.config.initial_capital
            )
        else:
            # 实盘模式需要对接券商 API
            raise NotImplementedError("实盘模式暂未实现")
        logger.info(f"执行器已初始化: {self.config.mode} 模式")
        
        # 初始化风控
        from src.risk.manager import RiskManager, RiskConfig
        self._risk_manager = RiskManager(RiskConfig())
        logger.info("风控管理器已初始化")
        
        # 初始化数据服务
        from src.data.market import MarketDataService, DataSource
        self._data_service = MarketDataService(source=DataSource.LOCAL)
        logger.info("数据服务已初始化")
    
    def _run_loop(self) -> None:
        """主交易循环"""
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
    
    def _tick(self) -> None:
        """
        单次交易循环
        
        对每个标的执行: 获取数据 -> 计算指标 -> 生成信号 -> 处理信号
        """
        for symbol in self.config.symbols:
            try:
                self._process_symbol(symbol)
            except Exception as e:
                logger.error(f"处理 {symbol} 异常: {e}")
    
    def _process_symbol(self, symbol: str) -> None:
        """
        处理单个标的
        
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
        from src.strategy.base import StrategyContext
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
    
    def _process_signal(self, signal: Signal) -> Optional[Order]:
        """
        处理交易信号
        
        Args:
            signal: 交易信号
        
        Returns:
            Optional[Order]: 执行的订单
        """
        logger.info(f"收到信号: {signal.symbol} {signal.signal_type.name} @ {signal.price:.2f}")
        
        # 发送信号事件
        self.event_bus.emit(
            EventType.SIGNAL_GENERATED,
            signal=signal.to_dict()
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
        result = self._executor.submit_order(order)
        
        # 发送订单事件
        if result.is_filled:
            logger.info(f"订单成交: {result.symbol} {result.side.value} "
                       f"{result.filled_quantity}@{result.filled_price:.2f}")
            self.event_bus.emit(
                EventType.ORDER_FILLED,
                order=result.to_dict()
            )
            
            # 通知策略
            self._strategy.on_order_filled(result)
            
            # 更新风控统计
            if result.side == OrderSide.SELL:
                pnl = (result.filled_price - signal.price) * result.filled_quantity
                self._risk_manager.update_daily_pnl(pnl)
        else:
            logger.warning(f"订单未成交: {result.message}")
            self.event_bus.emit(
                EventType.ORDER_REJECTED,
                order=result.to_dict()
            )
        
        return result
    
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
        检查退出条件（止盈止损）
        
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
