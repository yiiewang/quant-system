"""
策略上下文类型定义

这个模块不依赖任何其他业务模块，避免循环导入
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional


@dataclass
class StrategyContext:
    """
    策略执行上下文

    包含策略执行所需的环境信息

    Attributes:
        symbol: 当前处理的股票代码
        portfolio: 投资组合
        position: 当前持仓
        timestamp: 当前时间
        params: 策略参数
    """
    symbol: str
    portfolio: Any  # 使用 Any 避免导入 Portfolio 导致循环
    position: Optional[Any] = None  # 使用 Any 避免导入 Position
    timestamp: Optional[datetime] = None
    params: Dict[str, Any] = field(default_factory=dict)
