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
from src.core.models import EngineMode, TaskConfig
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
        # 从系统配置获取通知配置
        notification_config = None
        if self.config.notification and self.config.notification.enabled:
            notification_config = self.config.notification
        self._engine_manager = get_engine_manager(
            engine_config, self._event_bus, self._data_service, notification_config
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
        mode: EngineMode,
        strategy: str,
        symbols: list,
        strategy_config: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_capital: float = 1000000,
        interval: int = 60,
        frequency: str = "daily",
    ) -> CommandResult:
        """
        运行策略（IRunner 接口实现）
        
        根据 mode 构建 TaskConfig，通过 engine_manager 启动任务。
        """
        
        # 参数校验
        if not symbols:
            return CommandResult(success=False, error="缺少标的参数")

        if mode == EngineMode.BACKTEST and (not start_date or not end_date):
            return CommandResult(success=False, error="回测模式需要指定 start_date 和 end_date")

        # 构建 TaskConfig（直接包含所有引擎配置）
        # 注意：data_service 和 notification_config 由 EngineManager 从系统配置注入
        task_config = TaskConfig(
            mode=mode,
            symbols=symbols,
            strategy_name=strategy,
            strategy_config=strategy_config,
            initial_capital=initial_capital,
            start_date=start_date,
            end_date=end_date,
            poll_interval=interval,
            frequency=frequency,
            timeout=None,  # CLI 模式下不设置超时，由 CLI 自己控制
        )
        
        try:
            # 统一启动任务，返回 task_id
            task_id = self._engine_manager.start(task_config)
            
            return CommandResult(
                success=True,
                data={
                    "task_id": task_id,
                    "mode": mode.value,
                    "symbols": symbols,
                }
            )
            
        except Exception as e:
            logger.error(f"运行策略失败: {e}", exc_info=True)
            return CommandResult(success=False, error=str(e))

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

    def get_data_info(self, symbol: Optional[str] = None) -> CommandResult:
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

    # ──────────────────────────────────────────────────────────────────
    # HTTP API 支持
    # ──────────────────────────────────────────────────────────────────

    def create_app(self):
        """
        创建 FastAPI 应用
        
        Returns:
            FastAPI 应用实例
        """
        from fastapi import FastAPI, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel
        from typing import Optional, List
        
        # 请求模型
        class StrategyRequest(BaseModel):
            mode: str
            strategy: str
            symbols: List[str]
            strategy_config: Optional[str] = None
            start_date: Optional[str] = None
            end_date: Optional[str] = None
            days: int = 365
            initial_capital: float = 1000000
            interval: int = 60
            notify: bool = False

        class SyncDataRequest(BaseModel):
            symbols: List[str]
            frequency: str = "daily"
            days: int = 365

        class CreateStrategyRequest(BaseModel):
            name: str

        class DeleteStrategyRequest(BaseModel):
            name: str

        # 创建应用
        app = FastAPI(
            title="量化交易系统 API",
            description="基于 IRunner 接口的 HTTP API",
            version="1.0.0",
        )

        # CORS
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        def result_to_response(result: "CommandResult"):
            if not result.success:
                raise HTTPException(status_code=400, detail=result.error)
            return result.to_dict()

        # 端点
        @app.get("/api/health")
        async def health():
            return {"status": "healthy"}

        @app.get("/api/strategies")
        async def list_strategies():
            return result_to_response(self.list_strategies())

        @app.post("/api/strategy")
        async def run_strategy(request: StrategyRequest):
            return result_to_response(self.run(
                mode=request.mode,
                strategy=request.strategy,
                symbols=request.symbols,
                strategy_config=request.strategy_config,
                start_date=request.start_date,
                end_date=request.end_date,
                days=request.days,
                initial_capital=request.initial_capital,
                interval=request.interval,
                notify=request.notify,
            ))

        @app.get("/api/strategy-files")
        async def list_strategy_files():
            return result_to_response(self.list_strategy_files())

        @app.post("/api/strategy/create")
        async def create_strategy(request: CreateStrategyRequest):
            return result_to_response(self.create_strategy(request.name))

        @app.post("/api/strategy/delete")
        async def delete_strategy(request: DeleteStrategyRequest):
            return result_to_response(self.delete_strategy(request.name))

        @app.post("/api/strategy/reload")
        async def reload_strategies():
            return result_to_response(self.reload_strategies())

        @app.post("/api/data/sync")
        async def sync_data(request: SyncDataRequest):
            return result_to_response(self.sync_data(
                symbols=request.symbols,
                frequency=request.frequency,
                days=request.days,
            ))

        @app.get("/api/data/info")
        async def get_data_info(symbol: Optional[str] = None):
            return result_to_response(self.get_data_info(symbol=symbol))

        return app


__all__ = ["ApplicationRunner"]
