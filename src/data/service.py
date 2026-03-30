"""
行情数据服务

提供统一的数据访问接口，支持多数据源、自动降级、并行请求。
"""
import threading
import queue
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, cast
import logging

import pandas as pd

from src.config.schema import DataSource, DataConfig
from .provider import BaseDataProvider, Frequency as DataFrequency, TushareProvider, AkshareProvider, BaostockProvider, YFinanceProvider, SinaProvider
from .health_monitor import ProviderHealthMonitor
from .smart_adapter import SmartDataAdapter, DataSourceConfig
from .connection_pool import ReadWriteConnectionPool

logger = logging.getLogger(__name__)


class MarketDataServiceImpl:
    """
    行情数据服务

    提供统一的数据访问接口：
    - get_history(): 获取指定日期区间的历史数据（回测/分析）
    - get_latest(): 获取最近 N 条数据
    - get_latest_with_realtime(): 获取历史+实时合并数据（Live模式）

    Usage:
        from src.config import load_config, Config
        from src.data import get_data_service

        config = load_config(Config, "config/system.yaml")
        service = get_data_service(config.data)

        # Live模式
        data = service.get_latest_with_realtime('000001.SZ')

        # 回测模式
        data = service.get_history('000001.SZ', start_date, end_date)
    """

    def __init__(self, config: DataConfig):
        self.config = config
        self.source = config.source
        self.db_path = config.db_path

        # Fallback 配置
        if config.fallbacks:
            self.fallback_sources = config.fallbacks
        else:
            _defaults = [DataSource.AKSHARE, DataSource.BAOSTOCK]
            self.fallback_sources = [s for s in _defaults if s != config.source]

        self.parallel_fetch = config.parallel_fetch
        self.enable_health_monitor = config.enable_health_monitor

        # 缓存
        self._cache: Dict[str, pd.DataFrame] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = config.cache_ttl
        self._cache_maxsize = config.cache_maxsize

        self._history_cache: Dict[tuple, pd.DataFrame] = {}
        self._history_cache_time: Dict[tuple, datetime] = {}
        self._history_cache_ttl = config.cache_ttl
        self._history_cache_maxsize = config.cache_maxsize

        # 数据库
        self._db_lock = threading.Lock()
        self._connection_pool = ReadWriteConnectionPool(db_path=self.db_path, read_pool_size=10)

        # 异步持久化
        self._persist_queue: queue.Queue = queue.Queue()
        self._persist_worker = threading.Thread(
            target=self._persist_worker_loop, daemon=True, name="persist-worker"
        )
        self._persist_worker.start()

        # 适配器
        self._adapter: Optional[SmartDataAdapter] = None
        self._health_monitor: Optional[ProviderHealthMonitor] = None

        # 新浪Provider（实时数据专用，延迟初始化）
        self._sina_provider: Optional[SinaProvider] = None

        self._init_db()
        self._init_adapter()

        logger.info(f"数据服务初始化: source={self.source.value}, fallbacks={[s.value for s in self.fallback_sources]}")

    def _init_db(self) -> None:
        """初始化数据库"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS ohlcv (
                    symbol TEXT NOT NULL, date DATE NOT NULL,
                    open REAL, high REAL, low REAL, close REAL,
                    volume INTEGER, amount REAL,
                    PRIMARY KEY (symbol, date)
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS ohlcv_minute (
                    symbol TEXT NOT NULL, datetime TEXT NOT NULL, frequency TEXT NOT NULL,
                    open REAL, high REAL, low REAL, close REAL,
                    volume INTEGER, amount REAL,
                    PRIMARY KEY (symbol, datetime, frequency)
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_symbol ON ohlcv(symbol)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_date ON ohlcv(date)')
            conn.commit()
        finally:
            conn.close()

    def _init_adapter(self) -> None:
        """初始化智能适配器"""
        self._health_monitor = ProviderHealthMonitor()

        sources_config = []
        primary = self._create_source_config(self.source, priority=1)
        if primary:
            sources_config.append(primary)

        for i, fb in enumerate(self.fallback_sources, start=2):
            cfg = self._create_source_config(fb, priority=i)
            if cfg:
                sources_config.append(cfg)

        if sources_config:
            self._adapter = SmartDataAdapter(
                sources_config=sources_config,
                health_monitor=self._health_monitor,
                parallel_fetch=self.parallel_fetch,
                primary_source=self.source.value,
                max_workers=min(3, len(sources_config))
            )

    def _create_source_config(self, source: DataSource, priority: int) -> Optional[DataSourceConfig]:
        """创建数据源配置"""
        try:
            if source == DataSource.TUSHARE:
                token = self.config.get_tushare_token()
                provider: BaseDataProvider = TushareProvider(token)
            elif source == DataSource.AKSHARE:
                provider = AkshareProvider()
            elif source == DataSource.BAOSTOCK:
                provider = BaostockProvider()
            elif source == DataSource.YFINANCE:
                provider = YFinanceProvider()
            else:
                return None

            return DataSourceConfig(name=source.value, provider=provider, priority=priority)
        except Exception as e:
            logger.warning(f"创建数据源配置失败 {source.value}: {e}")
            return None

    def _get_sina_provider(self) -> SinaProvider:
        """获取/创建新浪Provider（实时数据专用）"""
        if self._sina_provider is None:
            self._sina_provider = SinaProvider()
        return self._sina_provider

    def close(self) -> None:
        """关闭服务"""
        self._persist_queue.put(None)
        self._persist_worker.join(timeout=5)
        self._connection_pool.close()
        logger.info("数据服务已关闭")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ==================== 公共API（2个核心方法）====================

    def get_history(self, symbol: str,
                    start_date: Optional[datetime] = None,
                    end_date: Optional[datetime] = None,
                    frequency: Optional[str] = None) -> pd.DataFrame:
        """
        获取历史数据

        Args:
            symbol: 标的代码
            start_date: 开始日期（可选，默认365天前）
            end_date: 结束日期（可选，默认为今天）
            frequency: 数据频率（默认日线）

        Returns:
            DataFrame: 包含 date, open, high, low, close, volume 列

        Examples:
            data = service.get_history('000001.SZ', start_date, end_date)
        """
        freq = frequency or DataFrequency.DAILY

        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=365)
        return self._get_history_by_date_range(symbol, start_date, end_date, freq)

    def _get_history_by_date_range(self, symbol: str, start_date: datetime,
                                    end_date: datetime, freq: str) -> pd.DataFrame:
        """按日期区间获取历史数据（内部实现）"""
        cache_key = (symbol, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), freq)

        # 检查缓存
        cached_time = self._history_cache_time.get(cache_key)
        if cached_time and (datetime.now() - cached_time).total_seconds() < self._history_cache_ttl:
            return self._history_cache[cache_key]

        # 查数据库
        data = self._query_from_db(symbol, start_date=start_date, end_date=end_date, frequency=freq)

        # 数据不足且非本地模式，拉取远端
        if len(data) < 10 and self.source != DataSource.LOCAL and self._adapter:
            try:
                fetched = self._adapter.fetch(symbol, start_date, end_date, freq)  # type: ignore[arg-type]
                if fetched is not None and not fetched.empty:
                    data = fetched
                    self._persist_queue.put((symbol, fetched, freq))
            except Exception as e:
                logger.warning(f"获取远程历史数据失败 {symbol}: {e}")

        self._set_history_cache(cache_key, data)
        return data

    def get_latest_with_realtime(self, symbol: str,
                                  frequency: Optional[str] = None) -> pd.DataFrame:
        """
        获取历史数据并用实时行情更新（Live模式核心方法）

        先获取历史K线数据，然后用新浪财经实时行情更新最后一根K线的价格。

        Args:
            symbol: 标的代码
            frequency: 数据频率

        Returns:
            DataFrame: 包含实时价格更新的K线数据
        """
        freq = frequency or DataFrequency.DAILY
        is_minute = freq != DataFrequency.DAILY

        # 获取历史数据（默认最近一年）
        end = datetime.now()
        start = end - timedelta(days=365)
        data = self.get_history(symbol, start_date=start, end_date=end, frequency=freq)

        # 如果数据库没有数据，尝试从远程获取
        if (data is None or data.empty) and self.source != DataSource.LOCAL and self._adapter:
            logger.info(f"数据库无{freq}数据，尝试从远程获取 {symbol}...")
            try:
                fetched = self._adapter.fetch(symbol, start, end, freq)  # type: ignore[arg-type]
                if fetched is not None and not fetched.empty:
                    data = fetched
                    self._persist_queue.put((symbol, fetched, freq))
                    logger.info(f"从远程获取 {symbol} {freq} 数据 {len(fetched)} 条")
            except Exception as e:
                logger.warning(f"从远程获取 {symbol} {freq} 数据失败: {e}")

        # 获取实时行情
        realtime = self._get_realtime_from_sina(symbol)
        if not realtime:
            logger.debug(f"无法获取 {symbol} 实时行情")
            if data is None or data.empty:
                return pd.DataFrame()
            return data

        # 如果没有历史数据，用实时数据构建一根K线
        if data is None or data.empty:
            logger.info(f"无历史数据，使用实时数据构建K线 {symbol}")
            now = datetime.now()
            data = pd.DataFrame([{
                'date': now,
                'open': realtime['open'],
                'high': realtime['high'],
                'low': realtime['low'],
                'close': realtime['price'],
                'volume': realtime['volume'],
            }])
            data.set_index('date', inplace=True)
            return data

        # 有历史数据，用实时数据更新最后一根K线
        data = data.copy()
        last_idx = len(data) - 1

        if is_minute:
            now = datetime.now()
            last_date = data.index[-1]
            is_same_day = (now.date() == pd.Timestamp(last_date).date())

            if is_same_day:
                data.iloc[last_idx, data.columns.get_loc('close')] = realtime['price']
                if realtime['price'] > data.iloc[last_idx]['high']:
                    data.iloc[last_idx, data.columns.get_loc('high')] = realtime['price']
                if realtime['price'] < data.iloc[last_idx]['low']:
                    data.iloc[last_idx, data.columns.get_loc('low')] = realtime['price']
                if 'volume' in data.columns:
                    data.iloc[last_idx, data.columns.get_loc('volume')] = realtime['volume']
                logger.debug(f"{symbol} 分钟模式-更新当日K线: {realtime['price']}")
            else:
                new_row = pd.DataFrame([{
                    'date': now,
                    'open': realtime['open'],
                    'high': realtime['high'],
                    'low': realtime['low'],
                    'close': realtime['price'],
                    'volume': realtime['volume'],
                }])
                new_row.set_index('date', inplace=True)
                data = pd.concat([data, new_row])
                logger.debug(f"{symbol} 分钟模式-新增K线: {realtime['price']}")
        else:
            data.iloc[last_idx, data.columns.get_loc('close')] = realtime['price']
            if realtime['price'] > data.iloc[last_idx]['high']:
                data.iloc[last_idx, data.columns.get_loc('high')] = realtime['price']
            if realtime['price'] < data.iloc[last_idx]['low']:
                data.iloc[last_idx, data.columns.get_loc('low')] = realtime['price']
            if 'volume' in data.columns and realtime['volume'] > data.iloc[last_idx]['volume']:
                data.iloc[last_idx, data.columns.get_loc('volume')] = realtime['volume']
            logger.debug(f"{symbol} 日线模式-更新: {realtime['price']}")

        return data

    # ==================== 数据管理方法 ====================

    def sync(self, symbols: Optional[List[str]] = None,
             start_date: Optional[datetime] = None,
             end_date: Optional[datetime] = None,
             frequency: str = DataFrequency.DAILY,
             progress_callback: Any = None) -> int:
        """同步数据到本地"""
        if not symbols or not self._adapter:
            return 0

        end = end_date or datetime.now()
        start = start_date or (end - timedelta(days=365))
        total = 0

        for i, symbol in enumerate(symbols):
            try:
                df = self._adapter.fetch(symbol, start, end, frequency)  # type: ignore[arg-type]
                if df is not None and not df.empty:
                    self._do_persist(symbol, df, frequency)
                    total += len(df)
                if progress_callback:
                    progress_callback((i + 1) / len(symbols) * 100)
            except Exception as e:
                logger.error(f"同步失败 {symbol}: {e}")

        return total

    def get_data_stats(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取数据统计"""
        with self._connection_pool.get_read_connection() as conn:
            query = """
                SELECT symbol, COUNT(*) as count,
                       MIN(date) as start_date, MAX(date) as end_date
                FROM ohlcv
            """
            params: List[str] = []
            if symbol:
                query += " WHERE symbol = ?"
                params.append(symbol)
            query += " GROUP BY symbol ORDER BY symbol"

            df = pd.read_sql_query(query, conn, params=params)
            return cast(List[Dict[str, Any]], df.to_dict('records'))

    def clean(self, symbol: Optional[str] = None, before_date: Optional[datetime] = None) -> int:
        """清理数据"""
        with self._connection_pool.get_write_connection() as conn:
            conditions: List[str] = []
            params: List[str] = []
            if symbol:
                conditions.append("symbol = ?")
                params.append(symbol)
            if before_date:
                conditions.append("date < ?")
                params.append(before_date.strftime('%Y-%m-%d'))

            where = " AND ".join(conditions) if conditions else "1=1"
            cursor = conn.execute(f"DELETE FROM ohlcv WHERE {where}", params)  # type: ignore[union-attr]
            conn.commit()  # type: ignore[union-attr]
            return cursor.rowcount

    # ==================== 内部方法 ====================

    def _get_realtime_from_sina(self, symbol: str) -> Dict[str, Any]:
        """从新浪获取实时行情（内部方法）"""
        # 新浪只支持 A 股，港股/美股使用 yfinance
        if symbol.endswith('.HK') or symbol.endswith('.US') or symbol.isalpha():
            return self._get_realtime_from_yfinance(symbol)
        try:
            return self._get_sina_provider().fetch_realtime(symbol)
        except Exception as e:
            logger.warning(f"获取新浪实时行情失败 {symbol}: {e}")
            return {}

    def _get_realtime_from_yfinance(self, symbol: str) -> Dict[str, Any]:
        """从 yfinance 获取实时行情（用于港股/美股）"""
        try:
            from .provider import YFinanceProvider
            provider = YFinanceProvider()
            return provider.fetch_realtime(symbol)
        except Exception as e:
            logger.warning(f"获取 yfinance 实时行情失败 {symbol}: {e}")
            return {}

    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self._cache:
            return False
        cache_time = self._cache_time.get(key)
        if cache_time is None:
            return False
        return (datetime.now() - cache_time).total_seconds() < self._cache_ttl

    def _set_cache(self, key: str, data: pd.DataFrame) -> None:
        """设置缓存"""
        if len(self._cache) >= self._cache_maxsize:
            # 清理最旧的缓存项
            oldest_key: Optional[str] = None
            oldest_time: Optional[datetime] = None
            for k, t in self._cache_time.items():
                if oldest_time is None or (t is not None and t < oldest_time):
                    oldest_key = k
                    oldest_time = t
            if oldest_key is not None:
                self._cache.pop(oldest_key, None)
                self._cache_time.pop(oldest_key, None)
        self._cache[key] = data
        self._cache_time[key] = datetime.now()

    def _set_history_cache(self, key: tuple, data: pd.DataFrame) -> None:
        """设置历史缓存"""
        if len(self._history_cache) >= self._history_cache_maxsize:
            # 清理最旧的缓存项
            oldest_key: Optional[tuple] = None
            oldest_time: Optional[datetime] = None
            for k, t in self._history_cache_time.items():
                if oldest_time is None or (t is not None and t < oldest_time):
                    oldest_key = k
                    oldest_time = t
            if oldest_key is not None:
                self._history_cache.pop(oldest_key, None)
                self._history_cache_time.pop(oldest_key, None)
        self._history_cache[key] = data
        self._history_cache_time[key] = datetime.now()

    def _query_from_db(self, symbol: str,
                       start_date: Optional[datetime] = None,
                       end_date: Optional[datetime] = None,
                       limit: Optional[int] = None,
                       frequency: str = DataFrequency.DAILY,
                       order_desc: bool = False) -> pd.DataFrame:
        """从数据库查询

        Args:
            symbol: 标的代码
            start_date: 开始日期
            end_date: 结束日期
            limit: 限制条数
            frequency: 数据频率
            order_desc: 是否按时间倒序（用于获取最近数据）
        """
        is_minute = frequency != DataFrequency.DAILY

        if is_minute:
            query = "SELECT * FROM ohlcv_minute WHERE symbol = ? AND frequency = ?"
            params = [symbol, frequency]
        else:
            query = "SELECT * FROM ohlcv WHERE symbol = ?"
            params = [symbol]

        if start_date:
            query += f" AND {'datetime' if is_minute else 'date'} >= ?"
            params.append(start_date.strftime('%Y-%m-%d %H:%M:%S' if is_minute else '%Y-%m-%d'))

        if end_date:
            query += f" AND {'datetime' if is_minute else 'date'} <= ?"
            params.append(end_date.strftime('%Y-%m-%d %H:%M:%S' if is_minute else '%Y-%m-%d'))

        # 排序方向：ASC正序（默认），DESC倒序（获取最近数据）
        order = "DESC" if order_desc else "ASC"
        query += f" ORDER BY {'datetime' if is_minute else 'date'} {order}"

        if limit:
            query += f" LIMIT {limit}"

        with self._connection_pool.get_read_connection() as conn:
            df: pd.DataFrame = pd.read_sql_query(query, conn, params=list(params))

        if not df.empty:
            date_col = 'date' if 'date' in df.columns else 'datetime'
            df['date'] = pd.to_datetime(cast(pd.Series, df[date_col]))
            # 设置日期为索引，方便排序
            df.set_index('date', inplace=True)
        return df

    def _persist_worker_loop(self) -> None:
        """持久化工作线程"""
        while True:
            try:
                item = self._persist_queue.get(timeout=1)
                if item is None:
                    break
                symbol, df, frequency = item
                self._do_persist(symbol, df, frequency)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"持久化异常: {e}")

    def _do_persist(self, symbol: str, df: pd.DataFrame, frequency: str) -> None:
        """执行持久化"""
        try:
            is_minute = frequency != DataFrequency.DAILY

            date_col = cast(pd.Series, df['date'])
            date_series = pd.to_datetime(date_col)
            fmt = '%Y-%m-%d %H:%M:%S' if is_minute else '%Y-%m-%d'
            date_strs = [x.strftime(fmt) for x in date_series]  # type: ignore[union-attr]

            if 'amount' in df.columns:
                amount_series = cast(pd.Series, df['amount'])
                amount_values = cast(pd.Series, amount_series.fillna(0))
            else:
                amount_values = pd.Series([0.0] * len(df))

            symbol_values = list(cast(pd.Series, df['symbol']))
            open_values = list(cast(pd.Series, df['open']))
            high_values = list(cast(pd.Series, df['high']))
            low_values = list(cast(pd.Series, df['low']))
            close_values = list(cast(pd.Series, df['close']))
            volume_values = list(cast(pd.Series, df['volume']))
            amount_list = list(amount_values)

            if is_minute:
                records = list(zip(symbol_values, date_strs, [frequency] * len(df),
                                 open_values, high_values, low_values, close_values,
                                 volume_values, amount_list))
                sql = '''INSERT OR REPLACE INTO ohlcv_minute
                    (symbol, datetime, frequency, open, high, low, close, volume, amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'''
            else:
                records = list(zip(symbol_values, date_strs,
                                 open_values, high_values, low_values, close_values,
                                 volume_values, amount_list))
                sql = '''INSERT OR REPLACE INTO ohlcv
                    (symbol, date, open, high, low, close, volume, amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)'''

            with self._db_lock:
                with self._connection_pool.get_write_connection() as conn:
                    conn.executemany(sql, records)  # type: ignore[union-attr]
                    conn.commit()  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"持久化失败 {symbol}: {e}")
