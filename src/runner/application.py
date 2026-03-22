"""
持久化的应用运行器
持有引擎、通知、监控、事件总线、策略管理等组件

业务接口层：
- 对外提供统一的业务操作接口
- CLI 各模式通过调用 Runner 执行业务逻辑
- Runner 内部协调 EngineManager 等组件完成操作
"""

import logging

from src.config.schema import Config
from src.core import EngineManager, get_engine_manager
from src.core.event_bus import get_event_bus
from src.notification.manager import NotificationManager
from src.strategy.manager import StrategyManager, get_strategy_manager
from src.data import MarketDataService, init_data_service

logger = logging.getLogger(__name__)


class ApplicationRunner:
    """
    应用运行器

    职责:
    - 持有 StrategyManager (策略管理组件)
    - 持有 EngineManager (引擎管理器，支持多任务)
    - 持有 EventBus (全局事件总线)
    - 持有 Notification (通知组件)

    Usage:
        runner = ApplicationRunner(config)

        # 启动任务（返回任务ID）
        task_id = runner.engine_manager.start(engineConfig)

        # 任务控制通过 engine_manager
        runner.engine_manager.stop(task_id)
        runner.engine_manager.pause(task_id)
        status = runner.engine_manager.status(task_id)
    """

    def __init__(self, config: Config):
        """
        初始化应用运行器

        Args:
            config: 系统配置

        Raises:
            Exception: 初始化失败时抛出异常
        """
        self.config = config

        try:
            # 分阶段初始化核心组件
            self._init_event_bus()
            self._init_data_service()
            self._init_engine_manager()
            self._init_strategy_manager()
            self._init_notifier()

            logger.info("应用运行器初始化完成")
        except Exception as e:
            logger.error(f"应用运行器初始化失败: {e}")
            raise

    def _init_event_bus(self) -> None:
        """初始化事件总线"""
        logger.info("正在初始化事件总线...")
        self._event_bus = get_event_bus()
        logger.info("事件总线初始化完成")

    def _init_engine_manager(self) -> None:
        """初始化引擎管理器"""
        logger.info("正在初始化引擎管理器...")
        engine_config = self.config.engine
        self._engine_manager = get_engine_manager(engine_config, self._event_bus, self._data_service)
        logger.info(
            f"引擎管理器初始化完成: "
            f"max_concurrent={engine_config.max_concurrent_tasks}, "
            f"max_total={engine_config.max_total_tasks}, "
            f"timeout={engine_config.default_task_timeout}s"
        )

    def _init_strategy_manager(self) -> None:
        """初始化策略管理器"""
        logger.info("正在初始化策略管理器...")
        self._strategy_manager = get_strategy_manager(config=self.config.strategy)
        logger.info(f"策略管理器初始化完成，策略目录: {self.config.strategy.directory}")

    def _init_notifier(self) -> None:
        """初始化通知服务"""
        logger.info("正在初始化通知服务...")
        self._notifier = NotificationManager(self.config.notification)
        if self._notifier.is_enabled():
            logger.info("通知服务已启用")
        else:
            logger.info("通知服务未启用")

    def _init_data_service(self) -> None:
        """初始化数据服务（全局共享）"""
        logger.info("正在初始化数据服务...")
        self._data_service = init_data_service(self.config.data)
        logger.info(f"数据服务初始化完成: {type(self._data_service).__name__}")

    @property
    def engine_manager(self) -> EngineManager:
        """获取引擎管理器（直接访问以控制任务）"""
        return self._engine_manager

    @property
    def strategy_manager(self) -> StrategyManager:
        """获取策略管理器（直接访问以管理策略）"""
        return self._strategy_manager

    @property
    def data_service(self):
        """获取数据服务（全局共享实例）"""
        return self._data_service
