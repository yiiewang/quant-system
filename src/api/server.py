"""
FastAPI HTTP 服务
提供回测、分析、监控等 RESTful API 接口

启动方式:
    python -m src.main serve --port 8000
    或
    uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
"""
import logging
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ==================== 请求/响应模型 ====================

class AnalyzeRequest(BaseModel):
    """分析请求"""
    symbols: List[str] = Field(..., description="分析标的列表", min_length=1)
    strategy: str = Field(default="macd", description="策略类型")
    days: int = Field(default=365, description="回溯天数", ge=1, le=3650)
    source: str = Field(default="baostock", description="数据源")
    config_path: Optional[str] = Field(default=None, description="策略配置文件路径")


class BacktestRequest(BaseModel):
    """回测请求"""
    symbols: List[str] = Field(..., description="回测标的列表", min_length=1)
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    strategy: str = Field(default="macd", description="策略类型")
    initial_capital: float = Field(default=1000000, description="初始资金", gt=0)
    config_path: Optional[str] = Field(default=None, description="策略配置文件路径")


class MonitorStartRequest(BaseModel):
    """监控启动请求"""
    symbols: List[str] = Field(..., description="监控标的列表", min_length=1)
    strategy: str = Field(default="macd", description="策略类型")
    interval: int = Field(default=60, description="检查间隔(秒)", ge=10, le=3600)
    source: str = Field(default="baostock", description="数据源")
    config_path: Optional[str] = Field(default=None, description="策略配置文件路径")


class ApiResponse(BaseModel):
    """统一响应"""
    success: bool = True
    message: str = ""
    data: Optional[Any] = None


# ==================== 全局状态 ====================

class _AppState:
    """应用全局状态，管理后台运行的 runner 实例"""

    def __init__(self):
        self.monitor_runner = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.monitor_config: Optional[Dict] = None

    @property
    def monitor_running(self) -> bool:
        return (
            self.monitor_thread is not None
            and self.monitor_thread.is_alive()
        )

    def stop_monitor(self):
        if self.monitor_runner:
            self.monitor_runner.stop()
        self.monitor_runner = None
        self.monitor_thread = None
        self.monitor_config = None


_state = _AppState()


# ==================== 辅助函数 ====================

def _ensure_strategies():
    """确保策略已注册"""
    from src.strategy.registry import get_registry
    registry = get_registry()
    if not registry.has('macd'):
        import src.strategy  # noqa: F401


def _load_config(config_path: Optional[str], strategy_name: str = "macd"):
    """加载配置"""
    from src.config.loader import load_config

    path = config_path or "src/strategy/configs/default.yaml"
    config = load_config(path)
    config.strategy.name = strategy_name
    return config


# ==================== FastAPI 应用 ====================

def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""

    app = FastAPI(
        title="MACD 量化交易系统 API",
        description="提供回测、分析、监控等 RESTful API 接口",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------- 系统信息 ----------

    @app.get("/", response_model=ApiResponse, tags=["系统"])
    async def root():
        """系统信息"""
        return ApiResponse(
            message="MACD 量化交易系统 API",
            data={
                "version": "1.0.0",
                "endpoints": {
                    "分析": "POST /api/analyze",
                    "回测": "POST /api/backtest",
                    "监控-启动": "POST /api/monitor/start",
                    "监控-停止": "POST /api/monitor/stop",
                    "监控-状态": "GET  /api/monitor/status",
                    "策略列表": "GET  /api/strategies",
                    "健康检查": "GET  /api/health",
                },
            },
        )

    @app.get("/api/health", response_model=ApiResponse, tags=["系统"])
    async def health():
        """健康检查"""
        return ApiResponse(
            message="ok",
            data={
                "status": "healthy",
                "monitor_running": _state.monitor_running,
            },
        )

    # ---------- 策略 ----------

    @app.get("/api/strategies", response_model=ApiResponse, tags=["策略"])
    async def list_strategies():
        """列出所有可用策略"""
        _ensure_strategies()
        from src.strategy.registry import get_registry

        registry = get_registry()
        strategies = registry.list_strategies()
        return ApiResponse(data=strategies)

    # ---------- 分析 ----------

    @app.post("/api/analyze", response_model=ApiResponse, tags=["分析"])
    async def analyze(req: AnalyzeRequest):
        """
        分析指定标的的当前状态

        返回每个标的的状态、建议操作、置信度和关键指标。
        """
        _ensure_strategies()

        config = _load_config(req.config_path, req.strategy)

        from src.config.loader import RunParams
        from src.runner.application import ApplicationRunner

        params = RunParams(
            mode="analyze",
            symbols=req.symbols,
            days=req.days,
            source=req.source,
        )
        params.merge_with_config(config)

        runner = ApplicationRunner(config=config, params=params)

        results = []
        for symbol in req.symbols:
            try:
                result = runner._engine.run_analyze(symbol, req.days)
                results.append(result)
            except Exception as e:
                results.append({"symbol": symbol, "error": str(e)})

        return ApiResponse(data=results)

    # ---------- 回测 ----------

    @app.post("/api/backtest", response_model=ApiResponse, tags=["回测"])
    async def backtest(req: BacktestRequest):
        """
        运行历史回测

        返回回测指标（收益率、夏普比率、最大回撤等）和交易记录。
        """
        # 校验日期
        try:
            datetime.strptime(req.start_date, "%Y-%m-%d")
            datetime.strptime(req.end_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

        _ensure_strategies()

        config = _load_config(req.config_path, req.strategy)

        from src.config.loader import RunParams
        from src.runner.application import ApplicationRunner

        params = RunParams(
            mode="backtest",
            symbols=req.symbols,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=req.initial_capital,
        )
        params.merge_with_config(config)

        runner = ApplicationRunner(config=config, params=params)
        result = runner.start("backtest")

        data = result.to_dict() if result else {}
        return ApiResponse(data=data)

    # ---------- 监控 ----------

    @app.post("/api/monitor/start", response_model=ApiResponse, tags=["监控"])
    async def monitor_start(req: MonitorStartRequest):
        """
        启动后台监控

        以后台线程运行，循环检查标的信号变化。
        同一时间只允许运行一个监控实例。
        """
        if _state.monitor_running:
            raise HTTPException(status_code=409, detail="监控已在运行中，请先停止")

        _ensure_strategies()

        config = _load_config(req.config_path, req.strategy)

        from src.config.loader import RunParams
        from src.runner.application import ApplicationRunner

        params = RunParams(
            mode="monitor",
            symbols=req.symbols,
            interval=req.interval,
            source=req.source,
        )
        params.merge_with_config(config)

        runner = ApplicationRunner(config=config, params=params)

        def _run():
            try:
                runner.start("monitor")
            except Exception as e:
                logger.error(f"监控异常退出: {e}")

        _state.monitor_runner = runner
        _state.monitor_config = {
            "symbols": req.symbols,
            "strategy": req.strategy,
            "interval": req.interval,
            "started_at": datetime.now().isoformat(),
        }

        t = threading.Thread(target=_run, daemon=True, name="monitor-thread")
        _state.monitor_thread = t
        t.start()

        return ApiResponse(message="监控已启动", data=_state.monitor_config)

    @app.post("/api/monitor/stop", response_model=ApiResponse, tags=["监控"])
    async def monitor_stop():
        """停止后台监控"""
        if not _state.monitor_running:
            raise HTTPException(status_code=400, detail="当前无运行中的监控")

        _state.stop_monitor()
        return ApiResponse(message="监控已停止")

    @app.get("/api/monitor/status", response_model=ApiResponse, tags=["监控"])
    async def monitor_status():
        """查看监控状态"""
        if not _state.monitor_running:
            return ApiResponse(data={"running": False})

        runner_status = {}
        if _state.monitor_runner:
            try:
                runner_status = _state.monitor_runner.get_status()
            except Exception:
                pass

        return ApiResponse(
            data={
                "running": True,
                "config": _state.monitor_config,
                "engine": runner_status,
            }
        )

    return app


# 模块级 app 实例，供 uvicorn 直接引用
app = create_app()
