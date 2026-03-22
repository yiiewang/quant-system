"""
策略动态加载器

支持两种发现方式：
1. 文件系统扫描（convention-based）: *_strategy.py / strategy_*.py
2. YAML 配置文件驱动（config-based）: strategies.yml

设计原则：
- 加载器不替换注册表，只是注册表的补充
- 所有发现结果最终都调用 registry.register() 写入全局注册表
- 与现有硬编码注册完全兼容（__init__.py 保底兜底）
- 支持多目录扫描，可扩展为插件系统

Usage（典型）：
    from src.strategy.loader import StrategyLoader

    loader = StrategyLoader()

    # 扫描指定目录（自动发现 *_strategy.py 文件）
    loader.discover_from_fs('src/strategy', 'custom/strategies')

    # 从 YAML 配置文件加载
    loader.load_from_config('config/strategies.yml')

    # 列出发现的策略
    print(loader.discovered)

YAML 配置格式：
    strategies:
      - name: my_macd
        module: src.strategy.macd      # Python 模块路径
        class: MACDStrategy            # 类名
        enabled: true
        params:                        # 默认参数（可选）
          fast: 12
          slow: 26

      - name: custom_rsi
        module: custom.strategies.rsi
        class: RSIStrategy
        enabled: true
"""

import importlib
import importlib.util
import inspect
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

logger = logging.getLogger(__name__)

# 文件名命名约定（满足其一即触发自动发现）
_STRATEGY_SUFFIXES = ('_strategy.py',)
_STRATEGY_PREFIXES = ('strategy_',)


def _is_strategy_file(filename: str) -> bool:
    """判断文件名是否符合策略命名约定"""
    name = filename.lower()
    if not name.endswith('.py') or name.startswith('_'):
        return False
    stem = name[:-3]
    return (
        any(stem.endswith(s[:-3]) for s in _STRATEGY_SUFFIXES)
        or any(stem.startswith(p) for p in _STRATEGY_PREFIXES)
    )


def _load_module_from_path(path: Path, force_reload: bool = True) -> Optional[object]:
    """从文件路径动态加载 Python 模块，失败返回 None
    
    Args:
        path: 模块文件路径
        force_reload: 是否强制重新加载模块（即使已在缓存中）
    """
    try:
        module_name = f"{path.stem}_{id(path)}" if force_reload else path.stem
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        logger.warning(f"加载模块失败 [{path}]: {e}")
        return None


class StrategyLoader:
    """
    策略动态加载器

    核心职责：
    1. 扫描目录，发现符合命名约定的策略文件
    2. 解析 YAML 配置，按配置加载策略类
    3. 将发现的策略注册到全局 registry

    线程安全：实例级别不保证线程安全，建议在启动阶段单线程调用。
    """

    def __init__(self, auto_register: bool = True):
        """
        Args:
            auto_register: 是否自动将发现的策略注册到全局 registry。
                          设为 False 时只扫描不注册（用于审查或测试）。
        """
        from .registry import registry
        self._registry = registry
        self.auto_register = auto_register

        # 发现记录：{name: (cls, source_desc)}
        self._discovered: Dict[str, Tuple[Type, str]] = {}

    # ──────────────────────────────────────────────────────────────────
    # 文件系统发现
    # ──────────────────────────────────────────────────────────────────

    def discover_from_fs(self, *dirs: str, recursive: bool = False) -> int:
        """
        扫描目录，发现并注册策略。

        命名约定（满足其一）：
          - 文件名以 _strategy.py 结尾（如 macd_strategy.py）
          - 文件名以 strategy_ 开头（如 strategy_macd.py）

        类发现逻辑：
          - 模块内继承 BaseStrategy 的非抽象类
          - 类名会被转为 snake_case 作为注册名（可被类属性 name 覆盖）

        Args:
            *dirs:     要扫描的目录（支持相对路径，相对于 cwd）
            recursive: 是否递归扫描子目录

        Returns:
            int: 本次新发现的策略数量
        """
        from .base import BaseStrategy

        count = 0
        for dir_str in dirs:
            dir_path = Path(dir_str).resolve()
            if not dir_path.is_dir():
                logger.warning(f"目录不存在，跳过: {dir_path}")
                continue

            pattern = '**/*.py' if recursive else '*.py'
            candidates = [p for p in dir_path.glob(pattern) if _is_strategy_file(p.name)]

            logger.debug(f"扫描目录 [{dir_path}]: 找到 {len(candidates)} 个候选文件")

            for py_file in candidates:
                # 确保目录在 sys.path（让模块内相对导入可用）
                parent = str(py_file.parent)
                if parent not in sys.path:
                    sys.path.insert(0, parent)

                mod = _load_module_from_path(py_file)
                if mod is None:
                    continue

                for attr_name in dir(mod):
                    obj = getattr(mod, attr_name, None)
                    if (
                        obj is None
                        or not isinstance(obj, type)
                        or obj is BaseStrategy
                        or not issubclass(obj, BaseStrategy)
                        or inspect.isabstract(obj)
                    ):
                        continue

                    # 策略注册名：优先读类属性 name，否则转换类名
                    strategy_name = getattr(obj, 'name', None) or _class_to_snake(obj.__name__)

                    if strategy_name in self._discovered:
                        logger.debug(f"策略 '{strategy_name}' 已发现，跳过重复: {py_file}")
                        continue

                    source = f"fs:{py_file}"
                    self._discovered[strategy_name] = (obj, source)
                    count += 1

                    if self.auto_register:
                        try:
                            self._registry.register(strategy_name, obj)
                            logger.info(f"自动注册策略: {strategy_name} ← {py_file.name}")
                        except Exception as e:
                            logger.warning(f"注册失败 [{strategy_name}]: {e}")

        logger.info(f"文件系统扫描完成，本次新发现 {count} 个策略")
        return count

    # ──────────────────────────────────────────────────────────────────
    # YAML 配置驱动加载
    # ──────────────────────────────────────────────────────────────────

    def load_from_config(self, config_path: str) -> int:
        """
        从 YAML 配置文件加载策略。

        YAML 格式示例（见模块文档字符串）。

        Args:
            config_path: YAML 文件路径

        Returns:
            int: 本次成功加载的策略数量
        """
        path = Path(config_path).resolve()
        if not path.exists():
            logger.warning(f"策略配置文件不存在: {path}")
            return 0

        try:
            import yaml
        except ImportError:
            logger.error("load_from_config 需要 PyYAML: pip install pyyaml")
            return 0

        try:
            with open(path, encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"读取策略配置失败: {path}, error={e}")
            return 0

        strategies_cfg = cfg.get('strategies', []) if cfg else []
        if not strategies_cfg:
            logger.warning(f"配置文件中无策略定义: {path}")
            return 0

        count = 0
        for entry in strategies_cfg:
            if not entry.get('enabled', True):
                logger.debug(f"策略已禁用，跳过: {entry.get('name', '?')}")
                continue

            name = entry.get('name')
            module_path = entry.get('module')
            class_name = entry.get('class')

            if not all([name, module_path, class_name]):
                logger.warning(f"配置条目缺少必要字段 (name/module/class): {entry}")
                continue

            cls = self._import_class(module_path, class_name)
            if cls is None:
                continue

            source = f"config:{path.name}:{name}"
            self._discovered[name] = (cls, source)
            count += 1

            if self.auto_register:
                try:
                    self._registry.register(name, cls)
                    logger.info(f"配置注册策略: {name} ← {module_path}.{class_name}")
                except Exception as e:
                    logger.warning(f"注册失败 [{name}]: {e}")

        logger.info(f"配置加载完成，本次成功加载 {count} 个策略")
        return count

    # ──────────────────────────────────────────────────────────────────
    # 辅助方法
    # ──────────────────────────────────────────────────────────────────

    def _import_class(self, module_path: str, class_name: str) -> Optional[Type]:
        """动态导入指定模块中的类，失败返回 None"""
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name, None)
            if cls is None:
                logger.warning(f"模块 {module_path} 中不存在类 {class_name}")
                return None
            return cls
        except ImportError as e:
            logger.warning(f"导入模块失败 [{module_path}]: {e}")
            return None
        except Exception as e:
            logger.warning(f"加载类失败 [{module_path}.{class_name}]: {e}")
            return None

    # ──────────────────────────────────────────────────────────────────
    # 查询接口
    # ──────────────────────────────────────────────────────────────────

    @property
    def discovered(self) -> List[Dict]:
        """返回本次发现的策略摘要列表"""
        return [
            {
                'name': name,
                'class': cls.__name__,
                'source': source,
                'registered': self._registry.has(name),
            }
            for name, (cls, source) in self._discovered.items()
        ]

    @property
    def discovered_names(self) -> List[str]:
        """返回本次发现的策略名称列表"""
        return list(self._discovered.keys())


# ──────────────────────────────────────────────────────────────────────
# 配置与初始化
# ──────────────────────────────────────────────────────────────────────

# 全局标志：策略是否已初始化
_initialized = False


def get_strategy_directories() -> List[str]:
    """
    从配置文件获取策略目录列表
    
    Returns:
        策略目录列表（绝对路径）
    """
    try:
        import yaml
        
        # 优先从环境变量读取配置路径
        config_path = os.environ.get('QUANT_DATA_CONFIG', 'config/system.yaml')
        
        if not Path(config_path).exists():
            return ['data/strategies']
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        strategy_dirs = config.get('strategy', {}).get('directories', ['data/strategies'])
        
        # 处理相对路径
        result = []
        for dir_path in strategy_dirs:
            path = Path(dir_path)
            if not path.is_absolute():
                path = Path.cwd() / path
            result.append(str(path))
        
        logger.debug(f"策略扫描目录: {result}")
        return result
        
    except Exception as e:
        logger.warning(f"读取策略目录配置失败: {e}，使用默认值")
        return ['data/strategies']


def get_recursive_config() -> bool:
    """从配置文件读取是否递归扫描"""
    try:
        import yaml
        
        config_path = os.environ.get('QUANT_DATA_CONFIG', 'config/system.yaml')
        if Path(config_path).exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config.get('strategy', {}).get('recursive', False)
    except Exception:
        pass
    return False


def ensure_strategies_registered() -> int:
    """
    确保所有策略已注册（扫描策略目录）
    
    使用全局标志避免重复扫描和注册
    
    Returns:
        新注册的策略数量
    """
    global _initialized
    
    if _initialized:
        return 0
    
    try:
        strategy_dirs = get_strategy_directories()
        recursive = get_recursive_config()
        
        loader = StrategyLoader(auto_register=True)
        count = loader.discover_from_fs(*strategy_dirs, recursive=recursive)
        
        _initialized = True
        logger.debug(f"已注册 {count} 个策略")
        return count
        
    except Exception as e:
        logger.warning(f"策略注册失败: {e}")
        return 0


def get_available_strategies() -> List[str]:
    """
    获取所有可用策略名称列表
    
    Returns:
        策略名称列表（排序后）
    """
    try:
        ensure_strategies_registered()
        
        from .registry import registry
        strategies_info = registry.list_strategies()
        
        # 提取策略名称
        strategies = []
        if isinstance(strategies_info, list):
            for item in strategies_info:
                if isinstance(item, dict) and 'name' in item:
                    strategies.append(item['name'])
        elif isinstance(strategies_info, dict):
            strategies = list(strategies_info.keys())
        else:
            strategies = list(strategies_info)
        
        return sorted(strategies)
        
    except Exception as e:
        logger.warning(f"无法获取策略列表: {e}，使用默认策略")
        return ['macd', 'multi_timeframe', 'weekly']


# ──────────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────────

def _class_to_snake(class_name: str) -> str:
    """
    将 CamelCase 类名转换为 snake_case 注册名，并去掉常见后缀。

    Examples:
        MACDStrategy     → macd
        MultiTimeframeMACDStrategy → multi_timeframe_macd
        WeeklyMACDStrategy → weekly_macd
        RSIStrategy      → rsi
    """
    import re
    # 去掉 "Strategy" 后缀
    name = re.sub(r'Strategy$', '', class_name)
    # CamelCase → snake_case（处理连续大写如 MACD）
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    name = name.lower().strip('_')
    return name
