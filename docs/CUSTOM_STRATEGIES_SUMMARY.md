# 自定义策略功能 - 实现总结

## 实现的功能

### 1. 可配置策略目录

**配置文件**：`config/system.yaml`

```yaml
strategy:
  directories:
    - "src/strategy"      # 内置策略
    - "data/strategies"    # 自定义策略
  recursive: false
```

**特点**：
- 支持多个策略目录，按优先级扫描
- 可配置递归扫描子目录
- 向后兼容（如果不配置，默认扫描 `src/strategy`）

### 2. 自动策略加载

**实现位置**：`src/cli/main.py`

- `_get_strategy_directories()`: 从配置文件读取策略目录
- `_ensure_strategies_registered()`: 扫描并注册所有策略
- 全局标志 `_strategies_initialized`: 避免重复扫描

**优点**：
- 只扫描一次，避免重复加载
- 支持自动重载（`reload-strategies` 命令）
- 创建/删除策略后自动刷新列表

### 3. 创建的文件

#### 配置文件
- `config/system.yaml`: 添加策略目录配置

#### 示例策略
- `data/strategies/custom_example_strategy.py`: 双均线交叉策略示例

#### 文档
- `docs/CUSTOM_STRATEGIES.md`: 详细的配置和使用指南
- `docs/CUSTOM_STRATEGIES_SUMMARY.md`: 本实现总结文档

#### 示例代码
- `examples/custom_strategy_demo.py`: 演示如何使用自定义策略
- `test_custom_strategies.py`: 功能测试脚本

#### README 更新
- 添加"自定义策略"章节

## 测试结果

运行 `python test_custom_strategies.py`：

```
测试总结
============================================================
  配置文件加载: ✓ 通过
  策略发现: ✓ 通过
  自定义策略加载: ✓ 通过
  多目录扫描: ✓ 通过
  策略注册表: ✓ 通过

总计: 5/5 通过

🎉 所有测试通过！
```

## 使用方法

### 1. 基本使用

```bash
# 启动交互模式
python -m src.cli.main interactive

# 查看所有策略（包括自定义策略）
quant> strategies

# 创建新策略（会自动加载）
quant> create-strategy my_custom

# 重新加载策略
quant> reload-strategies
```

### 2. 添加自定义策略

```bash
# 在自定义目录创建策略文件
cat > data/strategies/my_custom_strategy.py << 'EOF'
"""
我的自定义策略
"""
from src.strategy.base import BaseStrategy, AnalysisResult, Signal

class MyCustomStrategy(BaseStrategy):
    name = "my_custom"

    def __init__(self, params=None, **kwargs):
        super().__init__(params=params, **kwargs)

    def calculate_indicators(self, data):
        # 计算指标
        return data

    def generate_signal(self, data, context):
        return Signal(action="hold", reason="无信号", confidence=0.0)

    def analyze_status(self, data, symbol):
        return AnalysisResult(symbol=symbol, status="测试", action="观望", reason="", confidence=0.0)
EOF

# 重新加载策略
python -m src.cli.main interactive
quant> reload-strategies
```

### 3. 使用自定义策略运行

```bash
# 回测
python -m src.cli.main backtest \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --symbols 000001.SZ \
  --strategy custom_example

# 分析
python -m src.cli.main analyze \
  --symbols 000001.SZ \
  --strategy custom_example \
  --days 30
```

## 架构优势

### 1. 代码和策略分离
- 系统代码在 `src/strategy/`
- 用户策略在 `data/strategies/`
- 便于独立管理和版本控制

### 2. 灵活的目录组织
```
data/strategies/
├── trend/              # 趋势策略
│   ├── ma_strategy.py
│   └── ema_strategy.py
├── momentum/           # 动量策略
│   ├── rsi_strategy.py
│   └── macd_strategy.py
└── mean_revert/       # 均值回归策略
    └── bollinger_strategy.py
```

### 3. 向后兼容
- 现有策略无需修改
- 配置文件默认值保持向后兼容
- 用户可以选择是否启用自定义目录

### 4. 性能优化
- 只扫描一次（全局标志）
- 避免重复注册
- 支持增量更新（`reload-strategies`）

## 注意事项

### 1. 命名约定
策略文件必须符合命名约定：
- `*_strategy.py` - 例如：`my_strategy.py`
- `strategy_*.py` - 例如：`strategy_custom.py`

### 2. 抽象方法实现
策略类必须实现所有抽象方法：
- `calculate_indicators(data: pd.DataFrame) -> pd.DataFrame`
- `generate_signal(data: pd.DataFrame, context: StrategyContext) -> Signal`
- `analyze_status(data: pd.DataFrame, symbol: str) -> AnalysisResult`

### 3. 策略类要求
- 继承 `BaseStrategy`
- 设置 `name` 属性（策略唯一标识符）
- `__init__` 方法签名：`def __init__(self, params=None, **kwargs)`

### 4. 配置文件路径
- 默认：`config/system.yaml`
- 可通过环境变量覆盖：`QUANT_DATA_CONFIG`

## 未来改进方向

### 1. 策略版本管理
- 支持策略版本号
- 支持策略升级和回滚

### 2. 策略依赖管理
- 声明策略依赖的模块
- 自动安装缺失的依赖

### 3. 策略市场
- 策略分享平台
- 策略评价和排名

### 4. 策略验证
- 自动化测试框架
- 策略性能基准测试

### 5. 策略配置
- 每个策略独立的配置文件
- 参数调优工具

## 总结

本次实现完整地支持了自定义策略功能，包括：

✅ 可配置的策略目录（支持多目录）
✅ 自动策略发现和注册
✅ 创建/删除策略自动刷新
✅ 示例策略和文档
✅ 功能测试和示例代码
✅ 向后兼容性保证

用户现在可以轻松地在 `data/strategies` 目录中添加自己的策略，与系统代码完全分离，实现更灵活的策略管理。
