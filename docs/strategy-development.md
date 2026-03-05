# 策略开发指南

本指南将帮助开发者了解如何在量化交易系统中开发、测试和部署自定义交易策略。

## 1. 策略基础

### 1.1 策略基类

所有策略都继承自 `BaseStrategy` 基类，位于 `src/strategy/base.py`。

```python
from src.strategy.base import BaseStrategy, StrategyContext
from src.core.models import Signal, AnalysisResult
import pandas as pd

class MyStrategy(BaseStrategy):
    name = "MyStrategy"
    version = "1.0.0"
    author = "Your Name"
    description = "策略描述"
    
    @classmethod
    def default_params(cls) -> Dict[str, Any]:
        """定义默认参数"""
        return {
            'param1': 'value1',
            'param2': 100,
        }
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        pass
    
    def generate_signal(self, data: pd.DataFrame, context: StrategyContext) -> Signal:
        """生成交易信号"""
        pass
    
    def analyze_status(self, data: pd.DataFrame, symbol: str) -> AnalysisResult:
        """分析当前状态（可选）"""
        pass
```

### 1.2 策略生命周期

1. **初始化**: 加载参数，初始化内部状态
2. **指标计算**: 计算所需的技术指标
3. **信号生成**: 基于指标和市场数据生成交易信号
4. **状态分析**: 提供策略当前状态分析

## 2. 核心接口详解

### 2.1 calculate_indicators()

计算策略所需的技术指标，返回包含指标的数据框。

```python
def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
    """
    计算技术指标
    
    Args:
        data: OHLCV 数据，包含 ['open', 'high', 'low', 'close', 'volume'] 列
    
    Returns:
        添加了技术指标的数据框
    """
    df = data.copy()
    
    # 计算移动平均线
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma20'] = df['close'].rolling(window=20).mean()
    
    # 计算 RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + gain / loss))
    
    return df
```

### 2.2 generate_signal()

生成交易信号，这是策略的核心逻辑。

```python
def generate_signal(self, data: pd.DataFrame, context: StrategyContext) -> Signal:
    """
    生成交易信号
    
    Args:
        data: 计算完指标的 OHLCV 数据
        context: 策略上下文，包含持仓信息等
    
    Returns:
        Signal: 交易信号 (BUY/SELL/HOLD)
    """
    # 获取最新价格
    price = data['close'].iloc[-1]
    symbol = context.symbol
    
    # 获取当前持仓
    position = context.position
    
    # 信号生成逻辑
    if position and position.quantity > 0:
        # 有持仓时的卖出逻辑
        if self.should_sell(data, position):
            return create_sell_signal(
                symbol=symbol,
                price=price,
                strength=0.8,
                reason="卖出原因",
                indicator1=data['rsi'].iloc[-1],
                indicator2=data['ma5'].iloc[-1]
            )
    else:
        # 无持仓时的买入逻辑
        if self.should_buy(data):
            return create_buy_signal(
                symbol=symbol,
                price=price,
                strength=0.8,
                reason="买入原因",
                indicator1=data['rsi'].iloc[-1],
                indicator2=data['ma20'].iloc[-1]
            )
    
    # 持有信号
    return create_hold_signal(symbol, price, "观望")
```

### 2.3 Signal 创建

使用工厂函数创建标准化的交易信号：

```python
from src.strategy.base import create_buy_signal, create_sell_signal, create_hold_signal

# 买入信号
buy_signal = create_buy_signal(
    symbol="000001.SZ",
    price=10.50,
    strength=0.8,
    reason="金叉买入",
    ma5=10.2,
    ma20=10.0
)

# 卖出信号
sell_signal = create_sell_signal(
    symbol="000001.SZ",
    price=12.30,
    strength=0.9,
    reason="止损",
    stop_loss=10.0
)

# 持有信号
hold_signal = create_hold_signal(
    symbol="000001.SZ",
    price=11.20,
    reason="等待信号"
)
```

## 3. 策略示例

### 3.1 双均线策略

```python
from src.strategy.base import BaseStrategy, StrategyContext
from src.core.models import Signal, AnalysisResult
from src.strategy.base import create_buy_signal, create_sell_signal, create_hold_signal
from typing import Dict, Any
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class DualMovingAverageStrategy(BaseStrategy):
    """双均线策略"""
    
    name = "DualMA"
    version = "1.0.0"
    author = "Quant Team"
    description = "基于双均线交叉的趋势跟踪策略"
    
    @classmethod
    def default_params(cls) -> Dict[str, Any]:
        return {
            'short_period': 5,
            'long_period': 20,
            'min_data_length': 30,
        }
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算双均线"""
        df = data.copy()
        
        short_period = self.params['short_period']
        long_period = self.params['long_period']
        
        df['ma_short'] = df['close'].rolling(window=short_period).mean()
        df['ma_long'] = df['close'].rolling(window=long_period).mean()
        
        # 金叉死叉检测
        df['golden_cross'] = (df['ma_short'] > df['ma_long']) & (df['ma_short'].shift(1) <= df['ma_long'].shift(1))
        df['death_cross'] = (df['ma_short'] < df['ma_long']) & (df['ma_short'].shift(1) >= df['ma_long'].shift(1))
        
        return df
    
    def generate_signal(self, data: pd.DataFrame, context: StrategyContext) -> Signal:
        """生成交易信号"""
        if len(data) < self.params['min_data_length']:
            return create_hold_signal(context.symbol, data['close'].iloc[-1], "数据不足")
        
        price = data['close'].iloc[-1]
        latest = data.iloc[-1]
        
        # 卖出逻辑
        if context.position and context.position.quantity > 0:
            if latest['death_cross']:
                return create_sell_signal(
                    symbol=context.symbol,
                    price=price,
                    strength=0.9,
                    reason=f"死叉卖出 | 短线={latest['ma_short']:.2f}, 长线={latest['ma_long']:.2f}",
                    ma_short=round(latest['ma_short'], 2),
                    ma_long=round(latest['ma_long'], 2)
                )
        
        # 买入逻辑
        if latest['golden_cross']:
            strength = 0.8
            # 价格在均线下方金叉，信号更强
            if price < latest['ma_long']:
                strength = 0.9
            
            return create_buy_signal(
                symbol=context.symbol,
                price=price,
                strength=strength,
                reason=f"金叉买入 | 短线={latest['ma_short']:.2f}, 长线={latest['ma_long']:.2f}",
                ma_short=round(latest['ma_short'], 2),
                ma_long=round(latest['ma_long'], 2)
            )
        
        # 持有
        return create_hold_signal(
            context.symbol, 
            price, 
            f"无信号 | 短线={latest['ma_short']:.2f}, 长线={latest['ma_long']:.2f}"
        )
```

### 3.2 RSI 超买超卖策略

```python
class RSIStrategy(BaseStrategy):
    """RSI 超买超卖策略"""
    
    name = "RSI"
    version = "1.0.0"
    author = "Quant Team"
    description = "基于 RSI 指标的超买超卖策略"
    
    @classmethod
    def default_params(cls) -> Dict[str, Any]:
        return {
            'rsi_period': 14,
            'oversold': 30,
            'overbought': 70,
            'min_data_length': 30,
        }
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算 RSI 指标"""
        df = data.copy()
        period = self.params['rsi_period']
        
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        df['rsi'] = 100 - (100 / (1 + gain / loss))
        
        return df
    
    def generate_signal(self, data: pd.DataFrame, context: StrategyContext) -> Signal:
        """生成交易信号"""
        if len(data) < self.params['min_data_length']:
            return create_hold_signal(context.symbol, data['close'].iloc[-1], "数据不足")
        
        price = data['close'].iloc[-1]
        rsi = data['rsi'].iloc[-1]
        
        # 卖出逻辑
        if context.position and context.position.quantity > 0:
            if rsi > self.params['overbought']:
                return create_sell_signal(
                    symbol=context.symbol,
                    price=price,
                    strength=0.8,
                    reason=f"RSI超买卖出 | RSI={rsi:.2f}",
                    rsi=round(rsi, 2)
                )
        
        # 买入逻辑
        if rsi < self.params['oversold']:
            strength = 0.8
            # RSI 极度超卖，信号更强
            if rsi < 20:
                strength = 0.9
            
            return create_buy_signal(
                symbol=context.symbol,
                price=price,
                strength=strength,
                reason=f"RSI超卖买入 | RSI={rsi:.2f}",
                rsi=round(rsi, 2)
            )
        
        return create_hold_signal(context.symbol, price, f"RSI中性 | RSI={rsi:.2f}")
```

## 4. 策略注册

### 4.1 自动注册

使用装饰器自动注册策略：

```python
from src.strategy.registry import strategy_registry

@strategy_registry.register('dual_ma')
class DualMovingAverageStrategy(BaseStrategy):
    pass
```

### 4.2 配置文件注册

在策略配置文件中注册：

```yaml
# src/strategy/configs/dual_ma.yaml
strategy:
  name: "DualMA"
  class: "strategies.dual_ma.DualMovingAverageStrategy"
  params:
    short_period: 5
    long_period: 20
    min_data_length: 30
```

## 5. 策略测试

### 5.1 单元测试

```python
import pytest
import pandas as pd
from src.strategy.dual_ma import DualMovingAverageStrategy

class TestDualMovingAverageStrategy:
    
    def setup_method(self):
        self.strategy = DualMovingAverageStrategy()
        # 创建测试数据
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        prices = [100 + i * 0.1 for i in range(100)]
        self.test_data = pd.DataFrame({
            'date': dates,
            'open': prices,
            'high': [p * 1.02 for p in prices],
            'low': [p * 0.98 for p in prices],
            'close': prices,
            'volume': [10000] * 100
        }).set_index('date')
    
    def test_calculate_indicators(self):
        """测试指标计算"""
        result = self.strategy.calculate_indicators(self.test_data)
        assert 'ma_short' in result.columns
        assert 'ma_long' in result.columns
        assert not result['ma_short'].isna().all()
    
    def test_signal_generation(self):
        """测试信号生成"""
        context = StrategyContext(symbol="000001.SZ", position=None)
        signal = self.strategy.generate_signal(self.test_data, context)
        assert signal is not None
        assert signal.symbol == "000001.SZ"
```

### 5.2 回测验证

```bash
# 运行回测验证策略
python -m src.cli.main backtest \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --symbols 000001.SZ \
  --strategy dual_ma \
  --initial-capital 1000000
```

## 6. 策略优化

### 6.1 参数优化

```python
def optimize_parameters(symbol: str, start_date: str, end_date: str):
    """参数优化示例"""
    best_params = None
    best_score = -float('inf')
    
    for short_period in range(3, 11):
        for long_period in range(15, 31):
            if short_period >= long_period:
                continue
                
            params = {
                'short_period': short_period,
                'long_period': long_period
            }
            
            # 运行回测
            result = run_backtest(symbol, start_date, end_date, params)
            score = result.sharpe_ratio
            
            if score > best_score:
                best_score = score
                best_params = params
    
    return best_params, best_score
```

### 6.2 多周期优化

```python
@strategy_registry.register('optimized_dual_ma')
class OptimizedDualMAStrategy(BaseStrategy):
    """优化的双均线策略"""
    
    def generate_signal(self, data: pd.DataFrame, context: StrategyContext) -> Signal:
        # 基于市场状态调整参数
        volatility = data['close'].pct_change().rolling(20).std().iloc[-1]
        
        if volatility > 0.03:  # 高波动市场
            self.params['short_period'] = 3
            self.params['long_period'] = 10
        else:  # 低波动市场
            self.params['short_period'] = 5
            self.params['long_period'] = 20
        
        # 重新计算指标
        data = self.calculate_indicators(data)
        return self._generate_signal_logic(data, context)
```

## 7. 最佳实践

### 7.1 代码规范

- 使用类型提示
- 添加详细的文档字符串
- 遵循 PEP 8 代码风格
- 使用有意义的变量名

### 7.2 性能优化

- 缓存计算结果
- 避免重复计算
- 使用向量化操作
- 合理处理缺失数据

### 7.3 风险管理

- 设置合理的止损
- 控制仓位大小
- 考虑市场流动性
- 避免过度拟合

### 7.4 测试覆盖

- 测试所有代码路径
- 包含边界条件测试
- 进行样本外测试
- 定期重新验证策略

## 8. 常见问题

### 8.1 数据不足

```python
def generate_signal(self, data: pd.DataFrame, context: StrategyContext) -> Signal:
    min_data = self.params.get('min_data_length', 50)
    if len(data) < min_data:
        return create_hold_signal(context.symbol, data['close'].iloc[-1], "数据不足")
```

### 8.2 指标计算异常

```python
def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
    try:
        df = data.copy()
        # 指标计算逻辑
        return df
    except Exception as e:
        logger.error(f"指标计算失败: {e}")
        return data  # 返回原数据，避免程序崩溃
```

### 8.3 信号频率控制

```python
class FrequencyControlStrategy(BaseStrategy):
    def __init__(self, params=None):
        super().__init__(params)
        self.last_signal_date = None
    
    def generate_signal(self, data: pd.DataFrame, context: StrategyContext) -> Signal:
        current_date = data.index[-1]
        
        # 同一天内不重复信号
        if (self.last_signal_date and 
            current_date.date() == self.last_signal_date.date()):
            return create_hold_signal(context.symbol, data['close'].iloc[-1], "同日信号过滤")
        
        signal = self._generate_logic(data, context)
        if signal.signal_type != SignalType.HOLD:
            self.last_signal_date = current_date
        
        return signal
```

通过遵循本指南，开发者可以创建高质量、可靠且有效的交易策略，并在量化交易系统中成功部署。