"""
StrategyManager 单元测试

覆盖：
- 初始化 / 策略发现
- create_strategy / get_strategy_class / has_strategy
- list_strategies / get_strategy_names
- register_strategy / discover_from_directory
- reload
- get_strategy_manager 全局单例

注意：测试中禁用 auto_discover，避免加载外部配置依赖
"""

import pytest
from unittest.mock import patch, MagicMock
import tempfile
import os

from src.strategy.base import BaseStrategy, StrategyDecision
from src.strategy.manager import StrategyManager, get_strategy_manager
from src.strategy.registry import registry
from src.core.models import Portfolio, StrategyContext


# ═══════════════════════════════════════════════════════════════
# 测试用策略
# ═══════════════════════════════════════════════════════════════

class GammaStrategy(BaseStrategy):
    name = "gamma"
    version = "1.0.0"

    @classmethod
    def default_params(cls):
        return {"period": 30}

    def calculate_indicators(self, data):
        return data

    def evaluate(self, data, context):
        return StrategyDecision.hold(context.symbol)


class DeltaStrategy(BaseStrategy):
    name = "delta"
    version = "1.0.0"

    def calculate_indicators(self, data):
        return data

    def evaluate(self, data, context):
        return StrategyDecision.hold(context.symbol)


# ═══════════════════════════════════════════════════════════════
# fixture
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def clean_registry():
    registry.clear()
    yield
    registry.clear()


@pytest.fixture
def manager():
    """创建不自动发现的 manager，禁用文件系统扫描"""
    with patch.object(StrategyManager, "_load_builtin_strategies", return_value=0), \
         patch.object(StrategyManager, "_load_configured_strategies", return_value=0), \
         patch.object(StrategyManager, "_load_yaml_strategies", return_value=0):
        m = StrategyManager(auto_discover=False)
    # 持续 patch 实例方法，防止 _ensure_initialized 触发扫描
    m._load_builtin_strategies = lambda: 0
    m._load_configured_strategies = lambda: 0
    m._load_yaml_strategies = lambda: 0
    return m


# ═══════════════════════════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════════════════════════

class TestInit:
    def test_auto_discover_false(self, manager):
        assert manager._initialized is False
        assert registry.names() == []

    def test_initialize_idempotent(self, manager):
        manager.initialize()
        manager.initialize()
        assert manager._initialized is True


# ═══════════════════════════════════════════════════════════════
# 手动注册 + 查询
# ═══════════════════════════════════════════════════════════════

class TestQuery:
    def test_has_strategy_false(self, manager):
        assert manager.has_strategy("gamma") is False

    def test_has_strategy_true(self, manager):
        manager.register_strategy("gamma", GammaStrategy)
        assert manager.has_strategy("gamma") is True

    def test_get_strategy_names_empty(self, manager):
        names = manager.get_strategy_names()
        assert names == []

    def test_get_strategy_names_sorted(self, manager):
        manager.register_strategy("delta", DeltaStrategy)
        manager.register_strategy("gamma", GammaStrategy)
        names = manager.get_strategy_names()
        assert "delta" in names
        assert "gamma" in names

    def test_list_strategies(self, manager):
        manager.register_strategy("gamma", GammaStrategy)
        result = manager.list_strategies()
        assert len(result) == 1
        assert result[0]["name"] == "gamma"

    def test_get_strategy_class(self, manager):
        manager.register_strategy("gamma", GammaStrategy)
        cls = manager.get_strategy_class("gamma")
        assert cls is GammaStrategy

    def test_get_strategy_class_missing_raises(self, manager):
        with pytest.raises(KeyError):
            manager.get_strategy_class("nonexistent")


# ═══════════════════════════════════════════════════════════════
# create_strategy
# ═══════════════════════════════════════════════════════════════

class TestCreateStrategy:
    def test_create_default_params(self, manager):
        manager.register_strategy("gamma", GammaStrategy)
        s = manager.create_strategy("gamma")
        assert isinstance(s, GammaStrategy)
        assert s.params == {"period": 30}

    def test_create_with_params(self, manager):
        manager.register_strategy("gamma", GammaStrategy)
        s = manager.create_strategy("gamma", params={"period": 60})
        assert s.params["period"] == 60

    def test_create_missing_raises(self, manager):
        with pytest.raises(KeyError):
            manager.create_strategy("ghost")


# ═══════════════════════════════════════════════════════════════
# reload
# ═══════════════════════════════════════════════════════════════

class TestReload:
    def test_reload_clears_and_reinitializes(self, manager):
        manager.register_strategy("gamma", GammaStrategy)
        assert manager.has_strategy("gamma")

        # mock _load_builtin_strategies 等避免文件系统操作
        with patch.object(manager, "_load_builtin_strategies", return_value=0), \
             patch.object(manager, "_load_configured_strategies", return_value=0), \
             patch.object(manager, "_load_yaml_strategies", return_value=0):
            manager.reload()

        # reload 后 registry 应已清空
        assert not manager.has_strategy("gamma")


# ═══════════════════════════════════════════════════════════════
# discover_from_directory
# ═══════════════════════════════════════════════════════════════

class TestDiscoverFromDirectory:
    def test_discover_from_temp_dir(self, manager):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建符合命名约定的策略文件
            strategy_file = os.path.join(tmpdir, "gamma_strategy.py")
            with open(strategy_file, "w", encoding="utf-8") as f:
                f.write('''
from src.strategy.base import BaseStrategy
from src.core.models import StrategyDecision

class GammaStrat(BaseStrategy):
    name = "gamma_strat"
    version = "1.0.0"

    def calculate_indicators(self, data):
        return data

    def evaluate(self, data, ctx):
        return StrategyDecision.hold(ctx.symbol)
''')

            count = manager.discover_from_directory(tmpdir)
            assert count >= 1
            assert manager.has_strategy("gamma_strat")

    def test_discover_empty_dir(self, manager):
        with tempfile.TemporaryDirectory() as tmpdir:
            count = manager.discover_from_directory(tmpdir)
            assert count == 0


# ═══════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════

class TestGlobalSingleton:
    def test_get_strategy_manager_returns_same(self):
        # 重置全局实例
        from src.strategy.manager import _manager
        import src.strategy.manager as mgr_mod
        mgr_mod._manager = None

        m1 = get_strategy_manager()
        m2 = get_strategy_manager()
        assert m1 is m2

        # 清理
        mgr_mod._manager = None
