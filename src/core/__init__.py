"""
核心模块

提供交易引擎、事件总线、数据模型等核心组件。

公开 API:
    # 引擎
    - BaseEngine: 引擎基类
    - BacktestEngine: 回测引擎
    - LiveEngine: 实时引擎
    - AnalyzeEngine: 分析引擎
    - EngineManager: 引擎管理器（多策略并发）
    
    # 事件
    - EventBus: 事件总线
    - Event: 事件对象
    - EventType: 事件类型枚举
    
    # 数据模型
    - Signal: 交易信号
    - SignalType: 信号类型 (BUY/SELL/HOLD)
    - Order: 订单
    - OrderSide: 订单方向
    - OrderType: 订单类型
    - Portfolio: 持仓组合
    - TaskConfig: 任务配置
    - EngineMode: 引擎模式 (BACKTEST/LIVE/ANALYZE)
    - EngineState: 引擎状态
    
    # 指标
    - MetricsCalculator: 指标计算器
    - BacktestResult: 回测结果

内部模块（不导出）:
    - async_event_bus: 异步事件总线
    - audit_log: 审计日志
    - exceptions: 异常定义
"""

# 引擎
from .base_engine import BaseEngine
from .backtest_engine import BacktestEngine
from .live_engine import LiveEngine
from .analyze_engine import AnalyzeEngine
from .engine_manager import EngineManager, EngineTask, TaskStatus, get_engine_manager

# 事件
from .event_bus import EventBus, Event, EventType

# 数据模型
from .models import (
    Signal,
    SignalType,
    Order,
    OrderSide,
    OrderType,
    Portfolio,
    TaskConfig,
    EngineMode,
    EngineState,
)

# 指标
from .metrics import MetricsCalculator, BacktestResult


__all__ = [
    # 引擎
    'BaseEngine',
    'BacktestEngine',
    'LiveEngine',
    'AnalyzeEngine',
    'EngineManager',
    'EngineTask',
    'TaskStatus',
    'get_engine_manager',
    # 事件
    'EventBus',
    'Event',
    'EventType',
    # 数据模型
    'Signal',
    'SignalType',
    'Order',
    'OrderSide',
    'OrderType',
    'Portfolio',
    'TaskConfig',
    'EngineMode',
    'EngineState',
    # 指标
    'MetricsCalculator',
    'BacktestResult',
]
