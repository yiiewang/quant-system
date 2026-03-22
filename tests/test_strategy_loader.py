"""
策略发现集成测试

测试场景：
- _class_to_snake() 转换（MACDStrategy→macd 等）
- _is_strategy_file() 文件名判断
- StrategyLoader.discover_from_fs() 扫描（创建临时策略文件验证）
- StrategyLoader.load_from_config() YAML 配置加载
- registry 导入后包含 macd/multi_timeframe/weekly 三个内置策略
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from unittest.mock import Mock, MagicMock, patch
import tempfile
import shutil

from src.strategy.loader import (
    StrategyLoader, _class_to_snake, _is_strategy_file,
    _STRATEGY_SUFFIXES, _STRATEGY_PREFIXES
)
from src.strategy.registry import registry
from src.strategy.base import BaseStrategy


# ═══════════════════════════════════════════════════════════════════════════
# 测试用策略类
# ═══════════════════════════════════════════════════════════════════════════

class TestStrategy(BaseStrategy):
    """测试策略"""
    name = "test_strategy"
    version = "1.0.0"

    @classmethod
    def default_params(cls):
        return {'period': 20}

    def calculate_indicators(self, data):
        return data

    def generate_signal(self, data, context):
        from src.strategy.base import create_hold_signal
        return create_hold_signal(context.symbol, 100.0)

    def analyze_status(self, data, symbol):
        from src.core.models import AnalysisResult
        return AnalysisResult(
            status="test",
            action="hold",
            reason="test",
            indicators={},
            confidence=0.5
        )


class AnotherTestStrategy(BaseStrategy):
    """另一个测试策略"""
    name = "another_test"
    version = "1.0.0"

    @classmethod
    def default_params(cls):
        return {}

    def calculate_indicators(self, data):
        return data

    def generate_signal(self, data, context):
        from src.strategy.base import create_hold_signal
        return create_hold_signal(context.symbol, 100.0)

    def analyze_status(self, data, symbol):
        from src.core.models import AnalysisResult
        return AnalysisResult(
            status="test",
            action="hold",
            reason="test",
            indicators={},
            confidence=0.5
        )


# ═══════════════════════════════════════════════════════════════════════════
# _class_to_snake 测试
# ═══════════════════════════════════════════════════════════════════════════

class TestClassToSnake:
    """测试类名转 snake_case"""

    def test_macd_strategy(self):
        """MACDStrategy -> macd"""
        result = _class_to_snake('MACDStrategy')
        assert result == 'macd'

    def test_multi_timeframe_macd_strategy(self):
        """MultiTimeframeMACDStrategy -> multi_timeframe_macd"""
        result = _class_to_snake('MultiTimeframeMACDStrategy')
        assert result == 'multi_timeframe_macd'

    def test_weekly_macd_strategy(self):
        """WeeklyMACDStrategy -> weekly_macd"""
        result = _class_to_snake('WeeklyMACDStrategy')
        assert result == 'weekly_macd'

    def test_rsi_strategy(self):
        """RSIStrategy -> rsi"""
        result = _class_to_snake('RSIStrategy')
        assert result == 'rsi'

    def test_simple_moving_average_strategy(self):
        """SimpleMovingAverageStrategy -> simple_moving_average"""
        result = _class_to_snake('SimpleMovingAverageStrategy')
        assert result == 'simple_moving_average'

    def test_my_custom_strategy(self):
        """MyCustomStrategy -> my_custom"""
        result = _class_to_snake('MyCustomStrategy')
        assert result == 'my_custom'


# ═══════════════════════════════════════════════════════════════════════════
# _is_strategy_file 测试
# ═══════════════════════════════════════════════════════════════════════════

class TestIsStrategyFile:
    """测试策略文件判断"""

    def test_suffix_strategy(self):
        """测试 _strategy.py 后缀"""
        assert _is_strategy_file('macd_strategy.py') is True
        assert _is_strategy_file('my_custom_strategy.py') is True
        assert _is_strategy_file('rsi_strategy.py') is True

    def test_prefix_strategy(self):
        """测试 strategy_ 前缀"""
        assert _is_strategy_file('strategy_macd.py') is True
        assert _is_strategy_file('strategy_rsi.py') is True

    def test_non_strategy_files(self):
        """测试非策略文件"""
        assert _is_strategy_file('macd.py') is False
        assert _is_strategy_file('base.py') is False
        assert _is_strategy_file('registry.py') is False
        assert _is_strategy_file('loader.py') is False
        assert _is_strategy_file('__init__.py') is False
        assert _is_strategy_file('test_macd.py') is False

    def test_case_insensitive(self):
        """测试大小写不敏感"""
        assert _is_strategy_file('MACD_Strategy.py') is True
        assert _is_strategy_file('STRATEGY_macd.py') is True


# ═══════════════════════════════════════════════════════════════════════════
# StrategyLoader 文件系统扫描测试
# ═══════════════════════════════════════════════════════════════════════════

class TestStrategyLoaderFileDiscovery:
    """测试文件系统发现"""

    def test_discover_from_fs_with_temp_files(self):
        """测试从临时目录发现策略文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建临时策略文件
            strategy_file = os.path.join(tmpdir, 'my_test_strategy.py')
            with open(strategy_file, 'w', encoding='utf-8') as f:
                f.write('''
from src.strategy.base import BaseStrategy

class MyTestStrategy(BaseStrategy):
    name = "my_test"
    version = "1.0.0"

    @classmethod
    def default_params(cls):
        return {}

    def calculate_indicators(self, data):
        return data

    def generate_signal(self, data, context):
        from src.strategy.base import create_hold_signal
        return create_hold_signal(context.symbol, 100.0)

    def analyze_status(self, data, symbol):
        from src.core.models import AnalysisResult
        return AnalysisResult(
            status="test", action="hold", reason="test",
            indicators={}, confidence=0.5
        )
''')

            # 清空注册表避免干扰
            registry.clear()

            # 创建加载器并扫描
            loader = StrategyLoader(auto_register=True)
            count = loader.discover_from_fs(tmpdir)

            # 验证发现
            assert count >= 1
            assert 'my_test' in loader.discovered_names

    def test_discover_from_fs_empty_dir(self):
        """测试空目录扫描"""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry.clear()
            loader = StrategyLoader(auto_register=True)
            count = loader.discover_from_fs(tmpdir)

            # 空目录应返回 0
            assert count == 0

    def test_discover_from_fs_nonexistent_dir(self):
        """测试不存在的目录"""
        registry.clear()
        loader = StrategyLoader(auto_register=True)
        # 不存在的目录应返回 0，不抛异常
        count = loader.discover_from_fs('/nonexistent/path')
        assert count == 0

    def test_discover_recursive(self):
        """测试递归扫描子目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建子目录
            subdir = os.path.join(tmpdir, 'subdir')
            os.makedirs(subdir)

            # 在子目录创建策略文件
            strategy_file = os.path.join(subdir, 'nested_strategy.py')
            with open(strategy_file, 'w', encoding='utf-8') as f:
                f.write('''
from src.strategy.base import BaseStrategy

class NestedStrategy(BaseStrategy):
    name = "nested"
    version = "1.0.0"

    @classmethod
    def default_params(cls):
        return {}

    def calculate_indicators(self, data):
        return data

    def generate_signal(self, data, context):
        from src.strategy.base import create_hold_signal
        return create_hold_signal(context.symbol, 100.0)

    def analyze_status(self, data, symbol):
        from src.core.models import AnalysisResult
        return AnalysisResult(
            status="test", action="hold", reason="test",
            indicators={}, confidence=0.5
        )
''')

            registry.clear()
            loader = StrategyLoader(auto_register=True)
            count = loader.discover_from_fs(tmpdir, recursive=True)

            # 应该发现子目录中的策略
            assert count >= 1


# ═══════════════════════════════════════════════════════════════════════════
# StrategyLoader YAML 配置加载测试
# ═══════════════════════════════════════════════════════════════════════════

class TestStrategyLoaderConfig:
    """测试 YAML 配置加载"""

    def test_load_from_config_valid(self):
        """测试有效的 YAML 配置加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, 'strategies.yml')
            with open(config_file, 'w', encoding='utf-8') as f:
                f.write('''
strategies:
  - name: test_macd
    module: src.strategy.macd
    class: MACDStrategy
    enabled: true
    params:
      fast: 12
      slow: 26
''')

            registry.clear()
            loader = StrategyLoader(auto_register=True)
            count = loader.load_from_config(config_file)

            # 应该成功加载
            assert count == 1
            assert 'test_macd' in loader.discovered_names

    def test_load_from_config_disabled(self):
        """测试禁用的策略不加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, 'strategies.yml')
            with open(config_file, 'w', encoding='utf-8') as f:
                f.write('''
strategies:
  - name: disabled_strategy
    module: src.strategy.macd
    class: MACDStrategy
    enabled: false
''')

            registry.clear()
            loader = StrategyLoader(auto_register=True)
            count = loader.load_from_config(config_file)

            # 禁用的策略不应加载
            assert count == 0

    def test_load_from_config_missing_fields(self):
        """测试缺少必要字段的配置"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, 'strategies.yml')
            with open(config_file, 'w', encoding='utf-8') as f:
                f.write('''
strategies:
  - name: incomplete
    module: src.strategy.macd
    # 缺少 class 字段
''')

            registry.clear()
            loader = StrategyLoader(auto_register=True)
            count = loader.load_from_config(config_file)

            # 缺少必要字段应跳过
            assert count == 0

    def test_load_from_config_nonexistent_file(self):
        """测试不存在的配置文件"""
        registry.clear()
        loader = StrategyLoader(auto_register=True)
        count = loader.load_from_config('/nonexistent/config.yml')

        # 不存在的文件应返回 0
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════════
# Registry 内置策略测试
# ═══════════════════════════════════════════════════════════════════════════

class TestRegistryBuiltins:
    """测试 registry 内置策略"""

    def test_registry_contains_builtin_strategies(self):
        """测试 registry 导入后包含 macd/multi_timeframe/weekly 三个内置策略"""
        # 重新导入以确保注册
        import importlib
        import src.strategy
        importlib.reload(src.strategy)

        # 验证内置策略存在
        strategy_names = registry.names()

        assert 'macd' in strategy_names, "macd strategy not in registry"
        assert 'multi_timeframe' in strategy_names, "multi_timeframe strategy not in registry"
        assert 'weekly' in strategy_names, "weekly strategy not in registry"

    def test_registry_get_strategy(self):
        """测试获取策略类"""
        import importlib
        import src.strategy
        importlib.reload(src.strategy)

        macd_cls = registry.get('macd')
        assert macd_cls is not None
        assert issubclass(macd_cls, BaseStrategy)

    def test_registry_create_instance(self):
        """测试创建策略实例"""
        import importlib
        import src.strategy
        importlib.reload(src.strategy)

        strategy = registry.create('macd', params={'fast': 10, 'slow': 20})
        assert strategy is not None
        assert strategy.params['fast'] == 10
        assert strategy.params['slow'] == 20


# ═══════════════════════════════════════════════════════════════════════════
# StrategyLoader 查询接口测试
# ═══════════════════════════════════════════════════════════════════════════

class TestStrategyLoaderQueries:
    """测试 StrategyLoader 查询接口"""

    def test_discovered_property(self):
        """测试 discovered 属性"""
        registry.clear()
        loader = StrategyLoader(auto_register=False)

        # discovered 应返回列表
        assert isinstance(loader.discovered, list)
        assert isinstance(loader.discovered_names, list)

    def test_auto_register_false(self):
        """测试 auto_register=False 时不注册"""
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy_file = os.path.join(tmpdir, 'auto_test_strategy.py')
            with open(strategy_file, 'w', encoding='utf-8') as f:
                f.write('''
from src.strategy.base import BaseStrategy
from src.core.models import StrategyDecision

class AutoTestStrategy(BaseStrategy):
    name = "auto_test"
    version = "1.0.0"

    @classmethod
    def default_params(cls):
        return {}

    def calculate_indicators(self, data):
        return data

    def evaluate(self, data, context):
        return StrategyDecision.hold(context.symbol, "测试")
''')

            registry.clear()
            loader = StrategyLoader(auto_register=False)
            count = loader.discover_from_fs(tmpdir)

            # 应该发现策略
            assert count == 1
            assert 'auto_test' in loader.discovered_names
            # 但 registry 中不应有（因为 auto_register=False）
            assert not registry.has('auto_test')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
