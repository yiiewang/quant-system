# 日志分离配置说明

## 概述

系统实现了简化的日志分离功能，只保留两种日志类型：
- **系统日志**：所有非策略相关的日志
- **策略日志**：按策略名称分别记录

## 日志分类

| 日志类型 | 文件格式 | 说明 |
|---------|---------|------|
| 系统日志 | `logs/system.log.YYYYMMDD` | 所有非策略日志（启动、配置、引擎、数据等） |
| 策略日志 | `logs/{策略名称}.log.YYYYMMDD` | 策略相关的日志（策略加载、信号生成等） |

## 配置文件

日志配置位于 `config/system.yaml`：

```yaml
# ==================== 日志配置 ====================
logging:
  # 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
  level: "INFO"
  # 日志目录
  log_dir: "logs"
  # 是否输出到控制台
  console_output: true
  # 保留的日志文件数量（天数）
  backup_count: 30
```

## 使用方式

### 1. 自动初始化

系统启动时自动根据配置文件初始化日志系统。无需手动调用日志初始化代码。

### 2. 系统日志使用

在非策略模块中使用标准日志记录器：

```python
import logging

# 获取日志记录器（使用模块名）
logger = logging.getLogger(__name__)

# 记录日志
logger.info("这是一条系统日志")
logger.debug("这是调试信息")
logger.warning("这是警告信息")
```

### 3. 策略日志使用

在策略中使用专用的策略日志记录器：

```python
from src.utils.logging_config import get_strategy_logger

class MyStrategy(BaseStrategy):
    def __init__(self, params=None):
        # 使用策略专用日志记录器
        self._strategy_logger = get_strategy_logger(self.name)
        self._strategy_logger.info("策略初始化")

    def generate_signal(self, data, context):
        self._strategy_logger.info("开始生成信号")
        # 策略逻辑
        self._strategy_logger.info(f"生成信号: {signal}")
```

## 日志格式

### 文件日志格式

```
%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

示例：
```
2026-03-19 10:39:23,182 - src.strategy.macd - INFO - 策略初始化
2026-03-19 10:39:23,182 - src.core.engine - INFO - 引擎启动
```

### 控制台日志格式

```
%(levelname)s - %(message)s
```

示例：
```
INFO - 策略初始化
INFO - 引擎启动
```

## 日志文件管理

### 文件命名规则

- **系统日志**：`logs/system.log.YYYYMMDD`
  - 示例：`logs/system.log.20260319`

- **策略日志**：`logs/{策略名称}.log.YYYYMMDD`
  - MACD 策略：`logs/macd.log.20260319`
  - RSI 策略：`logs/rsi.log.20260319`

### 日志滚动

- 单个日志文件最大 10MB
- 当文件大小超过限制时，自动创建新文件
- 保留最近 30 天的日志文件（可通过 `backup_count` 配置）

### 示例

```
logs/
├── system.log.20260319       # 今天的系统日志
├── system.log.20260318       # 昨天的系统日志
├── macd.log.20260319         # MACD策略今天的日志
├── macd.log.20260318         # MACD策略昨天的日志
├── rsi.log.20260319          # RSI策略今天的日志
└── rsi.log.20260318          # RSI策略昨天的日志
```

## 常见问题

### 1. 策略日志没有独立文件

**原因**：策略没有使用专用的日志记录器

**解决方法**：
```python
from src.utils.logging_config import get_strategy_logger

class MyStrategy(BaseStrategy):
    def __init__(self, params=None):
        self._strategy_logger = get_strategy_logger(self.name)
```

### 2. 日志文件不存在

**原因**：
- 日志目录没有创建权限
- 日志初始化失败

**解决方法**：
- 确保程序有权限创建 `logs/` 目录
- 检查日志初始化代码是否正确执行

### 3. 控制台没有日志输出

**原因**：配置文件中 `console_output: false`

**解决方法**：修改配置文件设置 `console_output: true`

## 最佳实践

1. **策略日志**：使用 `get_strategy_logger()` 获取策略专用日志记录器
   ```python
   from src.utils.logging_config import get_strategy_logger
   logger = get_strategy_logger('macd')
   ```

2. **系统日志**：使用标准日志记录器
   ```python
   logger = logging.getLogger(__name__)
   ```

3. **日志级别**：根据重要性选择合适的日志级别
   - DEBUG：详细的调试信息
   - INFO：一般信息（推荐默认级别）
   - WARNING：警告信息
   - ERROR：错误信息
   - CRITICAL：严重错误

4. **敏感信息**：避免在日志中记录敏感信息（密码、token 等）

## 示例代码

### 策略模块日志

```python
from src.utils.logging_config import get_strategy_logger

class MACDStrategy(BaseStrategy):
    name = "macd"
    version = "1.0.0"

    def __init__(self, params=None):
        # 使用策略专用日志记录器
        self._strategy_logger = get_strategy_logger(self.name)
        self._strategy_logger.info(f"MACD策略初始化 v{self.version}")
        self._strategy_logger.debug(f"策略参数: {self.params}")

    def generate_signal(self, data, context):
        self._strategy_logger.info("开始生成信号")
        # 策略逻辑
        self._strategy_logger.info(f"生成信号: {signal.type}")
        return signal
```

### 系统模块日志

```python
import logging

logger = logging.getLogger(__name__)

class MarketDataService:
    def __init__(self):
        logger.info("数据服务初始化")

    def get_data(self, symbol):
        logger.info(f"获取数据: {symbol}")
        try:
            data = self._fetch_data(symbol)
            logger.debug(f"数据获取成功: {len(data)} 条")
            return data
        except Exception as e:
            logger.error(f"数据获取失败: {e}")
            raise
```

## 更新日志

- 2026-03-19: 简化为系统日志和策略日志两种类型，按日期和策略名称命名
