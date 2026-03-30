"""
Runner 接口协议定义

IRunner 定义了系统提供的所有业务能力，四种执行模式通过此接口调用 ApplicationRunner。
"""

try:
    from typing import Protocol, runtime_checkable
except ImportError:
    from typing_extensions import Protocol, runtime_checkable

from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.models import EngineMode


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
    
    def to_dict(self) -> dict:
        """转换为字典（用于 API 响应）"""
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "error": self.error,
        }


@runtime_checkable
class IRunner(Protocol):
    """
    Runner 业务接口
    
    定义系统提供的所有业务能力，四种执行模式通过此接口调用。
    
    设计原则：
    - 方法签名明确，IDE 可自动补全
    - 返回 CommandResult 统一结果格式
    - 所有参数通过 kwargs 传递，便于不同输入模式解析
    """
    
    # ──────────────────────────────────────────────────────────────────
    # 策略运行
    # ──────────────────────────────────────────────────────────────────
    
    def run(
        self,
        mode: "EngineMode",
        strategy: str,
        symbols: list,
        strategy_config: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_capital: float = 1000000,
        interval: int = 60,
        frequency: str = "daily",
    ) -> CommandResult:
        """
        运行策略（统一入口）

        Args:
            mode: 运行模式 (EngineMode.BACKTEST/ANALYZE/LIVE)
            strategy: 策略名称
            symbols: 标的列表
            strategy_config: 策略配置文件路径
            start_date: 开始日期 (backtest/analyze 必须)
            end_date: 结束日期 (backtest/analyze 必须)
            initial_capital: 初始资金 (backtest)
            interval: 轮询间隔秒数 (live)
            frequency: 数据频率 (daily/1min/5min 等)

        Returns:
            CommandResult: 执行结果
        """
        ...
    
    # ──────────────────────────────────────────────────────────────────
    # 策略管理
    # ──────────────────────────────────────────────────────────────────
    
    def list_strategies(self) -> CommandResult:
        """
        列出所有可用策略
        
        Returns:
            CommandResult: data 包含 {"strategies": [...], "count": N}
        """
        ...
    
    def reload_strategies(self) -> CommandResult:
        """
        重新加载策略
        
        Returns:
            CommandResult: data 包含策略名称列表
        """
        ...
    
    def list_strategy_files(self) -> CommandResult:
        """
        列出策略文件
        
        Returns:
            CommandResult: data 包含文件信息列表
        """
        ...
    
    def create_strategy(self, name: str) -> CommandResult:
        """
        创建策略文件
        
        Args:
            name: 策略名称
            
        Returns:
            CommandResult: 创建结果
        """
        ...
    
    def delete_strategy(self, name: str) -> CommandResult:
        """
        删除策略文件（软删除）
        
        Args:
            name: 策略名称
            
        Returns:
            CommandResult: 删除结果
        """
        ...
    
    # ──────────────────────────────────────────────────────────────────
    # 数据管理
    # ──────────────────────────────────────────────────────────────────
    
    def sync_data(
        self, 
        symbols: list, 
        frequency: str = "daily", 
        days: int = 365
    ) -> CommandResult:
        """
        同步行情数据
        
        Args:
            symbols: 标的列表
            frequency: 频率 (daily/hourly)
            days: 同步天数
            
        Returns:
            CommandResult: data 包含各标的同步结果
        """
        ...
    
    def get_data_info(self, symbol: Optional[str] = None) -> CommandResult:
        """
        查看数据信息
        
        Args:
            symbol: 标的代码（可选，不传则返回所有）
            
        Returns:
            CommandResult: data 包含数据统计信息
        """
        ...


__all__ = ["IRunner", "CommandResult"]
