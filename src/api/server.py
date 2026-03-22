"""
FastAPI HTTP 服务
提供回测、分析、监控等 RESTful API 接口

架构：
    API 端点 → ApplicationRunner 业务方法 → 内部组件

启动方式:
    python -m src.cli.main serve --port 8000
    或
    uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
"""
import logging
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)

# 创建限流器
limiter = Limiter(key_func=get_remote_address)


# ==================== 请求/响应模型 ====================

class AnalyzeRequest(BaseModel):
    """分析请求"""
    symbols: List[str] = Field(..., description="分析标的列表", min_length=1)
    strategy: Optional[str] = Field(default=None, description="策略类型")
    days: int = Field(default=365, description="回溯天数", ge=1, le=3650)
    source: str = Field(default="baostock", description="数据源")


class BacktestRequest(BaseModel):
    """回测请求"""
    symbols: List[str] = Field(..., description="回测标的列表", min_length=1)
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    strategy: Optional[str] = Field(default=None, description="策略类型")
    initial_capital: float = Field(default=1000000, description="初始资金", gt=0)


class MonitorStartRequest(BaseModel):
    """监控启动请求"""
    symbols: List[str] = Field(..., description="监控标的列表", min_length=1)
    strategy: Optional[str] = Field(default=None, description="策略类型")
    interval: int = Field(default=60, description="检查间隔(秒)", ge=10, le=3600)


class DataSyncRequest(BaseModel):
    """数据同步请求"""
    symbols: List[str] = Field(..., description="股票代码列表", min_length=1)
    frequency: str = Field(default="daily", description="数据频率: daily/5min/15min/30min/60min")
    days: int = Field(default=365, description="同步天数", ge=1, le=3650)


class ApiResponse(BaseModel):
    """统一响应"""
    success: bool = True
    message: str = ""
    data: Optional[Any] = None


# ==================== 全局状态 ====================

class _AppState:
    """应用全局状态"""

    def __init__(self):
        self._runner = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_config: Optional[Dict] = None

    @property
    def monitor_running(self) -> bool:
        return (
            self._monitor_thread is not None
            and self._monitor_thread.is_alive()
        )

    def get_runner(self):
        """获取或创建 Runner"""
        if self._runner is None:
            from src.config.base import load_config
            from src.config.schema import Config
            config = load_config(Config)
            params = {}
            from src.runner.application import ApplicationRunner
            self._runner = ApplicationRunner(config, params)
        return self._runner

    def stop_monitor(self):
        if self._runner:
            self._runner.stop()
        self._monitor_thread = None
        self._monitor_config = None


_state = _AppState()


# ==================== FastAPI 应用 ====================

def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""

    app = FastAPI(
        title="MACD 量化交易系统 API",
        description="提供回测、分析、监控等 RESTful API 接口",
        version="1.0.0",
    )
    
    # 配置限流器
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # 添加 CORS 中间件 - 修复：限制允许的来源
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",  # 前端开发服务器
            "http://localhost:8080",
            "https://quant-system.example.com",  # 生产环境域名
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
        max_age=600,
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
        runner = _state.get_runner()
        result = runner.list_strategies()
        return ApiResponse(
            success=result.success,
            message=result.message or "",
            data=result.data,
        )

    # ---------- 分析 ----------

    @app.post("/api/analyze", response_model=ApiResponse, tags=["分析"])
    async def analyze(req: AnalyzeRequest):
        """分析指定标的的当前状态"""
        runner = _state.get_runner()
        result = runner.analyze(
            symbols=req.symbols,
            strategy=req.strategy,
            days=req.days,
            source=req.source,
        )
        return ApiResponse(
            success=result.success,
            message=result.message or "",
            data=result.data,
        )

    # ---------- 回测 ----------

    @app.post("/api/backtest", response_model=ApiResponse, tags=["回测"])
    @limiter.limit("5/minute")  # 回测计算密集，限制每分钟5次
    async def backtest(req: BacktestRequest, request: Request):
        """运行历史回测"""
        # 校验日期
        try:
            datetime.strptime(req.start_date, "%Y-%m-%d")
            datetime.strptime(req.end_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

        runner = _state.get_runner()
        result = runner.backtest(
            symbols=req.symbols,
            start_date=req.start_date,
            end_date=req.end_date,
            strategy=req.strategy,
            initial_capital=req.initial_capital,
        )
        return ApiResponse(
            success=result.success,
            message=result.message or "",
            data=result.data,
        )

    # ---------- 监控 ----------

    @app.post("/api/monitor/start", response_model=ApiResponse, tags=["监控"])
    async def monitor_start(req: MonitorStartRequest):
        """启动后台监控"""
        if _state.monitor_running:
            raise HTTPException(status_code=409, detail="监控已在运行中，请先停止")

        runner = _state.get_runner()

        def _run():
            try:
                runner.monitor(
                    action="start",
                    symbols=req.symbols,
                    strategy=req.strategy,
                    interval=req.interval,
                )
            except Exception as e:
                logger.error(f"监控异常退出: {e}")

        _state._monitor_config = {
            "symbols": req.symbols,
            "strategy": req.strategy,
            "interval": req.interval,
            "started_at": datetime.now().isoformat(),
        }

        t = threading.Thread(target=_run, daemon=True, name="monitor-thread")
        _state._monitor_thread = t
        t.start()

        return ApiResponse(message="监控已启动", data=_state._monitor_config)

    @app.post("/api/monitor/stop", response_model=ApiResponse, tags=["监控"])
    async def monitor_stop():
        """停止后台监控"""
        if not _state.monitor_running:
            raise HTTPException(status_code=400, detail="当前无运行中的监控")

        runner = _state.get_runner()
        runner.monitor(action="stop")
        _state._monitor_thread = None
        _state._monitor_config = None
        
        return ApiResponse(message="监控已停止")

    @app.get("/api/monitor/status", response_model=ApiResponse, tags=["监控"])
    async def monitor_status():
        """查看监控状态"""
        if not _state.monitor_running:
            return ApiResponse(data={"running": False})

        runner = _state.get_runner()
        result = runner.monitor(action="status")
        
        return ApiResponse(
            data={
                "running": True,
                "config": _state._monitor_config,
                "status": result.data,
            }
        )

    # ---------- 数据同步 ----------

    @app.post("/api/data/sync", response_model=ApiResponse, tags=["数据"])
    async def data_sync(req: DataSyncRequest):
        """同步行情数据"""
        runner = _state.get_runner()
        result = runner.sync_data(
            symbols=req.symbols,
            frequency=req.frequency,
            days=req.days,
        )
        return ApiResponse(
            success=result.success,
            message=result.message or "",
            data=result.data,
        )

    @app.get("/api/data/info", response_model=ApiResponse, tags=["数据"])
    async def data_info(symbol: Optional[str] = None):
        """查看数据统计信息"""
        runner = _state.get_runner()
        result = runner.get_data_info(symbol)
        return ApiResponse(
            success=result.success,
            data=result.data,
        )

    return app


# 模块级 app 实例，供 uvicorn 直接引用
app = create_app()
