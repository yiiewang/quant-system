"""
Runner 接口协议定义

通过组合组件接口定义 ApplicationRunner 的能力
"""

from typing import Protocol

from src.core.engine_manager import EngineManager
from src.strategy.manager import StrategyManager


class IRunner(Protocol):
    """
    运行器接口协议

    职责：
    - 持有并暴露核心组件（EngineManager, StrategyManager）
    - 通过组件接口提供业务能力

    Usage:
        runner: IRunner = ApplicationRunner(config)

        # 任务管理
        task_id = runner.engine_manager.start(config)
        runner.engine_manager.stop(task_id)

        # 策略管理
        strategies = runner.strategy_manager.get_strategy_names()
    """

    @property
    def engine_manager(self) -> EngineManager:
        """获取引擎管理器（任务管理）"""
        ...

    @property
    def strategy_manager(self) -> StrategyManager:
        """获取策略管理器（策略管理）"""
        ...
