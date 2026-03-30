"""
HTTP API 服务端模式

启动HTTP服务器，将 HTTP 请求转换为 IRunner 方法调用。
"""
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.runner.interfaces import IRunner, CommandResult


class ServerMode:
    """
    HTTP API 服务端模式

    启动 FastAPI 服务器，将 HTTP 请求转换为 IRunner 方法调用。
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        workers: int = 1,
        auto_reload: bool = False,
        runner: "IRunner" = None
    ):
        self._runner = runner
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


__all__ = ["ServerMode"]
