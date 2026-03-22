"""
策略模块
包含策略基类、策略注册表、策略加载器和策略管理器

策略通过配置文件指定的目录加载，无内置策略概念。
"""
import logging
import os

from .base import BaseStrategy, StrategyContext
from .registry import registry, register_strategy, get_registry
from .loader import StrategyLoader
from .manager import StrategyManager, get_strategy_manager

logger = logging.getLogger(__name__)

__all__ = [
    # 基类
    'BaseStrategy',
    'StrategyContext',
    # 注册表
    'registry',
    'register_strategy',
    'get_registry',
    # 加载器
    'StrategyLoader',
    # 管理器
    'StrategyManager',
    'get_strategy_manager',
]
