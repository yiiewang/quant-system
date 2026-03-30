"""
实时引擎 - 实时数据运行策略，发送信号通知
"""

from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, time
import time as time_module
import logging

from .models import (
    Portfolio,
    StrategyContext,
    TaskConfig,
)
from src.data import IMarketDataService
from .base_engine import BaseEngine
from .event_bus import EventBus, EventType

logger = logging.getLogger(__name__)


class LiveEngine(BaseEngine):
    """
    实时引擎

    实时数据运行策略，检测信号并发送通知。

    Usage:
        config.mode = EngineMode.LIVE
        config.symbols = ["AAPL", "GOOG"]
        config.poll_interval = 60
        engine = LiveEngine(config, event_bus)
        engine.start()
    """

    def __init__(
        self,
        config: TaskConfig,
        event_bus: EventBus,
        data_service: IMarketDataService,
        notification_config=None,
    ):
        super().__init__(config, event_bus, data_service, notification_config)
        # 实时专用状态
        self._last_bar_time: Dict[str, Any] = {}

    def start(self, **kwargs) -> None:
        """
        启动实时引擎

        Args:
            symbols: 覆盖配置中的标的列表
            interval: 覆盖配置中的轮询间隔
            notify_callback: 信号通知回调函数
        """
        symbols = kwargs.get("symbols")
        interval = kwargs.get("interval", self.config.poll_interval)
        notify_callback = kwargs.get("notify_callback")

        if symbols:
            self.config.symbols = symbols
        self.config.poll_interval = interval

        logger.info("=" * 50)
        logger.info("实时模式启动")
        logger.info(f"监控标的: {self.config.symbols}")
        logger.info(f"检查间隔: {interval}s")
        logger.info("=" * 50)

        try:
            self._initialize_components()
            self.state = self.state.__class__.RUNNING
            self._stop_flag.clear()

            self.event_bus.emit(
                EventType.ENGINE_STARTED,
                mode="live",
                timestamp=datetime.now(),
                config=self.config.__dict__,
            )

            self._run_live_loop(notify_callback)

            self.event_bus.emit(EventType.ENGINE_STOPPED, timestamp=datetime.now())

        except Exception as e:
            self.state = self.state.__class__.ERROR
            logger.error(f"实时模式失败: {e}")
            self.event_bus.emit(EventType.ENGINE_ERROR, error=str(e))
            raise

    def get_status(self) -> Dict[str, Any]:
        status = super().get_status()
        status.update({
            "poll_interval": self.config.poll_interval,
            "trading_time": self._is_trading_time(),
        })
        return status

    # ==================== 私有方法 ====================

    def _run_live_loop(self, notify_callback: Optional[Callable] = None) -> None:
        """实时主循环"""
        last_signals: Dict = {}

        while not self._stop_flag.is_set():
            try:
                now = datetime.now()
                logger.info(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 检查中...")

                for symbol in self.config.symbols:
                    try:
                        self._process_live_symbol(symbol, last_signals, notify_callback)
                    except Exception as e:
                        logger.error(f"  {symbol}: 处理失败 - {e}")

                time_module.sleep(self.config.poll_interval)

            except KeyboardInterrupt:
                break

    def _process_live_symbol(
        self,
        symbol: str,
        last_signals: Dict,
        notify_callback: Optional[Callable] = None,
    ) -> None:
        """处理单个标的"""

        frequency = self.config.frequency
        is_minute = frequency != "daily"

        # 使用实时行情更新的数据（新浪财经API）
        if hasattr(self._data_service, 'get_latest_with_realtime'):
            data = self._data_service.get_latest_with_realtime(symbol, frequency=frequency)
        else:
            # 备选：使用get_history获取最近数据
            from datetime import datetime, timedelta
            end = datetime.now()
            start = end - timedelta(days=60)
            data = self._data_service.get_history(symbol, start_date=start, end_date=end, frequency=frequency)

        if data is None or data.empty:
            logger.info(f"  {symbol}: 无法获取数据")
            return

        # 分钟模式且数据不足时：用日线数据计算指标，用分钟数据更新价格
        if is_minute and len(data) < 26:  # MACD需要至少26根
            logger.debug(f"  {symbol}: 分钟数据不足({len(data)}根)，尝试获取日线数据计算指标")
            daily_data = self._data_service.get_latest_with_realtime(symbol, frequency="daily")
            if daily_data is not None and len(daily_data) >= 26 and self._strategy is not None:
                # 用日线计算指标
                daily_data = self._strategy.calculate_indicators(daily_data)
                # 用最后一根日线的指标值作为当前分钟数据的指标
                last_daily = daily_data.iloc[-1]
                for col in ['macd', 'signal', 'histogram']:
                    if col in daily_data.columns:
                        data[col] = last_daily[col]
                logger.debug(f"  {symbol}: 已用日线指标填充分钟数据")

        # 检查是否有新 K 线
        last_bar = data.iloc[-1]
        if "datetime" in data.columns:
            current_bar_time = last_bar["datetime"]
        elif "date" in data.columns:
            current_bar_time = last_bar["date"]
        else:
            current_bar_time = None

        if current_bar_time is not None:
            last_bar_time = self._last_bar_time.get(symbol)
            if last_bar_time is not None and current_bar_time == last_bar_time:
                logger.debug(f"  {symbol}: 无新数据 (bar_time={current_bar_time})")
                return
            self._last_bar_time[symbol] = current_bar_time
            logger.debug(f"  {symbol}: 检测到新 K 线 ({current_bar_time})")

        # 计算指标
        if self._strategy is None:
            logger.error("策略未初始化")
            return
        data = self._strategy.calculate_indicators(data)

        # 构建上下文并评估策略
        portfolio = Portfolio(cash=0, total_value=0)
        context = StrategyContext(symbol=symbol, portfolio=portfolio)
        decision = self._strategy.evaluate(data, context)

        logger.info(
            f"  {symbol}: "
            f"状态={decision.status}, "
            f"建议={decision.action}, "
            f"置信度={decision.confidence:.0%}"
        )

        # 策略决定是否通知
        last_signal = last_signals.get(symbol)
        if self._strategy.should_notify(decision, last_signal):
            logger.info(
                f"  >>> {symbol} 信号变化: {decision.signal_type.name} - {decision.reason}"
            )

            self.event_bus.emit(
                EventType.SIGNAL_GENERATED,
                signal={
                    "symbol": decision.symbol,
                    "signal_type": decision.signal_type.name,
                    "price": decision.price,
                    "reason": decision.reason,
                },
                mode="live",
            )

            if notify_callback:
                notify_callback({
                    "symbol": symbol,
                    "signal_type": decision.signal_type.name,
                    "price": decision.price,
                    "reason": decision.reason,
                    "indicators": decision.indicators,
                })

        last_signals[symbol] = decision

    def _is_trading_time(self) -> bool:
        """检查是否在交易时间内（A股）"""
        now = datetime.now()
        current_time = now.time()

        morning_start = time(9, 30)
        morning_end = time(11, 30)
        afternoon_start = time(13, 0)
        afternoon_end = time(15, 0)

        is_morning = morning_start <= current_time <= morning_end
        is_afternoon = afternoon_start <= current_time <= afternoon_end
        is_weekday = now.weekday() < 5

        return is_weekday and (is_morning or is_afternoon)
