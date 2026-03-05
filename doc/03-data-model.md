# 数据模型设计

## 1. 数据库 ER 图

```
┌────────────────────┐       ┌────────────────────┐
│      symbols       │       │      klines        │
├────────────────────┤       ├────────────────────┤
│ id          PK     │       │ id          PK     │
│ code        UK     │◄──────│ symbol_id   FK     │
│ name               │       │ timeframe          │
│ exchange           │       │ open_time          │
│ market             │       │ open               │
│ sector             │       │ high               │
│ is_active          │       │ low                │
│ created_at         │       │ close              │
│ updated_at         │       │ volume             │
└────────────────────┘       │ amount             │
         │                   │ created_at         │
         │                   └────────────────────┘
         │
         │                   ┌────────────────────┐
         │                   │     positions      │
         │                   ├────────────────────┤
         └──────────────────►│ id          PK     │
                             │ symbol_id   FK     │
                             │ account_id  FK     │
                             │ quantity           │
                             │ avg_price          │
                             │ market_value       │
                             │ unrealized_pnl     │
                             │ created_at         │
                             │ updated_at         │
                             └────────────────────┘

┌────────────────────┐       ┌────────────────────┐
│     accounts       │       │      orders        │
├────────────────────┤       ├────────────────────┤
│ id          PK     │◄──────│ id          PK     │
│ name               │       │ account_id  FK     │
│ initial_capital    │       │ symbol_id   FK     │
│ current_capital    │       │ order_type         │
│ total_value        │       │ side               │
│ realized_pnl       │       │ quantity           │
│ is_active          │       │ price              │
│ created_at         │       │ stop_price         │
│ updated_at         │       │ status             │
└────────────────────┘       │ filled_qty         │
                             │ filled_price       │
                             │ commission         │
                             │ created_at         │
                             │ updated_at         │
                             └────────────────────┘

┌────────────────────┐       ┌────────────────────┐
│      trades        │       │     signals        │
├────────────────────┤       ├────────────────────┤
│ id          PK     │       │ id          PK     │
│ order_id    FK     │       │ strategy_id FK     │
│ symbol_id   FK     │       │ symbol_id   FK     │
│ account_id  FK     │       │ signal_type        │
│ side               │       │ price              │
│ quantity           │       │ strength           │
│ price              │       │ reason             │
│ commission         │       │ is_executed        │
│ realized_pnl       │       │ created_at         │
│ trade_time         │       └────────────────────┘
│ created_at         │
└────────────────────┘
                             ┌────────────────────┐
                             │    strategies      │
                             ├────────────────────┤
                             │ id          PK     │
                             │ name               │
                             │ params      JSONB  │
                             │ is_active          │
                             │ created_at         │
                             │ updated_at         │
                             └────────────────────┘
```

## 2. 表结构定义

### 2.1 标的信息表 (symbols)

```sql
CREATE TABLE symbols (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    exchange VARCHAR(20) NOT NULL,          -- SSE/SZSE/HKEX
    market VARCHAR(20) NOT NULL,            -- A股/港股/美股
    sector VARCHAR(50),                      -- 行业板块
    list_date DATE,                          -- 上市日期
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_symbols_code ON symbols(code);
CREATE INDEX idx_symbols_market ON symbols(market);
```

### 2.2 K线数据表 (klines)

```sql
-- 使用 TimescaleDB 创建时序表
CREATE TABLE klines (
    id BIGSERIAL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    timeframe VARCHAR(10) NOT NULL,         -- 1m/5m/15m/30m/1h/1d/1w
    open_time TIMESTAMP NOT NULL,
    open DECIMAL(18, 4) NOT NULL,
    high DECIMAL(18, 4) NOT NULL,
    low DECIMAL(18, 4) NOT NULL,
    close DECIMAL(18, 4) NOT NULL,
    volume BIGINT NOT NULL,
    amount DECIMAL(20, 4),                   -- 成交额
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id, open_time)
);

-- 转换为 TimescaleDB 超表
SELECT create_hypertable('klines', 'open_time');

-- 创建索引
CREATE INDEX idx_klines_symbol_time ON klines(symbol_id, open_time DESC);
CREATE INDEX idx_klines_timeframe ON klines(timeframe, open_time DESC);
```

### 2.3 账户表 (accounts)

```sql
CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    account_type VARCHAR(20) NOT NULL,       -- simulation/real
    initial_capital DECIMAL(20, 4) NOT NULL,
    current_capital DECIMAL(20, 4) NOT NULL,
    total_value DECIMAL(20, 4) NOT NULL,     -- 总资产
    realized_pnl DECIMAL(20, 4) DEFAULT 0,   -- 已实现盈亏
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2.4 持仓表 (positions)

```sql
CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    quantity DECIMAL(18, 4) NOT NULL,
    avg_price DECIMAL(18, 4) NOT NULL,
    market_value DECIMAL(20, 4),
    unrealized_pnl DECIMAL(20, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol_id, account_id)
);

CREATE INDEX idx_positions_account ON positions(account_id);
```

### 2.5 订单表 (orders)

```sql
CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    strategy_id INTEGER REFERENCES strategies(id),
    order_type VARCHAR(20) NOT NULL,        -- market/limit/stop/stop_limit
    side VARCHAR(10) NOT NULL,              -- buy/sell
    quantity DECIMAL(18, 4) NOT NULL,
    price DECIMAL(18, 4),
    stop_price DECIMAL(18, 4),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    filled_qty DECIMAL(18, 4) DEFAULT 0,
    filled_price DECIMAL(18, 4) DEFAULT 0,
    commission DECIMAL(18, 4) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_orders_account ON orders(account_id, created_at DESC);
CREATE INDEX idx_orders_status ON orders(status);
```

### 2.6 成交表 (trades)

```sql
CREATE TABLE trades (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(18, 4) NOT NULL,
    price DECIMAL(18, 4) NOT NULL,
    commission DECIMAL(18, 4) DEFAULT 0,
    realized_pnl DECIMAL(20, 4),
    trade_time TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_trades_account_time ON trades(account_id, trade_time DESC);
```

### 2.7 策略表 (strategies)

```sql
CREATE TABLE strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    params JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- MACD 策略示例
INSERT INTO strategies (name, description, params) VALUES (
    'MACD_Standard',
    'MACD 标准策略',
    '{
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9,
        "zero_line_filter": true
    }'
);
```

### 2.8 信号表 (signals)

```sql
CREATE TABLE signals (
    id BIGSERIAL PRIMARY KEY,
    strategy_id INTEGER NOT NULL REFERENCES strategies(id),
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    signal_type VARCHAR(10) NOT NULL,       -- buy/sell/hold
    price DECIMAL(18, 4) NOT NULL,
    strength DECIMAL(5, 4) DEFAULT 1.0,     -- 信号强度 0-1
    reason TEXT,
    is_executed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_signals_strategy_time ON signals(strategy_id, created_at DESC);
```

### 2.9 每日净值表 (daily_equity)

```sql
CREATE TABLE daily_equity (
    id BIGSERIAL,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    date DATE NOT NULL,
    total_value DECIMAL(20, 4) NOT NULL,
    cash DECIMAL(20, 4) NOT NULL,
    position_value DECIMAL(20, 4) NOT NULL,
    daily_pnl DECIMAL(20, 4),
    daily_return DECIMAL(10, 6),
    cumulative_return DECIMAL(10, 6),
    max_drawdown DECIMAL(10, 6),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id, date)
);

SELECT create_hypertable('daily_equity', 'date');
CREATE INDEX idx_daily_equity_account ON daily_equity(account_id, date DESC);
```

## 3. 数据类定义 (Python)

```python
# models/entities.py

from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, Any
from enum import Enum

class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"

class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"

@dataclass
class Symbol:
    id: int
    code: str
    name: str
    exchange: str
    market: str
    sector: Optional[str] = None
    list_date: Optional[date] = None
    is_active: bool = True

@dataclass
class KLine:
    symbol_id: int
    timeframe: str
    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    amount: Optional[Decimal] = None

@dataclass
class Account:
    id: int
    name: str
    account_type: str
    initial_capital: Decimal
    current_capital: Decimal
    total_value: Decimal
    realized_pnl: Decimal = Decimal("0")
    is_active: bool = True

@dataclass
class Position:
    id: int
    symbol_id: int
    account_id: int
    quantity: Decimal
    avg_price: Decimal
    market_value: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None

@dataclass
class Order:
    id: Optional[int] = None
    account_id: int = 0
    symbol_id: int = 0
    strategy_id: Optional[int] = None
    order_type: OrderType = OrderType.MARKET
    side: OrderSide = OrderSide.BUY
    quantity: Decimal = Decimal("0")
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: Decimal = Decimal("0")
    filled_price: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class Trade:
    id: Optional[int] = None
    order_id: int = 0
    symbol_id: int = 0
    account_id: int = 0
    side: OrderSide = OrderSide.BUY
    quantity: Decimal = Decimal("0")
    price: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    realized_pnl: Optional[Decimal] = None
    trade_time: Optional[datetime] = None

@dataclass
class Strategy:
    id: int
    name: str
    description: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True

@dataclass
class Signal:
    id: Optional[int] = None
    strategy_id: int = 0
    symbol_id: int = 0
    signal_type: SignalType = SignalType.HOLD
    price: Decimal = Decimal("0")
    strength: float = 1.0
    reason: str = ""
    is_executed: bool = False
    created_at: Optional[datetime] = None
```

## 4. 数据访问层 (Repository)

```python
# repository/base.py

from abc import ABC, abstractmethod
from typing import List, Optional, TypeVar, Generic
import pandas as pd

T = TypeVar('T')

class BaseRepository(ABC, Generic[T]):
    
    @abstractmethod
    def get_by_id(self, id: int) -> Optional[T]:
        pass
    
    @abstractmethod
    def get_all(self) -> List[T]:
        pass
    
    @abstractmethod
    def save(self, entity: T) -> T:
        pass
    
    @abstractmethod
    def delete(self, id: int) -> bool:
        pass

# repository/kline_repository.py

class KLineRepository(BaseRepository[KLine]):
    
    def __init__(self, db_connection):
        self.conn = db_connection
    
    def get_by_symbol_and_timeframe(
        self,
        symbol_id: int,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """获取 K 线数据"""
        query = """
            SELECT open_time, open, high, low, close, volume, amount
            FROM klines
            WHERE symbol_id = %s
              AND timeframe = %s
              AND open_time BETWEEN %s AND %s
            ORDER BY open_time ASC
        """
        df = pd.read_sql(query, self.conn, params=[symbol_id, timeframe, start_time, end_time])
        df.set_index('open_time', inplace=True)
        return df
    
    def bulk_insert(self, klines: List[KLine]) -> int:
        """批量插入 K 线数据"""
        # 使用 COPY 命令或批量 INSERT 提高性能
        pass
```
