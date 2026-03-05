# 系统架构设计

## 1. 总体架构

```mermaid
graph TB
    subgraph "用户接口层"
        CLI[CLI命令行]
    end
    
    subgraph "应用层"
        RUNNER[应用运行器]
    end
    
    subgraph "核心层"
        ENGINE[交易引擎]
        EVENT[事件总线]
    end
    
    subgraph "业务模块层"
        STRATEGY[策略模块]
        RISK[风控模块]
        BROKER[执行模块]
        DATA[数据模块]
    end
    
    subgraph "基础设施层"
        CONFIG[配置管理]
        METRICS[指标计算]
        STORAGE[(数据存储)]
    end
    
    CLI --> RUNNER
    RUNNER --> ENGINE
    ENGINE --> EVENT
    ENGINE --> STRATEGY
    ENGINE --> RISK
    ENGINE --> BROKER
    ENGINE --> DATA
    
    STRATEGY --> CONFIG
    RISK --> CONFIG
    BROKER --> CONFIG
    DATA --> CONFIG
    
    ENGINE --> METRICS
    METRICS --> STORAGE
    DATA --> STORAGE
    
    style CLI fill:#e1f5fe
    style RUNNER fill:#f3e5f5
    style ENGINE fill:#e8f5e8
    style EVENT fill:#fff3e0
    style STRATEGY fill:#fce4ec
    style RISK fill:#fce4ec
    style BROKER fill:#fce4ec
    style DATA fill:#fce4ec
    style CONFIG fill:#f1f8e9
    style METRICS fill:#f1f8e9
    style STORAGE fill:#e0f2f1
```

## 2. 核心模块

### 2.1 交易引擎

```mermaid
flowchart LR
    subgraph "交易引擎核心流程"
        A[市场数据] --> B[策略分析]
        B --> C[信号生成]
        C --> D[风控检查]
        D --> E[订单执行]
        E --> F[结果记录]
        F --> A
    end
    
    subgraph "管理组件"
        G[策略管理]
        H[风险控制]
        I[事件分发]
    end
    
    B -.-> G
    D -.-> H
    C -.-> I
```

### 2.2 数据模型

```mermaid
classDiagram
    class Signal {
        +str symbol
        +SignalAction action
        +float price
        +datetime timestamp
        +str strategy
        +float confidence
    }
    
    class Order {
        +str symbol
        +OrderAction action
        +int quantity
        +float price
        +OrderType order_type
        +OrderStatus status
    }
    
    class Position {
        +str symbol
        +int quantity
        +float avg_cost
        +float market_value
        +float unrealized_pnl
    }
    
    class Portfolio {
        +float total_value
        +float cash
        +Dict[str, Position] positions
        +float total_pnl
    }
    
    class Trade {
        +str symbol
        +str order_id
        +int quantity
        +float price
        +datetime timestamp
        +float commission
    }
    
    Signal --> Order : 转换
    Order --> Trade : 成交
    Trade --> Position : 更新
    Position --> Portfolio : 汇总
```

## 3. 业务模块接口

### 3.1 策略模块

```mermaid
classDiagram
    class BaseStrategy {
        <<abstract>>
        +calculate_indicators()
        +generate_signal()
        +analyze_status()
    }
    
    class MACDStrategy {
        +fast_period: int
        +slow_period: int
        +signal_period: int
        +calculate_indicators()
        +generate_signal()
    }
    
    class WeeklyStrategy {
        +resample_to_weekly()
        +calculate_weekly_macd()
        +generate_signal()
    }
    
    class MultiTimeframeStrategy {
        +daily_strategy: MACDStrategy
        +weekly_strategy: WeeklyStrategy
        +check_alignment()
        +generate_signal()
    }
    
    BaseStrategy <|-- MACDStrategy
    BaseStrategy <|-- WeeklyStrategy
    BaseStrategy <|-- MultiTimeframeStrategy
    MultiTimeframeStrategy --> MACDStrategy
    MultiTimeframeStrategy --> WeeklyStrategy
```

### 3.2 执行器模块

```mermaid
classDiagram
    class BaseExecutor {
        <<abstract>>
        +submit_order()
        +cancel_order()
        +get_position()
        +get_account()
    }
    
    class SimulatedExecutor {
        +commission_rate: float
        +slippage_rate: float
        +simulate_execution()
        +calculate_commission()
    }
    
    BaseExecutor <|-- SimulatedExecutor
```

### 3.3 风控模块

```mermaid
flowchart TD
    A[交易信号] --> B{仓位检查}
    B -->|通过| C{风险检查}
    B -->|拒绝| D[拒绝信号]
    C -->|通过| E{单票限制}
    C -->|拒绝| D
    E -->|通过| F{总仓位}
    E -->|拒绝| D
    F -->|通过| G[允许交易]
    F -->|拒绝| D
    
    subgraph "风控规则"
        H[单票最大30%]
        I[总仓位最大80%]
        J[最大连续亏损3次]
        K[最大日亏损5%]
    end
    
    B --> H
    C --> J
    E --> K
    F --> I
```

## 4. 数据流架构

### 4.1 回测流程

```mermaid
sequenceDiagram
    participant CLI
    participant Runner
    participant Engine
    participant Strategy
    participant Risk
    participant Broker
    participant Data
    participant Metrics
    
    CLI->>Runner: 启动回测
    Runner->>Engine: 初始化引擎
    Engine->>Data: 加载历史数据
    Data-->>Engine: 返回数据
    
    loop 每个交易日
        Engine->>Strategy: 生成信号
        Strategy-->>Engine: 返回信号
        Engine->>Risk: 风控检查
        Risk-->>Engine: 检查结果
        alt 风控通过
            Engine->>Broker: 执行订单
            Broker-->>Engine: 成交记录
        end
    end
    
    Engine->>Metrics: 计算指标
    Metrics-->>Engine: 返回结果
    Engine-->>Runner: 回测结果
    Runner-->>CLI: 输出报告
```

### 4.2 实时监控流程

```mermaid
sequenceDiagram
    participant Market
    participant Data
    participant Engine
    participant Strategy
    participant Risk
    participant Broker
    participant Notification
    
    loop 实时数据推送
        Market->>Data: 新的市场数据
        Data->>Engine: 数据更新事件
        Engine->>Strategy: 策略分析
        Strategy-->>Engine: 交易信号
        Engine->>Risk: 风控检查
        Risk-->>Engine: 检查通过
        Engine->>Broker: 执行订单
        Broker-->>Engine: 执行结果
        Engine->>Notification: 发送通知
    end
```

## 5. 配置管理

### 5.1 配置层次结构

```mermaid
graph LR
    subgraph "配置文件"
        A[default.yaml<br/>系统默认配置]
        B[macd.yaml<br/>策略配置]
        C[weekly.yaml<br/>周线配置]
    end
    
    subgraph "配置优先级"
        D[命令行参数<br/>最高优先级]
        E[环境变量<br/>中等优先级]
        F[配置文件<br/>默认优先级]
    end
    
    subgraph "配置管理器"
        G[配置加载]
        H[配置验证]
        I[配置合并]
    end
    
    A --> G
    B --> G
    C --> G
    D --> I
    E --> I
    F --> I
    G --> H
    H --> I
```

## 6. 事件驱动架构

### 6.1 事件类型和流向

```mermaid
flowchart LR
    subgraph "事件源"
        A[市场数据更新]
        B[策略信号]
        C[订单状态]
        D[执行结果]
        E[风控事件]
    end
    
    subgraph "事件总线"
        EVENT[EventBus]
    end
    
    subgraph "事件订阅者"
        F[策略模块]
        G[风控模块]
        H[执行模块]
        I[监控模块]
        J[通知模块]
    end
    
    A --> EVENT
    B --> EVENT
    C --> EVENT
    D --> EVENT
    E --> EVENT
    
    EVENT --> F
    EVENT --> G
    EVENT --> H
    EVENT --> I
    EVENT --> J
```

## 7. 性能优化

### 7.1 缓存策略

```mermaid
flowchart TD
    A[数据请求] --> B{缓存检查}
    B -->|命中| C[返回缓存]
    B -->|未命中| D[获取数据]
    D --> E[更新缓存]
    E --> F[返回数据]
    
    subgraph "缓存类型"
        G[市场数据缓存]
        H[技术指标缓存]
        I[策略状态缓存]
    end
    
    B --> G
    B --> H
    B --> I
```

### 7.2 并发处理

```mermaid
graph TB
    subgraph "单线程处理"
        A[顺序处理<br/>简单但慢]
    end
    
    subgraph "多线程处理"
        B[并行策略计算]
        C[并行数据处理]
        D[并行风险检查]
    end
    
    subgraph "异步处理"
        E[异步事件处理]
        F[异步IO操作]
        G[异步通知发送]
    end
    
    A --> B
    B --> E
```

## 8. 安全设计

### 8.1 多层安全检查

```mermaid
flowchart TD
    A[交易请求] --> B[身份验证]
    B --> C[权限检查]
    C --> D[参数验证]
    D --> E[业务规则检查]
    E --> F[风险控制]
    F --> G[执行限制]
    G --> H[审计日志]
    H --> I[执行交易]
    
    subgraph "安全策略"
        J[访问控制]
        K[数据加密]
        L[操作审计]
        M[异常监控]
    end
    
    B --> J
    C --> K
    H --> L
    F --> M
```

这种 mermaid 图表化的架构设计提供了清晰的视觉表示，便于理解和维护系统的整体结构。