"""
数据模块

Usage:
    from src.config import load_config, Config
    from src.data import init_data_service, MarketDataService
    
    config = load_config(Config, "config/system.yaml")
    service = init_data_service(config.data)
    
    # 或直接使用
    service = MarketDataService(source=DataSource.TUSHARE)
"""

from .service import MarketDataService
from .factory import init_data_service
from .provider import Frequency

__all__ = [
    'MarketDataService',
    'init_data_service',
    'Frequency',
]
