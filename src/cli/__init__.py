"""
CLI 模块

提供四种执行模式：
- CommandMode: 单次命令执行
- InteractiveMode: 交互式 REPL
- ClientMode: 远程客户端
- ServerMode: HTTP API 服务端
"""

from .execution_modes import (
    ExecutionMode,
    create_mode,
)
from .command_mode import CommandMode
from .interactive_mode import InteractiveMode
from .client_mode import ClientMode
from .server_mode import ServerMode

__all__ = [
    "ExecutionMode",
    "CommandMode",
    "InteractiveMode",
    "ClientMode",
    "ServerMode",
    "create_mode",
]
