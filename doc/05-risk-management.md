# 风险控制设计

## 1. 风控体系架构

```
事前风控              事中风控              事后风控
   │                    │                    │
   ▼                    ▼                    ▼
• 仓位控制           • 止损止盈           • 绩效评估
• 标的筛选           • 动态调仓           • 归因分析
• 信号过滤           • 回撤控制           • 参数优化
• 市场环境           • 滑点控制           • 策略迭代
```

## 2. 仓位管理

### 2.1 固定比例法

```python
def fixed_ratio_position(capital: float, risk_ratio: float = 0.02) -> float:
    """每次交易风险不超过总资金的 2%"""
    return capital * risk_ratio
```

### 2.2 凯利公式

```python
def kelly_position(win_rate: float, win_loss_ratio: float) -> float:
    """
    f* = p - (1-p)/b
    实际使用半凯利更保守
    """
    f = win_rate - (1 - win_rate) / win_loss_ratio
    return max(0, f * 0.5)
```

### 2.3 ATR 仓位法

```python
def atr_position(capital, atr, price, risk_pct=0.02, atr_mult=2):
    risk_amount = capital * risk_pct
    stop_distance = atr * atr_mult
    quantity = int(risk_amount / stop_distance / 100) * 100
    return quantity
```

## 3. 止损止盈策略

| 类型 | 方法 | 参数建议 |
|------|------|----------|
| 固定止损 | 入场价 × (1 - 5%) | 5-8% |
| ATR止损 | 入场价 - 2×ATR | 2-3倍ATR |
| 移动止损 | 最高价 × (1 - 5%) | 5-8% |
| 分批止盈 | 涨10%卖30%，涨20%卖30%，涨30%卖40% | - |

## 4. 回撤控制

| 指标 | 保守 | 稳健 | 激进 |
|------|------|------|------|
| 单日最大亏损 | 2% | 3% | 5% |
| 总最大回撤 | 10% | 15% | 25% |

## 5. 风控参数配置

| 风控项 | 保守 | 稳健 | 激进 |
|--------|------|------|------|
| 单票最大仓位 | 20% | 30% | 50% |
| 总仓位上限 | 60% | 80% | 100% |
| 单笔止损 | 3% | 5% | 8% |
| 单笔止盈 | 10% | 15% | 25% |

## 6. 市场环境过滤

- **牛市**（价格 > MA20 > MA60）：正常交易
- **熊市**（价格 < MA20 < MA60）：减仓或停止
- **震荡市**：降低仓位至 50%
