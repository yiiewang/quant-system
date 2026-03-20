"""
数据服务工厂
"""
import logging

from src.config.schema import DataConfig
from .service import MarketDataService

logger = logging.getLogger(__name__)


def init_data_service(config: DataConfig) -> MarketDataService:
    """
    初始化数据服务
    
    Args:
        config: 数据配置对象
        
    Returns:
        MarketDataService 实例
        
    Usage:
        from src.config import load_config, Config
        from src.data import init_data_service
        
        config = load_config(Config, "config/system.yaml")
        service = init_data_service(config.data)
    """
    logger.info(f"创建数据服务: source={config.source.value}")
    
    return MarketDataService(
        source=config.source,
        db_path=config.db_path,
        config={'tushare_token': config.get_tushare_token()},
        fallback_sources=config.fallbacks,
        parallel_fetch=config.parallel_fetch,
        enable_health_monitor=config.enable_health_monitor,
    )
