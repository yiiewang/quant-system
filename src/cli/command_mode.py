"""
单次命令执行模式

从 CLI 参数解析命令并执行，通过 IRunner 接口调用 ApplicationRunner。
"""
from typing import List, TYPE_CHECKING

from .execution_modes import ExecutionMode

if TYPE_CHECKING:
    from src.runner.interfaces import CommandResult


class CommandMode(ExecutionMode):
    """
    单次命令执行模式
    
    从 CLI args 解析参数，调用 IRunner 接口执行。
    继承基类的统一命令分发逻辑。
    """

    @property
    def name(self) -> str:
        return "command"

    @property
    def description(self) -> str:
        return "单次命令执行模式"

    def _parse_args(self, command: str, args: List[str], base_kwargs: dict) -> dict:
        """
        解析 CLI 参数
        
        针对不同命令解析特定参数格式。
        """
        result = {}
        
        # run/analyze/backtest/live 命令的参数解析
        if command in ("run", "analyze", "backtest", "live"):
            result = self._parse_run_args(args)
        
        # sync 命令
        elif command == "sync":
            result = self._parse_sync_args(args)
        
        # data 命令
        elif command == "data":
            result = self._parse_data_args(args)
        
        # create-strategy/delete-strategy 命令
        elif command in ("create-strategy", "delete-strategy"):
            if args:
                result["name"] = args[0]
        
        # 默认解析
        else:
            result = super()._parse_args(command, args, {})
        
        # 合并 base_kwargs（优先级更高）
        result.update(base_kwargs)
        
        return result
    
    def _parse_run_args(self, args: List[str]) -> dict:
        """解析 run/analyze/backtest/live 命令参数"""
        result = {"symbols": []}
        
        i = 0
        while i < len(args):
            arg = args[i]
            
            if arg == "--strategy" and i + 1 < len(args):
                result["strategy"] = args[i + 1]
                i += 2
            elif arg == "--strategy-config" and i + 1 < len(args):
                result["strategy_config"] = args[i + 1]
                i += 2
            elif arg == "--start" and i + 1 < len(args):
                result["start_date"] = args[i + 1]
                i += 2
            elif arg == "--end" and i + 1 < len(args):
                result["end_date"] = args[i + 1]
                i += 2
            elif arg == "--days" and i + 1 < len(args):
                result["days"] = int(args[i + 1])
                i += 2
            elif arg == "--capital" and i + 1 < len(args):
                result["initial_capital"] = float(args[i + 1])
                i += 2
            elif arg == "--interval" and i + 1 < len(args):
                result["interval"] = int(args[i + 1])
                i += 2
            elif arg == "--notify":
                result["notify"] = True
                i += 1
            elif not arg.startswith("--"):
                result["symbols"].append(arg)
                i += 1
            else:
                i += 1
        
        return result
    
    def _parse_sync_args(self, args: List[str]) -> dict:
        """解析 sync 命令参数"""
        result = {"symbols": [], "frequency": "daily", "days": 365}
        
        i = 0
        while i < len(args):
            arg = args[i]
            
            if arg == "--freq" and i + 1 < len(args):
                result["frequency"] = args[i + 1]
                i += 2
            elif arg == "--days" and i + 1 < len(args):
                result["days"] = int(args[i + 1])
                i += 2
            elif not arg.startswith("--"):
                result["symbols"].append(arg)
                i += 1
            else:
                i += 1
        
        return result
    
    def _parse_data_args(self, args: List[str]) -> dict:
        """解析 data 命令参数"""
        if args and not args[0].startswith("--"):
            return {"symbol": args[0]}
        return {}


__all__ = ["CommandMode"]
