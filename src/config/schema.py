"""
全局配置定义

组合各模块的配置类。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


# ==================== 枚举定义 ====================

class DataSource(Enum):
    """数据源"""
    LOCAL = "local"
    TUSHARE = "tushare"
    AKSHARE = "akshare"
    BAOSTOCK = "baostock"
    YFINANCE = "yfinance"


class TradingMode(Enum):
    """交易模式"""
    PAPER = "paper"
    LIVE = "live"
    BACKTEST = "backtest"


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


# ==================== 配置类 ====================

@dataclass
class EmailConfig:
    """邮件通知配置"""
    enabled: bool = False
    recipients: List[str] = field(default_factory=list)
    sender_name: str = "量化交易系统"


@dataclass
class WebhookConfig:
    """Webhook 通知配置（企业微信/钉钉/飞书）"""
    enabled: bool = False
    url: str = ""
    type: str = ""  # wecom / dingtalk / feishu / custom，留空自动识别


@dataclass
class NotificationConfig:
    """通知模块配置"""
    email: EmailConfig = field(default_factory=EmailConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)


@dataclass
class DataConfig:
    """数据模块配置"""
    source: DataSource = DataSource.LOCAL
    fallbacks: List[DataSource] = field(default_factory=list)
    db_path: str = "data/market.db"
    parallel_fetch: bool = True
    enable_health_monitor: bool = True
    timeout: float = 10.0
    max_retries: int = 2
    cache_ttl: int = 300
    cache_maxsize: int = 200
    api_tokens: Dict[str, str] = field(default_factory=dict)
    
    def get_tushare_token(self) -> str:
        """获取 Tushare Token"""
        import os
        return os.environ.get('TUSHARE_TOKEN', '') or self.api_tokens.get('tushare', '')


@dataclass
class LogConfig:
    """日志配置"""
    level: LogLevel = LogLevel.INFO
    dir: str = "logs"
    console: bool = True
    backup_count: int = 30


@dataclass
class ApiConfig:
    """API 配置"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    secret_key: str = ""
    cors_origins: List[str] = field(default_factory=list)


@dataclass
class RiskConfig:
    """风控配置"""
    max_position_pct: float = 0.3
    max_total_position: float = 0.8
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.15
    max_drawdown: float = 0.2


@dataclass
class TradingConfig:
    """交易配置"""
    mode: TradingMode = TradingMode.PAPER
    initial_capital: float = 100000.0
    commission: float = 0.0003
    slippage: float = 0.001


@dataclass
class Config:
    """
    全局配置

    组合各模块配置，统一加载。

    Usage:
        from src.config import load_config, Config

        # 加载配置（YAML 中的字符串会自动转换为枚举）
        config = load_config(Config, "config/system.yaml", "APP")

        # config.data.source 是 DataSource 枚举
        print(config.data.source)  # DataSource.TUSHARE

        # 环境变量覆盖
        # APP_DATA_SOURCE=tushare -> 自动转换为 DataSource.TUSHARE
    """
    data: DataConfig = field(default_factory=DataConfig)
    log: LogConfig = field(default_factory=LogConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
