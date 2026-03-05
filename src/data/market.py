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
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class DataSource(Enum):
    """数据源类型"""
    TUSHARE = "tushare"
    AKSHARE = "akshare"
    BAOSTOCK = "baostock"
    LOCAL = "local"


class BaseDataProvider(ABC):
    """数据提供者基类"""
    
    @abstractmethod
    def fetch(self, symbol: str, start_date: datetime, 
              end_date: datetime) -> pd.DataFrame:
        """
        获取历史数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
        
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
              end_date: datetime) -> pd.DataFrame:
        """获取历史数据"""
        api = self._get_api()
        
        # 转换日期格式
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        
        # 获取日线数据
        df = api.daily(
            ts_code=symbol,
            start_date=start_str,
            end_date=end_str
        )
        
        if df is None or df.empty:
            return pd.DataFrame()
        
        # 标准化列名
        df = df.rename(columns={
            'ts_code': 'symbol',
            'trade_date': 'date',
            'vol': 'volume',
            'amount': 'amount'
        })
        
        # 转换日期类型
        df['date'] = pd.to_datetime(df['date'])
        
        # 按日期升序排列
        df = df.sort_values('date').reset_index(drop=True)
        
        return df[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount']]
    
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
              end_date: datetime) -> pd.DataFrame:
        """获取历史数据"""
        try:
            import akshare as ak
        except ImportError:
            raise ImportError("请安装 akshare: pip install akshare")
        
        # AKShare 使用不同的股票代码格式
        # 转换: 000001.SZ -> sz000001
        code = symbol.split('.')[0]
        market = symbol.split('.')[1].lower()
        ak_symbol = f"{market}{code}"
        
        # 获取日线数据
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date.strftime('%Y%m%d'),
            end_date=end_date.strftime('%Y%m%d'),
            adjust="qfq"  # 前复权
        )
        
        if df is None or df.empty:
            return pd.DataFrame()
        
        # 标准化列名
        df = df.rename(columns={
            '日期': 'date',
            '开盘': 'open',
            '最高': 'high',
            '最低': 'low',
            '收盘': 'close',
            '成交量': 'volume',
            '成交额': 'amount'
        })
        
        df['symbol'] = symbol
        df['date'] = pd.to_datetime(df['date'])
        
        return df[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount']]
    
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
              end_date: datetime) -> pd.DataFrame:
        """获取历史数据"""
        self._login()
        
        import baostock as bs
        
        # 转换股票代码
        bs_symbol = self._convert_symbol(symbol)
        
        # 获取日线数据
        rs = bs.query_history_k_data_plus(
            bs_symbol,
            "date,open,high,low,close,volume,amount",
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            frequency="d",
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
        
        df = pd.DataFrame(data_list, columns=['date', 'open', 'high', 'low', 'close', 'volume', 'amount'])
        
        # 转换数据类型
        df['symbol'] = symbol
        df['date'] = pd.to_datetime(df['date'])
        df['open'] = pd.to_numeric(df['open'], errors='coerce')
        df['high'] = pd.to_numeric(df['high'], errors='coerce')
        df['low'] = pd.to_numeric(df['low'], errors='coerce')
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        
        return df[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount']]
    
    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取实时行情（BaoStock 不支持实时行情，返回最新日线数据）"""
        end = datetime.now()
        start = end - timedelta(days=7)
        
        df = self.fetch(symbol, start, end)
        
        if df.empty:
            return {}
        
        row = df.iloc[-1]
        return {
            'symbol': symbol,
            'price': row['close'],
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'volume': row['volume'],
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
        
        # 内存缓存
        self._cache: Dict[str, pd.DataFrame] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = 60  # 缓存有效期（秒）
        
        # 数据提供者
        self._provider: BaseDataProvider = None
        
        # 初始化数据库
        self._init_db()
        
        logger.info(f"初始化数据服务: source={source.value}, db={db_path}")
    
    def get_latest(self, symbol: str, lookback: int = 100) -> pd.DataFrame:
        """
        获取最新行情数据
        
        优先从缓存获取，缓存过期则从数据库获取
        
        Args:
            symbol: 股票代码
            lookback: 回溯条数
        
        Returns:
            pd.DataFrame: OHLCV 数据
        """
        cache_key = f"{symbol}_{lookback}"
        
        # 检查缓存
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        # 从数据库获取
        data = self._query_from_db(symbol, limit=lookback)
        
        # 如果数据不足，尝试同步
        if len(data) < lookback:
            self._sync_symbol(symbol)
            data = self._query_from_db(symbol, limit=lookback)
        
        # 更新缓存
        self._cache[cache_key] = data
        self._cache_time[cache_key] = datetime.now()
        
        return data
    
    def get_history(self, symbol: str, 
                    start_date: datetime,
                    end_date: datetime) -> pd.DataFrame:
        """
        获取历史数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            pd.DataFrame: OHLCV 数据
        """
        return self._query_from_db(symbol, start_date=start_date, end_date=end_date)
    
    def get_realtime(self, symbol: str) -> Dict[str, Any]:
        """
        获取实时行情
        
        Args:
            symbol: 股票代码
        
        Returns:
            Dict: 实时行情
        """
        provider = self._get_provider()
        return provider.fetch_realtime(symbol)
    
    def sync(self, symbols: List[str] = None,
             start_date: datetime = None,
             end_date: datetime = None,
             progress_callback: callable = None) -> int:
        """
        同步数据到本地
        
        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            progress_callback: 进度回调函数
        
        Returns:
            int: 同步的记录数
        """
        if symbols is None:
            symbols = self._get_tracked_symbols()
        
        if not symbols:
            logger.warning("无股票需要同步")
            return 0
        
        start = start_date or datetime.now() - timedelta(days=365)
        end = end_date or datetime.now()
        
        total_count = 0
        
        for i, symbol in enumerate(symbols):
            try:
                count = self._sync_symbol(symbol, start, end)
                total_count += count
                
                if progress_callback:
                    progress_callback((i + 1) / len(symbols) * 100)
                
            except Exception as e:
                logger.error(f"同步失败: {symbol}, error={e}")
        
        logger.info(f"同步完成: {len(symbols)} 只股票, {total_count} 条数据")
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
        """清空缓存"""
        self._cache.clear()
        self._cache_time.clear()
    
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
        
        # 创建索引
        conn.execute('CREATE INDEX IF NOT EXISTS idx_symbol ON ohlcv(symbol)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_date ON ohlcv(date)')
        
        conn.commit()
        conn.close()
    
    def _get_provider(self) -> BaseDataProvider:
        """获取数据提供者"""
        if self._provider is None:
            if self.source == DataSource.TUSHARE:
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
                     end_date: datetime = None) -> int:
        """同步单个股票数据"""
        start = start_date or datetime.now() - timedelta(days=365)
        end = end_date or datetime.now()
        
        # 获取数据
        provider = self._get_provider()
        df = provider.fetch(symbol, start, end)
        
        if df.empty:
            logger.warning(f"未获取到数据: {symbol}")
            return 0
        
        # 保存到数据库
        conn = sqlite3.connect(self.db_path)
        
        # 使用 REPLACE 处理重复数据
        for _, row in df.iterrows():
            conn.execute('''
                INSERT OR REPLACE INTO ohlcv 
                (symbol, date, open, high, low, close, volume, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                row['symbol'],
                row['date'].strftime('%Y-%m-%d'),
                row['open'],
                row['high'],
                row['low'],
                row['close'],
                row['volume'],
                row.get('amount', 0)
            ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"同步完成: {symbol}, {len(df)} 条数据")
        return len(df)
    
    def _get_tracked_symbols(self) -> List[str]:
        """获取已追踪的股票列表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM ohlcv")
        symbols = [row[0] for row in cursor.fetchall()]
        conn.close()
        return symbols
