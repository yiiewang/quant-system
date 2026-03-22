"""
引擎抽象基类
定义所有引擎的公共接口和共享逻辑
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
import threading
import logging

import pandas as pd

from .models import (
    EngineState,
    EngineConfig,
    EngineMode,
    Signal,
    SignalType,
    Order,
    OrderSide,
    OrderType,
    Portfolio,
    StrategyContext,
)
from .event_bus import EventBus, EventHandler, EventType, Event, get_event_bus

logger = logging.getLogger(__name__)


class BaseEngine(ABC):
    """
    引擎抽象基类

    定义所有引擎模式的公共接口：
    - start(): 启动引擎
    - stop(): 停止引擎
    - pause(): 暂停引擎
    - resume(): 恢复引擎
    - get_status(): 获取状态

    以及共享逻辑：
    - 组件初始化
    - 信号处理
    - 订单创建
    - 事件订阅管理
    """

    def __init__(self, config: EngineConfig, event_bus: EventBus):
        self.config = config
        self.state = EngineState.IDLE
        self.event_bus = event_bus or get_event_bus()
        self.mode: EngineMode = config.mode

        # 核心组件（延迟初始化）
        self._strategy = None
        self._executor = None
        self._risk_manager = None
        self._data_service = None
        self._strategy_manager = None

        # 运行时状态
        self._stop_flag = threading.Event()

        # 事件订阅管理
        self._event_handlers: List[EventHandler] = []

        logger.info(
            f"初始化引擎 [{self.mode.value}]: {config.symbols}, strategy={config.strategy_name}"
        )

    @abstractmethod
    def start(self, **kwargs) -> Any:
        """启动引擎"""
        ...

    def stop(self) -> None:
        """停止引擎"""
        if self.state not in (EngineState.RUNNING, EngineState.PAUSED):
            return

        logger.info("正在停止引擎...")
        self._stop_flag.set()
        self.state = EngineState.STOPPED

        # 取消所有待执行订单
        if self._executor:
            cancelled = self._executor.cancel_all_orders()
            if cancelled:
                logger.info(f"已取消 {cancelled} 个待执行订单")

        self.event_bus.emit(EventType.ENGINE_STOPPED, timestamp=datetime.now())
        logger.info("引擎已停止")

    def pause(self) -> None:
        """暂停引擎"""
        if self.state == EngineState.RUNNING:
            self.state = EngineState.PAUSED
            self.event_bus.emit(EventType.ENGINE_PAUSED, timestamp=datetime.now())
            logger.info("引擎已暂停")

    def resume(self) -> None:
        """恢复引擎"""
        if self.state == EngineState.PAUSED:
            self.state = EngineState.RUNNING
            self.event_bus.emit(EventType.ENGINE_RESUMED, timestamp=datetime.now())
            logger.info("引擎已恢复")

    def get_status(self) -> Dict[str, Any]:
        """获取引擎状态"""
        portfolio = self._executor.get_portfolio() if self._executor else None
        return {
            "state": self.state.value,
            "mode": self.mode.value,
            "symbols": self.config.symbols,
            "strategy": self.config.strategy_name,
            "portfolio": portfolio.to_dict() if portfolio else None,
        }

    # ==================== 共享逻辑 ====================

    def _initialize_components(self) -> None:
        """初始化所有组件"""
        logger.info("初始化组件...")

        # 1. 策略实例
        if self._strategy_manager is None:
            from src.strategy.manager import get_strategy_manager
            self._strategy_manager = get_strategy_manager()

        self._strategy = self._strategy_manager.create_strategy(
            self.config.strategy_name,
            self.config.strategy_config,
        )
        logger.info(
            f"策略已创建: {self._strategy.name} (params={self.config.strategy_params})"
        )

        # 2. 执行器
        self._init_executor()

        # 3. 风控
        from src.risk.manager import RiskManager, RiskConfig
        self._risk_manager = RiskManager(RiskConfig())
        logger.info("风控管理器已初始化")

        # 4. 数据服务
        self._init_data_service()

        # 5. 策略依赖注入
        from src.strategy.base import StrategyDeps
        deps = StrategyDeps(
            data_service=self._data_service,
            risk_manager=self._risk_manager,
            executor=self._executor,
        )
        self._strategy.initialize(deps)
        logger.info(f"策略已初始化: {self._strategy.name}")

    def _init_executor(self) -> None:
        """初始化执行器（子类可覆盖）"""
        from src.broker.simulator import SimulatedExecutor

        self._executor = SimulatedExecutor(
            initial_capital=self.config.initial_capital,
            commission_rate=self.config.commission,
            slippage=self.config.slippage,
        )
        logger.info(f"执行器已初始化: {self.mode.value} 模式")

    def _init_data_service(self) -> None:
        """初始化数据服务（优先使用注入的服务）"""
        # 如果配置中已注入数据服务，直接使用
        if self.config.data_service is not None:
            self._data_service = self.config.data_service
            logger.info(f"使用注入的数据服务: {type(self._data_service).__name__}")
            return

        # 否则自行创建（兼容旧代码）
        from src.data import MarketDataService
        from src.config.schema import DataSource
        from src.data.smart_adapter import SmartDataAdapter

        if self.config.data_source:
            source_map = {
                "tushare": DataSource.TUSHARE,
                "akshare": DataSource.AKSHARE,
                "baostock": DataSource.BAOSTOCK,
                "yfinance": DataSource.YFINANCE,
            }
            source = source_map.get(self.config.data_source.lower())
            if source:
                self._data_service = MarketDataService(source=source)
            else:
                logger.warning(f"未知数据源: {self.config.data_source}，使用智能适配器")
                self._data_service = SmartDataAdapter()
        else:
            self._data_service = SmartDataAdapter()
        logger.info(f"数据服务已初始化: {type(self._data_service).__name__}")

    def _process_signal(self, signal: Signal, is_backtest: bool = False) -> Optional[Order]:
        """
        处理交易信号

        Args:
            signal: 交易信号
            is_backtest: 是否为回测模式

        Returns:
            Optional[Order]: 执行的订单结果
        """
        if signal.signal_type == SignalType.HOLD:
            return None

        logger.info(
            f"收到信号: {signal.symbol} {signal.signal_type.name} @ {signal.price:.2f}"
        )

        self.event_bus.emit(
            EventType.SIGNAL_GENERATED,
            signal=signal.to_dict(),
            mode=self.mode.value,
        )

        # 风控检查
        if self.config.enable_risk_check:
            if self._executor is None or self._risk_manager is None:
                logger.error("执行器或风控管理器未初始化")
                return None
            portfolio = self._executor.get_portfolio()
            result = self._risk_manager.check_signal(signal, portfolio)
            if not result.passed:
                logger.warning(f"风控拦截: {result.message}")
                self.event_bus.emit(
                    EventType.SIGNAL_REJECTED,
                    signal=signal.to_dict(),
                    reason=result.message,
                )
                return None

        # 创建并执行订单
        order = self._create_order(signal)
        if order is None:
            return None

        if self._executor is None:
            logger.error("执行器未初始化")
            return None

        executed_order = self._executor.submit_order(order)

        from src.core.models import OrderStatus
        if executed_order.status == OrderStatus.FILLED:
            logger.info(
                f"订单成交: {executed_order.symbol} {executed_order.side.value} "
                f"{executed_order.quantity}@{executed_order.price:.2f}"
            )
            self.event_bus.emit(EventType.ORDER_FILLED, order=executed_order.to_dict())

            if executed_order.side == OrderSide.SELL:
                pnl = (
                    executed_order.filled_price - signal.price
                ) * executed_order.filled_quantity
                if self._risk_manager is not None:
                    self._risk_manager.update_daily_pnl(pnl)
        else:
            logger.warning(f"订单未成交: {executed_order.status.value}")
            self.event_bus.emit(
                EventType.ORDER_REJECTED, order=executed_order.to_dict()
            )

        return executed_order

    def _create_order(self, signal: Signal) -> Optional[Order]:
        """根据信号创建订单"""
        if self._executor is None:
            logger.error("执行器未初始化")
            return None
        portfolio = self._executor.get_portfolio()

        if signal.signal_type == SignalType.BUY:
            if self._risk_manager is None:
                logger.error("风控管理器未初始化")
                return None
            quantity = self._risk_manager.calculate_position_size(signal, portfolio)
            if quantity <= 0:
                logger.info(f"计算仓位为 0，跳过买入: {signal.symbol}")
                return None
            return Order(
                symbol=signal.symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=quantity,
                price=signal.price,
            )
        elif signal.signal_type == SignalType.SELL:
            position = portfolio.get_position(signal.symbol)
            if not position or position.quantity <= 0:
                logger.warning(f"无持仓可卖: {signal.symbol}")
                return None
            return Order(
                symbol=signal.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=position.quantity,
                price=signal.price,
            )
        return None

    def setup_event_subscriptions(self, task_id: str) -> None:
        """设置事件订阅"""
        if not self.config.notify:
            return

        def on_signal_generated(event: Event):
            try:
                signal_data = event.data.get("signal", {})
                logger.info(f"任务 {task_id} 生成信号: {signal_data}")
                self.event_bus.publish(
                    EventType.SIGNAL_GENERATED,
                    {"task_id": task_id, "signal": signal_data},
                )
            except Exception as e:
                logger.error(f"任务 {task_id} 处理信号事件失败: {e}")

        def on_order_filled(event: Event):
            try:
                order_data = event.data.get("order", {})
                logger.info(f"任务 {task_id} 订单成交: {order_data}")
                self.event_bus.publish(
                    EventType.ORDER_FILLED,
                    {"task_id": task_id, "order": order_data},
                )
            except Exception as e:
                logger.error(f"任务 {task_id} 处理订单事件失败: {e}")

        self.event_bus.subscribe(EventType.SIGNAL_GENERATED, on_signal_generated)
        self.event_bus.subscribe(EventType.ORDER_FILLED, on_order_filled)
        self._event_handlers = [on_signal_generated, on_order_filled]
        logger.info(f"任务 {task_id} 已订阅通知事件")

    def cleanup_event_subscriptions(self) -> None:
        """取消事件订阅"""
        if not self._event_handlers:
            return
        for handler in self._event_handlers:
            self.event_bus.unsubscribe(EventType.SIGNAL_GENERATED, handler)
            self.event_bus.unsubscribe(EventType.ORDER_FILLED, handler)
        self._event_handlers.clear()
        logger.info("已取消事件订阅")
