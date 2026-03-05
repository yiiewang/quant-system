"""
策略注册表
提供策略的自动发现、注册和实例化功能

Usage:
    # 方式1: 装饰器注册
    @register_strategy('my_strategy')
    class MyStrategy(BaseStrategy):
        ...

    # 方式2: 手动注册
    registry.register('my_strategy', MyStrategy)

    # 获取策略
    strategy_cls = registry.get('my_strategy')
    strategy = registry.create('my_strategy', params={'fast': 12})

    # 列出所有策略
    registry.list_strategies()
"""
from typing import Dict, Any, Optional, Type, List
import logging

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """
    策略注册表（单例）
    
    管理所有可用策略的注册和查找。
    策略通过 @register_strategy 装饰器或 registry.register() 注册。
    """
    
    _instance: Optional['StrategyRegistry'] = None
    
    def __new__(cls) -> 'StrategyRegistry':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._strategies: Dict[str, Type] = {}
        return cls._instance
    
    def register(self, name: str, strategy_cls: Type) -> None:
        """
        注册策略
        
        Args:
            name: 策略名称（唯一标识，用于配置文件和CLI）
            strategy_cls: 策略类（必须继承 BaseStrategy）
        """
        from .base import BaseStrategy
        
        if not (isinstance(strategy_cls, type) and issubclass(strategy_cls, BaseStrategy)):
            raise TypeError(f"{strategy_cls} 必须继承 BaseStrategy")
        
        if name in self._strategies:
            logger.warning(f"策略 '{name}' 已存在，将被覆盖: {self._strategies[name]} -> {strategy_cls}")
        
        self._strategies[name] = strategy_cls
        logger.debug(f"注册策略: {name} -> {strategy_cls.__name__}")
    
    def get(self, name: str) -> Type:
        """
        获取策略类
        
        Args:
            name: 策略名称
        
        Returns:
            策略类
        
        Raises:
            KeyError: 策略不存在
        """
        if name not in self._strategies:
            available = ', '.join(self._strategies.keys()) or '(无)'
            raise KeyError(f"策略 '{name}' 未注册。可用策略: {available}")
        return self._strategies[name]
    
    def create(self, name: str, params: Dict[str, Any] = None) -> Any:
        """
        创建策略实例
        
        Args:
            name: 策略名称
            params: 策略参数（与默认参数合并）
        
        Returns:
            策略实例
        """
        strategy_cls = self.get(name)
        return strategy_cls(params=params)
    
    def has(self, name: str) -> bool:
        """是否已注册"""
        return name in self._strategies
    
    def list_strategies(self) -> List[Dict[str, Any]]:
        """
        列出所有已注册策略
        
        Returns:
            策略信息列表
        """
        result = []
        for name, cls in self._strategies.items():
            result.append({
                'name': name,
                'class': cls.__name__,
                'version': getattr(cls, 'version', ''),
                'author': getattr(cls, 'author', ''),
                'description': getattr(cls, 'description', ''),
                'default_params': cls.default_params() if hasattr(cls, 'default_params') else {},
            })
        return result
    
    def names(self) -> List[str]:
        """获取所有已注册策略名称"""
        return list(self._strategies.keys())
    
    def clear(self) -> None:
        """清空注册表（主要用于测试）"""
        self._strategies.clear()


# 全局注册表实例
registry = StrategyRegistry()


def register_strategy(name: str):
    """
    策略注册装饰器
    
    Usage:
        @register_strategy('macd')
        class MACDStrategy(BaseStrategy):
            ...
    
    Args:
        name: 策略名称
    """
    def decorator(cls):
        registry.register(name, cls)
        return cls
    return decorator


def get_registry() -> StrategyRegistry:
    """获取全局注册表"""
    return registry
