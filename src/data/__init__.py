"""
数据模块 - 行情数据服务

提供统一的数据访问接口，支持多数据源、自动降级、并行请求。

Usage:
    from src.data import get_data_service
    
    service = get_data_service()
    data = service.get_history('000001.SZ', start_date, end_date)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
import pandas as pd

from src.config.schema import DataConfig

# Python 3.6 兼容性：使用 typing_extensions 或 abc.ABC
try:
    from typing import Protocol
except ImportError:
    from typing_extensions import Protocol


class IMarketDataService(Protocol):
    """行情数据服务接口定义"""
    
    def get_history(self, symbol: str,
                    start_date: Optional[datetime] = None,
                    end_date: Optional[datetime] = None,
                    frequency: Optional[str] = None) -> pd.DataFrame:
        """获取历史数据
        
        Args:
            symbol: 标的代码
            start_date: 开始日期（可选，默认365天前）
            end_date: 结束日期（可选，默认为今天）
            frequency: 数据频率（默认日线）
            
        Returns:
            DataFrame: 包含 date, open, high, low, close, volume 列
            
        Examples:
            data = service.get_history('000001.SZ', start_date, end_date)
        """
        ...
    
    def get_latest_with_realtime(self, symbol: str,
                                  frequency: Optional[str] = None) -> pd.DataFrame:
        """获取历史数据并用实时行情更新（Live模式核心方法）
        
        Args:
            symbol: 标的代码
            frequency: 数据频率
            
        Returns:
            DataFrame: 包含实时价格更新的K线数据
        """
        ...
    
    def sync(self, symbols: Optional[List[str]] = None,
             start_date: Optional[datetime] = None,
             end_date: Optional[datetime] = None,
             frequency: str = "daily",
             progress_callback: Any = None) -> int:
        """同步数据到本地"""
        ...
    
    def get_data_stats(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取数据统计"""
        ...
    
    def clean(self, symbol: Optional[str] = None, before_date: Optional[datetime] = None) -> int:
        """清理数据"""
        ...
    
    def close(self) -> None:
        """关闭服务，释放资源"""
        ...


# 延迟导入实现类，避免循环依赖
from .service import MarketDataServiceImpl
from .provider import Frequency


# 全局单例实例
_instance: Optional[MarketDataServiceImpl] = None


def get_data_service(config: Optional[DataConfig] = None) -> IMarketDataService:
    """获取全局数据服务实例
    
    首次调用会自动初始化，后续调用返回已创建的实例。
    
    Args:
        config: 数据配置对象，首次调用时生效。如果为 None，使用默认配置。
        
    Returns:
        IMarketDataService: 全局数据服务实例
        
    Usage:
        from src.data import get_data_service
        
        service = get_data_service()
        data = service.get_history('000001.SZ')
    """
    global _instance
    if _instance is None:
        from src.config.schema import DataConfig
        if config is None:
            config = DataConfig()
        _instance = MarketDataServiceImpl(config)
    return _instance

__all__ = [
    'IMarketDataService',
    'get_data_service',
    'Frequency',
]
