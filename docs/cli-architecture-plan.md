# CLI 架构开发设计方案

## 1. 背景与目标

本文档用于统一当前项目的 CLI 与服务启动架构，明确以下核心目标：

1. 固化初始化顺序：**加载配置 -> 初始化引擎 -> 加载通知模块 -> 解析并执行策略**。
2. 规范策略配置文件组织与字段分层。
3. 约束命令行模式：**仅支持单策略操作**。
4. 支持服务模式：**可同时运行多策略**。
5. 给出模块调用链与后续重构建议，降低现有实现分裂带来的维护成本。

---

## 2. 初始化顺序设计（统一生命周期）

### 2.1 统一初始化阶段

所有运行入口（CLI 单次执行、服务常驻执行）统一遵循以下顺序：

1. **加载配置（Load Config）**
   - 读取系统配置 `config/default.yaml`
   - 读取策略配置 `src/strategy/configs/<strategy>.yaml`
   - 进行环境变量替换与配置校验
   - 生成最终运行配置 `RuntimeConfig`

2. **初始化引擎（Init Engine）**
   - 根据运行模式初始化执行引擎：
     - 实时/模拟：`TradingEngine`
     - 历史回测：`BacktestEngine`
   - 注入数据服务、执行器、风控管理器、事件总线

3. **加载通知模块（Init Notifier）**
   - 根据 `notification` 配置装配 `EmailNotifier / WebhookNotifier / CompositeNotifier`
   - 在事件总线注册通知订阅（如 `SIGNAL_GENERATED`、`ORDER_FILLED`）

4. **解析并执行策略（Resolve & Execute Strategy）**
   - 从策略注册表按名称创建策略实例
   - 调用策略初始化（参数校验、状态初始化）
   - 启动执行循环（分析/监控/回测/实盘）

### 2.2 统一生命周期接口建议

建议新增统一启动器接口：

- `Bootstrap.run(runtime_context)`
  - `load_config()`
  - `init_engine()`
  - `init_notifier()`
  - `run_strategy()`

通过统一启动器，避免不同命令路径出现“有通知无引擎”或“有引擎无通知”的不一致。

---

## 3. 策略配置文件组织

### 3.1 目录组织

```text
config/
  default.yaml                      # 系统级配置（日志、存储、默认行为）

src/strategy/configs/
  macd.yaml                         # 单策略配置（策略参数 + 运行参数）
  weekly.yaml
  multi_timeframe.yaml
```

### 3.2 配置分层约定

每个策略配置文件建议统一为以下顶层结构：

- `engine`: 执行模式、轮询间隔、交易时间窗
- `strategy`: 策略名称、参数、标的列表
- `risk`: 风控阈值
- `broker`: 交易执行参数（费用、滑点、初始资金）
- `data`: 数据源与缓存参数
- `notification`: 通知渠道与模板
- `backtest`: 回测区间与输出配置

### 3.3 组织规则

1. 文件名应与策略名一致（如 `strategy.name: macd` 对应 `macd.yaml`）。
2. 系统配置与策略配置分离：系统配置不承载策略参数。
3. CLI 参数只允许覆盖白名单字段（如 `symbols/mode/start/end`）。
4. 配置校验失败时快速失败，禁止带缺失字段运行。

---

## 4. 命令行模式限制：仅单策略操作

### 4.1 约束定义

CLI 模式仅允许单策略运行：

- 每次命令只能接收一个 `--strategy-config`
- 每次命令仅绑定一个 `strategy.name`
- 不在 CLI 进程内做多策略调度

### 4.2 约束原因

1. 交互体验清晰：输出、日志、告警与策略一一对应。
2. 运维风险可控：单次运行失败边界清晰，便于定位。
3. 降低参数组合复杂度：避免命令行层面的并发与状态管理。

### 4.3 参数建议

- 保留：`--strategy-config <path>`（单值）
- 拒绝：多次传入 `--strategy-config`
- 若检测到多策略参数，直接报错并提示使用服务模式。

---

## 5. 服务启动：支持多策略运行

### 5.1 多策略服务定义

服务模式（如 `service start`）允许同时加载多个策略配置，并由统一调度器管理：

- 一个服务进程可托管多个策略实例
- 每个策略拥有独立上下文（配置、状态、持仓视图、通知路由）
- 调度器统一驱动心跳、数据拉取、执行与监控

### 5.2 运行模型建议

- `StrategySupervisor`（监督器）
  - 生命周期管理：启动/停止/重启
  - 健康检查：策略级运行状态
- `MultiStrategyScheduler`（调度器）
  - 串行 tick + 策略隔离（初版）
  - 后续支持并发执行池（线程/协程）
- `ContextIsolation`（上下文隔离）
  - 每策略独立日志前缀、告警通道、运行快照

### 5.3 服务配置建议

新增 `config/service.yaml`：

```yaml
service:
  enabled: true
  strategies:
    - src/strategy/configs/macd.yaml
    - src/strategy/configs/weekly.yaml
  scheduler:
    interval_seconds: 300
    max_workers: 4
```

---

## 6. 模块调用链（设计态）

### 6.1 CLI 单策略调用链

```text
src/main.py
  -> cli/main.py (strategy command)
    -> Bootstrap.load_config()
    -> Bootstrap.init_engine()
    -> Bootstrap.init_notifier()
    -> Bootstrap.run_strategy()
      -> StrategyRegistry.create(name)
      -> Engine.run_once() / Engine.run_loop()
```

### 6.2 服务多策略调用链

```text
src/main.py
  -> cli/main.py (service start)
    -> ServiceBootstrap.load_service_config()
    -> StrategySupervisor.start_all()
      -> for each strategy_config:
         -> Bootstrap.load_config()
         -> Bootstrap.init_engine()
         -> Bootstrap.init_notifier()
         -> Bootstrap.run_strategy()
    -> MultiStrategyScheduler.loop()
```

### 6.3 事件与通知链

```text
Strategy.generate_signal()
  -> EventBus.emit(SIGNAL_GENERATED)
    -> RiskManager.check()
    -> Executor.submit_order()
    -> EventBus.emit(ORDER_FILLED / ORDER_REJECTED)
      -> Notifier.on_event()
        -> Email/Webhook send
```

---

## 7. 后续重构建议

### 7.1 架构收敛

1. 将遗留命令与统一命令收敛到同一启动器（Bootstrap）。
2. 将初始化步骤显式化，避免散落在命令函数内部。
3. 引入 `RuntimeContext` 作为跨模块依赖注入容器。

### 7.2 配置治理

1. 定义统一配置 Schema（建议使用 dataclass/pydantic）。
2. 统一风险字段命名，避免 `_pct` 与非 `_pct` 混用。
3. 增加配置 lint 检查（文件名与策略名一致、必填项完整）。

### 7.3 运行治理

1. CLI 与 Service 功能边界固定：CLI 单策略、Service 多策略。
2. 增加策略级运行指标：成功率、异常数、通知发送率。
3. 增加故障恢复机制：策略级重启、告警降噪、熔断保护。

### 7.4 兼容迁移建议

1. 第一步：新增 Bootstrap，不改变现有命令语义。
2. 第二步：命令逐步迁移到 Bootstrap。
3. 第三步：引入 Service 多策略调度器并灰度启用。
4. 第四步：移除重复初始化逻辑与遗留入口。

---

## 8. 验收标准

1. CLI 单策略命令全量通过，且拒绝多策略参数。
2. 服务模式可同时加载并运行多个策略。
3. 初始化日志完整体现四阶段顺序。
4. 配置错误在启动期即失败并输出明确错误信息。
5. 通知链路在策略信号与成交事件上可观测、可追踪。
