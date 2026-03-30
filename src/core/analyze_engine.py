"""
分析引擎 - 一次性分析当前状态
"""

from typing import Dict, Any
from datetime import datetime, timedelta
import logging

from .models import (
    EngineMode,
    Portfolio,
    StrategyContext,
    TaskConfig,
)
from .base_engine import BaseEngine
from .event_bus import EventBus, EventType

logger = logging.getLogger(__name__)


class AnalyzeEngine(BaseEngine):
    """
    分析引擎

    一次性获取数据、计算指标、评估策略，返回分析结果。

    Usage:
        config.mode = EngineMode.ANALYZE
        config.symbols = ["AAPL"]
        config.days = 60
        engine = AnalyzeEngine(config, event_bus)
        result = engine.start()
    """

    def start(self, **kwargs) -> Dict[str, Any]:
        """
        启动分析

        Args:
            symbol: 分析标的（默认使用 config.symbols[0]）
            days: 回溯天数（默认使用 config.days）

        Returns:
            Dict: 分析结果
        """
        symbol = kwargs.get("symbol") or (
            self.config.symbols[0] if self.config.symbols else None
        )
        if symbol is None:
            raise ValueError("分析模式需要 symbol 参数")

        days = kwargs.get("days", self.config.days)
        logger.info(f"分析 {symbol} (最近 {days} 天)")

        try:
            self._initialize_components()
            self.state = self.state.__class__.RUNNING
            self._stop_flag.clear()

            self.event_bus.emit(
                EventType.ENGINE_STARTED,
                mode="analyze",
                timestamp=datetime.now(),
                config=self.config.__dict__,
            )

            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            data = self._data_service.get_history(symbol, start_date, end_date)
            if data is None or data.empty:
                return {"error": f"无法获取 {symbol} 的数据"}

            if self._strategy is None:
                return {"error": "策略未初始化"}

            data = self._strategy.calculate_indicators(data)

            portfolio = Portfolio(cash=0, total_value=0)
            context = StrategyContext(symbol=symbol, portfolio=portfolio)
            decision = self._strategy.evaluate(data, context)

            result = {
                "symbol": symbol,
                "status": decision.status,
                "action": decision.action,
                "confidence": decision.confidence,
                "reason": decision.reason,
                "indicators": decision.indicators,
                "current_price": decision.price,
            }

            self.state = self.state.__class__.STOPPED
            return result

        except Exception as e:
            self.state = self.state.__class__.ERROR
            logger.error(f"分析失败: {e}")
            return {"error": str(e)}

    def _init_executor(self) -> None:
        """分析模式不需要执行器"""
        self._executor = None
        logger.info("分析模式，无需执行器")
