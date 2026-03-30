"""
Runner 模块

提供 IRunner 接口定义和 ApplicationRunner 实现。
"""

from .interfaces import IRunner, CommandResult
from .application import ApplicationRunner

__all__ = [
    "IRunner",
    "CommandResult",
    "ApplicationRunner",
]
