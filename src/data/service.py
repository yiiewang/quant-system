"""
行情数据服务

提供统一的数据访问接口，支持多数据源、自动降级、并行请求。
"""
import threading
import queue
import sqlite3
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging

import pandas as pd

from src.config.schema import DataSource
from .provider import BaseDataProvider, Frequency as DataFrequency, TushareProvider, AkshareProvider, BaostockProvider, YFinanceProvider
from .health_monitor import ProviderHealthMonitor
from .smart_adapter import SmartDataAdapter, DataSourceConfig
from .connection_pool import ReadWriteConnectionPool

logger = logging.getLogger(__name__)


class MarketDataService:
    """
    行情数据服务（原增强版）

    支持:
    - 多数据源自动降级
    - 并行请求（取最快结果）
    - 健康监控与自动隔离
    - 本地缓存与持久化

    Usage:
        from src.config import load_config, Config
        from src.data import init_data_service

        config = load_config(Config, "config/system.yaml")
        service = init_data_service(config.data)

        data = service.get_latest('000001.SZ', lookback=100)
    """

    def __init__(self,
                 source: DataSource = DataSource.LOCAL,
                 db_path: str = "data/market.db",
                 config: Optional[Dict[str, Any]] = None,
                 fallback_sources: Optional[List[DataSource]] = None,
                 parallel_fetch: bool = True,
                 enable_health_monitor: bool = True):
        self.source = source
        self.db_path = db_path
        self.config = config or {}

        # Fallback 配置
        if fallback_sources is None:
            _defaults = [DataSource.AKSHARE, DataSource.BAOSTOCK]
            self.fallback_sources = [s for s in _defaults if s != source]
        else:
            self.fallback_sources = fallback_sources

        self.parallel_fetch = parallel_fetch
        self.enable_health_monitor = enable_health_monitor

        # 缓存
        self._cache: Dict[str, pd.DataFrame] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = 60
        self._cache_maxsize = 200

        self._history_cache: Dict[tuple, pd.DataFrame] = {}
        self._history_cache_time: Dict[tuple, datetime] = {}
        self._history_cache_ttl = 300
        self._history_cache_maxsize = 100

        # 数据库
        self._db_lock = threading.Lock()
        self._connection_pool = ReadWriteConnectionPool(db_path=db_path, read_pool_size=10)

        # 异步持久化
        self._persist_queue: queue.Queue = queue.Queue()
        self._persist_worker = threading.Thread(
            target=self._persist_worker_loop, daemon=True, name="persist-worker"
        )
        self._persist_worker.start()

        # 适配器
        self._adapter: Optional[SmartDataAdapter] = None
        self._health_monitor: Optional[ProviderHealthMonitor] = None

        self._init_db()
        self._init_adapter()

        logger.info(f"数据服务初始化: source={source.value}, fallbacks={[s.value for s in self.fallback_sources]}")

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
                token = self.config.get('tushare_token', '') if self.config else ''
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

    def get_latest(self, symbol: str, lookback: int = 100, frequency: Optional[str] = None) -> pd.DataFrame:
        """获取最新数据"""
        freq = frequency or DataFrequency.DAILY
        cache_key = f"{symbol}_{lookback}_{freq}"

        # 检查缓存
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        # 查数据库
        data = self._query_from_db(symbol, limit=lookback, frequency=freq)

        # 数据不足且非本地模式，拉取远端
        if len(data) < lookback and self.source != DataSource.LOCAL and self._adapter:
            end = datetime.now()
            start = end - timedelta(days=max(lookback * 2, 365))
            fetched = self._adapter.fetch(symbol, start, end, freq)  # type: ignore[arg-type]
            if fetched is not None and not fetched.empty:
                data = fetched.tail(lookback)
                self._persist_queue.put((symbol, fetched, freq))

        self._set_cache(cache_key, data)
        return data

    def get_history(self, symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """获取历史数据"""
        cache_key = (symbol, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))

        # 检查缓存
        cached_time = self._history_cache_time.get(cache_key)
        if cached_time and (datetime.now() - cached_time).total_seconds() < self._history_cache_ttl:
            return self._history_cache[cache_key]

        # 查数据库
        data = self._query_from_db(symbol, start_date=start_date, end_date=end_date)
        self._set_history_cache(cache_key, data)
        return data

    def get_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取实时行情"""
        if not self._adapter:
            return {}

        for attempt in range(3):
            try:
                # Try to get from adapter sources
                for _name, cfg in self._adapter.sources.items():
                    try:
                        result = cfg.provider.fetch_realtime(symbol)
                        if result:
                            return result
                    except Exception:
                        continue
                return {}
            except Exception as e:
                logger.warning(f"获取实时行情失败 {symbol}: {e}")
                time.sleep(1.0 * (2 ** attempt))
        return {}

    def sync(self, symbols: Optional[List[str]] = None,
             start_date: Optional[datetime] = None,
             end_date: Optional[datetime] = None,
             frequency: str = DataFrequency.DAILY,
             progress_callback: Any = None) -> int:
        """同步数据到本地"""
        if not symbols:
            return 0

        end = end_date or datetime.now()
        start = start_date or (end - timedelta(days=365))
        total = 0

        for i, symbol in enumerate(symbols):
            try:
                if not self._adapter:
                    continue
                df = self._adapter.fetch(symbol, start, end, frequency)  # type: ignore[arg-type]
                if df is not None and not df.empty:
                    self._do_persist(symbol, df, frequency)
                    total += len(df)
                if progress_callback:
                    progress_callback((i + 1) / len(symbols) * 100)
            except Exception as e:
                logger.error(f"同步失败 {symbol}: {e}")

        return total

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
            # Find oldest entry
            oldest_key = None
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
            # Find oldest entry
            oldest_key = None
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
                       frequency: str = DataFrequency.DAILY) -> pd.DataFrame:
        """从数据库查询"""
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

        query += f" ORDER BY {'datetime' if is_minute else 'date'} ASC"

        if limit:
            query += f" LIMIT {limit}"

        with self._connection_pool.get_read_connection() as conn:
            df = pd.read_sql_query(query, conn, params=list(params))

        if not df.empty:
            df['date'] = pd.to_datetime(df['date'] if 'date' in df.columns else df['datetime'])
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

            # Convert dates to string format
            date_series = pd.to_datetime(df['date'])
            fmt = '%Y-%m-%d %H:%M:%S' if is_minute else '%Y-%m-%d'
            dates = date_series.apply(lambda x: x.strftime(fmt)).tolist()  # type: ignore[arg-type]
            amount = df['amount'].fillna(0) if 'amount' in df.columns else pd.Series(0.0, index=df.index)

            if is_minute:
                records = list(zip(df['symbol'], dates, [frequency] * len(df),
                                 df['open'], df['high'], df['low'], df['close'],
                                 df['volume'], amount))
                sql = '''INSERT OR REPLACE INTO ohlcv_minute
                    (symbol, datetime, frequency, open, high, low, close, volume, amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'''
            else:
                records = list(zip(df['symbol'], dates,
                                 df['open'], df['high'], df['low'], df['close'],
                                 df['volume'], amount))
                sql = '''INSERT OR REPLACE INTO ohlcv
                    (symbol, date, open, high, low, close, volume, amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)'''

            with self._db_lock:
                with self._connection_pool.get_write_connection() as conn:
                    conn.executemany(sql, records)  # type: ignore[union-attr]
                    conn.commit()  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"持久化失败 {symbol}: {e}")

    def get_data_stats(self, symbol: Optional[str] = None) -> List[Dict]:
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
            return df.to_dict('records')

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

    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._cache_time.clear()
        self._history_cache.clear()
        self._history_cache_time.clear()
