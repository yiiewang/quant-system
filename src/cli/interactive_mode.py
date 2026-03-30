"""
本地交互式模式

在终端持续执行命令，支持历史记录。
通过 IRunner 接口执行业务逻辑。
"""
import os
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.runner.interfaces import IRunner, CommandResult


class InteractiveMode:
    """
    本地交互式模式
    
    在终端持续执行命令，通过 IRunner 接口调用。
    """

    def __init__(self, runner: Optional["IRunner"] = None):
        self._runner = runner
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

    def execute(self, command: str, args: Optional[list] = None, **kwargs) -> "CommandResult":
        """
        执行命令
        
        解析参数并调用 IRunner 对应方法。
        """
        from src.runner.interfaces import CommandResult
        
        if self._runner is None:
            return CommandResult(success=False, error="Runner 未初始化")
        
        # 解析参数
        if args:
            parsed = self._parse_args(command, args)
            parsed.update(kwargs)
            kwargs = parsed

        # 命令分发
        if command == "run":
            return self._runner.run(**kwargs)

        if command == "analyze":
            kwargs["mode"] = "analyze"
            return self._runner.run(**kwargs)

        if command == "backtest":
            kwargs["mode"] = "backtest"
            return self._runner.run(**kwargs)

        if command == "live":
            kwargs["mode"] = "live"
            return self._runner.run(**kwargs)

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

        if command == "sync":
            return self._runner.sync_data(**kwargs)

        if command == "data":
            return self._runner.get_data_info(**kwargs)

        return CommandResult(success=False, error=f"未知命令: {command}")

    def _parse_args(self, command: str, args: list) -> dict:
        """解析命令参数"""
        if command in ("run", "analyze", "backtest", "live"):
            return self._parse_run_args(args)
        elif command == "sync":
            return self._parse_sync_args(args)
        elif command == "data":
            return self._parse_data_args(args)
        elif command in ("create-strategy", "delete-strategy"):
            if args:
                return {"name": args[0]}
        return {}

    def _parse_run_args(self, args: list) -> dict:
        """解析 run 命令参数"""
        result: dict = {"symbols": []}
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

    def _parse_sync_args(self, args: list) -> dict:
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

    def _parse_data_args(self, args: list) -> dict:
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

                # 执行业务命令
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
