"""
HTTP API 服务

将 HTTP 请求转换为 IRunner 方法调用，所有端点统一调用 Runner 接口。
"""
import logging
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.runner.interfaces import CommandResult

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
# 全局 Runner 实例
# ──────────────────────────────────────────────────────────────────

_runner = None


def get_runner():
    """获取或创建 Runner 实例"""
    global _runner
    if _runner is None:
        from src.config.base import load_config
        from src.config.schema import Config
        from src.runner.application import ApplicationRunner
        config = load_config(Config)
        _runner = ApplicationRunner(config)
    return _runner


# ──────────────────────────────────────────────────────────────────
# 请求模型（对应 IRunner 方法签名）
# ──────────────────────────────────────────────────────────────────

class StrategyRequest(BaseModel):
    """运行策略请求"""
    mode: str  # analyze/backtest/live
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
    """同步数据请求"""
    symbols: List[str]
    frequency: str = "daily"
    days: int = 365


class CreateStrategyRequest(BaseModel):
    """创建策略请求"""
    name: str


class DeleteStrategyRequest(BaseModel):
    """删除策略请求"""
    name: str


# ──────────────────────────────────────────────────────────────────
# FastAPI 应用
# ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动时初始化 Runner
    get_runner()
    logger.info("API 服务已启动")
    yield
    logger.info("API 服务已停止")


app = FastAPI(
    title="量化交易系统 API",
    description="基于 IRunner 接口的 HTTP API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 限流配置
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter


# ──────────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────────

def result_to_response(result: CommandResult):
    """将 CommandResult 转换为 HTTP 响应"""
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return result.to_dict()


# ──────────────────────────────────────────────────────────────────
# API 端点
# ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}


@app.get("/api/strategies")
async def list_strategies():
    """列出可用策略"""
    runner = get_runner()
    result = runner.list_strategies()
    return result_to_response(result)


@app.post("/api/strategy")
async def run_strategy(request: StrategyRequest):
    """运行策略（统一入口）"""
    runner = get_runner()
    result = runner.run(
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
    )
    return result_to_response(result)


@app.get("/api/strategy-files")
async def list_strategy_files():
    """列出策略文件"""
    runner = get_runner()
    result = runner.list_strategy_files()
    return result_to_response(result)


@app.post("/api/strategy/create")
async def create_strategy(request: CreateStrategyRequest):
    """创建策略"""
    runner = get_runner()
    result = runner.create_strategy(request.name)
    return result_to_response(result)


@app.post("/api/strategy/delete")
async def delete_strategy(request: DeleteStrategyRequest):
    """删除策略"""
    runner = get_runner()
    result = runner.delete_strategy(request.name)
    return result_to_response(result)


@app.post("/api/strategy/reload")
async def reload_strategies():
    """重新加载策略"""
    runner = get_runner()
    result = runner.reload_strategies()
    return result_to_response(result)


@app.post("/api/data/sync")
async def sync_data(request: SyncDataRequest):
    """同步数据"""
    runner = get_runner()
    result = runner.sync_data(
        symbols=request.symbols,
        frequency=request.frequency,
        days=request.days,
    )
    return result_to_response(result)


@app.get("/api/data/info")
async def get_data_info(symbol: Optional[str] = None):
    """查看数据信息"""
    runner = get_runner()
    result = runner.get_data_info(symbol=symbol)
    return result_to_response(result)


__all__ = ["app"]
