# 统一策略目录架构 - 实现总结

## 📋 变更说明

### 核心改动

**移除"内置策略"概念**，所有策略都存放在用户配置的策略目录中（默认 `data/strategies`）。

### 架构变更

**变更前**：
- 内置策略：`src/strategy/` 目录
- 自定义策略：用户配置的目录
- 需要在配置文件中同时指定两个目录

**变更后**：
- 统一策略：所有策略都在配置的目录中
- 无需区分内置/自定义
- 配置文件只需指定策略目录

## 🔧 具体修改

### 1. 策略文件移动

**移动的文件**：
- `src/strategy/macd.py` → `data/strategies/macd_strategy.py`
- `src/strategy/macd_multi_timeframe.py` → `data/strategies/macd_multi_timeframe_strategy.py`
- `src/strategy/macd_weekly.py` → `data/strategies/macd_weekly_strategy.py`
- `src/strategy/rsi_strategy.py` → `data/strategies/rsi_strategy.py`（已在正确位置）

**命名约定**：
- 所有策略文件必须符合命名约定：`*_strategy.py` 或 `strategy_*.py`

### 2. 配置文件更新

**修改文件**：`config/system.yaml`

```yaml
strategy:
  # 策略目录（支持多个目录，按优先级顺序扫描）
  # 所有策略文件都应放在这些目录中
  directories:
    - "data/strategies"
  recursive: false
```

### 3. 代码逻辑更新

#### src/cli/main.py

**修改 `_get_strategy_directories()` 函数**：
- 移除内置策略目录的自动扫描
- 只从配置文件读取策略目录

```python
def _get_strategy_directories() -> list:
    """从配置文件获取策略目录列表"""
    # 直接从配置文件读取，不添加内置目录
    strategy_dirs = config.get('strategy', {}).get('directories', ['data/strategies'])
    # ... 处理路径并返回
```

**修改 `handle_create_strategy()` 函数**：
- 创建策略文件到配置的第一个策略目录
- 修复策略模板的 `__init__` 方法参数

**修改 `handle_delete_strategy()` 函数**：
- 在所有策略目录中查找策略文件
- 支持多目录搜索

#### src/strategy/__init__.py

**移除内置策略导入和注册**：
- 删除 `from .macd import MACDStrategy` 等导入
- 删除策略注册逻辑
- 简化为只导出基础类和工具

### 4. 策略文件导入修复

修改移动的策略文件，使用绝对导入：
```python
# 变更前（相对导入）
from .base import BaseStrategy

# 变更后（绝对导入）
from src.strategy.base import BaseStrategy
```

## ✅ 测试验证

### 测试 1：策略目录扫描

```bash
$ python verify_unified_strategies.py

✓ data/strategies/: 5 个策略文件
  - custom_example_strategy.py
  - macd_multi_timeframe_strategy.py
  - macd_strategy.py
  - macd_weekly_strategy.py
  - rsi_strategy.py
✓ src/strategy/: 无策略文件（仅基础文件）
```

### 测试 2：策略列表

```bash
$ quant> strategies

可用策略列表:

  • MACD
  • MultiTimeframeMACD
  • WeeklyMACD
  • custom_example
  • rsi
```

### 测试 3：创建策略

```bash
$ quant> create-strategy my_strategy
✓ 策略文件已创建: /data/workspace/tmp/quant-system/data/strategies/my_strategy_strategy.py
  请编辑该文件以实现策略逻辑
  ✓ 策略已自动加载
```

### 测试 4：删除策略

```bash
$ quant> delete-strategy my_strategy
✓ 策略已禁用: .../data/strategies/my_strategy_strategy.py -> .../data/strategies/my_strategy_strategy.py.disabled
  如需恢复，重命名回原文件即可
  ✓ 策略列表已更新
```

## 🎯 核心优势

### 1. 架构简化
- ✅ 无需区分内置/自定义策略
- ✅ 统一的策略管理方式
- ✅ 降低学习和维护成本

### 2. 配置清晰
- ✅ 配置文件只关注策略目录
- ✅ 用户完全控制策略位置
- ✅ 支持多目录灵活组织

### 3. 易于扩展
- ✅ 可以按类型、版本等分类策略
- ✅ 方便团队协作
- ✅ 策略文件集中管理

### 4. 向后兼容
- ✅ 配置文件结构保持一致
- ✅ 策略接口无变化
- ✅ 现有功能正常工作

## 📚 文档更新

### 更新的文档

1. **README.md** - 更新策略管理说明
2. **QUICKSTART_CUSTOM_STRATEGIES.md** - 更新快速开始指南
3. **docs/CUSTOM_STRATEGIES.md** - 更新详细配置指南
4. **docs/STRATEGY_CONFIG_OPTIMIZATION.md** - （已废弃）
5. **docs/UNIFIED_STRATEGIES.md** - 新增：统一策略架构总结

### 新增文档

- `verify_unified_strategies.py` - 验证脚本
- `docs/UNIFIED_STRATEGIES.md` - 本文档

## 🔍 技术细节

### 策略命名约定

所有策略文件必须符合以下命名约定之一：
- `*_strategy.py` - 例如：`my_strategy.py`
- `strategy_*.py` - 例如：`strategy_custom.py`

### 策略文件结构

```
data/strategies/
├── custom_example_strategy.py     # 示例策略
├── macd_strategy.py             # MACD 策略
├── macd_multi_timeframe_strategy.py  # 多周期 MACD
├── macd_weekly_strategy.py      # 周线 MACD
└── rsi_strategy.py              # RSI 策略
```

### src/strategy 目录结构

```
src/strategy/
├── __init__.py      # 策略模块入口（仅基础类）
├── base.py         # 策略基类
├── loader.py       # 策略加载器
├── registry.py     # 策略注册表
└── configs/        # 策略配置文件
```

## 🚀 使用示例

### 基本使用

```bash
# 启动交互模式
python -m src.cli.main interactive

# 查看所有策略
quant> strategies

# 创建新策略
quant> create-strategy my_strategy

# 使用策略分析
quant> analyze 000001.SZ --strategy macd --days 30

# 删除策略
quant> delete-strategy my_strategy
```

### 多目录配置

```yaml
# config/system.yaml
strategy:
  directories:
    - "data/strategies"          # 主策略目录
    - "data/strategies/v2"       # 其他策略目录
  recursive: false
```

## ✨ 总结

通过这次重大架构调整，系统策略管理变得更加简洁和统一：

1. **统一管理** - 所有策略都在配置目录中，无内置概念
2. **配置清晰** - 用户只需关心自己的策略目录
3. **易于扩展** - 支持多目录、分类组织
4. **向后兼容** - 接口保持一致，迁移成本低

所有策略文件都按照统一的命名约定和结构组织，便于用户理解和维护。
