"""
远程客户端模式

连接HTTP API服务执行命令，通过 HTTP 调用远程 Runner。
"""
import json
from typing import List, TYPE_CHECKING

from .execution_modes import ExecutionMode

if TYPE_CHECKING:
    from src.runner.interfaces import IRunner, CommandResult


class ClientMode(ExecutionMode):
    """
    远程客户端模式
    
    通过 HTTP API 调用远程 Runner，不依赖本地 Runner 实例。
    重写 _dispatch 方法，将命令转换为 HTTP 请求。
    """
    
    def __init__(self, server: str = "localhost:8000", runner: "IRunner" = None):
        super().__init__(runner)  # ClientMode 通常不需要本地 runner
        self.server = server if server.startswith("http") else f"http://{server}"
        self.running = False
    
    @property
    def name(self) -> str:
        return "client"
    
    @property
    def description(self) -> str:
        return "远程客户端模式(连接HTTP API)"
    
    def _dispatch(self, command: str, **kwargs) -> "CommandResult":
        """
        重写分发方法：通过 HTTP 调用远程 Runner
        
        将命令转换为对应的 API 端点请求。
        """
        from src.runner.interfaces import CommandResult
        
        # 策略运行
        if command in ("run", "analyze", "backtest", "live"):
            if command != "run":
                kwargs["mode"] = command
            return self._request("POST", "/api/strategy", kwargs)
        
        # 策略管理
        if command == "strategies":
            return self._request("GET", "/api/strategies")
        
        if command == "list-strategy-files":
            return self._request("GET", "/api/strategy-files")
        
        if command == "create-strategy":
            return self._request("POST", "/api/strategy/create", kwargs)
        
        if command == "delete-strategy":
            return self._request("POST", "/api/strategy/delete", kwargs)
        
        if command == "reload-strategies":
            return self._request("POST", "/api/strategy/reload")
        
        # 数据管理
        if command == "sync":
            return self._request("POST", "/api/data/sync", kwargs, timeout=300)
        
        if command == "data":
            symbol = kwargs.get("symbol")
            path = f"/api/data/info?symbol={symbol}" if symbol else "/api/data/info"
            return self._request("GET", path)
        
        # 健康检查
        if command == "health":
            return self._request("GET", "/api/health")
        
        return CommandResult(success=False, error=f"未知命令: {command}")
    
    def _request(
        self, 
        method: str, 
        path: str, 
        payload: dict = None, 
        timeout: int = 120
    ) -> "CommandResult":
        """发送HTTP请求"""
        from src.runner.interfaces import CommandResult
        
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
            
            return CommandResult(
                success=True, 
                data=data.get("data"), 
                message=data.get("message", "")
            )
            
        except Exception as e:
            return CommandResult(success=False, error=str(e))
    
    def start(self):
        """启动客户端REPL"""
        from .main import Colors
        from src.runner.interfaces import CommandResult
        
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
            print(f"提示: 先启动服务 python -m src.main serve\n")
        
        while self.running:
            try:
                cmd_input = input(f"{Colors.OKGREEN}quant> {Colors.ENDC}").strip()
                
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
                    import os
                    os.system('clear' if os.name == 'posix' else 'cls')
                    continue
                
                # 执行命令（通过基类的统一分发，最终调用 _dispatch）
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
        print("  live <symbols>      实时运行")
        print("  sync <symbols>      同步数据")
        print("  data [symbol]       查看数据信息")
        print("  help                显示帮助")
        print("  clear               清屏")
        print("  exit                退出\n")
    
    def _print_result(self, result: "CommandResult"):
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


__all__ = ["ClientMode"]
