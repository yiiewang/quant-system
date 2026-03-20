"""
配置基类

各模块定义自己的配置类，全局 Config 组合所有模块配置。

Usage:
    # 各模块定义自己的配置
    @dataclass
    class DataConfig:
        source: str = "local"
        db_path: str = "data/market.db"
    
    # 全局 Config 组合
    @dataclass
    class Config(BaseConfig):
        data: DataConfig = field(default_factory=DataConfig)
        log: LogConfig = field(default_factory=LogConfig)
    
    # 使用
    config = Config.load("config.yaml")
    service = init_data_service(config.data)
"""
from enum import Enum
import os
import re
from pathlib import Path
from typing import Dict, Any, Type, TypeVar, get_type_hints, List, Optional
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


def _load_yaml_file(path: str) -> Dict[str, Any]:
    """加载 YAML 文件"""
    p = Path(path)
    if not p.exists():
        logger.warning(f"配置文件不存在: {path}")
        return {}
    
    try:
        import yaml
    except ImportError:
        raise ImportError("请安装 PyYAML: pip install pyyaml")
    
    with open(p, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换环境变量
    content = re.sub(
        r'\$\{(\w+)(?::-([^}]*))?\}',
        lambda m: os.environ.get(m.group(1), m.group(2) or ''),
        content
    )
    
    data = yaml.safe_load(content)
    return data if data else {}


def _convert_value(value: Any, target_type: Any) -> Any:
    """类型转换"""
    if value is None:
        return None
    
    origin = getattr(target_type, '__origin__', target_type)
    
    # Optional 处理
    if hasattr(target_type, '__args__') and type(None) in getattr(target_type, '__args__', []):
        args = [a for a in target_type.__args__ if a is not type(None)]
        if args:
            target_type = args[0]
            origin = getattr(target_type, '__origin__', target_type)
    
    # 枚举转换
    if isinstance(target_type, type) and issubclass(target_type, Enum):
        if isinstance(value, Enum):
            return value
        return target_type(value)
    
    # 列表中的枚举转换
    if origin in (list, List):
        if isinstance(value, list):
            # 获取列表元素类型
            args = getattr(target_type, '__args__', ())
            elem_type = args[0] if args else str
            return [_convert_value(v, elem_type) for v in value]
        return [_convert_value(value, getattr(target_type, '__args__', (str,))[0])]
    
    if target_type is bool and isinstance(value, str):
        return value.lower() in ('true', '1', 'yes')
    
    try:
        return target_type(value)
    except (TypeError, ValueError):
        return value


def _is_config_class(cls: Type) -> bool:
    """判断是否是配置类（dataclass 且字段都有默认值）"""
    import dataclasses
    if not dataclasses.is_dataclass(cls):
        return False
    for f in dataclasses.fields(cls):
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            return False
    return True


def _from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
    """从字典创建配置对象"""
    import dataclasses
    
    if not dataclasses.is_dataclass(cls):
        return _convert_value(data, cls)
    
    kwargs = {}
    type_hints = get_type_hints(cls)
    
    for f in dataclasses.fields(cls):
        field_name = f.name
        field_type = type_hints.get(field_name, f.type)
        
        if field_name.startswith('_'):
            continue
        
        if field_name in data:
            value = data[field_name]
            
            # 嵌套配置类
            if _is_config_class(field_type) and isinstance(value, dict):
                kwargs[field_name] = _from_dict(field_type, value)
            else:
                kwargs[field_name] = _convert_value(value, field_type)
    
    return cls(**kwargs)


def _from_env(cls: Type[T], prefix: str = "") -> T:
    """从环境变量创建配置对象"""
    import dataclasses
    
    if not dataclasses.is_dataclass(cls):
        return cls()
    
    kwargs = {}
    
    for f in dataclasses.fields(cls):
        field_name = f.name
        if field_name.startswith('_'):
            continue
        
        env_var = f"{prefix}_{field_name}".upper()
        
        if env_var in os.environ:
            field_type = f.type
            kwargs[field_name] = _convert_value(os.environ[env_var], field_type)
    
    return cls(**kwargs)


def load_config(
    config_class: Type[T],
    yaml_path: Optional[str] = None,
    env_prefix: Optional[str] = None
) -> T:
    """
    加载配置
    
    优先级: 环境变量 > YAML 文件 > 默认值
    
    Args:
        config_class: 配置类
        yaml_path: YAML 文件路径
        env_prefix: 环境变量前缀
    """
    # 1. 默认值
    config = config_class()
    
    # 2. 从 YAML 加载
    if yaml_path:
        data = _load_yaml_file(yaml_path)
        if data:
            yaml_config = _from_dict(config_class, data)
            config = _merge(config, yaml_config)
    
    # 3. 从环境变量加载
    if env_prefix:
        env_config = _from_env(config_class, env_prefix)
        config = _merge(config, env_config)
    
    return config


def _merge(base: Any, override: Any) -> Any:
    """合并配置（override 覆盖 base）"""
    import dataclasses
    
    if not dataclasses.is_dataclass(base) or not dataclasses.is_dataclass(override):
        return override
    
    kwargs = {}
    for f in dataclasses.fields(base):
        field_name = f.name
        base_val = getattr(base, field_name)
        override_val = getattr(override, field_name, None)
        
        # 如果 override 有非默认值，使用它
        if override_val is not None:
            # 嵌套配置递归合并
            if dataclasses.is_dataclass(base_val) and dataclasses.is_dataclass(override_val):
                kwargs[field_name] = _merge(base_val, override_val)
            else:
                kwargs[field_name] = override_val
        else:
            kwargs[field_name] = base_val
    
    return type(base)(**kwargs)
