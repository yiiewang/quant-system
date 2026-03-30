"""
策略管理器

负责策略的生命周期管理：
- 自动发现和加载策略
- 提供策略实例给引擎使用
- 支持热重载

设计原则：
- Manager 是 Runner 和 Engine 的策略提供者
- Manager 内部使用 Registry 和 Loader
- 外部只需与 Manager 交互，无需关心加载细节
"""

from typing import List, Optional, Dict, Any, Type, TYPE_CHECKING
from pathlib import Path
import logging

from .registry import StrategyRegistry, registry
from .loader import StrategyLoader
from .base import BaseStrategy

if TYPE_CHECKING:
    from src.config.schema import StrategyConfig

logger = logging.getLogger(__name__)


class StrategyManager:
    """
    策略管理器
    
    统一管理策略的发现、加载、创建
    
    Usage:
        manager = StrategyManager()
        manager.initialize()  # 自动发现并加载策略
        
        # 获取策略列表
        strategies = manager.list_strategies()
        
        # 创建策略实例
        strategy = manager.create_strategy('macd', params={'fast': 12})
        
        # 热重载
        manager.reload()
    """
    
    def __init__(self, config: Optional['StrategyConfig']=None, auto_discover: bool = True):
        """
        初始化策略管理器
        
        Args:
            config: 策略配置对象（由 Runner 传入）
            auto_discover: 是否自动发现策略
        """


        if config is None:
            raise RuntimeError("stategy config is null")

        self._registry: StrategyRegistry = registry
        self._loader = StrategyLoader(auto_register=True)
        self._config  = config
        self._initialized = False
        
        if auto_discover:
            self.initialize()
    
    def initialize(self) -> int:
        """
        初始化：发现并加载所有策略
        
        Returns:
            加载的策略数量
        """
        if self._initialized:
            logger.debug("策略管理器已初始化，跳过")
            return 0
        
        count = 0
        
        # 1. 加载内置策略（src/strategy/ 目录下的策略）
        count += self._load_builtin_strategies()
        
        # 2. 加载配置中的策略目录
        count += self._load_configured_strategies()
        
        # 3. 加载 YAML 配置的策略
        count += self._load_yaml_strategies()
        
        self._initialized = True
        logger.info(f"策略管理器初始化完成，共加载 {count} 个策略")
        return count
    
    def _load_builtin_strategies(self) -> int:
        """加载内置策略"""
        try:
            # 导入 src.strategy 触发 __init__.py 中的注册
            import src.strategy  # noqa: F401
            
            # 扫描 src/strategy 目录
            builtin_dir = Path(__file__).parent
            if builtin_dir.exists():
                count = self._loader.discover_from_fs(str(builtin_dir), recursive=True)
                logger.debug(f"加载内置策略: {count} 个")
                return count
        except Exception as e:
            logger.warning(f"加载内置策略失败: {e}")
        return 0
    
    def _load_configured_strategies(self) -> int:
        """从配置的策略目录加载策略"""
        directory = self._config.directory
        recursive = self._config.recursive
        
        if not directory:
            return 0
        
        # 处理相对路径
        p = Path(directory)
        if not p.is_absolute():
            p = Path.cwd() / p
        
        count = self._loader.discover_from_fs(str(p), recursive=recursive)
        logger.debug(f"从配置目录加载策略: {count} 个")
        return count
    
    def _load_yaml_strategies(self) -> int:
        """从 YAML 配置文件加载策略定义"""
        # 检查是否有 strategies.yml
        yaml_paths = [
            'config/strategies.yml',
            'config/strategies.yaml',
            'data/strategies/strategies.yml',
        ]
        
        for yaml_path in yaml_paths:
            if Path(yaml_path).exists():
                try:
                    count = self._loader.load_from_config(yaml_path)
                    logger.debug(f"从 YAML 加载策略: {count} 个")
                    return count
                except Exception as e:
                    logger.warning(f"从 YAML 加载策略失败 [{yaml_path}]: {e}")
        
        return 0
    
    def reload(self) -> int:
        """
        重新加载所有策略
        
        Returns:
            新加载的策略数量
        """
        logger.info("重新加载策略...")
        self._initialized = False
        self._registry.clear()
        # 重置 loader，清空已发现的记录
        self._loader = StrategyLoader(auto_register=True)
        return self.initialize()
    
    # ──────────────────────────────────────────────────────────────────
    # 策略查询接口
    # ──────────────────────────────────────────────────────────────────
    
    def list_strategies(self) -> List[Dict[str, Any]]:
        """
        列出所有可用策略
        
        Returns:
            策略信息列表
        """
        self._ensure_initialized()
        return self._registry.list_strategies()
    
    def get_strategy_names(self) -> List[str]:
        """
        获取所有策略名称
        
        Returns:
            策略名称列表
        """
        self._ensure_initialized()
        return sorted(self._registry.names())
    
    def has_strategy(self, name: str) -> bool:
        """
        检查策略是否存在
        
        Args:
            name: 策略名称
            
        Returns:
            是否存在
        """
        self._ensure_initialized()
        return self._registry.has(name)
    
    def get_strategy_class(self, name: str) -> Type[BaseStrategy]:
        """
        获取策略类
        
        Args:
            name: 策略名称
            
        Returns:
            策略类
            
        Raises:
            KeyError: 策略不存在
        """
        self._ensure_initialized()
        return self._registry.get(name)
    
    def create_strategy(self, name: str, config_path: Optional[str] = None) -> BaseStrategy:
        """
        创建策略实例
        
        Args:
            name: 策略名称
            config_path: 策略配置文件路径（可选）
                - 如果提供，使用指定路径的配置文件
                - 如果不提供，按默认规则查找配置文件：
                  策略同目录下的 {strategy_name}.yaml
            
        Returns:
            策略实例
            
        Raises:
            KeyError: 策略不存在
        """
        self._ensure_initialized()
        
        # 获取策略类
        strategy_cls = self._registry.get(name)
        
        # 加载配置文件（使用策略管理器的查找规则）
        config = self._load_strategy_config(name, strategy_cls, config_path)
        
        # 从配置中提取参数
        params: Optional[Dict[str, Any]] = None
        if config and isinstance(config, dict):
            strategy_config = config.get('strategy', {})
            if isinstance(strategy_config, dict):
                p = strategy_config.get('params')
                if p is None or isinstance(p, dict):
                    params = p
        
        # 创建策略实例
        strategy = self._registry.create(
            name, 
            params=params,
            config=config
        )
        
        logger.debug(f"创建策略实例: {name}, config_path={config_path}, has_config={bool(config)}")
        return strategy
    
    def _load_strategy_config(self, name: str, strategy_cls: Type["BaseStrategy"],
                              config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        加载策略配置文件
        
        查找规则:
        1. 如果指定了 config_path，使用该路径
        2. 否则使用策略同目录下的 {strategy_name}.yaml
        3. 未找到则返回空配置
        
        Args:
            name: 策略名称
            strategy_cls: 策略类
            config_path: 配置文件路径（可选）
            
        Returns:
            Dict[str, Any]: 配置字典
        """
        import yaml
        import sys
        
        # 策略名称
        strategy_name = name
        
        # 确定配置文件路径
        config_file: Optional[Path] = None
        if config_path:
            config_file = Path(config_path)
        else:
            # 策略同目录下的配置
            try:
                module = sys.modules[strategy_cls.__module__]
                if module.__file__:
                    module_file = Path(module.__file__)
                    strategy_dir = module_file.parent
                    config_file = strategy_dir / f"{strategy_name}.yaml"
            except (KeyError, AttributeError):
                pass
        
        if not config_file or not config_file.exists():
            logger.debug(f"未找到策略 {strategy_name} 的配置文件")
            return {}
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            
            logger.info(f"加载策略配置: {config_file}")
            return strategy_cls.parse_config(config)
            
        except Exception as e:
            logger.warning(f"加载策略配置失败: {e}")
            return {}
    
    def _ensure_initialized(self):
        """确保已初始化"""
        if not self._initialized:
            self.initialize()

    def _get_strategy_directories(self) -> List[str]:
        """获取策略目录列表"""
        directory = self._config.directory
        return [directory] if directory else []
    
    # ──────────────────────────────────────────────────────────────────
    # 策略管理接口
    # ──────────────────────────────────────────────────────────────────
    
    def register_strategy(self, name: str, strategy_cls: Type[BaseStrategy]) -> None:
        """
        手动注册策略
        
        Args:
            name: 策略名称
            strategy_cls: 策略类
        """
        self._registry.register(name, strategy_cls)
        logger.info(f"手动注册策略: {name}")
    
    def discover_from_directory(self, *directories: str, recursive: bool = False) -> int:
        """
        从指定目录发现策略
        
        Args:
            *directories: 目录路径
            recursive: 是否递归扫描
            
        Returns:
            发现的策略数量
        """
        return self._loader.discover_from_fs(*directories, recursive=recursive)
    
    # ──────────────────────────────────────────────────────────────────
    # 策略文件管理
    # ──────────────────────────────────────────────────────────────────
    
    def list_strategy_files(self) -> List[Dict[str, Any]]:
        """
        列出所有策略文件
        
        Returns:
            策略文件信息列表
        """
        files = []
        
        # 扫描内置策略目录
        builtin_dir = Path(__file__).parent
        for f in sorted(builtin_dir.glob("*_strategy.py")):
            files.append({
                "name": f.stem.replace("_strategy", ""),
                "path": str(f),
                "type": "builtin",
            })
        
        # 扫描配置的策略目录
        strategy_dirs = self._get_strategy_directories()

        for strategy_dir in strategy_dirs:
            p = Path(strategy_dir)
            if p.exists():
                for f in sorted(p.glob("*_strategy.py")):
                    files.append({
                        "name": f.stem.replace("_strategy", ""),
                        "path": str(f),
                        "type": "custom",
                    })
        
        return files
    
    def create_strategy_file(self, name: str) -> str:
        """
        创建策略文件

        Args:
            name: 策略名称

        Returns:
            创建的文件路径
        """
        # 获取策略目录
        strategy_dirs = self._get_strategy_directories()
        strategy_dir = strategy_dirs[0] if strategy_dirs else "data/strategies"
        filename = f"{strategy_dir}/{name}_strategy.py"
        
        if Path(filename).exists():
            raise ValueError(f"策略文件已存在: {filename}")
        
        # 创建策略模板
        template = f'''"""
{name.upper()} 策略

请在此处添加策略说明
"""
import pandas as pd
from src.strategy.base import BaseStrategy
from src.core.models import StrategyContext, StrategyDecision


class {name.capitalize()}Strategy(BaseStrategy):
    """{name.upper()} 策略实现"""
    
    name = "{name}"
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        result = data.copy()
        # TODO: 实现指标计算
        return result
    
    def evaluate(self, data: pd.DataFrame, context: 'StrategyContext') -> 'StrategyDecision':
        """策略评估（统一方法）"""
        # TODO: 实现策略逻辑
        return StrategyDecision.hold(context.symbol, "策略未实现")
'''
        
        # 确保目录存在
        Path(strategy_dir).mkdir(parents=True, exist_ok=True)
        Path(filename).write_text(template)
        logger.info(f"创建策略文件: {filename}")
        
        return filename
    
    def disable_strategy_file(self, name: str) -> str:
        """
        禁用策略文件（重命名为 .py.disabled）

        Args:
            name: 策略名称

        Returns:
            新文件路径
        """
        strategy_dirs = self._get_strategy_directories()

        # 查找策略文件
        old_file = None
        for strategy_dir in strategy_dirs:
            potential_file = Path(f"{strategy_dir}/{name}_strategy.py")
            if potential_file.exists():
                old_file = potential_file
                break
        
        if not old_file:
            raise FileNotFoundError(f"策略文件不存在: {name}_strategy.py")
        
        new_file = old_file.with_suffix('.py.disabled')
        old_file.rename(new_file)
        logger.info(f"禁用策略文件: {old_file} -> {new_file}")
        
        return str(new_file)


# 全局策略管理器实例（由 Runner 初始化）
_manager: Optional[StrategyManager] = None


def get_strategy_manager(config: Optional['StrategyConfig'] = None) -> 'StrategyManager':
    """
    获取全局策略管理器
    
    Args:
        config: 策略配置对象（首次调用必须传入）
        
    Returns:
        StrategyManager: 全局策略管理器实例
        
    Raises:
        RuntimeError: 首次调用未提供 config
    """
    global _manager
    if _manager is None:
        _manager = StrategyManager(config=config)
    return _manager
