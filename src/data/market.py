"""
行情数据服务
提供行情数据的获取、缓存和存储功能
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
import sqlite3
import threading
import queue
import time
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class DataSource(Enum):
    """数据源类型"""
    TUSHARE = "tushare"
    AKSHARE = "akshare"
    BAOSTOCK = "baostock"
    LOCAL = "local"


class Frequency(Enum):
    """数据频率"""
    DAILY = "daily"
    MIN_5 = "5min"
    MIN_15 = "15min"
    MIN_30 = "30min"
    MIN_60 = "60min"


class BaseDataProvider(ABC):
    """数据提供者基类"""
    
    @abstractmethod
    def fetch(self, symbol: str, start_date: datetime, 
              end_date: datetime,
              frequency: Frequency = Frequency.DAILY) -> pd.DataFrame:
        """
        获取历史数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            frequency: 数据频率 (daily/5min/15min/30min/60min)
        
        Returns:
            pd.DataFrame: OHLCV 数据
        """
        pass
    
    @abstractmethod
    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        """
        获取实时行情
        
        Args:
            symbol: 股票代码
        
        Returns:
            Dict: 实时行情数据
        """
        pass


class TushareProvider(BaseDataProvider):
    """Tushare 数据提供者"""
    
    def __init__(self, token: str = None):
        self.token = token
        self._api = None
    
    def _get_api(self):
        """获取 API 实例"""
        if self._api is None:
            try:
                import tushare as ts
                ts.set_token(self.token)
                self._api = ts.pro_api()
            except ImportError:
                raise ImportError("请安装 tushare: pip install tushare")
        return self._api
    
    def fetch(self, symbol: str, start_date: datetime, 
              end_date: datetime,
              frequency: Frequency = Frequency.DAILY) -> pd.DataFrame:
        """获取历史数据"""
        api = self._get_api()
        
        # 转换日期格式
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        
        if frequency == Frequency.DAILY:
            # 获取日线数据
            df = api.daily(
                ts_code=symbol,
                start_date=start_str,
                end_date=end_str
            )
        else:
            # 分钟级数据: Tushare 需要积分权限
            freq_map = {
                Frequency.MIN_5: '5min',
                Frequency.MIN_15: '15min',
                Frequency.MIN_30: '30min',
                Frequency.MIN_60: '60min',
            }
            df = api.stk_mins(
                ts_code=symbol,
                start_date=start_str,
                end_date=end_str,
                freq=freq_map[frequency],
            )
        
        if df is None or df.empty:
            return pd.DataFrame()
        
        # 标准化列名
        if frequency == Frequency.DAILY:
            df = df.rename(columns={
                'ts_code': 'symbol',
                'trade_date': 'date',
                'vol': 'volume',
                'amount': 'amount'
            })
            df['date'] = pd.to_datetime(df['date'])
        else:
            df = df.rename(columns={
                'ts_code': 'symbol',
                'trade_time': 'datetime',
                'vol': 'volume',
            })
            df['datetime'] = pd.to_datetime(df['datetime'])
        
        # 按时间升序排列
        sort_col = 'date' if frequency == Frequency.DAILY else 'datetime'
        df = df.sort_values(sort_col).reset_index(drop=True)
        
        if frequency == Frequency.DAILY:
            return df[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount']]
        else:
            cols = ['symbol', 'datetime', 'open', 'high', 'low', 'close', 'volume']
            if 'amount' in df.columns:
                cols.append('amount')
            else:
                df['amount'] = 0.0
                cols.append('amount')
            return df[cols]
    
    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取实时行情"""
        api = self._get_api()
        
        # 获取实时行情
        df = api.daily(ts_code=symbol, limit=1)
        
        if df is None or df.empty:
            return {}
        
        row = df.iloc[0]
        return {
            'symbol': symbol,
            'price': row['close'],
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'volume': row['vol'],
        }


class AkshareProvider(BaseDataProvider):
    """AKShare 数据提供者"""
    
    def fetch(self, symbol: str, start_date: datetime, 
              end_date: datetime,
              frequency: Frequency = Frequency.DAILY) -> pd.DataFrame:
        """获取历史数据"""
        try:
            import akshare as ak
        except ImportError:
            raise ImportError("请安装 akshare: pip install akshare")
        
        # AKShare 使用不同的股票代码格式
        code = symbol.split('.')[0]
        
        if frequency == Frequency.DAILY:
            # 获取日线数据
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date.strftime('%Y%m%d'),
                end_date=end_date.strftime('%Y%m%d'),
                adjust="qfq"
            )
            
            if df is None or df.empty:
                return pd.DataFrame()
            
            df = df.rename(columns={
                '日期': 'date', '开盘': 'open', '最高': 'high',
                '最低': 'low', '收盘': 'close', '成交量': 'volume', '成交额': 'amount'
            })
            df['symbol'] = symbol
            df['date'] = pd.to_datetime(df['date'])
            return df[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount']]
        else:
            # 分时数据
            freq_map = {
                Frequency.MIN_5: '5',
                Frequency.MIN_15: '15',
                Frequency.MIN_30: '30',
                Frequency.MIN_60: '60',
            }
            df = ak.stock_zh_a_hist_min_em(
                symbol=code,
                period=freq_map[frequency],
                start_date=start_date.strftime('%Y-%m-%d %H:%M:%S'),
                end_date=end_date.strftime('%Y-%m-%d %H:%M:%S'),
                adjust="qfq",
            )
            
            if df is None or df.empty:
                return pd.DataFrame()
            
            df = df.rename(columns={
                '时间': 'datetime', '开盘': 'open', '最高': 'high',
                '最低': 'low', '收盘': 'close', '成交量': 'volume', '成交额': 'amount'
            })
            df['symbol'] = symbol
            df['datetime'] = pd.to_datetime(df['datetime'])
            return df[['symbol', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'amount']]
    
    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取实时行情"""
        try:
            import akshare as ak
        except ImportError:
            raise ImportError("请安装 akshare: pip install akshare")
        
        code = symbol.split('.')[0]
        
        df = ak.stock_zh_a_spot_em()
        row = df[df['代码'] == code]
        
        if row.empty:
            return {}
        
        row = row.iloc[0]
        return {
            'symbol': symbol,
            'price': row['最新价'],
            'open': row['今开'],
            'high': row['最高'],
            'low': row['最低'],
            'volume': row['成交量'],
        }


class BaostockProvider(BaseDataProvider):
    """BaoStock 数据提供者（免费，支持 Python 3.6+）"""
    
    def __init__(self):
        self._logged_in = False
    
    def _login(self):
        """登录 BaoStock"""
        if not self._logged_in:
            try:
                import baostock as bs
                import sys
                import io
                # 抑制 baostock 的 "login success!" 输出
                old_stdout = sys.stdout
                sys.stdout = io.StringIO()
                try:
                    lg = bs.login()
                finally:
                    sys.stdout = old_stdout
                if lg.error_code != '0':
                    raise ConnectionError(f"BaoStock 登录失败: {lg.error_msg}")
                self._logged_in = True
            except ImportError:
                raise ImportError("请安装 baostock: pip install baostock")
    
    def _logout(self):
        """登出 BaoStock"""
        if self._logged_in:
            import baostock as bs
            bs.logout()
            self._logged_in = False
    
    def _convert_symbol(self, symbol: str) -> str:
        """
        转换股票代码格式
        000001.SZ -> sz.000001
        600036.SH -> sh.600036
        """
        code, market = symbol.split('.')
        return f"{market.lower()}.{code}"
    
    def fetch(self, symbol: str, start_date: datetime, 
              end_date: datetime,
              frequency: Frequency = Frequency.DAILY) -> pd.DataFrame:
        """获取历史数据"""
        self._login()
        
        import baostock as bs
        
        # 转换股票代码
        bs_symbol = self._convert_symbol(symbol)
        
        # 频率映射
        if frequency == Frequency.DAILY:
            bs_freq = "d"
            fields = "date,open,high,low,close,volume,amount"
        else:
            freq_map = {
                Frequency.MIN_5: "5",
                Frequency.MIN_15: "15",
                Frequency.MIN_30: "30",
                Frequency.MIN_60: "60",
            }
            bs_freq = freq_map[frequency]
            fields = "time,open,high,low,close,volume,amount"
        
        rs = bs.query_history_k_data_plus(
            bs_symbol,
            fields,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            frequency=bs_freq,
            adjustflag="2"  # 前复权
        )
        
        if rs.error_code != '0':
            raise RuntimeError(f"获取数据失败: {rs.error_msg}")
        
        # 转换为 DataFrame
        data_list = []
        while (rs.error_code == '0') and rs.next():
            data_list.append(rs.get_row_data())
        
        if not data_list:
            return pd.DataFrame()
        
        col_names = fields.split(',')
        df = pd.DataFrame(data_list, columns=col_names)
        
        # 转换数据类型
        df['symbol'] = symbol
        for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        if frequency == Frequency.DAILY:
            df['date'] = pd.to_datetime(df['date'])
            return df[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount']]
        else:
            # baostock 分钟线 time 格式: 20240101150000000
            df['datetime'] = pd.to_datetime(df['time'].str[:14], format='%Y%m%d%H%M%S')
            return df[['symbol', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'amount']]
    
    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        """
        获取实时行情
        
        优先使用 akshare 获取真实实时价格；
        akshare 不可用时降级为最新日线数据（非实盘场景）。
        """
        try:
            import akshare as ak
            code = symbol.split('.')[0]
            df = ak.stock_zh_a_spot_em()
            row = df[df['代码'] == code]
            if not row.empty:
                row = row.iloc[0]
                return {
                    'symbol': symbol,
                    'price': float(row['最新价']),
                    'open': float(row['今开']),
                    'high': float(row['最高']),
                    'low': float(row['最低']),
                    'volume': float(row['成交量']),
                    'source': 'realtime',
                }
        except Exception as e:
            logger.warning(f"akshare 实时行情获取失败，降级为日线数据: {e}")
        
        # 降级：返回最新日线收盘价（注意：非实时）
        end = datetime.now()
        start = end - timedelta(days=7)
        df = self.fetch(symbol, start, end)
        
        if df.empty:
            return {}
        
        row = df.iloc[-1]
        logger.warning(f"{symbol} 使用日线收盘价作为实时价格（非实时）")
        return {
            'symbol': symbol,
            'price': row['close'],
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'volume': row['volume'],
            'source': 'daily_close',
        }


class MarketDataService:
    """
    行情数据服务
    
    提供行情数据的统一访问接口，支持:
    - 多数据源切换
    - 本地缓存
    - SQLite 持久化存储
    
    Usage:
        service = MarketDataService(source=DataSource.TUSHARE)
        
        # 获取最新数据（自动缓存）
        data = service.get_latest('000001.SZ', lookback=100)
        
        # 获取历史数据
        data = service.get_history('000001.SZ', start, end)
        
        # 同步数据到本地
        service.sync(['000001.SZ'], start, end)
    """
    
    def __init__(self, source: DataSource = DataSource.LOCAL,
                 db_path: str = "data/market.db",
                 config: Dict[str, Any] = None):
        """
        初始化数据服务
        
        Args:
            source: 数据源类型
            db_path: SQLite 数据库路径
            config: 配置参数（如 API token）
        """
        self.source = source
        self.db_path = db_path
        self.config = config or {}
        
        # 内存缓存（get_latest 用，key=symbol_lookback）
        self._cache: Dict[str, pd.DataFrame] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = 60  # 缓存有效期（秒）

        # get_history 缓存（key=(symbol, start_str, end_str)）
        self._history_cache: Dict[tuple, pd.DataFrame] = {}
        self._history_cache_time: Dict[tuple, datetime] = {}
        self._history_cache_ttl = 300  # 5分钟，回测场景读多写少
        
        # 数据提供者
        self._provider: BaseDataProvider = None
        
        # SQLite 并发写入锁
        self._db_lock = threading.Lock()

        # 异步持久化队列（单后台写线程消费）
        self._persist_queue: queue.Queue = queue.Queue()
        self._persist_worker = threading.Thread(
            target=self._persist_worker_loop,
            daemon=True,
            name="market-persist-worker"
        )
        self._persist_worker.start()
        
        # 初始化数据库
        self._init_db()
        
        logger.info(f"初始化数据服务: source={source.value}, db={db_path}")
    
    def get_latest(self, symbol: str, lookback: int = 100) -> pd.DataFrame:
        """
        获取最新行情数据
        
        流程：
        ① 检查内存缓存（TTL=60s）
        ② 缓存未命中 → 查 SQLite
        ③ 数据不足 → 调 Provider.fetch() 拉取远端
        ④ 更新内存缓存
        ⑤ 返回 DataFrame
        ⑥ 异步后台将缓存数据写入 SQLite（不阻塞查询链路）
        
        Args:
            symbol: 股票代码
            lookback: 回溯条数
        
        Returns:
            pd.DataFrame: OHLCV 数据
        """
        cache_key = f"{symbol}_{lookback}"
        
        # ① 命中缓存直接返回
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        # ② 查 SQLite
        data = self._query_from_db(symbol, limit=lookback)
        
        # ③ 数据不足 → 拉取远端（LOCAL 模式跳过）
        if len(data) < lookback and self.source != DataSource.LOCAL:
            end = datetime.now()
            start = end - timedelta(days=max(lookback * 2, 365))
            fetched = self._fetch_with_retry(symbol, start, end)
            if not fetched.empty:
                data = fetched.tail(lookback)
                # ⑥ 入队异步写入 SQLite，不阻塞当前返回
                self._persist_queue.put((symbol, fetched, None))
        
        # ④ 更新缓存
        self._cache[cache_key] = data
        self._cache_time[cache_key] = datetime.now()
        
        # ⑤ 返回
        return data

    def _persist_worker_loop(self) -> None:
        """
        后台单线程写入 Worker。
        消费 _persist_queue，串行写入 SQLite，避免大量并发写线程。
        队列元素：(symbol, df, frequency)
        """
        while True:
            try:
                item = self._persist_queue.get(timeout=1)
                symbol, df, frequency = item
                self._do_persist(symbol, df, frequency)
                self._persist_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"persist worker 异常: {e}")

    def _do_persist(self, symbol: str, df: pd.DataFrame,
                    frequency: 'Frequency' = None) -> None:
        """
        执行实际的 SQLite 写入（由 worker 线程调用）。
        异常只记录日志，不向上抛。
        """
        freq = frequency or Frequency.DAILY
        try:
            if freq == Frequency.DAILY:
                records = [
                    (
                        row['symbol'],
                        row['date'].strftime('%Y-%m-%d'),
                        row['open'], row['high'], row['low'], row['close'],
                        row['volume'], row.get('amount', 0)
                    )
                    for _, row in df.iterrows()
                ]
                sql = '''
                    INSERT OR REPLACE INTO ohlcv
                    (symbol, date, open, high, low, close, volume, amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                '''
                table = 'ohlcv'
            else:
                records = [
                    (
                        row['symbol'],
                        row['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
                        freq.value,
                        row['open'], row['high'], row['low'], row['close'],
                        row['volume'], row.get('amount', 0)
                    )
                    for _, row in df.iterrows()
                ]
                sql = '''
                    INSERT OR REPLACE INTO ohlcv_minute
                    (symbol, datetime, frequency, open, high, low, close, volume, amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                '''
                table = 'ohlcv_minute'

            with self._db_lock:
                conn = sqlite3.connect(self.db_path)
                try:
                    conn.executemany(sql, records)
                    conn.commit()
                    logger.debug(f"异步持久化完成: {symbol} {len(records)} 条 → {table}")
                finally:
                    conn.close()
        except Exception as e:
            logger.error(f"异步持久化失败: {symbol} — {e}")

    
    def get_history(self, symbol: str, 
                    start_date: datetime,
                    end_date: datetime) -> pd.DataFrame:
        """
        获取历史数据（带缓存，TTL=5分钟，适合回测反复读同一段数据）
        
        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            pd.DataFrame: OHLCV 数据
        """
        cache_key = (
            symbol,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )
        # 检查 history 缓存
        cached_time = self._history_cache_time.get(cache_key)
        if cached_time is not None:
            elapsed = (datetime.now() - cached_time).total_seconds()
            if elapsed < self._history_cache_ttl:
                return self._history_cache[cache_key]

        # 查 SQLite
        data = self._query_from_db(symbol, start_date=start_date, end_date=end_date)

        # 更新 history 缓存
        self._history_cache[cache_key] = data
        self._history_cache_time[cache_key] = datetime.now()

        return data
    
    def get_realtime(self, symbol: str) -> Dict[str, Any]:
        """
        获取实时行情
        
        Args:
            symbol: 股票代码
        
        Returns:
            Dict: 实时行情
        """
        provider = self._get_provider()
        last_exc = None
        for attempt in range(3):
            try:
                result = provider.fetch_realtime(symbol)
                if result:
                    return result
            except Exception as e:
                last_exc = e
                logger.warning(f"fetch_realtime 失败: {symbol}, 第{attempt+1}次, error={e}")
            if attempt < 2:
                time.sleep(1.0 * (2 ** attempt))
        logger.error(f"fetch_realtime 多次重试均失败: {symbol}, last_error={last_exc}")
        return {}
    
    def get_minute_data(self, symbol: str,
                        frequency: Frequency = Frequency.MIN_5,
                        start_date: datetime = None,
                        end_date: datetime = None,
                        limit: int = None) -> pd.DataFrame:
        """
        获取分时数据
        
        Args:
            symbol: 股票代码
            frequency: 数据频率
            start_date: 开始时间
            end_date: 结束时间
            limit: 返回条数限制
        """
        conn = sqlite3.connect(self.db_path)
        
        query = "SELECT * FROM ohlcv_minute WHERE symbol = ? AND frequency = ?"
        params: list = [symbol, frequency.value]
        
        if start_date:
            query += " AND datetime >= ?"
            params.append(start_date.strftime('%Y-%m-%d %H:%M:%S'))
        if end_date:
            query += " AND datetime <= ?"
            params.append(end_date.strftime('%Y-%m-%d %H:%M:%S'))
        
        query += " ORDER BY datetime ASC"
        
        if limit:
            query += f" LIMIT {limit}"
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        if not df.empty:
            df['datetime'] = pd.to_datetime(df['datetime'])
        return df
    
    def get_minute_stats(self, symbol: Optional[str] = None) -> List[Dict]:
        """获取分时数据统计信息"""
        conn = sqlite3.connect(self.db_path)
        
        query = """
            SELECT symbol, frequency, COUNT(*) as count,
                   MIN(datetime) as start_time, MAX(datetime) as end_time
            FROM ohlcv_minute
        """
        if symbol:
            query += " WHERE symbol = ?"
            params = (symbol,)
        else:
            params = ()
        
        query += " GROUP BY symbol, frequency ORDER BY symbol, frequency"
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df.to_dict('records')
    
    def sync(self, symbols: List[str] = None,
             start_date: datetime = None,
             end_date: datetime = None,
             progress_callback: callable = None,
             frequency: Frequency = Frequency.DAILY) -> int:
        """
        同步数据到本地
        
        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            progress_callback: 进度回调函数
            frequency: 数据频率 (daily/5min/15min/30min/60min)
        
        Returns:
            int: 同步的记录数
        """
        if symbols is None:
            symbols = self._get_tracked_symbols()
        
        if not symbols:
            logger.warning("无股票需要同步")
            return 0
        
        # 分时数据默认只同步最近 5 天
        if frequency != Frequency.DAILY:
            start = start_date or datetime.now() - timedelta(days=5)
        else:
            start = start_date or datetime.now() - timedelta(days=365)
        end = end_date or datetime.now()
        
        total_count = 0
        
        for i, symbol in enumerate(symbols):
            try:
                count = self._sync_symbol(symbol, start, end, frequency=frequency)
                total_count += count
                
                if progress_callback:
                    progress_callback((i + 1) / len(symbols) * 100)
                
            except Exception as e:
                logger.error(f"同步失败: {symbol}, error={e}")
        
        freq_label = frequency.value
        logger.info(f"同步完成 [{freq_label}]: {len(symbols)} 只股票, {total_count} 条数据")
        return total_count
    
    def get_data_stats(self, symbol: str = None) -> List[Dict]:
        """
        获取数据统计信息
        
        Args:
            symbol: 股票代码（可选）
        
        Returns:
            List[Dict]: 统计信息列表
        """
        conn = sqlite3.connect(self.db_path)
        
        query = """
            SELECT 
                symbol,
                COUNT(*) as count,
                MIN(date) as start_date,
                MAX(date) as end_date
            FROM ohlcv
        """
        
        if symbol:
            query += f" WHERE symbol = ?"
            params = (symbol,)
        else:
            params = ()
        
        query += " GROUP BY symbol ORDER BY symbol"
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        return df.to_dict('records')
    
    def clean(self, symbol: str = None, before_date: datetime = None) -> int:
        """
        清理数据
        
        Args:
            symbol: 股票代码（可选）
            before_date: 删除此日期之前的数据
        
        Returns:
            int: 删除的记录数
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        conditions = []
        params = []
        
        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)
        
        if before_date:
            conditions.append("date < ?")
            params.append(before_date.strftime('%Y-%m-%d'))
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        cursor.execute(f"DELETE FROM ohlcv WHERE {where_clause}", params)
        count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        logger.info(f"清理数据: {count} 条")
        return count
    
    def clear_cache(self) -> None:
        """清空所有内存缓存（get_latest 缓存 + get_history 缓存）"""
        self._cache.clear()
        self._cache_time.clear()
        self._history_cache.clear()
        self._history_cache_time.clear()

    def _fetch_with_retry(self, symbol: str, start: datetime, end: datetime,
                          frequency: Frequency = Frequency.DAILY,
                          max_retries: int = 3,
                          base_delay: float = 1.0) -> pd.DataFrame:
        """
        带重试的 Provider.fetch 包装。
        网络抖动时自动重试（指数退避），3次均失败返回空 DataFrame。

        Args:
            symbol: 股票代码
            start / end: 日期范围
            frequency: 数据频率
            max_retries: 最大重试次数（含第1次）
            base_delay: 首次重试等待秒数，之后翻倍
        """
        provider = self._get_provider()
        last_exc = None
        for attempt in range(max_retries):
            try:
                df = provider.fetch(symbol, start, end, frequency=frequency)
                if df is not None and not df.empty:
                    return df
                # 返回空 DataFrame 也视为失败，继续重试
                logger.warning(f"Provider 返回空数据: {symbol}, 第{attempt+1}次")
            except Exception as e:
                last_exc = e
                logger.warning(f"Provider.fetch 失败: {symbol}, 第{attempt+1}次, error={e}")
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.info(f"等待 {delay:.1f}s 后重试...")
                time.sleep(delay)
        logger.error(f"Provider.fetch 多次重试均失败: {symbol}, last_error={last_exc}")
        return pd.DataFrame()
    
    def _init_db(self) -> None:
        """初始化数据库"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS ohlcv (
                symbol TEXT NOT NULL,
                date DATE NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                amount REAL,
                PRIMARY KEY (symbol, date)
            )
        ''')
        
        # 分时数据表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS ohlcv_minute (
                symbol TEXT NOT NULL,
                datetime TEXT NOT NULL,
                frequency TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                amount REAL,
                PRIMARY KEY (symbol, datetime, frequency)
            )
        ''')
        
        # 创建索引
        conn.execute('CREATE INDEX IF NOT EXISTS idx_symbol ON ohlcv(symbol)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_date ON ohlcv(date)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_minute_symbol ON ohlcv_minute(symbol)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_minute_dt ON ohlcv_minute(datetime)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_minute_freq ON ohlcv_minute(frequency)')
        
        conn.commit()
        conn.close()
    
    def _get_provider(self) -> BaseDataProvider:
        """获取数据提供者（懒加载）"""
        if self._provider is None:
            if self.source == DataSource.LOCAL:
                # LOCAL 模式只读本地 SQLite，不需要 Provider
                # 调用方应先通过 sync() 或手动导入数据
                raise RuntimeError(
                    "当前数据源为 LOCAL，不支持从远端拉取数据。"
                    "请先调用 sync() 将数据写入本地，或切换为 AKSHARE / TUSHARE / BAOSTOCK。"
                )
            elif self.source == DataSource.TUSHARE:
                self._provider = TushareProvider(self.config.get('tushare_token'))
            elif self.source == DataSource.AKSHARE:
                self._provider = AkshareProvider()
            elif self.source == DataSource.BAOSTOCK:
                self._provider = BaostockProvider()
            else:
                raise ValueError(f"不支持的数据源: {self.source}")
        
        return self._provider
    
    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self._cache:
            return False
        
        cache_time = self._cache_time.get(key)
        if cache_time is None:
            return False
        
        elapsed = (datetime.now() - cache_time).total_seconds()
        return elapsed < self._cache_ttl
    
    def _query_from_db(self, symbol: str, 
                       start_date: datetime = None,
                       end_date: datetime = None,
                       limit: int = None) -> pd.DataFrame:
        """从数据库查询数据"""
        conn = sqlite3.connect(self.db_path)
        
        query = "SELECT * FROM ohlcv WHERE symbol = ?"
        params = [symbol]
        
        if start_date:
            query += " AND date >= ?"
            params.append(start_date.strftime('%Y-%m-%d'))
        
        if end_date:
            query += " AND date <= ?"
            params.append(end_date.strftime('%Y-%m-%d'))
        
        query += " ORDER BY date ASC"
        
        if limit:
            query = f"""
                SELECT * FROM (
                    SELECT * FROM ohlcv WHERE symbol = ?
                    ORDER BY date DESC
                    LIMIT ?
                ) ORDER BY date ASC
            """
            params = [symbol, limit]
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
        
        return df
    
    def _sync_symbol(self, symbol: str,
                     start_date: datetime = None,
                     end_date: datetime = None,
                     frequency: Frequency = Frequency.DAILY) -> int:
        """同步单个股票数据"""
        start = start_date or datetime.now() - timedelta(days=365)
        end = end_date or datetime.now()
        
        # 获取数据（带重试）
        df = self._fetch_with_retry(symbol, start, end, frequency=frequency)
        
        if df.empty:
            logger.warning(f"未获取到数据: {symbol} [{frequency.value}]")
            return 0
        
        with self._db_lock:
            conn = sqlite3.connect(self.db_path)
            try:
                if frequency == Frequency.DAILY:
                    # 日线存 ohlcv 表 — 批量写入
                    records = [
                        (
                            row['symbol'],
                            row['date'].strftime('%Y-%m-%d'),
                            row['open'], row['high'], row['low'], row['close'],
                            row['volume'], row.get('amount', 0)
                        )
                        for _, row in df.iterrows()
                    ]
                    conn.executemany('''
                        INSERT OR REPLACE INTO ohlcv 
                        (symbol, date, open, high, low, close, volume, amount)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', records)
                else:
                    # 分时存 ohlcv_minute 表 — 批量写入
                    records = [
                        (
                            row['symbol'],
                            row['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
                            frequency.value,
                            row['open'], row['high'], row['low'], row['close'],
                            row['volume'], row.get('amount', 0)
                        )
                        for _, row in df.iterrows()
                    ]
                    conn.executemany('''
                        INSERT OR REPLACE INTO ohlcv_minute
                        (symbol, datetime, frequency, open, high, low, close, volume, amount)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', records)
                conn.commit()
            finally:
                conn.close()
        
        logger.info(f"同步完成: {symbol} [{frequency.value}], {len(df)} 条数据")
        return len(df)
    
    def _get_tracked_symbols(self) -> List[str]:
        """获取已追踪的股票列表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM ohlcv")
        symbols = [row[0] for row in cursor.fetchall()]
        conn.close()
        return symbols
