"""
本地交互式模式

在终端持续执行命令，支持历史记录。
通过 IRunner 接口执行业务逻辑。
"""
import os
from typing import List, TYPE_CHECKING

from .execution_modes import ExecutionMode

if TYPE_CHECKING:
    from src.runner.interfaces import IRunner, CommandResult


class InteractiveMode(ExecutionMode):
    """
    本地交互式模式
    
    在终端持续执行命令，通过 IRunner 接口调用。
    继承基类的统一命令分发逻辑。
    """
    
    def __init__(self, runner: "IRunner" = None):
        super().__init__(runner)
        self.running = False
        self._setup_readline()
    
    def _setup_readline(self):
        """配置readline支持历史记录"""
        try:
            import readline
            readline.parse_and_bind("tab: complete")
        except ImportError:
            pass
    
    @property
    def name(self) -> str:
        return "interactive"
    
    @property
    def description(self) -> str:
        return "本地交互式REPL模式"
    
    def _parse_args(self, command: str, args: List[str], base_kwargs: dict) -> dict:
        """
        解析交互式输入参数
        
        与 CommandMode 类似，但支持更灵活的输入格式。
        """
        result = {}
        
        # run 命令参数解析
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
        
        # 合并 base_kwargs
        result.update(base_kwargs)
        
        return result
    
    def _parse_run_args(self, args: List[str]) -> dict:
        """解析 run 命令参数"""
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
    
    def start(self):
        """启动交互式REPL"""
        from .main import Colors
        from src.runner.application import ApplicationRunner
        from src.config.base import load_config
        from src.config.schema import Config

        # 初始化 Runner（如果未设置）
        if not self._runner:
            config = load_config(Config)
            self._runner = ApplicationRunner(config)
        
        self.running = True
        
        def print_help():
            """打印帮助信息"""
            print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
            print(f"{Colors.BOLD}量化交易系统 - 交互式模式{Colors.ENDC}")
            print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")
            print(f"{Colors.BOLD}可用命令:{Colors.ENDC}")
            print("  strategies              列出所有可用策略")
            print("  list-strategy-files     列出策略文件")
            print(f"  {Colors.OKCYAN}create-strategy <name>{Colors.ENDC}  创建新策略模板")
            print(f"  {Colors.OKCYAN}delete-strategy <name>{Colors.ENDC}  软删除策略")
            print("  reload-strategies       重新加载策略")
            print(f"  {Colors.OKCYAN}analyze <symbols> [...] {Colors.ENDC}  分析标的")
            print(f"  {Colors.OKCYAN}backtest <symbols> [...] {Colors.ENDC} 运行回测")
            print(f"  {Colors.OKCYAN}live <symbols> [...] {Colors.ENDC}    实时运行")
            print("  sync <symbols>          同步数据")
            print("  data [symbol]           查看数据信息")
            print("  help                    显示帮助")
            print("  clear                   清屏")
            print("  exit                    退出\n")
        
        # 显示欢迎信息
        print_help()
        
        while self.running:
            try:
                cmd_input = input(f"{Colors.OKGREEN}quant> {Colors.ENDC}").strip()
                
                if not cmd_input:
                    continue
                
                # 解析命令
                parts = cmd_input.split()
                command = parts[0].lower()
                args = parts[1:]
                
                # 处理特殊命令
                if command in ('exit', 'quit', 'q'):
                    print(f"\n{Colors.OKGREEN}再见！{Colors.ENDC}\n")
                    self.running = False
                    break
                
                if command == 'help':
                    print_help()
                    continue
                
                if command == 'clear':
                    os.system('clear' if os.name == 'posix' else 'cls')
                    continue
                
                # 执行业务命令（通过基类的统一分发）
                result = self.execute(command, args)
                
                # 输出结果
                if not result.success and result.error:
                    print(f"{Colors.FAIL}错误: {result.error}{Colors.ENDC}")
                elif result.message:
                    print(f"{Colors.OKGREEN}{result.message}{Colors.ENDC}")
                    if result.data:
                        import json
                        print(json.dumps(result.data, indent=2, ensure_ascii=False, default=str))
                elif result.data:
                    import json
                    print(json.dumps(result.data, indent=2, ensure_ascii=False, default=str))
                
            except KeyboardInterrupt:
                print(f"\n{Colors.WARNING}使用 'exit' 命令退出{Colors.ENDC}")
            except EOFError:
                print(f"\n{Colors.OKGREEN}再见！{Colors.ENDC}\n")
                self.running = False


__all__ = ["InteractiveMode"]
