"""
持久化的应用运行器
持有引擎、通知、监控、事件总线、策略管理等组件

业务接口层：
- 实现 IRunner 接口，对外提供统一的业务操作
- CLI 各模式通过 IRunner 接口调用
- Runner 内部协调 EngineManager 等组件完成操作
"""

import logging
from typing import Optional, List

from src.config.schema import Config
from src.core import EngineManager, get_engine_manager
from src.core.event_bus import get_event_bus
from src.core.models import EngineConfig, EngineMode
from src.notification.manager import NotificationManager
from src.strategy.manager import StrategyManager, get_strategy_manager
from src.data import get_data_service
from src.runner.interfaces import CommandResult

logger = logging.getLogger(__name__)


class ApplicationRunner:
    """
    应用运行器

    实现 IRunner 接口，提供所有业务能力。
    
    职责:
    - 持有并初始化所有核心组件
    - 实现 IRunner 定义的业务方法
    - 协调组件完成业务操作
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
        self._engine_manager = get_engine_manager(
            engine_config, self._event_bus, self._data_service
        )
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
        self._data_service = get_data_service(self.config.data)
        logger.info(f"数据服务初始化完成: {type(self._data_service).__name__}")

    # ──────────────────────────────────────────────────────────────────
    # 组件属性（供内部使用）
    # ──────────────────────────────────────────────────────────────────

    @property
    def engine_manager(self) -> EngineManager:
        """获取引擎管理器"""
        return self._engine_manager

    @property
    def strategy_manager(self) -> StrategyManager:
        """获取策略管理器"""
        return self._strategy_manager

    @property
    def data_service(self):
        """获取数据服务"""
        return self._data_service

    # ──────────────────────────────────────────────────────────────────
    # IRunner 接口实现：策略运行
    # ──────────────────────────────────────────────────────────────────

    def run(
        self,
        mode: str,
        strategy: str,
        symbols: list,
        strategy_config: str = None,
        start_date: str = None,
        end_date: str = None,
        days: int = 365,
        initial_capital: float = 1000000,
        interval: int = 60,
        notify: bool = False,
        **kwargs
    ) -> CommandResult:
        """
        运行策略（IRunner 接口实现）
        
        根据 mode 构建 EngineConfig，通过 engine_manager 启动任务。
        """
        import time
        
        # 参数校验
        if not symbols:
            return CommandResult(success=False, error="缺少标的参数")
        
        if mode == "backtest" and (not start_date or not end_date):
            return CommandResult(success=False, error="回测模式需要指定 start_date 和 end_date")
        
        # 获取通知配置
        notification_config = None
        if notify or (self.config.notification and self.config.notification.enabled):
            notification_config = self.config.notification
        
        # 构建 EngineConfig
        mode_map = {
            "backtest": EngineMode.BACKTEST,
            "analyze": EngineMode.ANALYZE,
            "live": EngineMode.LIVE,
        }
        engine_mode = mode_map.get(mode)
        if not engine_mode:
            return CommandResult(success=False, error=f"不支持的运行模式: {mode}")
        
        config = EngineConfig(
            mode=engine_mode,
            symbols=symbols,
            strategy_name=strategy,
            strategy_config=strategy_config,
            initial_capital=initial_capital,
            start_date=start_date,
            end_date=end_date,
            days=days,
            poll_interval=interval,
            frequency=kwargs.get("frequency", "daily"),
            notify=notify or (notification_config is not None),
            notification_config=notification_config,
            data_service=self._data_service,
        )
        
        try:
            task_id = self._engine_manager.start(config)
            
            # live 模式：保持运行
            if mode == "live":
                return self._run_live_mode(task_id, symbols)
            
            # backtest/analyze：同步等待结果
            timeout = 600 if mode == "backtest" else 120
            return self._wait_for_result(task_id, timeout=timeout)
            
        except Exception as e:
            logger.error(f"运行策略失败: {e}", exc_info=True)
            return CommandResult(success=False, error=str(e))

    def _wait_for_result(self, task_id: str, timeout: int = 300) -> CommandResult:
        """同步等待任务完成"""
        from src.core.engine_manager import TaskStatus
        
        poll_interval = 0.5
        elapsed = 0
        
        while elapsed < timeout:
            status_info = self._engine_manager.status(task_id)
            
            if status_info is None:
                return CommandResult(success=False, error=f"任务 {task_id} 不存在")
            
            task_status = status_info.get("status")
            
            if task_status == TaskStatus.STOPPED.value:
                result = self._engine_manager.get_result(task_id)
                return CommandResult(success=True, data=result)
            
            if task_status == TaskStatus.ERROR.value:
                error = status_info.get("error", "未知错误")
                return CommandResult(success=False, error=error)
            
            import time
            time.sleep(poll_interval)
            elapsed += poll_interval
        
        self._engine_manager.stop(task_id)
        return CommandResult(success=False, error=f"任务超时 ({timeout}s)")

    def _run_live_mode(self, task_id: str, symbols: list) -> CommandResult:
        """运行实时模式"""
        import time
        import sys
        from src.core.engine_manager import TaskStatus
        
        print(f"\n✓ 实时任务已启动 (task_id={task_id})")
        print(f"  监控标的: {', '.join(symbols)}")
        print(f"\n按 Ctrl+C 停止...\n")
        sys.stdout.flush()
        
        try:
            while True:
                time.sleep(1)
                status_info = self._engine_manager.status(task_id)
                if status_info and status_info.get("status") == "error":
                    error = status_info.get("error", "未知错误")
                    return CommandResult(success=False, error=f"任务异常: {error}")
        except KeyboardInterrupt:
            print("\n\n正在停止实时任务...")
            self._engine_manager.stop(task_id)
            return CommandResult(
                success=True,
                message="实时任务已停止",
                data={"task_id": task_id},
            )

    # ──────────────────────────────────────────────────────────────────
    # IRunner 接口实现：策略管理
    # ──────────────────────────────────────────────────────────────────

    def list_strategies(self) -> CommandResult:
        """列出所有可用策略"""
        try:
            names = self._strategy_manager.get_strategy_names()
            return CommandResult(
                success=True, 
                data={"strategies": names, "count": len(names)}
            )
        except Exception as e:
            return CommandResult(success=False, error=str(e))

    def reload_strategies(self) -> CommandResult:
        """重新加载策略"""
        try:
            self._strategy_manager.reload()
            names = self._strategy_manager.get_strategy_names()
            return CommandResult(
                success=True,
                message="策略已重新加载",
                data=names
            )
        except Exception as e:
            return CommandResult(success=False, error=str(e))

    def list_strategy_files(self) -> CommandResult:
        """列出策略文件"""
        try:
            from pathlib import Path
            strategy_dir = Path(self.config.strategy.directory)
            files = []
            
            for f in strategy_dir.glob("*.py"):
                if f.name.startswith("_"):
                    continue
                files.append({
                    "name": f.stem,
                    "path": str(f),
                    "type": "python"
                })
            
            for f in strategy_dir.glob("*.yaml"):
                files.append({
                    "name": f.stem,
                    "path": str(f),
                    "type": "config"
                })
            
            return CommandResult(success=True, data=files)
        except Exception as e:
            return CommandResult(success=False, error=str(e))

    def create_strategy(self, name: str) -> CommandResult:
        """创建策略文件"""
        try:
            from pathlib import Path
            strategy_dir = Path(self.config.strategy.directory)
            strategy_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = strategy_dir / f"{name}_strategy.py"
            
            template = f'''"""
{name} 策略
"""
from src.strategy.base import BaseStrategy


class {name.capitalize()}Strategy(BaseStrategy):
    """TODO: 实现策略逻辑"""
    
    def on_bar(self, bar):
        """处理 K 线数据"""
        pass
'''
            
            file_path.write_text(template)
            return CommandResult(
                success=True,
                message=f"策略文件已创建: {file_path}",
                data={"path": str(file_path)}
            )
        except Exception as e:
            return CommandResult(success=False, error=str(e))

    def delete_strategy(self, name: str) -> CommandResult:
        """删除策略文件（软删除）"""
        try:
            from pathlib import Path
            strategy_dir = Path(self.config.strategy.directory)
            
            # 查找匹配的文件
            for f in strategy_dir.glob(f"{name}*.py"):
                new_name = f.with_name(f"_{f.name}")
                f.rename(new_name)
                return CommandResult(
                    success=True,
                    message=f"策略已软删除: {f.name} -> {new_name.name}"
                )
            
            return CommandResult(success=False, error=f"未找到策略文件: {name}")
        except Exception as e:
            return CommandResult(success=False, error=str(e))

    # ──────────────────────────────────────────────────────────────────
    # IRunner 接口实现：数据管理
    # ──────────────────────────────────────────────────────────────────

    def sync_data(
        self, 
        symbols: list, 
        frequency: str = "daily", 
        days: int = 365
    ) -> CommandResult:
        """同步行情数据"""
        try:
            from datetime import datetime, timedelta
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            results = {}
            
            for symbol in symbols:
                try:
                    df = self._data_service.get_history(symbol, start_date, end_date)
                    count = len(df) if df is not None and not df.empty else 0
                    results[symbol] = {"status": "ok", "count": count}
                except Exception as e:
                    results[symbol] = {"status": "error", "error": str(e)}
            
            success_count = sum(1 for v in results.values() if v["status"] == "ok")
            return CommandResult(
                success=True,
                message=f"数据同步完成: {success_count}/{len(symbols)} 成功",
                data=results,
            )
        except Exception as e:
            return CommandResult(success=False, error=str(e))

    def get_data_info(self, symbol: str = None) -> CommandResult:
        """查看数据信息"""
        try:
            if symbol:
                stats_list = self._data_service.get_data_stats(symbol)
                return CommandResult(success=True, data={"daily": stats_list})
            else:
                stats_list = self._data_service.get_data_stats()
                return CommandResult(success=True, data={"daily": stats_list})
        except Exception as e:
            return CommandResult(success=False, error=str(e))


__all__ = ["ApplicationRunner"]
