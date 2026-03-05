# MACD 策略设计文档

## 1. MACD 指标原理

### 1.1 什么是 MACD？

MACD 是由 Gerald Appel 于 1970 年代发明的趋势跟踪动量指标，通过两条指数移动平均线（EMA）的差值来判断买卖时机。

### 1.2 计算公式

```
DIF（快线）= EMA(12) - EMA(26)
DEA（慢线）= EMA(DIF, 9)
MACD柱    = 2 × (DIF - DEA)
```

其中 EMA 计算公式：

```
EMA(t) = Price(t) × k + EMA(t-1) × (1-k)
k = 2 / (N + 1)
```

### 1.3 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| fast_period | 12 | 快速 EMA 周期 |
| slow_period | 26 | 慢速 EMA 周期 |
| signal_period | 9 | 信号线 EMA 周期 |

## 2. 交易信号设计

### 2.1 基础信号

#### 金叉买入信号
```
条件: DIF 上穿 DEA（DIF从下方穿越DEA到上方）
动作: 开多仓 / 平空仓
```

#### 死叉卖出信号
```
条件: DIF 下穿 DEA（DIF从上方穿越DEA到下方）
动作: 平多仓 / 开空仓
```

### 2.2 增强信号（可选）

#### 零轴过滤
```python
# 只在零轴上方做多
buy_signal = (dif > dea) and (dif > 0) and (dea > 0)

# 只在零轴下方做空
sell_signal = (dif < dea) and (dif < 0) and (dea < 0)
```

#### 背离检测
```python
# 底背离：价格创新低，MACD 不创新低 → 看涨
# 顶背离：价格创新高，MACD 不创新高 → 看跌
```

#### MACD 柱状图确认
```python
# 红柱放大 + 金叉 → 强烈买入
# 绿柱放大 + 死叉 → 强烈卖出
```

## 3. 策略逻辑流程

```
┌─────────────────────────────────────────────────────────┐
│                    获取实时/历史行情                      │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    计算 MACD 指标                        │
│            DIF = EMA(12) - EMA(26)                      │
│            DEA = EMA(DIF, 9)                            │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    信号判断                              │
│    金叉? ──────► 买入信号                               │
│    死叉? ──────► 卖出信号                               │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    过滤器（可选）                         │
│    - 零轴位置过滤                                        │
│    - 背离确认                                           │
│    - 成交量确认                                          │
│    - 大盘环境过滤                                        │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    风控检查                              │
│    - 仓位限制                                           │
│    - 止损止盈                                           │
│    - 最大回撤控制                                        │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    执行交易                              │
│    - 计算下单数量                                        │
│    - 发送订单                                           │
│    - 记录日志                                           │
└─────────────────────────────────────────────────────────┘
```

## 4. 代码实现示例

### 4.1 MACD 计算

```python
import pandas as pd
import numpy as np

def calculate_macd(df: pd.DataFrame, 
                   fast: int = 12, 
                   slow: int = 26, 
                   signal: int = 9) -> pd.DataFrame:
    """
    计算 MACD 指标
    
    Args:
        df: 包含 'close' 列的 DataFrame
        fast: 快速 EMA 周期
        slow: 慢速 EMA 周期
        signal: 信号线周期
    
    Returns:
        包含 DIF, DEA, MACD 列的 DataFrame
    """
    # 计算快慢 EMA
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    
    # 计算 DIF（快线）
    df['dif'] = ema_fast - ema_slow
    
    # 计算 DEA（慢线/信号线）
    df['dea'] = df['dif'].ewm(span=signal, adjust=False).mean()
    
    # 计算 MACD 柱状图
    df['macd'] = 2 * (df['dif'] - df['dea'])
    
    return df
```

### 4.2 信号生成

```python
def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    生成交易信号
    
    Returns:
        signal: 1=买入, -1=卖出, 0=持有
    """
    df['signal'] = 0
    
    # 金叉：DIF 上穿 DEA
    golden_cross = (df['dif'] > df['dea']) & (df['dif'].shift(1) <= df['dea'].shift(1))
    df.loc[golden_cross, 'signal'] = 1
    
    # 死叉：DIF 下穿 DEA
    death_cross = (df['dif'] < df['dea']) & (df['dif'].shift(1) >= df['dea'].shift(1))
    df.loc[death_cross, 'signal'] = -1
    
    return df
```

### 4.3 零轴增强版

```python
def generate_enhanced_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    带零轴过滤的增强信号
    """
    df['signal'] = 0
    
    # 零轴上方金叉 - 强买入
    strong_buy = (
        (df['dif'] > df['dea']) & 
        (df['dif'].shift(1) <= df['dea'].shift(1)) &
        (df['dif'] > 0)
    )
    df.loc[strong_buy, 'signal'] = 1
    
    # 零轴下方死叉 - 强卖出
    strong_sell = (
        (df['dif'] < df['dea']) & 
        (df['dif'].shift(1) >= df['dea'].shift(1)) &
        (df['dif'] < 0)
    )
    df.loc[strong_sell, 'signal'] = -1
    
    return df
```

## 5. 策略优缺点分析

### 5.1 优点

| 优点 | 说明 |
|------|------|
| **趋势跟踪** | 能有效捕捉中长期趋势 |
| **参数简单** | 仅 3 个核心参数，易于理解和优化 |
| **信号明确** | 金叉死叉判断清晰，无歧义 |
| **适用性广** | 股票、期货、外汇、加密货币均可使用 |

### 5.2 缺点

| 缺点 | 解决方案 |
|------|----------|
| **滞后性** | 结合 RSI、布林带等先行指标 |
| **震荡市表现差** | 增加 ADX 过滤震荡行情 |
| **假信号多** | 增加确认条件（成交量、零轴位置） |

## 6. 适用场景

- ✅ 趋势明显的单边行情
- ✅ 中长线交易（日线、周线）
- ✅ 股票、ETF、期货交易
- ⚠️ 震荡行情需要额外过滤
- ❌ 超短线/高频交易不适用
