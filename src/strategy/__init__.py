"""
策略模块
包含策略基类、策略注册表和具体策略实现

导入本模块会自动将所有内置策略注册到全局注册表。
"""
from .base import BaseStrategy, StrategyContext
from .registry import registry, register_strategy, get_registry
from .macd import MACDStrategy
from .macd_multi_timeframe import MultiTimeframeMACDStrategy
from .macd_weekly import WeeklyMACDStrategy

# 注册内置策略
registry.register('macd', MACDStrategy)
registry.register('multi_timeframe', MultiTimeframeMACDStrategy)
registry.register('weekly', WeeklyMACDStrategy)

__all__ = [
    # 基类
    'BaseStrategy',
    'StrategyContext',
    # 注册表
    'registry',
    'register_strategy',
    'get_registry',
    # 内置策略
    'MACDStrategy',
    'MultiTimeframeMACDStrategy',
    'WeeklyMACDStrategy',
]
