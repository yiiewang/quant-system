"""
回测引擎 - 历史数据重放，模拟交易计算收益
"""

from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
import logging

import pandas as pd

from .models import (
    EngineConfig,
    EngineMode,
    Signal,
    SignalType,
)
from src.common import StrategyContext
from .base_engine import BaseEngine
from .metrics import BacktestResult
from .event_bus import EventBus, EventType

logger = logging.getLogger(__name__)


class BacktestEngine(BaseEngine):
    """
    回测引擎

    在历史数据上运行策略，模拟交易计算收益。

    Usage:
        config.mode = EngineMode.BACKTEST
        config.start_date = "2024-01-01"
        config.end_date = "2024-12-31"
        engine = BacktestEngine(config, event_bus)
        result = engine.start()
    """

    def __init__(self, config: EngineConfig, event_bus: EventBus):
        super().__init__(config, event_bus)
        # 回测专用数据
        self._backtest_data: Dict[str, pd.DataFrame] = {}
        self._equity_curve: List[Dict] = []
        self._trades: List[Dict] = []
        self._signals: List[Dict] = []

    def start(self, **kwargs) -> BacktestResult:
        """
        启动回测

        Args:
            progress_callback: 进度回调函数 (0-100)

        Returns:
            BacktestResult: 回测结果
        """
        progress_callback = kwargs.get("progress_callback")

        if not self.config.start_date or not self.config.end_date:
            raise ValueError("回测模式需要配置 start_date 和 end_date")

        try:
            start_date = datetime.fromisoformat(self.config.start_date)
            end_date = datetime.fromisoformat(self.config.end_date)
        except ValueError as e:
            raise ValueError(f"日期格式错误，需要 ISO 格式 (YYYY-MM-DD): {e}")

        logger.info("=" * 50)
        logger.info("回测模式启动")
        logger.info("=" * 50)

        try:
            self._initialize_components()
            self.state = self.state.__class__.RUNNING
            self._stop_flag.clear()

            self.event_bus.emit(
                EventType.ENGINE_STARTED,
                mode="backtest",
                timestamp=datetime.now(),
                config=self.config.__dict__,
            )

            self._load_backtest_data(start_date, end_date)
            result = self._run_backtest_loop(progress_callback)

            self.event_bus.emit(EventType.ENGINE_STOPPED, timestamp=datetime.now())
            return result

        except Exception as e:
            self.state = self.state.__class__.ERROR
            logger.error(f"回测失败: {e}")
            self.event_bus.emit(EventType.ENGINE_ERROR, error=str(e))
            raise

    def get_status(self) -> Dict[str, Any]:
        status = super().get_status()
        status.update({
            "start_date": self.config.start_date,
            "end_date": self.config.end_date,
            "backtest_symbols": list(self._backtest_data.keys()),
        })
        return status

    def get_equity_curve(self) -> pd.DataFrame:
        """获取权益曲线"""
        return pd.DataFrame(self._equity_curve)

    def get_trades(self) -> pd.DataFrame:
        """获取交易记录"""
        return pd.DataFrame(self._trades)

    def get_signals(self) -> pd.DataFrame:
        """获取信号记录"""
        return pd.DataFrame(self._signals)

    # ==================== 私有方法 ====================

    def _init_executor(self) -> None:
        """回测使用模拟执行器"""
        from src.broker.simulator import SimulatedExecutor

        self._executor = SimulatedExecutor(
            initial_capital=self.config.initial_capital,
            commission_rate=self.config.commission,
            slippage=self.config.slippage,
        )
        logger.info(f"执行器已初始化: {self.mode.value} 模式")

    def _init_data_service(self) -> None:
        """回测使用本地数据（优先使用注入的服务）"""
        # 如果配置中已注入数据服务，直接使用
        if self.config.data_service is not None:
            self._data_service = self.config.data_service
            logger.info(f"使用注入的数据服务: {type(self._data_service).__name__}")
            return

        # 否则自行创建（兼容旧代码）
        from src.data import MarketDataService
        from src.config.schema import DataSource

        self._data_service = MarketDataService(source=DataSource.LOCAL)
        logger.info(f"数据服务已初始化: {type(self._data_service).__name__}")

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

    def _run_backtest_loop(
        self, progress_callback: Optional[Callable[[float], None]] = None
    ) -> BacktestResult:
        """运行回测循环"""
        logger.info("开始回测...")
        all_dates = self._get_all_dates()
        total_days = len(all_dates)
        logger.info(f"回测区间: {total_days} 个交易日")

        for i, current_date in enumerate(all_dates):
            if self._stop_flag.is_set():
                break

            for symbol in self.config.symbols:
                self._process_bar(symbol, current_date)

            self._record_equity(current_date)

            if progress_callback and i % 10 == 0:
                progress = (i + 1) / total_days * 100
                progress_callback(progress)

        result = self._calculate_backtest_result()
        logger.info(f"回测完成: 总收益率={result.total_return:.2%}")
        return result

    def _process_bar(self, symbol: str, current_date: datetime) -> None:
        """处理单根 K 线（回测）"""
        if self._strategy is None:
            return

        data = self._backtest_data.get(symbol)
        if data is None or data.empty:
            return

        mask = data["date"] <= current_date
        available_data = data[mask].copy()

        if len(available_data) < self._strategy.min_bars:
            return

        current_bar = available_data.iloc[-1]
        current_price = current_bar["close"]

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
            params=self._strategy.params,
        )

        # 策略评估
        decision = self._strategy.evaluate(available_data, context)

        # 记录信号
        if decision.signal_type != SignalType.HOLD:
            self._signals.append({
                "date": current_date,
                "symbol": symbol,
                "type": decision.signal_type.name,
                "price": decision.price,
                "reason": decision.reason,
            })

        # 处理信号
        signal = Signal(
            symbol=decision.symbol,
            signal_type=decision.signal_type,
            price=decision.price,
            reason=decision.reason,
            strength=decision.strength,
            timestamp=decision.timestamp,
            metadata=decision.metadata,
        )
        executed_order = self._process_signal(signal, is_backtest=True)

        if executed_order and executed_order.side.value == "sell":
            self._trades.append({
                "date": signal.timestamp,
                "symbol": signal.symbol,
                "side": executed_order.side.value,
                "quantity": executed_order.filled_quantity,
                "price": executed_order.filled_price,
                "reason": signal.reason,
            })

        # 检查止盈止损
        if position and position.quantity > 0:
            self._check_exit(symbol, position, current_price)

    def _check_exit(self, symbol: str, position, current_price: float) -> None:
        """检查退出条件（止盈止损）"""
        if self._risk_manager is None or position is None:
            return

        portfolio = self._executor.get_portfolio()

        if self._risk_manager.check_stop_loss(position, current_price):
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                price=current_price,
                reason="止损",
                strength=1.0,
            )
            executed_order = self._process_signal(signal, is_backtest=True)
            if executed_order:
                self._trades.append({
                    "date": signal.timestamp,
                    "symbol": signal.symbol,
                    "side": executed_order.side.value,
                    "quantity": executed_order.filled_quantity,
                    "price": executed_order.filled_price,
                    "reason": signal.reason,
                })

        elif self._risk_manager.check_take_profit(position, current_price):
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                price=current_price,
                reason="止盈",
                strength=1.0,
            )
            executed_order = self._process_signal(signal, is_backtest=True)
            if executed_order:
                self._trades.append({
                    "date": signal.timestamp,
                    "symbol": signal.symbol,
                    "side": executed_order.side.value,
                    "quantity": executed_order.filled_quantity,
                    "price": executed_order.filled_price,
                    "reason": signal.reason,
                })

    def _record_equity(self, date: datetime) -> None:
        """记录权益曲线"""
        portfolio = self._executor.get_portfolio()
        self._equity_curve.append({
            "date": date,
            "total_value": portfolio.total_value,
            "cash": portfolio.cash,
            "position_value": portfolio.position_value,
            "daily_pnl": portfolio.daily_pnl,
        })

    def _get_all_dates(self) -> List[datetime]:
        """获取所有交易日期"""
        all_dates = set()
        for data in self._backtest_data.values():
            dates = data["date"].tolist()
            all_dates.update(dates)
        return sorted(list(all_dates))

    def _calculate_backtest_result(self) -> BacktestResult:
        """计算回测结果"""
        from .metrics import MetricsCalculator

        equity_df = pd.DataFrame(self._equity_curve)
        if equity_df.empty:
            return BacktestResult()

        metrics_calc = MetricsCalculator()
        return metrics_calc.calculate(
            equity_curve=equity_df,
            trades=self._trades,
            initial_capital=self.config.initial_capital,
            risk_free_rate=0.03,
        )
