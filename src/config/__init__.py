"""
配置管理模块

组合式配置设计：
- 枚举和配置类定义在 schema.py
- 全局 Config 组合所有模块配置
- 加载时自动转换枚举类型

Usage:
    from src.config import load_config, Config, DataSource
    
    # 加载配置
    config = load_config(Config, "config/system.yaml", "APP")
    
    # 使用（枚举自动转换）
    print(config.data.source)  # DataSource.TUSHARE
"""
from .base import load_config
from .schema import (
    Config,
    DataConfig,
    LogConfig,
    ApiConfig,
    RiskConfig,
    TradingConfig,
    NotificationConfig,
    EmailConfig,
    WebhookConfig,
    DataSource,
    TradingMode,
    LogLevel,
)

__all__ = [
    'load_config',
    'Config',
    'DataConfig',
    'LogConfig',
    'ApiConfig',
    'RiskConfig',
    'TradingConfig',
    'NotificationConfig',
    'EmailConfig',
    'WebhookConfig',
    'DataSource',
    'TradingMode',
    'LogLevel',
]
