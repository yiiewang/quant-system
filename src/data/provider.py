"""
数据提供者基类和实现

提供各种数据源的 Provider 实现。
"""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging

import pandas as pd

logger = logging.getLogger(__name__)


class Frequency:
    """数据频率（简化版）"""
    MIN_1 = "1min"
    MIN_5 = "5min"
    MIN_15 = "15min"
    MIN_30 = "30min"
    MIN_60 = "60min"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class BaseDataProvider(ABC):
    """数据提供者基类"""
    
    @abstractmethod
    def fetch(self, symbol: str, start_date: datetime,
              end_date: datetime,
              frequency: str = Frequency.DAILY) -> pd.DataFrame:
        """获取历史数据"""
        pass
    
    @abstractmethod
    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取实时行情"""
        pass


class TushareProvider(BaseDataProvider):
    """Tushare 数据提供者"""
    
    def __init__(self, token: Optional[str] = None):
        self.token = token
        self._api = None
    
    def _get_api(self):
        """获取 API 实例"""
        if self._api is None:
            import tushare as ts
            ts.set_token(self.token)
            self._api = ts.pro_api()
        return self._api
    
    def fetch(self, symbol: str, start_date: datetime,
              end_date: datetime,
              frequency: str = Frequency.DAILY) -> pd.DataFrame:
        """获取历史数据"""
        api = self._get_api()
        
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        
        if frequency == Frequency.DAILY:
            df = api.daily(ts_code=symbol, start_date=start_str, end_date=end_str)
        else:
            freq_map = {
                Frequency.MIN_5: '5min',
                Frequency.MIN_15: '15min',
                Frequency.MIN_30: '30min',
                Frequency.MIN_60: '60min',
            }
            df = api.stk_mins(ts_code=symbol, start_date=start_str, end_date=end_str,
                             freq=freq_map.get(frequency, '5min'))
        
        if df is None or df.empty:
            return pd.DataFrame()
        
        # 标准化列名
        df = df.rename(columns={
            'ts_code': 'symbol',
            'trade_date': 'date',
            'trade_time': 'datetime',
            'vol': 'volume',
            'amount': 'amount'
        })
        df['date'] = pd.to_datetime(df['date'] if 'date' in df.columns else df['datetime'])
        df = df.sort_values('date').reset_index(drop=True)

        return pd.DataFrame(df[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount']])
    
    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取实时行情"""
        api = self._get_api()
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
              frequency: str = Frequency.DAILY) -> pd.DataFrame:
        """获取历史数据"""
        import akshare as ak
        
        code = symbol.split('.')[0]
        
        if frequency in (Frequency.DAILY, Frequency.WEEKLY, Frequency.MONTHLY):
            period = frequency
            df = ak.stock_zh_a_hist(symbol=code, period=period,
                                   start_date=start_date.strftime('%Y%m%d'),
                                   end_date=end_date.strftime('%Y%m%d'),
                                   adjust="qfq")
            df = df.rename(columns={
                '日期': 'date', '开盘': 'open', '最高': 'high',
                '最低': 'low', '收盘': 'close', '成交量': 'volume', '成交额': 'amount'
            })
            df['symbol'] = symbol
            df['date'] = pd.to_datetime(df['date'])
        else:
            # 分钟数据
            freq_map = {Frequency.MIN_1: '1', Frequency.MIN_5: '5', 
                       Frequency.MIN_15: '15', Frequency.MIN_30: '30', Frequency.MIN_60: '60'}
            df = ak.stock_zh_a_hist_min_em(symbol=code, period=freq_map.get(frequency, '5'),
                                          adjust="qfq")
            df = df.rename(columns={
                '时间': 'date', '开盘': 'open', '最高': 'high',
                '最低': 'low', '收盘': 'close', '成交量': 'volume', '成交额': 'amount'
            })
            df['symbol'] = symbol
            df['date'] = pd.to_datetime(df['date'])
        
        return df[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount']]
    
    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取实时行情"""
        import akshare as ak
        
        code = symbol.split('.')[0]
        df = ak.stock_zh_a_spot_em()
        row = df[df['代码'] == code]
        
        if row.empty:
            return {}
        
        row = row.iloc[0]
        return {
            'symbol': symbol,
            'price': float(row['最新价']),
            'open': float(row['今开']),
            'high': float(row['最高']),
            'low': float(row['最低']),
            'volume': float(row['成交量']),
        }


class BaostockProvider(BaseDataProvider):
    """BaoStock 数据提供者"""
    
    def __init__(self):
        self._logged_in = False
    
    def _login(self):
        """登录 BaoStock"""
        if not self._logged_in:
            import baostock as bs
            import sys
            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                lg = bs.login()
            finally:
                sys.stdout = old_stdout
            if lg.error_code != '0':
                raise ConnectionError(f"BaoStock 登录失败: {lg.error_msg}")
            self._logged_in = True
    
    def _convert_symbol(self, symbol: str) -> str:
        """转换股票代码格式 000001.SZ -> sz.000001"""
        code, market = symbol.split('.')
        return f"{market.lower()}.{code}"
    
    def fetch(self, symbol: str, start_date: datetime,
              end_date: datetime,
              frequency: str = Frequency.DAILY) -> pd.DataFrame:
        """获取历史数据"""
        self._login()
        
        import baostock as bs
        
        bs_symbol = self._convert_symbol(symbol)
        
        if frequency == Frequency.DAILY:
            bs_freq = "d"
            fields = "date,open,high,low,close,volume,amount"
        else:
            freq_map = {
                Frequency.MIN_5: "5", Frequency.MIN_15: "15",
                Frequency.MIN_30: "30", Frequency.MIN_60: "60"
            }
            bs_freq = freq_map.get(frequency, "5")
            fields = "time,open,high,low,close,volume,amount"
        
        rs = bs.query_history_k_data_plus(
            bs_symbol, fields,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            frequency=bs_freq, adjustflag="2"
        )

        if rs is None:
            raise RuntimeError("获取数据失败: 返回值为 None")

        if rs.error_code != '0':
            raise RuntimeError(f"获取数据失败: {rs.error_msg}")

        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())
        
        if not data_list:
            return pd.DataFrame()
        
        df = pd.DataFrame(data_list, columns=fields.split(','))
        df['symbol'] = symbol
        for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        if frequency == Frequency.DAILY:
            df['date'] = pd.to_datetime(df['date'])
        else:
            df['date'] = pd.to_datetime(df['time'].str[:14], format='%Y%m%d%H%M%S')

        return pd.DataFrame(df[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount']])
    
    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取实时行情（降级为最新日线）"""
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
            'source': 'daily_close'
        }


class YFinanceProvider(BaseDataProvider):
    """YFinance 数据提供者（美股/港股）"""

    def fetch(self, symbol: str, start_date: datetime,
              end_date: datetime,
              frequency: str = Frequency.DAILY) -> pd.DataFrame:
        """获取历史数据"""
        import yfinance as yf
        
        ticker = yf.Ticker(symbol)
        
        interval_map = {
            Frequency.MIN_1: "1m", Frequency.MIN_5: "5m",
            Frequency.MIN_15: "15m", Frequency.MIN_30: "30m",
            Frequency.MIN_60: "60m", Frequency.DAILY: "1d",
            Frequency.WEEKLY: "1wk", Frequency.MONTHLY: "1mo"
        }
        interval = interval_map.get(frequency, "1d")
        
        # 分钟数据限制 7 天
        if frequency in (Frequency.MIN_1, Frequency.MIN_5, Frequency.MIN_15,
                        Frequency.MIN_30, Frequency.MIN_60):
            start_date = max(start_date, datetime.now() - timedelta(days=7))
        
        df = ticker.history(start=start_date.strftime('%Y-%m-%d'),
                           end=end_date.strftime('%Y-%m-%d'),
                           interval=interval)
        
        if df.empty:
            return pd.DataFrame()
        
        df = df.reset_index()
        df = df.rename(columns={
            'Date': 'date', 'Datetime': 'date',
            'Open': 'open', 'High': 'high',
            'Low': 'low', 'Close': 'close', 'Volume': 'volume'
        })
        df['symbol'] = symbol
        date_series = pd.to_datetime(df['date'])
        df['date'] = date_series.apply(lambda x: x.tz_localize(None) if x.tzinfo else x)  # type: ignore[arg-type]

        return pd.DataFrame(df[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume']])
    
    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取实时行情"""
        import yfinance as yf
        
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        return {
            'symbol': symbol,
            'price': info.get('currentPrice') or info.get('regularMarketPrice', 0),
            'open': info.get('regularMarketOpen', 0),
            'high': info.get('dayHigh') or info.get('regularMarketDayHigh', 0),
            'low': info.get('dayLow') or info.get('regularMarketDayLow', 0),
            'volume': info.get('regularMarketVolume', 0),
        }
