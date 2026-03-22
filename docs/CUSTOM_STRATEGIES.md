# 策略配置指南

## 概述

所有策略文件都存放在用户配置的策略目录中。系统通过配置文件指定策略目录位置，灵活管理策略文件。

**核心特点**：
- **灵活配置**：支持多个策略目录
- **独立管理**：策略文件与系统代码分离
- **版本控制友好**：自定义策略可以独立管理

## 配置方法

### 1. 修改配置文件

编辑 `config/system.yaml`，在 `strategy` 节点下配置策略目录：

```yaml
# ==================== 策略配置 ====================
strategy:
  # 策略目录（支持多个目录，按优先级顺序扫描）
  directories:
    - "data/strategies"        # 策略目录
  # 是否递归扫描子目录
  recursive: false
```

### 2. 创建策略目录

```bash
# 创建目录（如果不存在）
mkdir -p data/strategies
```

### 3. 在目录中添加策略文件

在 `data/strategies` 目录中创建策略文件，文件名需符合命名约定：

- `*_strategy.py` - 例如：`my_custom_strategy.py`
- `strategy_*.py` - 例如：`strategy_custom.py`

**示例策略文件**：
- `data/strategies/macd.py` - MACD 策略
- `data/strategies/rsi_strategy.py` - RSI 策略
- `data/strategies/custom_example_strategy.py` - 示例策略

## 策略目录扫描规则

### 命名约定

策略文件必须符合以下命名约定之一：

- 文件名以 `_strategy.py` 结尾
- 文件名以 `strategy_` 开头

**示例**：
- ✅ `my_strategy.py`
- ✅ `strategy_macd.py`
- ✅ `custom_test_strategy.py`
- ❌ `my_strategy.py.txt`
- ❌ `strategy.py`

### 扫描顺序

系统按照 `config/system.yaml` 中配置的目录顺序扫描，后面的目录可以覆盖前面的同名策略。

**示例配置**：
```yaml
directories:
  - "data/strategies"     # 主策略目录
  - "data/strategies/v2"  # 其他策略目录
```

**覆盖规则**：
- 多个目录之间，后面的可以覆盖前面的同名策略
- 如果 `data/strategies` 和 `data/strategies/v2` 都有名为 `macd` 的策略，`v2` 中的策略会生效

### 递归扫描

设置 `recursive: true` 可以递归扫描子目录：

```yaml
strategy:
  directories:
    - "src/strategy"
    - "data/strategies"
  recursive: true  # 递归扫描子目录
```

这样可以在子目录中组织策略：

```
data/strategies/
├── trend/
│   ├── ma_strategy.py
│   └── custom_trend_strategy.py
└── momentum/
    ├── rsi_strategy.py
    └── macd_strategy.py
```

## 策略类要求

策略类必须：

1. **继承 `BaseStrategy`**
2. **实现所有抽象方法**：
   - `calculate_indicators(data: pd.DataFrame) -> pd.DataFrame`
   - `generate_signal(data: pd.DataFrame, context: StrategyContext) -> Signal`
   - `analyze_status(data: pd.DataFrame, symbol: str) -> AnalysisResult`
3. **设置 `name` 属性**：策略的唯一标识符

**示例**：

```python
from src.strategy.base import BaseStrategy, AnalysisResult, Signal
from src.core.models import StrategyContext

class MyCustomStrategy(BaseStrategy):
    """我的自定义策略"""

    name = "my_custom"  # 必须设置

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.params = {"param1": 10}

    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        # 计算指标
        return data

    def generate_signal(self, data: pd.DataFrame, context: StrategyContext) -> Signal:
        # 生成信号
        return Signal(action="hold", reason="无信号", confidence=0.0)

    def analyze_status(self, data: pd.DataFrame, symbol: str) -> AnalysisResult:
        # 分析状态
        return AnalysisResult(symbol=symbol, status="测试", action="观望", reason="", confidence=0.0)
```

## 使用交互式命令

在交互式模式中，系统会自动扫描所有配置的策略目录：

```bash
python -m src.cli.main interactive

# 查看所有可用策略（包括自定义策略）
quant> strategies

# 创建策略（会根据配置创建到 src/strategy）
quant> create-strategy my_custom

# 重新加载策略（修改策略文件后使用）
quant> reload-strategies
```

## 版本控制

### Git 忽略规则

默认配置下，整个 `data/` 目录会被 Git 忽略（见 `.gitignore`）。

**如果需要追踪自定义策略**，可以选择以下方案之一：

#### 方案 1：添加到项目根目录（推荐用于开源项目）

```bash
# 在项目根目录创建 strategies 目录
mkdir -p strategies

# 修改配置文件
# config/system.yaml
strategy:
  directories:
    - "src/strategy"
    - "strategies"  # 追踪的策略目录
```

然后在 `.gitignore` 中添加：
```
# 忽略 data/ 但保留 strategies/
/data/
!/strategies/
```

#### 方案 2：使用子模块

```bash
# 在 data/strategies 中使用 git submodule
cd data/strategies
git submodule add <your-strategies-repo> custom
```

#### 方案 3：本地使用（适合个人项目）

直接使用 `data/strategies` 目录，不提交到 Git，适合本地开发。

## 故障排查

### 问题：自定义策略没有出现在列表中

**可能原因**：
1. 文件名不符合命名约定
2. 策略类未实现所有抽象方法
3. 类被 `inspect.isabstract()` 判定为抽象类
4. 配置文件路径错误

**排查步骤**：
```bash
# 1. 检查文件名
ls -la data/strategies/

# 2. 检查配置
cat config/system.yaml | grep -A 5 "strategy:"

# 3. 启用调试日志
python -m src.cli.main interactive --verbose
```

### 问题：重复注册警告

如果出现类似警告：
```
WARNING:src.strategy.registry:策略 'my_strategy' 已存在，将被覆盖
```

说明有多个目录中存在同名策略。可以：
- 删除或重命名重复的策略
- 调整目录扫描顺序

## 最佳实践

1. **目录组织**：按策略类型分类存放
   ```
   data/strategies/
   ├── trend/         # 趋势策略
   ├── momentum/      # 动量策略
   └── mean_revert/  # 均值回归策略
   ```

2. **命名规范**：使用描述性的策略名称
   - ✅ `ema_crossover_strategy.py`
   - ❌ `test1.py`

3. **文档**：在策略文件头部添加详细的说明
   ```python
   """
   EMA Crossover Strategy
   Author: Your Name
   Version: 1.0.0
   Description: 基于指数移动平均线的交叉策略
   """
   ```

4. **测试**：为策略编写单元测试
   ```python
   # tests/test_custom_strategies.py
   def test_my_custom_strategy():
       strategy = MyCustomStrategy()
       # 测试逻辑...
   ```
