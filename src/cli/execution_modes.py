"""
执行模式统一架构

使用策略模式(Strategy Pattern)统一四种执行模式:
- CommandMode: 单次命令执行（CLI 参数）
- InteractiveMode: 本地交互式REPL（用户输入）
- ClientMode: 远程客户端（HTTP 请求）
- ServerMode: HTTP API服务端（HTTP 响应）

设计原则：
- 四种模式只是输入方式不同
- 基类定义统一的命令分发，调用 IRunner 接口
- 子类只需实现输入解析逻辑
"""
from abc import ABC, abstractmethod
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.runner.interfaces import IRunner, CommandResult


class ExecutionMode(ABC):
    """
    执行模式抽象基类
    
    定义统一的命令分发逻辑，四种模式通过 IRunner 接口调用 ApplicationRunner。
    """
    
    def __init__(self, runner: "IRunner"):
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
    
    @property
    def runner(self) -> "IRunner":
        """获取关联的 Runner"""
        return self._runner
    
    @runner.setter
    def runner(self, value: "IRunner"):
        """设置关联的 Runner"""
        self._runner = value
    
    def execute(self, command: str, args: Optional[List[str]] = None, **kwargs) -> "CommandResult":
        """
        执行命令（统一入口）
        
        四种模式统一调用 IRunner 接口的方法。
        kwargs 已包含解析好的参数时直接使用，否则从 args 解析。
        
        Args:
            command: 命令名称
            args: 命令行参数（需要解析）
            **kwargs: 已解析好的参数（优先使用）
            
        Returns:
            CommandResult: 执行结果
        """
        # kwargs 已有完整参数时直接调用
        if kwargs and not args:
            return self._dispatch(command, **kwargs)
        
        # 从 args 解析参数
        parsed = self._parse_args(command, args or [], kwargs)
        return self._dispatch(command, **parsed)
    
    def _dispatch(self, command: str, **kwargs) -> "CommandResult":
        """
        分发命令到 IRunner 方法
        
        所有模式统一调用此方法，确保步调一致。
        子类可重写此方法实现不同的调用方式（如 HTTP）。
        """
        from src.runner.interfaces import CommandResult
        
        # 需要 runner 的命令检查
        if self._runner is None:
            return CommandResult(success=False, error="Runner 未初始化")
        
        # 策略运行（支持 mode 参数区分 analyze/backtest/live）
        if command == "run":
            return self._runner.run(**kwargs)
        
        # 命令别名：analyze/backtest/live -> run(mode=xxx)
        if command == "analyze":
            kwargs["mode"] = "analyze"
            return self._runner.run(**kwargs)
        
        if command == "backtest":
            kwargs["mode"] = "backtest"
            return self._runner.run(**kwargs)
        
        if command == "live":
            kwargs["mode"] = "live"
            return self._runner.run(**kwargs)
        
        # 策略管理
        if command == "strategies":
            return self._runner.list_strategies()
        
        if command == "reload-strategies":
            return self._runner.reload_strategies()
        
        if command == "list-strategy-files":
            return self._runner.list_strategy_files()
        
        if command == "create-strategy":
            name = kwargs.get("name")
            if not name:
                return CommandResult(success=False, error="缺少策略名称")
            return self._runner.create_strategy(name)
        
        if command == "delete-strategy":
            name = kwargs.get("name")
            if not name:
                return CommandResult(success=False, error="缺少策略名称")
            return self._runner.delete_strategy(name)
        
        # 数据管理
        if command == "sync":
            return self._runner.sync_data(**kwargs)
        
        if command == "data":
            return self._runner.get_data_info(**kwargs)
        
        # 未知命令
        return CommandResult(success=False, error=f"未知命令: {command}")
    
    def _parse_args(self, command: str, args: List[str], base_kwargs: dict) -> dict:
        """
        解析命令行参数（子类可重写）
        
        默认实现：将 args 中的位置参数和选项参数解析到 kwargs。
        
        Args:
            command: 命令名称
            args: 命令行参数列表
            base_kwargs: 基础 kwargs（优先级更高）
            
        Returns:
            dict: 解析后的参数
        """
        result = {}
        
        # 通用参数解析
        i = 0
        while i < len(args):
            arg = args[i]
            
            # --key value 格式
            if arg.startswith("--"):
                key = arg[2:].replace("-", "_")
                if i + 1 < len(args) and not args[i + 1].startswith("--"):
                    result[key] = args[i + 1]
                    i += 2
                    continue
            
            # 位置参数
            if not arg.startswith("--"):
                if "symbols" not in result:
                    result["symbols"] = []
                result["symbols"].append(arg)
            
            i += 1
        
        # 合并 base_kwargs（优先级更高）
        result.update(base_kwargs)
        
        return result
    
    def start(self):
        """启动模式（用于交互式模式）"""
        pass
    
    def stop(self):
        """停止模式"""
        pass


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
