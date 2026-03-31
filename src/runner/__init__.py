"""
Runner 模块

提供 IRunner 接口定义和 ApplicationRunner 实现。
"""

from .interfaces import IRunner, CommandResult
from .application import ApplicationRunner

# 全局 Runner 实例（用于 API 服务）
_runner = None


def get_runner():
    """获取或创建全局 Runner 实例"""
    global _runner
    if _runner is None:
        from src.config.base import load_config
        from src.config.schema import Config
        config = load_config(Config)
        _runner = ApplicationRunner(config)
    return _runner


def create_app():
    """创建 FastAPI 应用（uvicorn factory 模式）"""
    runner = get_runner()
    return runner.create_app()


__all__ = [
    "IRunner",
    "CommandResult",
    "ApplicationRunner",
    "get_runner",
    "create_app",
]
