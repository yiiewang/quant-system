"""
StrategyRegistry 单元测试

覆盖：
- 单例行为
- register / get / create / has / names / list_strategies
- 重复注册覆盖
- 注册非 BaseStrategy 子类报错
- 获取未注册策略报错
- clear / register_strategy 装饰器
"""

import pytest

from src.strategy.base import BaseStrategy, StrategyDecision
from src.strategy.registry import (
    StrategyRegistry,
    registry,
    register_strategy,
    get_registry,
)
from src.core.models import Portfolio, StrategyContext


# ═══════════════════════════════════════════════════════════════
# 测试用策略
# ═══════════════════════════════════════════════════════════════

class AlphaStrategy(BaseStrategy):
    name = "alpha"
    version = "1.0.0"

    @classmethod
    def default_params(cls):
        return {"n": 10}

    def calculate_indicators(self, data):
        return data

    def evaluate(self, data, context):
        return StrategyDecision.hold(context.symbol)


class BetaStrategy(BaseStrategy):
    name = "beta"
    version = "2.0.0"

    def calculate_indicators(self, data):
        return data

    def evaluate(self, data, context):
        return StrategyDecision.hold(context.symbol)


# ═══════════════════════════════════════════════════════════════
# fixture：每个测试前清空全局注册表
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def clean_registry():
    """每个测试前后清空全局注册表"""
    registry.clear()
    yield
    registry.clear()


# ═══════════════════════════════════════════════════════════════
# 单例
# ═══════════════════════════════════════════════════════════════

class TestSingleton:
    def test_registry_is_singleton(self):
        r1 = StrategyRegistry()
        r2 = StrategyRegistry()
        assert r1 is r2

    def test_get_registry_returns_same_instance(self):
        assert get_registry() is registry


# ═══════════════════════════════════════════════════════════════
# register
# ═══════════════════════════════════════════════════════════════

class TestRegister:
    def test_register_success(self):
        registry.register("alpha", AlphaStrategy)
        assert registry.has("alpha")

    def test_register_non_basesubclass_raises(self):
        class NotAStrategy:
            pass

        with pytest.raises(TypeError):
            registry.register("bad", NotAStrategy)

    def test_register_base_itself_allowed(self):
        """registry.register 允许注册 BaseStrategy 本身（设计决策）"""
        registry.register("base", BaseStrategy)
        assert registry.has("base")

    def test_register_duplicate_overwrites(self):
        registry.register("alpha", AlphaStrategy)
        registry.register("alpha", BetaStrategy)
        assert registry.get("alpha") is BetaStrategy


# ═══════════════════════════════════════════════════════════════
# get
# ═══════════════════════════════════════════════════════════════

class TestGet:
    def test_get_registered(self):
        registry.register("alpha", AlphaStrategy)
        cls = registry.get("alpha")
        assert cls is AlphaStrategy

    def test_get_unregistered_raises(self):
        with pytest.raises(KeyError, match="notexist"):
            registry.get("notexist")

    def test_get_error_shows_available(self):
        registry.register("alpha", AlphaStrategy)
        with pytest.raises(KeyError, match="alpha"):
            registry.get("missing")


# ═══════════════════════════════════════════════════════════════
# create
# ═══════════════════════════════════════════════════════════════

class TestCreate:
    def test_create_instance(self):
        registry.register("alpha", AlphaStrategy)
        s = registry.create("alpha")
        assert isinstance(s, AlphaStrategy)
        assert s.params == {"n": 10}

    def test_create_with_params(self):
        registry.register("alpha", AlphaStrategy)
        s = registry.create("alpha", params={"n": 50})
        assert s.params["n"] == 50

    def test_create_unregistered_raises(self):
        with pytest.raises(KeyError):
            registry.create("ghost")


# ═══════════════════════════════════════════════════════════════
# has / names / list_strategies
# ═══════════════════════════════════════════════════════════════

class TestQueries:
    def test_has_true(self):
        registry.register("alpha", AlphaStrategy)
        assert registry.has("alpha") is True

    def test_has_false(self):
        assert registry.has("alpha") is False

    def test_names_empty(self):
        assert registry.names() == []

    def test_names_sorted(self):
        registry.register("beta", BetaStrategy)
        registry.register("alpha", AlphaStrategy)
        assert registry.names() == ["beta", "alpha"]  # dict 保持插入顺序

    def test_list_strategies(self):
        registry.register("alpha", AlphaStrategy)
        result = registry.list_strategies()
        assert len(result) == 1
        assert result[0]["name"] == "alpha"
        assert result[0]["class"] == "AlphaStrategy"
        assert result[0]["version"] == "1.0.0"
        assert result[0]["default_params"] == {"n": 10}

    def test_list_strategies_empty(self):
        assert registry.list_strategies() == []


# ═══════════════════════════════════════════════════════════════
# clear
# ═══════════════════════════════════════════════════════════════

class TestClear:
    def test_clear_empties_all(self):
        registry.register("alpha", AlphaStrategy)
        registry.register("beta", BetaStrategy)
        registry.clear()
        assert registry.names() == []
        assert registry.has("alpha") is False


# ═══════════════════════════════════════════════════════════════
# register_strategy 装饰器
# ═══════════════════════════════════════════════════════════════

class TestDecorator:
    def test_decorator_registers(self):
        @register_strategy("decorated")
        class DecoratedStrategy(BaseStrategy):
            name = "decorated"
            def calculate_indicators(self, data):
                return data
            def evaluate(self, data, ctx):
                return StrategyDecision.hold(ctx.symbol)

        assert registry.has("decorated")
        assert registry.get("decorated") is DecoratedStrategy

    def test_decorator_preserves_class(self):
        @register_strategy("deco2")
        class Deco2(BaseStrategy):
            name = "deco2"
            def calculate_indicators(self, data):
                return data
            def evaluate(self, data, ctx):
                return StrategyDecision.hold(ctx.symbol)

        # 装饰器不改变类本身
        assert Deco2.name == "deco2"
