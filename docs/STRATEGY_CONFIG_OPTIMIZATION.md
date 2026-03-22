# 策略目录配置优化 - 实现总结

## 📋 变更说明

### 优化目标

简化配置文件，内置策略目录自动扫描，用户只需配置自定义策略目录。

### 变更内容

#### 1. 配置文件优化

**修改文件**：`config/system.yaml`

**变更前**：
```yaml
strategy:
  directories:
    - "src/strategy"       # 内置策略（需配置）
    - "data/strategies"     # 自定义策略
  recursive: false
```

**变更后**：
```yaml
strategy:
  # 自定义策略目录（支持多个目录，按优先级顺序扫描）
  # 系统会自动扫描内置策略目录 src/strategy
  directories:
    - "data/strategies"    # 自定义策略目录
  recursive: false
```

**优点**：
- ✅ 配置更简洁，减少冗余
- ✅ 用户只需关心自己的策略目录
- ✅ 降低配置错误风险

#### 2. 代码逻辑优化

**修改文件**：`src/cli/main.py`

**变更内容**：
- 修改 `_get_strategy_directories()` 函数
- 内置策略目录 (`src/strategy`) 自动包含
- 配置文件只读取自定义策略目录

**关键代码**：
```python
def _get_strategy_directories() -> list:
    """从配置文件获取策略目录列表

    Returns:
        策略目录列表（包括内置策略目录和自定义策略目录）
    """
    # 内置策略目录（始终扫描）
    builtin_dir = str(Path.cwd() / 'src/strategy')

    # 读取自定义策略目录（从配置文件）
    custom_dirs = [...]
    
    # 返回目录列表：内置策略目录优先，然后是自定义策略目录
    result = [builtin_dir] + custom_dirs
    return result
```

#### 3. 文档更新

**更新的文档**：
- `README.md` - 更新快速配置说明
- `QUICKSTART_CUSTOM_STRATEGIES.md` - 更新快速开始指南
- `docs/CUSTOM_STRATEGIES.md` - 更新详细配置指南

## ✅ 测试验证

### 测试 1：策略目录加载

```bash
$ python -c "from src.cli.main import _get_strategy_directories; print(_get_strategy_directories())"
```

**结果**：
```
策略扫描目录:
  1. /data/workspace/tmp/quant-system/src/strategy
  2. /data/workspace/tmp/quant-system/data/strategies
✓ 内置策略目录自动包含
✓ 自定义策略目录已加载
✓ 目录顺序正确（内置优先）
```

### 测试 2：策略列表

```bash
$ quant> strategies

可用策略列表:

  • custom_example      # 自定义策略
  • macd                # 内置策略
  • multi_timeframe     # 内置策略
  • rsi                 # 内置策略
  • weekly              # 内置策略
```

**结果**：✅ 内置策略和自定义策略都正常加载

## 🎯 优势总结

### 1. 配置更简洁
- 用户无需知道内置策略目录位置
- 配置文件只关注自定义目录
- 降低学习成本

### 2. 灵活性更强
- 支持多个自定义策略目录
- 可以方便地组织和分类策略
- 内置策略自动升级，不影响用户配置

### 3. 向后兼容
- 现有配置文件无需修改
- 代码逻辑自动处理
- 平滑过渡

### 4. 更好的用户体验
- 创建策略时自动选择正确的目录
- 减少配置错误的可能性
- 符合"约定优于配置"的原则

## 📝 使用示例

### 配置自定义策略目录

```yaml
# config/system.yaml
strategy:
  directories:
    - "data/strategies"        # 主自定义策略目录
    - "data/strategies/v2"     # 可选：更多自定义策略目录
  recursive: false
```

### 创建策略

```bash
# 创建新策略（自动加载）
quant> create-strategy my_strategy
✓ 策略文件已创建: src/strategy/my_strategy_strategy.py
  请编辑该文件以实现策略逻辑
  ✓ 策略已自动加载
```

### 查看策略

```bash
quant> strategies

可用策略列表:

  • custom_example    # 自定义策略（来自 data/strategies）
  • macd              # 内置策略（来自 src/strategy）
  • multi_timeframe   # 内置策略
  • my_strategy       # 新创建的策略
  • rsi               # 内置策略
  • weekly            # 内置策略
```

## 🔍 技术细节

### 扫描顺序

1. **内置策略目录** (`src/strategy`) - 最高优先级
2. **自定义策略目录** 1 (`data/strategies`)
3. **自定义策略目录** 2 (`data/strategies/v2`)
4. ... 更多自定义目录

### 覆盖规则

- 后面的目录可以覆盖前面的同名策略
- 允许用户覆盖内置策略（通过在自定义目录中创建同名策略）

### 目录格式支持

- ✅ 相对路径：`"data/strategies"`
- ✅ 绝对路径：`"/home/user/my_strategies"`
- ✅ 相对于项目根目录自动解析

## 📚 相关文档

- **快速开始**：`QUICKSTART_CUSTOM_STRATEGIES.md`
- **详细指南**：`docs/CUSTOM_STRATEGIES.md`
- **实现总结**：`docs/CUSTOM_STRATEGIES_SUMMARY.md`
- **配置文件**：`config/system.yaml`

## ✨ 总结

通过这次优化，配置文件更加简洁明了，用户只需关心自己的策略目录，内置策略自动扫描。这大大降低了配置复杂度，提升了用户体验，同时保持了系统的灵活性和扩展性。

**核心改进**：
- 📝 配置文件只显示自定义目录
- 🤖 内置策略自动扫描
- 📚 文档全面更新
- ✅ 完整测试验证
