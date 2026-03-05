"""
配置加载器
支持 YAML 配置文件和环境变量替换

配置体系分两层:
1. SystemConfig - 系统级配置（日志、存储、通知等），来自 config/default.yaml
2. StrategyConfig - 策略级配置（策略参数、风控、引擎等），来自 src/strategy/configs/*.yaml
3. RunParams - 来自 CLI 命令行的动态参数

优先级: CLI 参数 > 策略配置 > 系统配置 > 默认值
"""
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


# ==================== 系统配置 ====================

@dataclass
class SystemBaseConfig:
    """系统基础配置"""
    name: str = "MACD Trading System"
    version: str = "1.0.0"
    log_level: str = "INFO"
    log_file: str = ""
    data_dir: str = "data/"


@dataclass
class StorageConfig:
    """数据存储配置"""
    db_path: str = "data/market.db"
    portfolio_db: str = "data/portfolio.db"


@dataclass
class ReportConfig:
    """报告配置"""
    output_dir: str = "output/reports"
    format: str = "markdown"
    include_charts: bool = False


@dataclass
class NotificationConfig:
    """通知配置"""
    enabled: bool = False
    email: Dict[str, Any] = field(default_factory=dict)
    webhook: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemConfig:
    """
    系统级配置（来自 config/default.yaml）
    
    包含日志、存储、通知、报告等基础设施配置。
    """
    system: SystemBaseConfig = field(default_factory=SystemBaseConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    
    _raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SystemConfig':
        """从字典创建系统配置"""
        config = cls()
        config._raw = data
        
        if 'system' in data:
            sys_data = data['system']
            config.system = SystemBaseConfig(
                name=sys_data.get('name', 'MACD Trading System'),
                version=sys_data.get('version', '1.0.0'),
                log_level=sys_data.get('log_level', 'INFO'),
                log_file=sys_data.get('log_file', ''),
                data_dir=sys_data.get('data_dir', 'data/'),
            )
        
        if 'storage' in data:
            st_data = data['storage']
            config.storage = StorageConfig(
                db_path=st_data.get('db_path', 'data/market.db'),
                portfolio_db=st_data.get('portfolio_db', 'data/portfolio.db'),
            )
        
        if 'report' in data:
            rp_data = data['report']
            config.report = ReportConfig(
                output_dir=rp_data.get('output_dir', 'output/reports'),
                format=rp_data.get('format', 'markdown'),
                include_charts=rp_data.get('include_charts', False),
            )
        
        if 'notification' in data:
            notif = data['notification']
            config.notification = NotificationConfig(
                enabled=notif.get('enabled', False),
                email=notif.get('email', {}),
                webhook=notif.get('webhook', {}),
            )
        
        return config
    
    def get_raw(self, *keys, default=None):
        """从原始字典获取值"""
        d = self._raw
        for key in keys:
            if isinstance(d, dict):
                d = d.get(key)
            else:
                return default
            if d is None:
                return default
        return d


# ==================== 策略配置 ====================

@dataclass
class StrategyParamsConfig:
    """策略参数配置"""
    name: str = "macd"
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskConfig:
    """风控配置"""
    max_position_pct: float = 0.3
    max_total_position: float = 0.8
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.15
    max_drawdown: float = 0.2
    max_daily_loss: float = 0.05


@dataclass
class DataSourceConfig:
    """数据源配置"""
    provider: str = "tushare"
    tushare_token: str = ""


@dataclass
class TradingConfig:
    """交易配置"""
    mode: str = "paper"
    initial_capital: float = 100000
    commission: float = 0.0003
    slippage: float = 0.001


@dataclass
class SchedulerConfig:
    """调度配置"""
    poll_interval: int = 60
    trading_start: str = "09:30"
    trading_end: str = "15:00"


@dataclass
class StrategyFileConfig:
    """
    策略级配置（来自 src/strategy/configs/*.yaml）
    
    每个策略配置文件包含策略参数、风控、引擎、数据源等。
    """
    strategy: StrategyParamsConfig = field(default_factory=StrategyParamsConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    data_source: DataSourceConfig = field(default_factory=DataSourceConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    
    _raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StrategyFileConfig':
        """从字典创建策略配置"""
        config = cls()
        config._raw = data
        
        if 'strategy' in data:
            config.strategy = StrategyParamsConfig(
                name=data['strategy'].get('name', 'macd'),
                params=data['strategy'].get('params', {})
            )
        
        if 'notification' in data:
            notif = data['notification']
            config.notification = NotificationConfig(
                enabled=notif.get('enabled', False),
                email=notif.get('email', {}),
                webhook=notif.get('webhook', {}),
            )
        
        if 'risk' in data:
            import dataclasses
            valid_fields = {f.name for f in dataclasses.fields(RiskConfig)}
            filtered = {k: v for k, v in data['risk'].items() if k in valid_fields}
            config.risk = RiskConfig(**filtered)
        
        if 'data_source' in data:
            import dataclasses
            valid_fields = {f.name for f in dataclasses.fields(DataSourceConfig)}
            filtered = {k: v for k, v in data['data_source'].items() if k in valid_fields}
            config.data_source = DataSourceConfig(**filtered)
        
        if 'trading' in data:
            import dataclasses
            valid_fields = {f.name for f in dataclasses.fields(TradingConfig)}
            filtered = {k: v for k, v in data['trading'].items() if k in valid_fields}
            config.trading = TradingConfig(**filtered)
        
        if 'scheduler' in data:
            config.scheduler = SchedulerConfig(
                poll_interval=data['scheduler'].get('poll_interval', 60),
                trading_start=data['scheduler'].get('trading_hours', {}).get('start', '09:30'),
                trading_end=data['scheduler'].get('trading_hours', {}).get('end', '15:00')
            )
        
        return config
    
    def get_raw(self, *keys, default=None):
        """从原始 YAML 字典获取值"""
        d = self._raw
        for key in keys:
            if isinstance(d, dict):
                d = d.get(key)
            else:
                return default
            if d is None:
                return default
        return d


# ==================== 兼容旧接口：Config ====================

@dataclass
class Config:
    """
    主配置类（兼容旧接口）
    
    组合系统配置和策略配置。
    """
    system: SystemBaseConfig = field(default_factory=SystemBaseConfig)
    data_source: DataSourceConfig = field(default_factory=DataSourceConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategy: StrategyParamsConfig = field(default_factory=StrategyParamsConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    
    _raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    
    @classmethod
    def from_system_and_strategy(
        cls,
        sys_config: SystemConfig,
        strat_config: StrategyFileConfig,
    ) -> 'Config':
        """从系统配置和策略配置组合创建"""
        config = cls()
        config.system = sys_config.system
        # 通知配置：策略级优先，系统级兜底
        if strat_config.notification.enabled or 'notification' in strat_config._raw:
            config.notification = strat_config.notification
        else:
            config.notification = sys_config.notification
        config.data_source = strat_config.data_source
        config.trading = strat_config.trading
        config.risk = strat_config.risk
        config.strategy = strat_config.strategy
        config.scheduler = strat_config.scheduler
        
        # 合并 raw: 系统配置为底层，策略配置覆盖
        config._raw = {**sys_config._raw, **strat_config._raw}
        return config
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        """从字典创建配置（兼容旧接口）"""
        config = cls()
        config._raw = data
        
        def filter_fields(dataclass_type, data_dict):
            import dataclasses
            valid_fields = {f.name for f in dataclasses.fields(dataclass_type)}
            return {k: v for k, v in data_dict.items() if k in valid_fields}
        
        if 'system' in data:
            config.system = SystemBaseConfig(**filter_fields(SystemBaseConfig, data['system']))
        
        if 'data_source' in data:
            config.data_source = DataSourceConfig(**filter_fields(DataSourceConfig, data['data_source']))
        
        if 'trading' in data:
            config.trading = TradingConfig(**filter_fields(TradingConfig, data['trading']))
        
        if 'risk' in data:
            config.risk = RiskConfig(**filter_fields(RiskConfig, data['risk']))
        
        if 'strategy' in data:
            config.strategy = StrategyParamsConfig(
                name=data['strategy'].get('name', 'macd'),
                params=data['strategy'].get('params', {})
            )
        
        if 'notification' in data:
            notif = data['notification']
            config.notification = NotificationConfig(
                enabled=notif.get('enabled', False),
                email=notif.get('email', {}),
                webhook=notif.get('webhook', {}),
            )
        
        if 'scheduler' in data:
            config.scheduler = SchedulerConfig(
                poll_interval=data['scheduler'].get('poll_interval', 60),
                trading_start=data['scheduler'].get('trading_hours', {}).get('start', '09:30'),
                trading_end=data['scheduler'].get('trading_hours', {}).get('end', '15:00')
            )
        
        return config
    
    def get_raw(self, *keys, default=None):
        """从原始 YAML 字典获取值"""
        d = self._raw
        for key in keys:
            if isinstance(d, dict):
                d = d.get(key)
            else:
                return default
            if d is None:
                return default
        return d
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'system': {
                'log_level': self.system.log_level,
                'log_file': self.system.log_file,
                'data_dir': self.system.data_dir,
            },
            'data_source': {
                'provider': self.data_source.provider,
                'tushare_token': self.data_source.tushare_token,
            },
            'trading': {
                'mode': self.trading.mode,
                'initial_capital': self.trading.initial_capital,
                'commission': self.trading.commission,
                'slippage': self.trading.slippage,
            },
            'risk': {
                'max_position_pct': self.risk.max_position_pct,
                'max_total_position': self.risk.max_total_position,
                'stop_loss_pct': self.risk.stop_loss_pct,
                'take_profit_pct': self.risk.take_profit_pct,
                'max_drawdown': self.risk.max_drawdown,
                'max_daily_loss': self.risk.max_daily_loss,
            },
            'strategy': {
                'name': self.strategy.name,
                'params': self.strategy.params,
            },
            'notification': {
                'enabled': self.notification.enabled,
                'email': self.notification.email,
                'webhook': self.notification.webhook,
            },
            'scheduler': {
                'poll_interval': self.scheduler.poll_interval,
                'trading_hours': {
                    'start': self.scheduler.trading_start,
                    'end': self.scheduler.trading_end,
                }
            }
        }


# ==================== 动态参数 (CLI) ====================

@dataclass
class RunParams:
    """
    运行时动态参数（来自 CLI 命令行）
    
    每次运行时可以不同，优先级高于 YAML 配置。
    """
    mode: str = "analyze"
    symbols: List[str] = field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    days: int = 365
    source: str = "baostock"
    interval: int = 60
    notify: bool = True
    output_dir: str = "output"
    initial_capital: float = 1000000
    verbose: bool = False
    dry_run: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def merge_with_config(self, config: Config) -> 'RunParams':
        """
        用 YAML 配置填充未设置的参数
        
        优先级: CLI 参数 > YAML 配置 > 默认值
        """
        # symbols: CLI > YAML engine.symbols > 默认
        if not self.symbols:
            yaml_symbols = config.get_raw('engine', 'symbols', default=[])
            self.symbols = yaml_symbols if yaml_symbols else ['000001.SZ']
        
        # source: CLI > YAML data.provider > 默认
        if self.source == 'baostock':
            yaml_provider = config.get_raw('data', 'provider')
            if yaml_provider:
                self.source = yaml_provider
        
        # initial_capital: CLI > YAML broker.initial_capital > 默认
        yaml_capital = config.get_raw('broker', 'initial_capital')
        if yaml_capital and self.initial_capital == 1000000:
            self.initial_capital = yaml_capital
        
        # output_dir: CLI > YAML backtest.output_dir / report.output_dir > 默认
        if self.output_dir == 'output':
            if self.mode == 'backtest':
                yaml_out = config.get_raw('backtest', 'output_dir')
            else:
                yaml_out = config.get_raw('report', 'output_dir')
            if yaml_out:
                self.output_dir = yaml_out
        
        # interval: CLI > YAML engine.tick_interval > 默认
        yaml_interval = config.get_raw('engine', 'tick_interval')
        if yaml_interval and self.interval == 60:
            self.interval = yaml_interval
        
        return self


# ==================== 加载函数 ====================

def _load_yaml(path: str) -> Dict[str, Any]:
    """加载单个 YAML 文件并替换环境变量"""
    p = Path(path)
    if not p.exists():
        logger.warning(f"配置文件不存在: {path}")
        return {}
    
    try:
        import yaml
    except ImportError:
        logger.error("请安装 PyYAML: pip install pyyaml")
        return {}
    
    with open(p, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = _substitute_env_vars(content)
    data = yaml.safe_load(content)
    return data if data else {}


def load_system_config(path: str = None) -> SystemConfig:
    """
    加载系统配置
    
    Args:
        path: 系统配置文件路径，默认 config/default.yaml
    
    Returns:
        SystemConfig
    """
    if path is None:
        path = _find_system_config_default()
    
    if path is None:
        logger.info("未找到系统配置文件，使用默认配置")
        return SystemConfig()
    
    data = _load_yaml(path)
    if not data:
        return SystemConfig()
    
    logger.info(f"加载系统配置: {path}")
    return SystemConfig.from_dict(data)


def load_strategy_config(path: str) -> StrategyFileConfig:
    """
    加载策略配置
    
    Args:
        path: 策略配置文件路径
    
    Returns:
        StrategyFileConfig
    """
    data = _load_yaml(path)
    if not data:
        logger.warning(f"策略配置文件为空或不存在: {path}")
        return StrategyFileConfig()
    
    logger.info(f"加载策略配置: {path}")
    return StrategyFileConfig.from_dict(data)


def load_config(config_path: str = None, system_config_path: str = None) -> Config:
    """
    加载配置文件（兼容旧接口）
    
    组合系统配置和策略配置为一个 Config 对象。
    
    Args:
        config_path: 策略配置文件路径
        system_config_path: 系统配置文件路径，不指定则自动查找
    
    Returns:
        Config
    """
    if config_path is None:
        return Config()
    
    # 加载系统配置
    sys_config = load_system_config(system_config_path)
    
    # 加载策略配置
    strat_config = load_strategy_config(config_path)
    
    return Config.from_system_and_strategy(sys_config, strat_config)


def _find_system_config_default() -> Optional[str]:
    """查找默认系统配置文件"""
    candidates = [
        Path('config/default.yaml'),
        Path('config/system.yaml'),
    ]
    
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())
    
    return None


def _find_system_config(strategy_config_path: str) -> Optional[str]:
    """
    根据策略配置路径自动查找系统配置文件
    
    查找顺序:
    1. 项目根目录下 config/default.yaml
    2. 策略配置同级目录下回退查找
    """
    strategy_path = Path(strategy_config_path).resolve()
    
    candidates = [
        strategy_path.parent / '../../../config/default.yaml',
        strategy_path.parent / '../../config/default.yaml',
        strategy_path.parent / '../config/default.yaml',
        Path('config/default.yaml'),
    ]
    
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists() and resolved != strategy_path.resolve():
            return str(resolved)
    
    return None


def _substitute_env_vars(content: str) -> str:
    """替换环境变量，支持 ${VAR} 和 ${VAR:-default} 格式"""
    pattern = r'\$\{(\w+)(?::-([^}]*))?\}'
    
    def replace(match):
        var_name = match.group(1)
        default_value = match.group(2) or ''
        return os.environ.get(var_name, default_value)
    
    return re.sub(pattern, replace, content)


def save_config(config: Config, path: str) -> None:
    """保存配置到文件"""
    try:
        import yaml
    except ImportError:
        logger.error("请安装 PyYAML: pip install pyyaml")
        return
    
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(config.to_dict(), f, default_flow_style=False, allow_unicode=True)
    
    logger.info(f"配置已保存: {path}")


def get_default_config_content() -> str:
    """获取默认策略配置文件内容"""
    return """# MACD 量化交易系统 - 策略配置
# 系统级配置（通知、报告等）见 config/default.yaml

# 交易引擎配置
engine:
  mode: simulation
  tick_interval: 60
  symbols:
    - "000001.SZ"

# 策略配置
strategy:
  name: macd
  params:
    fast_period: 12
    slow_period: 26
    signal_period: 9
    volume_confirm: true
    volume_ratio: 1.5

# 风控配置
risk:
  max_position_pct: 0.3
  max_total_position_pct: 0.8
  stop_loss_pct: 0.05
  take_profit_pct: 0.15
  max_drawdown_pct: 0.2
  daily_loss_limit: 0.05

# 交易执行配置
broker:
  type: simulator
  initial_capital: 100000
  commission_rate: 0.0003
  slippage: 0.001

# 数据源配置
data:
  provider: akshare
  cache:
    enabled: true
    db_path: data/market.db
    expire_days: 1

# 回测配置
backtest:
  start_date: "2024-01-01"
  end_date: "2024-12-31"
  benchmark: "000300.SH"
  output_dir: output/backtest
  save_trades: true
  generate_report: true
"""
