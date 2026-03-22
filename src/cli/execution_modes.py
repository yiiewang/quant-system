"""
执行模式统一架构

使用策略模式(Strategy Pattern)统一四种执行模式:
- CommandMode: 单次命令执行
- InteractiveMode: 本地交互式REPL
- ClientMode: 远程客户端(连接HTTP API)
- ServerMode: HTTP API服务端

设计原则：
- ExecutionMode 只关注"如何执行"（单次/交互/远程/服务端）
- 业务逻辑由 ApplicationRunner 提供
- CLI 层是纯粹的交互层
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from src.runner.interfaces import IRunner


# ==================== 核心类型定义 ====================

@dataclass
class CommandResult:
    """命令执行结果"""
    success: bool
    data: Any = None
    message: str = ""
    error: Optional[str] = None
    
    @classmethod
    def from_operation_result(cls, result) -> "CommandResult":
        """从 OperationResult 转换"""
        return cls(
            success=result.success,
            data=result.data,
            message=result.message,
            error=result.error,
        )


class ExecutionMode(ABC):
    """
    执行模式抽象基类
    
    只定义交互方式，不定义具体业务操作
    业务操作由 IRunner 提供
    """
    
    def __init__(self, runner: "IRunner" = None):
        """
        初始化执行模式
        
        Args:
            runner: IRunner 实例（本地模式需要）
        """
        self._runner = runner
    
    @property
    @abstractmethod
    def name(self) -> str:
        """模式名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """模式描述"""
        pass
    
    @abstractmethod
    def execute(self, command: str, args: Optional[List[str]] = None, **kwargs) -> CommandResult:
        """
        执行命令
        
        Args:
            command: 命令名称 (analyze/backtest/live/strategies等)
            args: 命令参数
            **kwargs: 额外参数
            
        Returns:
            CommandResult: 执行结果
        """
        pass
    
    @property
    def runner(self) -> "IRunner":
        """获取关联的 Runner"""
        return self._runner
    
    @runner.setter
    def runner(self, value: "IRunner"):
        """设置关联的 Runner"""
        self._runner = value
    
    def start(self):
        """
        启动模式（用于交互式模式）
        默认空实现，子类可重写
        """
        pass
    
    def stop(self):
        """
        停止模式
        默认空实现，子类可重写
        """
        pass


# ==================== 模式工厂 ====================

def create_mode(mode: str, runner: "IRunner" = None, **kwargs) -> ExecutionMode:
    """
    创建执行模式实例
    
    Args:
        mode: 模式名称 (command/interactive/client/server)
        runner: IRunner 实例
        **kwargs: 模式参数
        
    Returns:
        ExecutionMode: 执行模式实例
        
    Raises:
        ValueError: 无效的模式名称
    """
    from .command_mode import CommandMode
    from .interactive_mode import InteractiveMode
    from .client_mode import ClientMode
    from .server_mode import ServerMode
    
    modes = {
        "command": CommandMode,
        "interactive": InteractiveMode,
        "client": lambda: ClientMode(
            server=kwargs.get("server", "localhost:8000"),
            runner=runner,
        ),
        "server": lambda: ServerMode(
            host=kwargs.get("host", "0.0.0.0"),
            port=kwargs.get("port", 8000),
            workers=kwargs.get("workers", 1),
            auto_reload=kwargs.get("auto_reload", False),
            runner=runner,
        ),
    }
    
    factory = modes.get(mode)
    if not factory:
        raise ValueError(f"无效的执行模式: {mode}. 可用: {list(modes.keys())}")
    
    # 创建实例并设置 runner
    if mode in ("command", "interactive"):
        instance = factory(runner=runner)
    else:
        instance = factory()
    
    return instance


__all__ = [
    "ExecutionMode",
    "CommandResult", 
    "CommandMode",
    "InteractiveMode",
    "ClientMode",
    "ServerMode",
    "create_mode",
]
