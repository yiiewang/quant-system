"""
HTTP API 服务端模式

启动HTTP服务器，提供RESTful API
"""
import sys
from typing import List, TYPE_CHECKING

from .execution_modes import ExecutionMode, CommandResult

if TYPE_CHECKING:
    from src.runner.interfaces import ITradingRunner


class ServerMode(ExecutionMode):
    """
    HTTP API 服务端模式
    
    启动HTTP服务器，通过 API 暴露 ITradingRunner 的业务接口
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8000,
                 workers: int = 1, auto_reload: bool = False,
                 runner: "ITradingRunner" = None):
        super().__init__(runner)
        self.host = host
        self.port = port
        self.workers = workers
        self.auto_reload = auto_reload
    
    @property
    def name(self) -> str:
        return "server"
    
    @property
    def description(self) -> str:
        return "HTTP API服务端模式"
    
    def execute(self, command: str, args: List[str], **kwargs) -> CommandResult:
        """服务端不支持直接执行命令"""
        return CommandResult(success=False, error="服务端模式不支持直接执行命令，请通过HTTP API调用")
    
    def start(self):
        """启动HTTP服务"""
        from .main import Colors
        
        print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")
        print(f"{Colors.BOLD}量化交易系统 - HTTP API 服务{Colors.ENDC}")
        print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")
        print(f"  地址: http://{self.host}:{self.port}")
        print(f"  文档: http://{self.host}:{self.port}/docs")
        print(f"  工作进程: {self.workers}")
        print(f"  自动重载: {'启用' if self.auto_reload else '禁用'}")
        print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")
        
        try:
            import uvicorn
            from src.api.server import app
            
            uvicorn.run(
                "src.api.server:app",
                host=self.host,
                port=self.port,
                workers=self.workers if not self.auto_reload else 1,
                reload=self.auto_reload,
            )
        except ImportError:
            print(f"{Colors.FAIL}错误: 需要安装 uvicorn{Colors.ENDC}")
            print("  pip install uvicorn")
            sys.exit(1)
