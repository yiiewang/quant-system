"""
单次命令执行模式

通过 ApplicationRunner.engine_manager 启动引擎任务，
轮询任务状态获取结果。

职责:
- 接收 CLI 解析好的参数，构建 EngineConfig
- 通过 EngineManager.start() 启动任务
- 同步等待结果（回测/分析）或直接返回 task_id（实时）
- 返回 CommandResult 供 CLI 层输出
"""
import time
from typing import List, Optional, Callable, TYPE_CHECKING

from src.core.models import EngineConfig

from .execution_modes import ExecutionMode, CommandResult

if TYPE_CHECKING:
    from src.runner.interfaces import IRunner


class CommandMode(ExecutionMode):
    """
    单次命令执行模式

    通过 ApplicationRunner.engine_manager 执行业务操作
    CLI 层负责解析参数，本层只负责构建 EngineConfig 并启动任务
    """

    @property
    def name(self) -> str:
        return "command"

    @property
    def description(self) -> str:
        return "单次命令执行模式"

    def execute(self, command: str, args: Optional[List[str]] = None, **kwargs) -> CommandResult:
        """
        执行命令

        Args:
            command: 命令名称 (run)
            args: 保留参数（兼容旧接口，实际参数通过 kwargs 传递）
            **kwargs: CLI 解析好的参数
        """
        if not self._runner:
            return CommandResult(success=False, error="Runner 未初始化")

        dispatch = {
            "run": self._cmd_run,
            "sync": self._cmd_sync,
            "data": self._cmd_data,
        }

        handler = dispatch.get(command)
        if not handler:
            return CommandResult(success=False, error=f"未知命令: {command}")

        return handler(**kwargs)

    # ──────────────────────────────────────────────────────────────────
    # 策略执行命令（通过 engine_manager）
    # ──────────────────────────────────────────────────────────────────

    def _build_engine_config(self, mode: str, **kwargs) -> EngineConfig:
        """根据 kwargs 构建 EngineConfig"""
        from src.core.models import EngineConfig, EngineMode  # type: ignore

        mode_map = {
            "backtest": EngineMode.BACKTEST,
            "analyze": EngineMode.ANALYZE,
            "live": EngineMode.LIVE,
        }
        engine_mode = mode_map.get(mode)
        if not engine_mode:
            raise ValueError(f"不支持的运行模式: {mode}")

        return EngineConfig(
            mode=engine_mode,
            symbols=kwargs.get("symbols") or [],
            strategy_name=kwargs.get("strategy") or "macd",
            strategy_config=kwargs.get("strategy_config"),
            initial_capital=kwargs.get("initial_capital", 1000000),
            start_date=kwargs.get("start_date"),
            end_date=kwargs.get("end_date"),
            days=kwargs.get("days", 365),
            poll_interval=kwargs.get("interval", 60),
            notify=kwargs.get("notify", False),
            data_service=kwargs.get("data_service"),  # 注入共享数据服务
        )

    def _cmd_run(
        self,
        mode: str = "live",
        symbol: Optional[List[str]] = None,
        strategy: Optional[str] = None,
        strategy_config: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days: int = 365,
        source: str = "baostock",
        interval: int = 60,
        initial_capital: float = 1000000,
        notify: bool = False,
        progress_callback: Optional[Callable[[float], None]] = None,
        **kwargs
    ) -> CommandResult:
        """
        统一策略执行入口

        根据 mode 构建对应的 EngineConfig，通过 engine_manager.start() 启动任务。
        - backtest/analyze: 同步等待结果返回
        - live: 立即返回 task_id
        """
        if not symbol:
            return CommandResult(success=False, error="缺少标的参数")

        # 回测模式校验日期
        if mode == "backtest" and (not start_date or not end_date):
            return CommandResult(success=False, error="回测模式需要指定 --start 和 --end")

        config = self._build_engine_config(
            mode,
            symbols=symbol,
            strategy=strategy,
            strategy_config=strategy_config,
            start_date=start_date,
            end_date=end_date,
            days=days,
            interval=interval,
            initial_capital=initial_capital,
            notify=notify,
        )

        try:
            task_id = self._runner.engine_manager.start(
                config, progress_callback=progress_callback
            )

            # live 模式直接返回 task_id，不等待
            if mode == "live":
                return CommandResult(
                    success=True,
                    message=f"实时任务已启动, task_id={task_id}",
                    data={"task_id": task_id, "symbols": symbol},
                )

            # backtest/analyze 同步等待结果
            timeout = 600 if mode == "backtest" else 120
            return self._wait_for_result(task_id, timeout=timeout)
        except Exception as e:
            return CommandResult(success=False, error=str(e))

    # ──────────────────────────────────────────────────────────────────
    # 数据管理命令
    # ──────────────────────────────────────────────────────────────────

    def _cmd_sync(
        self,
        symbols: Optional[List[str]] = None,
        frequency: str = "daily",
        days: int = 365,
        **kwargs
    ) -> CommandResult:
        """同步行情数据"""
        if not symbols:
            return CommandResult(success=False, error="缺少标的参数")

        try:
            from src.data.market import MarketDataService
            service = MarketDataService()
            results = {}
            for symbol in symbols:
                try:
                    df = service.get_history(symbol, days=days)
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

    def _cmd_data(
        self,
        symbol: Optional[str] = None,
        **kwargs
    ) -> CommandResult:
        """查看数据信息"""
        try:
            from src.data.market import MarketDataService
            service = MarketDataService()

            if symbol:
                # 单个标的的数据统计
                df = service.get_history(symbol)
                if df is not None and not df.empty:
                    stats = {
                        "symbol": symbol,
                        "count": len(df),
                        "start_date": str(df.index[0])[:10],
                        "end_date": str(df.index[-1])[:10],
                    }
                    return CommandResult(success=True, data={"daily": [stats]})
                return CommandResult(success=True, data={"daily": []})

            # 全部标的的数据统计
            symbols = service.list_symbols() if hasattr(service, 'list_symbols') else []
            stats_list = []
            for sym in symbols:
                df = service.get_history(sym)
                if df is not None and not df.empty:
                    stats_list.append({
                        "symbol": sym,
                        "count": len(df),
                        "start_date": str(df.index[0])[:10],
                        "end_date": str(df.index[-1])[:10],
                    })
            return CommandResult(success=True, data={"daily": stats_list})
        except Exception as e:
            return CommandResult(success=False, error=str(e))

    # ──────────────────────────────────────────────────────────────────
    # 内部工具方法
    # ──────────────────────────────────────────────────────────────────

    def _wait_for_result(
        self, task_id: str, timeout: int = 300, poll_interval: float = 0.5
    ) -> CommandResult:
        """
        同步等待任务完成并返回结果

        Args:
            task_id: 任务ID
            timeout: 超时时间（秒）
            poll_interval: 轮询间隔（秒）
        """
        from src.core.engine_manager import TaskStatus

        elapsed = 0
        while elapsed < timeout:
            status_info = self._runner.engine_manager.status(task_id)

            if status_info is None:
                return CommandResult(success=False, error=f"任务 {task_id} 不存在")

            task_status = status_info.get("status")

            if task_status == TaskStatus.STOPPED.value:
                result = self._runner.engine_manager.get_result(task_id)
                return CommandResult(success=True, data=result)

            if task_status == TaskStatus.ERROR.value:
                error = status_info.get("error", "未知错误")
                return CommandResult(success=False, error=error)

            time.sleep(poll_interval)
            elapsed += poll_interval

        # 超时，停止任务
        self._runner.engine_manager.stop(task_id)
        return CommandResult(success=False, error=f"任务超时 ({timeout}s)")
