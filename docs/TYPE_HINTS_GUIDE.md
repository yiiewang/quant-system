# 类型注解指南

## 📚 概述

本文档提供 quant-system 项目的类型注解规范和最佳实践。

---

## 🎯 目标

- 提升代码可读性
- 增强 IDE 支持（自动补全、类型检查）
- 减少运行时错误
- 提高代码质量

---

## 📦 类型注解工具

### 1. 基础类型别名

```python
from src.utils.type_hints import (
    Number,      # Union[int, float, Decimal]
    Symbol,      # str - 股票代码
    DateStr,     # str - 日期字符串
    Price,       # float - 价格
    Quantity,    # int - 数量
    DataFrame,   # pd.DataFrame
    Series,      # pd.Series
)

# 使用示例
def process_bar(
    symbol: Symbol,
    price: Price,
    quantity: Quantity
) -> DataFrame:
    ...
```

### 2. Result 类型

用于函数返回值，支持成功和错误状态：

```python
from src.utils.type_hints import Result

def divide(a: float, b: float) -> Result[float]:
    """安全除法"""
    if b == 0:
        return Result.error("除数不能为 0")
    return Result.success(a / b)

# 使用
result = divide(10, 2)
if result.is_success():
    print(f"结果: {result.value}")
else:
    print(f"错误: {result.error}")

# 或使用 unwrap
value = result.unwrap(default=0.0)
```

### 3. 类型检查装饰器

运行时类型检查：

```python
from src.utils.type_hints import enforce_types

@enforce_types
def process_data(
    symbol: str,
    prices: List[float]
) -> Dict[str, float]:
    return {
        'symbol': symbol,
        'avg': sum(prices) / len(prices)
    }

# 正确调用
result = process_data("AAPL", [100.0, 200.0, 300.0])

# 错误调用（会抛出 TypeError）
result = process_data(123, [100, 200])  # 参数类型错误
```

### 4. DataFrame 验证

```python
from src.utils.type_hints import validate_dataframe

def process_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """处理 OHLCV 数据"""
    if not validate_dataframe(
        df,
        required_columns=['symbol', 'date', 'close'],
        column_types={'symbol': str, 'date': str, 'close': float}
    ):
        raise ValueError("DataFrame 结构不符合要求")
    
    # 处理逻辑
    ...
```

---

## 📐 类型注解规范

### 1. 函数参数和返回值

```python
# ✅ 推荐
def calculate_ma(
    prices: List[float],
    window: int = 20
) -> List[float]:
    """计算移动平均线"""
    ...

# ❌ 不推荐
def calculate_ma(prices, window=20):
    ...
```

### 2. 可选参数

```python
from typing import Optional

# ✅ 推荐
def get_data(
    symbol: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> DataFrame:
    ...

# ❌ 不推荐
def get_data(symbol, start_date=None, end_date=None):
    ...
```

### 3. 联合类型

```python
from typing import Union

# ✅ 推荐
def process_value(value: Union[int, float, str]) -> float:
    ...

# 使用类型别名更清晰
from src.utils.type_hints import Number

def process_value(value: Number) -> float:
    ...
```

### 4. 泛型类型

```python
from typing import List, Dict, Tuple, Generic, TypeVar

# 列表
def process_symbols(symbols: List[str]) -> Dict[str, DataFrame]:
    ...

# 字典
def get_prices(data: Dict[str, List[float]]) -> Dict[str, float]:
    ...

# 元组
def get_ohlcv(symbol: str) -> Tuple[float, float, float, float, int]:
    """返回 (open, high, low, close, volume)"""
    ...
```

### 5. Callable 类型

```python
from typing import Callable

# 函数类型
EventHandler = Callable[[Event], None]

def register_handler(
    event_type: str,
    handler: EventHandler
) -> None:
    ...

# 带返回值的函数
Validator = Callable[[Any], bool]

def validate_data(
    data: dict,
    validator: Validator
) -> bool:
    ...
```

### 6. Protocol（协议）

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class DataProvider(Protocol):
    """数据提供者协议"""
    
    def fetch(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> DataFrame:
        ...

# 使用
def backtest(
    provider: DataProvider,
    strategy: Strategy
) -> Dict[str, Any]:
    # provider 必须实现 fetch 方法
    data = provider.fetch(symbol, start, end)
    ...
```

---

## 🔍 类型检查工具

### 1. mypy 配置

在 `pyproject.toml` 中已配置：

```toml
[tool.mypy]
python_version = "3.9"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true
strict_equality = true
ignore_missing_imports = true
```

### 2. 运行类型检查

```bash
# 检查整个项目
mypy src/

# 检查单个文件
mypy src/core/engine.py

# 生成报告
mypy src/ --html-report mypy-report/
```

### 3. 常见问题修复

#### 问题 1: 缺少类型注解

```python
# ❌ 错误
def process_data(data):
    return data['value']

# ✅ 修复
def process_data(data: Dict[str, Any]) -> Any:
    return data['value']
```

#### 问题 2: Any 类型过多

```python
# ❌ 不推荐
def process(value: Any) -> Any:
    ...

# ✅ 推荐
def process(value: Union[int, float]) -> float:
    ...
```

#### 问题 3: 忽略 None 检查

```python
# ❌ 错误
def get_name(user: Optional[dict]) -> str:
    return user['name']  # user 可能是 None

# ✅ 修复
def get_name(user: Optional[dict]) -> str:
    if user is None:
        return ""
    return user['name']
```

---

## 📋 类型注解检查清单

- [ ] 所有公共函数都有参数类型注解
- [ ] 所有公共函数都有返回值类型注解
- [ ] 使用 `Optional[T]` 而不是 `T | None`（Python 3.9 兼容）
- [ ] 使用类型别名提高可读性
- [ ] 复杂类型使用 Protocol 而不是抽象基类
- [ ] 关键函数使用 `@enforce_types` 装饰器
- [ ] DataFrame 验证使用 `validate_dataframe`
- [ ] 函数返回值考虑使用 `Result[T]`
- [ ] mypy 检查无错误
- [ ] IDE 类型提示正常工作

---

## 🎓 最佳实践

### 1. 渐进式类型注解

对于大型项目，可以渐进式添加类型注解：

```python
# 第一步：添加基础类型
def process(symbol: str, data: dict) -> dict:
    ...

# 第二步：细化类型
from typing import TypedDict

class BarData(TypedDict):
    open: float
    high: float
    low: float
    close: float
    volume: int

def process(symbol: str, data: BarData) -> Dict[str, float]:
    ...
```

### 2. 使用 TypeGuard（Python 3.10+）

```python
from typing import TypeGuard

def is_valid_bar(data: dict) -> TypeGuard[BarData]:
    """检查字典是否为有效的 BarData"""
    required_keys = {'open', 'high', 'low', 'close', 'volume'}
    return all(key in data for key in required_keys)

def process_bar(data: dict) -> None:
    if is_valid_bar(data):
        # data 现在被识别为 BarData 类型
        print(data['close'])
```

### 3. 类型注解与文档结合

```python
def calculate_sharpe_ratio(
    returns: List[float],
    risk_free_rate: float = 0.02
) -> float:
    """
    计算夏普比率
    
    Args:
        returns: 收益率序列，为小数形式（如 0.05 表示 5%）
        risk_free_rate: 无风险利率，默认 2%
    
    Returns:
        夏普比率
    
    Raises:
        ValueError: 如果收益序列为空或包含无效值
    
    Example:
        >>> returns = [0.05, -0.02, 0.08, 0.03]
        >>> sharpe = calculate_sharpe_ratio(returns)
    """
    if not returns:
        raise ValueError("收益序列不能为空")
    
    # 计算逻辑
    ...
```

---

## 📚 参考资料

- [Python 类型注解官方文档](https://docs.python.org/zh-cn/3/library/typing.html)
- [mypy 官方文档](https://mypy.readthedocs.io/)
- [PEP 484 - Type Hints](https://www.python.org/dev/peps/pep-0484/)
- [PEP 526 - Syntax for Variable Annotations](https://www.python.org/dev/peps/pep-0526/)

---

**最后更新**: 2026-03-20
