"""
远程客户端模式

连接HTTP API服务执行命令
"""
import json
import os
from typing import List, TYPE_CHECKING

from .execution_modes import ExecutionMode, CommandResult

if TYPE_CHECKING:
    from src.runner.interfaces import ITradingRunner


class ClientMode(ExecutionMode):
    """
    远程客户端模式
    
    连接HTTP API服务执行命令
    不依赖本地 Runner，直接调用远程 API
    """
    
    def __init__(self, server: str = "localhost:8000", runner: "ITradingRunner" = None):
        super().__init__(runner)  # ClientMode 通常不需要本地 runner
        self.server = server if server.startswith("http") else f"http://{server}"
        self.running = False
    
    @property
    def name(self) -> str:
        return "client"
    
    @property
    def description(self) -> str:
        return "远程客户端模式(连接HTTP API)"
    
    def _request(self, method: str, path: str, payload: dict = None, 
                 timeout: int = 120) -> CommandResult:
        """发送HTTP请求"""
        try:
            import requests
            url = f"{self.server}{path}"
            
            if method == "GET":
                resp = requests.get(url, timeout=timeout)
            else:
                resp = requests.post(url, json=payload, timeout=timeout)
            
            data = resp.json()
            
            if resp.status_code >= 400:
                error = data.get("detail", data.get("error", resp.text))
                return CommandResult(success=False, error=error)
            
            return CommandResult(success=True, data=data.get("data"), 
                               message=data.get("message", ""))
            
        except Exception as e:
            return CommandResult(success=False, error=str(e))
    
    def execute(self, command: str, args: List[str], **kwargs) -> CommandResult:
        """执行远程命令"""
        dispatch = {
            "strategies": lambda: self._request("GET", "/api/strategies"),
            "analyze": lambda: self._parse_and_analyze(args),
            "backtest": lambda: self._parse_and_backtest(args),
            "live": lambda: self._parse_and_live(args),
            "sync": lambda: self._parse_and_sync(args),
            "data": lambda: self._parse_and_data(args),
            "health": lambda: self._request("GET", "/api/health"),
        }
        
        handler = dispatch.get(command)
        if not handler:
            return CommandResult(success=False, error=f"未知命令: {command}")
        
        return handler()
    
    def _parse_and_analyze(self, args: List[str]) -> CommandResult:
        """解析参数并执行analyze"""
        symbols = []
        strategy = None
        days = 365
        source = "baostock"
        
        i = 0
        while i < len(args):
            if args[i] == "--strategy" and i + 1 < len(args):
                strategy = args[i + 1]
                i += 2
            elif args[i] == "--days" and i + 1 < len(args):
                days = int(args[i + 1])
                i += 2
            elif args[i] == "--source" and i + 1 < len(args):
                source = args[i + 1]
                i += 2
            elif not args[i].startswith("--"):
                symbols.append(args[i])
                i += 1
            else:
                i += 1
        
        payload = {
            "symbols": symbols,
            "days": days,
            "source": source,
        }
        if strategy:
            payload["strategy"] = strategy
        
        return self._request("POST", "/api/analyze", payload)
    
    def _parse_and_backtest(self, args: List[str]) -> CommandResult:
        """解析参数并执行backtest"""
        symbols = []
        start_date = None
        end_date = None
        strategy = None
        capital = 1000000
        
        i = 0
        while i < len(args):
            if args[i] == "--start" and i + 1 < len(args):
                start_date = args[i + 1]
                i += 2
            elif args[i] == "--end" and i + 1 < len(args):
                end_date = args[i + 1]
                i += 2
            elif args[i] == "--strategy" and i + 1 < len(args):
                strategy = args[i + 1]
                i += 2
            elif args[i] == "--capital" and i + 1 < len(args):
                capital = float(args[i + 1])
                i += 2
            elif not args[i].startswith("--"):
                symbols.append(args[i])
                i += 1
            else:
                i += 1
        
        if not start_date or not end_date:
            return CommandResult(success=False, error="缺少 --start 或 --end 参数")
        
        payload = {
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": capital,
        }
        if strategy:
            payload["strategy"] = strategy
        
        return self._request("POST", "/api/backtest", payload, timeout=300)
    
    def _parse_and_live(self, args: List[str]) -> CommandResult:
        """解析参数并执行live"""
        if not args:
            return CommandResult(success=False, error="缺少子命令")

        action = args[0]
        rest = args[1:]

        symbols = []
        strategy = None
        interval = 60

        i = 0
        while i < len(rest):
            if rest[i] == "--strategy" and i + 1 < len(rest):
                strategy = rest[i + 1]
                i += 2
            elif rest[i] == "--interval" and i + 1 < len(rest):
                interval = int(rest[i + 1])
                i += 2
            elif not rest[i].startswith("--"):
                symbols.append(rest[i])
                i += 1
            else:
                i += 1

        if action == "start":
            payload = {"symbols": symbols, "interval": interval}
            if strategy:
                payload["strategy"] = strategy
            return self._request("POST", "/api/live/start", payload)

        elif action == "stop":
            return self._request("POST", "/api/live/stop")

        elif action == "status":
            return self._request("GET", "/api/live/status")

        else:
            return CommandResult(success=False, error=f"未知操作: {action}")
    
    def _parse_and_sync(self, args: List[str]) -> CommandResult:
        """解析参数并执行sync"""
        symbols = []
        frequency = "daily"
        days = 365
        
        i = 0
        while i < len(args):
            if args[i] == "--freq" and i + 1 < len(args):
                frequency = args[i + 1]
                i += 2
            elif args[i] == "--days" and i + 1 < len(args):
                days = int(args[i + 1])
                i += 2
            elif not args[i].startswith("--"):
                symbols.append(args[i])
                i += 1
            else:
                i += 1
        
        payload = {
            "symbols": symbols,
            "frequency": frequency,
            "days": days,
        }
        return self._request("POST", "/api/data/sync", payload, timeout=300)
    
    def _parse_and_data(self, args: List[str]) -> CommandResult:
        """解析参数并执行data"""
        symbol = None
        if args and not args[0].startswith("--"):
            symbol = args[0]
        
        path = "/api/data/info"
        if symbol:
            path += f"?symbol={symbol}"
        return self._request("GET", path)
    
    def start(self):
        """启动客户端REPL"""
        from .main import Colors
        self.running = True
        
        print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")
        print(f"{Colors.BOLD}量化交易系统 - 远程客户端模式{Colors.ENDC}")
        print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")
        print(f"  服务地址: {self.server}")
        print(f"  输入 help 查看命令, exit 退出")
        print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")
        
        # 检查连接
        result = self._request("GET", "/api/health", timeout=5)
        if result.success:
            print(f"{Colors.OKGREEN}[连接成功]{Colors.ENDC} 服务运行正常\n")
        else:
            print(f"{Colors.FAIL}[连接失败]{Colors.ENDC} {result.error}")
            print(f"提示: 先启动服务 python -m src.cli.main serve\n")
        
        while self.running:
            try:
                cmd_input = input(f"{Colors.OKGREEN}macd> {Colors.ENDC}").strip()
                
                if not cmd_input:
                    continue
                
                parts = cmd_input.split()
                command = parts[0].lower()
                args = parts[1:]
                
                if command in ('exit', 'quit', 'q'):
                    print(f"\n{Colors.OKGREEN}再见！{Colors.ENDC}\n")
                    self.running = False
                    break
                
                if command == 'help':
                    self._print_help()
                    continue
                
                if command == 'clear':
                    os.system('clear' if os.name == 'posix' else 'cls')
                    continue
                
                # 执行命令
                result = self.execute(command, args)
                self._print_result(result)
                
            except KeyboardInterrupt:
                print()
            except EOFError:
                print(f"\n{Colors.OKGREEN}再见！{Colors.ENDC}\n")
                self.running = False
    
    def _print_help(self):
        """打印帮助"""
        from .main import Colors
        print(f"\n{Colors.BOLD}可用命令:{Colors.ENDC}")
        print("  health              检查服务状态")
        print("  strategies          列出可用策略")
        print("  analyze <symbols>   分析标的")
        print("  backtest <symbols>  运行回测")
        print("  live <action>       实时运行管理")
        print("  sync <symbols>      同步数据")
        print("  data [symbol]       查看数据信息")
        print("  help                显示帮助")
        print("  clear               清屏")
        print("  exit                退出\n")
    
    def _print_result(self, result: CommandResult):
        """格式化打印结果"""
        from .main import Colors
        
        if not result.success:
            print(f"{Colors.FAIL}[错误]{Colors.ENDC} {result.error}\n")
            return
        
        if result.message:
            print(f"{result.message}")
        
        if result.data:
            print(json.dumps(result.data, ensure_ascii=False, indent=2))
        print()
