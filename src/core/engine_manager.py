"""
引擎管理器 - 支持多策略并发运行
管理多个引擎实例，提供任务级别的生命周期管理
"""

from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading
import uuid
import logging

from .models import EngineMode, TaskConfig
from .base_engine import BaseEngine
from .event_bus import EventBus
from src.config.schema import EngineManagerConfig
from src.data import IMarketDataService

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态"""

    PENDING = "pending"  # 等待启动
    RUNNING = "running"  # 运行中
    PAUSED = "paused"  # 暂停
    STOPPED = "stopped"  # 已停止
    ERROR = "error"  # 错误


@dataclass
class EngineTask:
    """
    引擎任务 - 表示一个运行中的策略实例

    Attributes:
        task_id: 任务唯一标识
        config: 任务配置（包含引擎运行所需的所有参数）
        engine: 交易引擎实例
        status: 任务状态
        mode: 运行模式
        created_at: 创建时间
        started_at: 启动时间
        stopped_at: 停止时间
        result: 执行结果（回测模式）
        error: 错误信息
        max_runtime: 最大运行时间（秒），0表示无限制
        timeout_callback: 超时回调函数
    """

    task_id: str
    config: TaskConfig
    engine: BaseEngine
    status: TaskStatus = TaskStatus.PENDING
    mode: Optional[EngineMode] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None
    max_runtime: int = 0  # 0 表示无限制
    timeout_callback: Optional[Callable[[str], None]] = field(default=None, repr=False)

    # 内部字段
    _thread: Optional[threading.Thread] = field(default=None, repr=False)
    _progress_callback: Optional[Callable[[float], None]] = field(
        default=None, repr=False
    )
    _timeout_timer: Optional[threading.Timer] = field(default=None, repr=False)

    def _mark_completed(self) -> None:
        """标记任务完成"""
        self.status = TaskStatus.STOPPED
        self.stopped_at = datetime.now()

    def _mark_failed(self, error: str) -> None:
        """标记任务失败"""
        self.error = error
        self.status = TaskStatus.ERROR
        self.stopped_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "mode": self.mode.value if self.mode else None,
            "strategy": self.config.strategy_name,
            "symbols": self.config.symbols,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "error": self.error,
        }


class EngineManager:
    """
    引擎管理器

    职责：
    - 管理多个引擎任务实例
    - 提供任务级别的生命周期管理
    - 支持并发运行多个策略

    Usage:
        event_bus = get_event_bus()
        config = EngineManagerConfig()
        manager = EngineManager(event_bus=event_bus, config=config)

        # 启动回测
        task_id = manager.start(config)  # config.mode 决定运行模式

        # 查询状态
        status = manager.status(task_id)

        # 停止任务
        manager.stop(task_id)

        # 列出所有任务
        tasks = manager.list_tasks()
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: EngineManagerConfig,
        data_service: IMarketDataService,
        notification_config=None,
    ):
        """
        初始化引擎管理器

        Args:
            event_bus: 事件总线
            config: 引擎管理器配置对象
            data_service: 共享数据服务实例（必需）
            notification_config: 通知配置（从系统配置传入）
        """
        self._tasks: Dict[str, EngineTask] = {}
        self._lock = threading.RLock()
        self._event_bus = event_bus
        self._data_service = data_service  # 共享数据服务（必需）
        self._notification_config = notification_config  # 通知配置

        # 限制配置
        self._max_concurrent_tasks = config.max_concurrent_tasks
        self._max_total_tasks = config.max_total_tasks
        self._default_task_timeout = config.default_task_timeout

        # 超时检查线程
        self._timeout_checker: Optional[threading.Thread] = None
        self._stop_timeout_checker = threading.Event()

        if config.default_task_timeout > 0:
            self._start_timeout_checker()

        logger.info(
            f"引擎管理器初始化完成: max_concurrent={config.max_concurrent_tasks}, "
            f"max_total={config.max_total_tasks}, timeout={config.default_task_timeout}s"
        )

    def start(
        self,
        task_config: TaskConfig,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        """
        启动引擎任务

        Args:
            task_config: 任务启动配置（包含引擎配置和任务元数据）
            progress_callback: 进度回调（回测模式）

        Returns:
            str: 任务ID

        Raises:
            ValueError: 配置无效
            RuntimeError: 启动失败，或达到任务数限制
        """
        # 1. 检查限制
        self._check_limits()

        # 2. 创建任务（包含生成ID、创建引擎、注入依赖）
        task = self._create_task(task_config, progress_callback)

        # 3. 注册任务
        with self._lock:
            self._tasks[task.task_id] = task

        # 4. 启动任务
        try:
            self._launch_task(task, progress_callback)
            return task.task_id

        except Exception as e:
            task._mark_failed(str(e))
            logger.error(f"任务 {task.task_id} 启动失败: {e}")
            raise RuntimeError(f"启动任务失败: {e}")

    def _check_limits(self) -> None:
        """检查任务数限制，超限则抛出异常"""
        with self._lock:
            # 1. 检查总任务数限制
            if len(self._tasks) >= self._max_total_tasks:
                # 清理已停止的任务
                self._cleanup_stopped_tasks()

                # 再次检查
                if len(self._tasks) >= self._max_total_tasks:
                    raise RuntimeError(f"已达到最大任务数限制: {self._max_total_tasks}")

            # 2. 检查并发任务数限制
            running_count = sum(
                1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING
            )
            if running_count >= self._max_concurrent_tasks:
                raise RuntimeError(
                    f"已达到最大并发任务数限制: {self._max_concurrent_tasks}"
                )

    def _create_task(
        self,
        task_config: TaskConfig,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> EngineTask:
        """
        创建任务对象

        包含：生成ID、注入依赖、创建引擎实例
        """
        # 生成任务ID
        task_id = self._generate_task_id(task_config)

        # 确定超时时间
        max_runtime = task_config.timeout
        task_timeout = (
            max_runtime if max_runtime is not None else self._default_task_timeout
        )

        # 创建引擎实例（工厂方法），注入数据服务和通知配置
        engine = self._create_engine(
            config=task_config,
            event_bus=self._event_bus,
            data_service=self._data_service,
            notification_config=self._notification_config,
        )

        # 创建任务对象
        task = EngineTask(
            task_id=task_id,
            config=task_config,
            engine=engine,
            status=TaskStatus.PENDING,
            max_runtime=task_timeout,
            _progress_callback=progress_callback,
        )

        return task

    def _launch_task(
        self,
        task: EngineTask,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        启动已创建的任务

        设置状态、启动引擎后台线程
        """
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        task.mode = task.config.mode

        logger.info(
            f"启动任务 {task.task_id}: mode={task.mode.value}, strategy={task.config.strategy_name}"
        )

        # 设置事件订阅
        task.engine.setup_event_subscriptions(task.task_id)

        # 统一启动引擎（各引擎根据 mode 自行处理参数）
        self._start_engine_task(task, progress_callback)

    def stop(self, task_id: str) -> bool:
        """
        停止引擎任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功
        """
        task = self._get_task(task_id)
        if not task:
            logger.warning(f"任务 {task_id} 不存在")
            return False

        if task.status not in (TaskStatus.RUNNING, TaskStatus.PAUSED):
            logger.warning(f"任务 {task_id} 当前状态 {task.status.value}，无法停止")
            return False

        try:
            logger.info(f"停止任务 {task_id}")

            task.engine.stop()
            task.engine.cleanup_event_subscriptions()
            task._mark_completed()
            return True
        except Exception as e:
            logger.error(f"停止任务 {task_id} 失败: {e}")
            return False

    def reload(self, task_id: str, new_config: TaskConfig) -> bool:
        """
        重新加载任务配置

        Args:
            task_id: 任务ID
            new_config: 新配置

        Returns:
            bool: 是否成功

        Note:
            - 只有停止状态的任务可以重新加载
            - 重新加载后需要调用 start() 重启
        """
        task = self._get_task(task_id)
        if not task:
            logger.warning(f"任务 {task_id} 不存在")
            return False

        if task.status != TaskStatus.STOPPED:
            logger.warning(f"任务 {task_id} 必须先停止才能重新加载")
            return False

        try:
            logger.info(f"重新加载任务 {task_id}")

            # 创建新引擎（工厂方法）
            new_engine = self._create_engine(
                new_config, self._event_bus, self._data_service, self._notification_config
            )

            # 更新任务
            task.config = new_config
            task.engine = new_engine
            task.status = TaskStatus.PENDING
            task.error = None
            task.result = None

            return True
        except Exception as e:
            logger.error(f"重新加载任务 {task_id} 失败: {e}")
            return False

    def pause(self, task_id: str) -> bool:
        """
        暂停任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功
        """
        task = self._get_task(task_id)
        if not task or task.status != TaskStatus.RUNNING:
            return False

        task.engine.pause()
        task.status = TaskStatus.PAUSED
        logger.info(f"任务 {task_id} 已暂停")
        return True

    def resume(self, task_id: str) -> bool:
        """
        恢复任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功
        """
        task = self._get_task(task_id)
        if not task or task.status != TaskStatus.PAUSED:
            return False

        task.engine.resume()
        task.status = TaskStatus.RUNNING
        logger.info(f"任务 {task_id} 已恢复")
        return True

    def status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            Dict: 状态信息，任务不存在返回 None
        """
        task = self._get_task(task_id)
        if not task:
            return None

        # 获取引擎状态
        engine_status = task.engine.get_status()

        return {
            **task.to_dict(),
            "engine": engine_status,
        }

    def list_tasks(
        self, status_filter: Optional[TaskStatus] = None
    ) -> List[Dict[str, Any]]:
        """
        列出所有任务

        Args:
            status_filter: 状态过滤（可选）

        Returns:
            List[Dict]: 任务列表
        """
        with self._lock:
            tasks = list(self._tasks.values())

        if status_filter:
            tasks = [t for t in tasks if t.status == status_filter]

        return [t.to_dict() for t in tasks]

    def get_result(self, task_id: str) -> Any:
        """
        获取任务结果

        Args:
            task_id: 任务ID

        Returns:
            Any: 执行结果（回测模式返回 BacktestResult）
        """
        task = self._get_task(task_id)
        return task.result if task else None

    def remove_task(self, task_id: str) -> bool:
        """
        移除任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功
        """
        task = self._get_task(task_id)
        if not task:
            return False

        # 如果任务还在运行，先停止
        if task.status == TaskStatus.RUNNING:
            self.stop(task_id)

        with self._lock:
            del self._tasks[task_id]

        logger.info(f"任务 {task_id} 已移除")
        return True

    def stop_all(self) -> None:
        """停止所有任务"""
        with self._lock:
            task_ids = list(self._tasks.keys())

        for task_id in task_ids:
            self.stop(task_id)

    def _cleanup_stopped_tasks(self) -> int:
        """
        清理已停止的任务

        Returns:
            int: 清理的任务数
        """
        with self._lock:
            stopped_tasks = [
                task_id
                for task_id, task in self._tasks.items()
                if task.status in (TaskStatus.STOPPED, TaskStatus.ERROR)
            ]
            for task_id in stopped_tasks:
                del self._tasks[task_id]

            if stopped_tasks:
                logger.info(f"清理了 {len(stopped_tasks)} 个已停止的任务")
            return len(stopped_tasks)

    def _start_timeout_checker(self) -> None:
        """启动超时检查线程"""

        def check_timeouts():
            while not self._stop_timeout_checker.is_set():
                try:
                    self._check_task_timeouts()
                except Exception as e:
                    logger.error(f"检查任务超时出错: {e}")

                # 每分钟检查一次
                self._stop_timeout_checker.wait(60)

        self._timeout_checker = threading.Thread(target=check_timeouts, daemon=True)
        self._timeout_checker.start()
        logger.info("任务超时检查线程已启动")

    def _check_task_timeouts(self) -> None:
        """检查并处理超时任务"""
        now = datetime.now()

        with self._lock:
            tasks_to_check = list(self._tasks.values())

        for task in tasks_to_check:
            if task.status != TaskStatus.RUNNING or task.max_runtime <= 0:
                continue

            if not task.started_at:
                continue

            # 计算运行时间
            runtime = (now - task.started_at).total_seconds()

            if runtime > task.max_runtime:
                logger.warning(
                    f"任务 {task.task_id} 运行超时 ({runtime:.0f}s > {task.max_runtime}s)，正在停止..."
                )

                # 停止任务
                self.stop(task.task_id)

                # 调用超时回调
                if task.timeout_callback:
                    try:
                        task.timeout_callback(task.task_id)
                    except Exception as e:
                        logger.error(f"超时回调执行失败: {e}")

    def _get_task(self, task_id: str) -> Optional[EngineTask]:
        """获取任务"""
        with self._lock:
            return self._tasks.get(task_id)

    def _generate_task_id(self, config: TaskConfig) -> str:
        """生成任务ID"""
        prefix = config.strategy_name[:8] if config.strategy_name else "task"
        return f"{prefix}_{uuid.uuid4().hex[:8].upper()}"

    @staticmethod
    def _create_engine(
        config: TaskConfig,
        event_bus: EventBus,
        data_service: IMarketDataService,
        notification_config=None,
    ) -> BaseEngine:
        """
        工厂方法：根据配置创建引擎实例

        Args:
            config: 引擎配置（mode 字段决定创建哪种引擎）
            event_bus: 事件总线
            data_service: 数据服务实例（必需）
            notification_config: 通知配置

        Returns:
            BaseEngine: 对应模式的引擎实例
        """
        mode = config.mode

        if mode == EngineMode.BACKTEST:
            from .backtest_engine import BacktestEngine
            return BacktestEngine(config, event_bus, data_service, notification_config)
        elif mode == EngineMode.LIVE:
            from .live_engine import LiveEngine
            return LiveEngine(config, event_bus, data_service, notification_config)
        elif mode == EngineMode.ANALYZE:
            from .analyze_engine import AnalyzeEngine
            return AnalyzeEngine(config, event_bus, data_service, notification_config)
        else:
            raise ValueError(f"不支持的运行模式: {mode}")

    def _start_engine_task(
        self, task: EngineTask, progress_callback: Optional[Callable[[float], None]] = None
    ) -> None:
        """统一启动引擎任务（异步执行）

        各引擎已实现为根据 mode 自动处理参数，无需在此处判断 mode。
        引擎配置已包含在 task.config 中，通过 **kwargs 传递给 engine.start()。
        """
        config = task.config
        mode = config.mode
        mode_name = mode.value

        # 构建启动参数（各引擎从 kwargs 中提取所需参数）
        kwargs = {}
        if mode == EngineMode.BACKTEST:
            if not config.start_date or not config.end_date:
                raise ValueError("回测模式需要指定 start_date 和 end_date")
            kwargs["progress_callback"] = progress_callback
        elif mode == EngineMode.LIVE:
            if not config.symbols:
                raise ValueError("实时模式需要指定标的")
            kwargs["symbols"] = config.symbols
            kwargs["interval"] = config.poll_interval
        elif mode == EngineMode.ANALYZE:
            if not config.symbols:
                raise ValueError("分析模式需要指定标的")
            kwargs["symbol"] = config.symbols[0]
            kwargs["days"] = config.days

        def run_engine():
            try:
                result = task.engine.start(**kwargs)
                if result is not None:
                    task.result = result
                    task._mark_completed()
                task.engine.cleanup_event_subscriptions()
                logger.info(f"任务 {task.task_id} {mode_name}完成")
            except Exception as e:
                logger.error(f"任务 {task.task_id} {mode_name}出错: {e}")
                task._mark_failed(str(e))
                task.engine.cleanup_event_subscriptions()

        thread = threading.Thread(target=run_engine, daemon=True)
        task._thread = thread
        thread.start()
        logger.info(f"任务 {task.task_id} {mode_name}已启动（后台线程）")


# 全局管理器实例
_global_manager: Optional[EngineManager] = None


def get_engine_manager(
    config: EngineManagerConfig,
    event_bus: EventBus,
    data_service: IMarketDataService,
    notification_config=None,
) -> EngineManager:
    """
    获取全局引擎管理器

    Args:
        config: 引擎管理器配置对象
        event_bus: 事件总线
        data_service: 共享数据服务实例（必需）
        notification_config: 通知配置（可选）

    Returns:
        EngineManager: 全局引擎管理器实例

    Note:
        第一次调用时创建实例，参数只在第一次调用时生效
    """
    global _global_manager
    if _global_manager is None:
        _global_manager = EngineManager(
            config=config,
            event_bus=event_bus,
            data_service=data_service,
            notification_config=notification_config,
        )
    return _global_manager
