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
    """邮件通知配置

    SMTP 发送端配置优先从环境变量读取，用户主要配置收件人即可。

    环境变量:
        SMTP_SERVER: SMTP 服务器地址 (默认 smtp.qq.com)
        SMTP_PORT: SMTP 端口 (默认 465)
        SMTP_USER: 发件邮箱账号
        SMTP_PASS: 邮箱授权码
        SMTP_SSL: 是否使用 SSL (默认 true)
    """
    enabled: bool = False
    recipients: List[str] = field(default_factory=list)
    sender_name: str = "量化交易系统"

    # SMTP 配置（可通过环境变量如 APP_NOTIFICATION_EMAIL_SMTP_SERVER 覆盖）
    smtp_server: str = "smtp.qq.com"
    smtp_port: int = 465
    username: str = ""
    password: str = ""
    use_ssl: bool = True


@dataclass
class WebhookConfig:
    """Webhook 通知配置（企业微信/钉钉/飞书）"""
    enabled: bool = False
    url: str = ""
    type: str = ""  # wecom / dingtalk / feishu / custom，留空自动识别


@dataclass
class NotificationConfig:
    """通知模块配置"""
    enabled: bool = False
    email: EmailConfig = field(default_factory=EmailConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)


@dataclass
class StrategyConfig:
    """策略管理器配置"""
    directory: str = field(default_factory=lambda: "data/strategies")
    recursive: bool = False


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
class EngineManagerConfig:
    """引擎管理器配置"""
    max_concurrent_tasks: int = 5      # 最大并发任务数
    max_total_tasks: int = 20          # 最大总任务数
    default_task_timeout: int = 0      # 默认任务超时时间（秒，0表示无限制）


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
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    log: LogConfig = field(default_factory=LogConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    engine: EngineManagerConfig = field(default_factory=EngineManagerConfig)
