"""
BaseStrategy 单元测试

覆盖：
- 初始化 / 参数合并
- 抽象方法约束
- calculate_indicators / evaluate 正常调用
- should_notify 逻辑
- validate_data / validate_params
- initialize / on_start / on_stop 生命周期
- min_bars / get_info / reset 等工具方法
- 便捷函数 create_hold_signal / create_buy_signal / create_sell_signal
"""

import pytest
from unittest.mock import patch, MagicMock

import pandas as pd
import numpy as np

from src.strategy.base import (
    BaseStrategy,
    StrategyDeps,
    StrategyContext,
    create_hold_signal,
    create_buy_signal,
    create_sell_signal,
)
from src.core.models import (
    Signal,
    SignalType,
    StrategyDecision,
    Portfolio,
    Position,
)


# ═══════════════════════════════════════════════════════════════
# 测试用具体策略类
# ═══════════════════════════════════════════════════════════════

class DummyStrategy(BaseStrategy):
    name = "dummy"
    version = "1.0.0"

    @classmethod
    def default_params(cls):
        return {"period": 20, "threshold": 0.5}

    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        data = data.copy()
        data["ma"] = data["close"].rolling(self.params["period"]).mean()
        return data

    def evaluate(self, data: pd.DataFrame, context: StrategyContext) -> StrategyDecision:
        return StrategyDecision.hold(context.symbol, "测试")


class MinimalStrategy(BaseStrategy):
    """无 default_params 覆盖的策略"""
    name = "minimal"
    version = "2.0.0"

    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        return data

    def evaluate(self, data: pd.DataFrame, context: StrategyContext) -> StrategyDecision:
        return StrategyDecision.hold(context.symbol)


# ═══════════════════════════════════════════════════════════════
# fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def sample_ohlcv():
    """生成标准 OHLCV DataFrame"""
    n = 100
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    np.random.seed(42)
    close = 10 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "date": dates,
        "open": close + np.random.randn(n) * 0.2,
        "high": close + abs(np.random.randn(n) * 0.3),
        "low": close - abs(np.random.randn(n) * 0.3),
        "close": close,
        "volume": np.random.randint(1000, 10000, n),
    })


@pytest.fixture
def sample_context():
    return StrategyContext(
        symbol="AAPL",
        portfolio=Portfolio(cash=100000, total_value=100000),
    )


@pytest.fixture
def strategy():
    return DummyStrategy(params={"period": 10})


# ═══════════════════════════════════════════════════════════════
# 初始化 & 参数
# ═══════════════════════════════════════════════════════════════

class TestStrategyInit:
    def test_default_params(self):
        s = DummyStrategy()
        assert s.params == {"period": 20, "threshold": 0.5}

    def test_params_override(self):
        s = DummyStrategy(params={"period": 10})
        assert s.params["period"] == 10
        assert s.params["threshold"] == 0.5  # 未覆盖的保持默认

    def test_empty_default_params(self):
        s = MinimalStrategy()
        assert s.params == {}

    def test_meta_info(self):
        s = DummyStrategy()
        assert s.name == "dummy"
        assert s.version == "1.0.0"
        assert not s._initialized

    def test_repr(self):
        s = DummyStrategy()
        assert "dummy" in repr(s)
        assert "1.0.0" in repr(s)


# ═══════════════════════════════════════════════════════════════
# 抽象方法约束
# ═══════════════════════════════════════════════════════════════

class TestAbstractMethods:
    def test_cannot_instantiate_base(self):
        with pytest.raises(TypeError):
            BaseStrategy()

    def test_missing_calculate_indicators(self):
        class Broken(BaseStrategy):
            name = "broken"
            def evaluate(self, data, context):
                return StrategyDecision.hold("X")

        with pytest.raises(TypeError):
            Broken()

    def test_missing_evaluate(self):
        class Broken2(BaseStrategy):
            name = "broken2"
            def calculate_indicators(self, data):
                return data

        with pytest.raises(TypeError):
            Broken2()


# ═══════════════════════════════════════════════════════════════
# calculate_indicators / evaluate
# ═══════════════════════════════════════════════════════════════

class TestStrategyCore:
    def test_calculate_indicators(self, strategy, sample_ohlcv):
        result = strategy.calculate_indicators(sample_ohlcv)
        assert "ma" in result.columns
        # 前 period-1 行为 NaN
        assert result["ma"].iloc[:9].isna().all()
        assert not pd.isna(result["ma"].iloc[9])

    def test_evaluate_returns_decision(self, strategy, sample_ohlcv, sample_context):
        data = strategy.calculate_indicators(sample_ohlcv)
        decision = strategy.evaluate(data, sample_context)
        assert isinstance(decision, StrategyDecision)
        assert decision.signal_type == SignalType.HOLD
        assert decision.symbol == "AAPL"

    def test_evaluate_returns_hold_action(self, strategy, sample_ohlcv, sample_context):
        data = strategy.calculate_indicators(sample_ohlcv)
        decision = strategy.evaluate(data, sample_context)
        assert decision.action == "持有"


# ═══════════════════════════════════════════════════════════════
# should_notify
# ═══════════════════════════════════════════════════════════════

class TestShouldNotify:
    def test_first_buy_notifies(self, strategy):
        decision = StrategyDecision.buy("AAPL", 100.0, reason="突破")
        assert strategy.should_notify(decision) is True

    def test_first_hold_does_not_notify(self, strategy):
        decision = StrategyDecision.hold("AAPL", "观望")
        assert strategy.should_notify(decision) is False

    def test_signal_change_notifies(self, strategy):
        prev = StrategyDecision.hold("AAPL", "观望")
        curr = StrategyDecision.buy("AAPL", 100.0, reason="突破")
        assert strategy.should_notify(curr, prev) is True

    def test_same_signal_no_notify(self, strategy):
        prev = StrategyDecision.hold("AAPL", "观望")
        curr = StrategyDecision.hold("AAPL", "观望")
        assert strategy.should_notify(curr, prev) is False

    def test_hold_to_sell_notifies(self, strategy):
        prev = StrategyDecision.hold("AAPL", "观望")
        curr = StrategyDecision.sell("AAPL", 100.0, reason="止损")
        assert strategy.should_notify(curr, prev) is True

    def test_buy_to_buy_no_notify(self, strategy):
        prev = StrategyDecision.buy("AAPL", 99.0, reason="首次")
        curr = StrategyDecision.buy("AAPL", 100.0, reason="继续")
        assert strategy.should_notify(curr, prev) is False


# ═══════════════════════════════════════════════════════════════
# validate_data
# ═══════════════════════════════════════════════════════════════

class TestValidateData:
    def test_valid_data(self, strategy, sample_ohlcv):
        assert strategy.validate_data(sample_ohlcv) is True

    def test_empty_dataframe(self, strategy):
        assert strategy.validate_data(pd.DataFrame()) is False

    def test_none_data(self, strategy):
        assert strategy.validate_data(None) is False

    def test_missing_columns(self, strategy):
        bad = pd.DataFrame({"close": [1, 2, 3]})
        assert strategy.validate_data(bad) is False


# ═══════════════════════════════════════════════════════════════
# validate_params (无 schema 默认通过)
# ═══════════════════════════════════════════════════════════════

class TestValidateParams:
    def test_no_schema_always_pass(self, strategy):
        assert strategy.validate_params() is True


# ═══════════════════════════════════════════════════════════════
# 生命周期
# ═══════════════════════════════════════════════════════════════

class TestLifecycle:
    def test_initialize_success(self, strategy):
        strategy.initialize()
        assert strategy._initialized is True

    def test_initialize_idempotent(self, strategy):
        strategy.initialize()
        strategy.initialize()  # 第二次不报错
        assert strategy._initialized is True

    def test_on_start_called(self):
        called = []
        class TrackingStrategy(DummyStrategy):
            def on_start(self, deps):
                called.append(True)

        s = TrackingStrategy()
        s.initialize()
        assert len(called) == 1

    def test_on_stop(self, strategy):
        strategy.initialize()
        strategy.on_stop()  # 不应抛异常

    def test_reset(self, strategy):
        strategy.initialize()
        strategy.set_indicator("ma", 20.0)
        strategy.set_state("count", 5)
        strategy.reset()
        assert strategy._initialized is False
        assert strategy.get_indicator("ma") is None
        assert strategy.get_state("count") is None


# ═══════════════════════════════════════════════════════════════
# 工具方法
# ═══════════════════════════════════════════════════════════════

class TestUtilityMethods:
    def test_min_bars_default(self, strategy):
        assert strategy.min_bars == 60  # 默认 min_data_length

    def test_min_bars_custom(self):
        s = DummyStrategy(params={"period": 30, "threshold": 0.5, "min_data_length": 120})
        assert s.min_bars == 120

    def test_get_info(self, strategy):
        info = strategy.get_info()
        assert info["name"] == "dummy"
        assert info["version"] == "1.0.0"
        assert info["params"]["period"] == 10  # fixture 使用 params={"period": 10}
        assert info["initialized"] is False

    def test_indicator_get_set(self, strategy):
        assert strategy.get_indicator("x") is None
        strategy.set_indicator("x", 42)
        assert strategy.get_indicator("x") == 42

    def test_state_get_set(self, strategy):
        assert strategy.get_state("count", 0) == 0
        strategy.set_state("count", 10)
        assert strategy.get_state("count") == 10
        assert strategy.get_state("missing", "default") == "default"

    def test_on_bar_default(self, strategy, sample_context):
        assert strategy.on_bar({}, sample_context) is None

    def test_on_order_filled_default(self, strategy):
        strategy.on_order_filled(None)  # 不应抛异常

    def test_on_position_changed_default(self, strategy):
        pos = Position(symbol="AAPL", quantity=100, avg_cost=50.0)
        strategy.on_position_changed(pos)  # 不应抛异常


# ═══════════════════════════════════════════════════════════════
# config 解析
# ═══════════════════════════════════════════════════════════════

class TestConfigParsing:
    def test_no_config_returns_empty(self, strategy):
        assert strategy.config == {}

    def test_dict_config(self):
        s = DummyStrategy(config={"key": "value"})
        assert s.config == {"key": "value"}

    def test_dataclass_config(self):
        from dataclasses import dataclass

        @dataclass
        class MyConfig:
            fast: int = 12
            slow: int = 26

        class ConfigStrategy(DummyStrategy):
            ConfigClass = MyConfig

        s = ConfigStrategy(config={"fast": 10, "slow": 20})
        cfg = s.config
        assert isinstance(cfg, MyConfig)
        assert cfg.fast == 10
        assert cfg.slow == 20

    def test_dataclass_config_with_defaults(self):
        from dataclasses import dataclass

        @dataclass
        class MyConfig:
            fast: int = 12
            slow: int = 26

        class ConfigStrategy(DummyStrategy):
            ConfigClass = MyConfig

        # 只传部分字段
        s = ConfigStrategy(config={"fast": 5})
        cfg = s.config
        assert cfg.fast == 5
        assert cfg.slow == 26  # 使用默认值


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

class TestHelperFunctions:
    def test_create_hold_signal(self):
        sig = create_hold_signal("AAPL", 100.0, reason="观望")
        assert isinstance(sig, Signal)
        assert sig.symbol == "AAPL"
        assert sig.signal_type == SignalType.HOLD
        assert sig.price == 100.0

    def test_create_buy_signal(self):
        sig = create_buy_signal("AAPL", 100.0, strength=0.8, reason="突破")
        assert sig.signal_type == SignalType.BUY
        assert sig.strength == 0.8

    def test_create_sell_signal(self):
        sig = create_sell_signal("AAPL", 100.0, reason="止损")
        assert sig.signal_type == SignalType.SELL

    def test_create_buy_signal_metadata(self):
        sig = create_buy_signal("AAPL", 100.0, source="macd")
        assert sig.metadata["source"] == "macd"


# ═══════════════════════════════════════════════════════════════
# StrategyDeps
# ═══════════════════════════════════════════════════════════════

class TestStrategyDeps:
    def test_default_none(self):
        deps = StrategyDeps()
        assert deps.data_service is None
        assert deps.risk_manager is None
        assert deps.executor is None

    def test_with_values(self):
        deps = StrategyDeps(data_service="svc", risk_manager="rm", executor="ex")
        assert deps.data_service == "svc"
