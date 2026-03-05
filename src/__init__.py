"""
MACD 量化交易系统

一个基于 MACD 指标的量化交易系统，支持：
- 模拟交易
- 历史回测
- 风险管理
- 命令行操作
"""

__version__ = "1.0.0"
__author__ = "Cloaks"

from src.core.models import Signal, SignalType, Order, OrderType, OrderSide, Position, Portfolio
from src.core.engine import TradingEngine
from src.core.event_bus import EventBus, EventType

__all__ = [
    "Signal",
    "SignalType", 
    "Order",
    "OrderType",
    "OrderSide",
    "Position",
    "Portfolio",
    "TradingEngine",
    "EventBus",
    "EventType",
]
