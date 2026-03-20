"""
指标计算器
提供常用技术指标的计算功能
"""
from typing import Dict, Optional
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class IndicatorCalculator:
    """
    技术指标计算器
    
    提供各类技术指标的计算方法，所有方法都返回添加了指标列的 DataFrame
    
    Usage:
        calc = IndicatorCalculator()
        
        # 计算单个指标
        data = calc.macd(data)
        data = calc.rsi(data)
        
        # 计算多个指标
        data = calc.calculate(data, ['macd', 'rsi', 'bollinger'])
    """
    
    def __init__(self):
        # 注册可用的指标计算方法
        self._indicators = {
            'macd': self.macd,
            'rsi': self.rsi,
            'bollinger': self.bollinger,
            'ma': self.ma,
            'ema': self.ema,
            'kdj': self.kdj,
            'atr': self.atr,
            'volume_ma': self.volume_ma,
        }
    
    def calculate(self, data: pd.DataFrame,
                  indicators: list,
                  params: Optional[Dict[str, Dict]] = None) -> pd.DataFrame:
        """
        批量计算指标
        
        Args:
            data: OHLCV 数据
            indicators: 指标名称列表
            params: 各指标的参数
        
        Returns:
            pd.DataFrame: 添加了指标列的数据
        """
        params = params or {}
        df = data.copy()
        
        for indicator in indicators:
            if indicator in self._indicators:
                indicator_params = params.get(indicator, {})
                df = self._indicators[indicator](df, **indicator_params)
            else:
                logger.warning(f"未知指标: {indicator}")
        
        return df
    
    def macd(self, data: pd.DataFrame,
             fast_period: int = 12,
             slow_period: int = 26,
             signal_period: int = 9) -> pd.DataFrame:
        """
        计算 MACD 指标
        
        Args:
            data: OHLCV 数据
            fast_period: 快线周期
            slow_period: 慢线周期
            signal_period: 信号线周期
        
        Returns:
            pd.DataFrame: 添加 macd, signal, histogram 列
        """
        df = data.copy()
        
        # 计算 EMA
        ema_fast = df['close'].ewm(span=fast_period, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow_period, adjust=False).mean()
        
        # MACD = 快线 - 慢线
        df['macd'] = ema_fast - ema_slow
        
        # Signal = MACD 的 EMA
        df['signal'] = df['macd'].ewm(span=signal_period, adjust=False).mean()
        
        # Histogram = MACD - Signal
        df['histogram'] = df['macd'] - df['signal']
        
        # 金叉/死叉标记
        df['macd_cross'] = 0
        df.loc[
            (df['macd'] > df['signal']) & 
            (df['macd'].shift(1) <= df['signal'].shift(1)),
            'macd_cross'
        ] = 1  # 金叉
        df.loc[
            (df['macd'] < df['signal']) & 
            (df['macd'].shift(1) >= df['signal'].shift(1)),
            'macd_cross'
        ] = -1  # 死叉
        
        return df
    
    def rsi(self, data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        计算 RSI 指标
        
        Args:
            data: OHLCV 数据
            period: 计算周期
        
        Returns:
            pd.DataFrame: 添加 rsi 列
        """
        df = data.copy()
        
        # 计算涨跌
        delta = df['close'].diff()
        
        # 分离涨跌
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)
        
        # 计算平均涨跌
        avg_gain = gain.ewm(span=period, adjust=False).mean()
        avg_loss = loss.ewm(span=period, adjust=False).mean()
        
        # 计算 RS 和 RSI
        rs = avg_gain / avg_loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        return df
    
    def bollinger(self, data: pd.DataFrame,
                  period: int = 20,
                  std_dev: float = 2.0) -> pd.DataFrame:
        """
        计算布林带指标
        
        Args:
            data: OHLCV 数据
            period: 均线周期
            std_dev: 标准差倍数
        
        Returns:
            pd.DataFrame: 添加 bb_upper, bb_middle, bb_lower, bb_width 列
        """
        df = data.copy()
        
        # 中轨 = SMA
        df['bb_middle'] = df['close'].rolling(window=period).mean()
        
        # 标准差
        std = df['close'].rolling(window=period).std()
        
        # 上轨和下轨
        df['bb_upper'] = df['bb_middle'] + (std * std_dev)
        df['bb_lower'] = df['bb_middle'] - (std * std_dev)
        
        # 带宽
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
        
        # %B 指标（当前价格在带中的位置）
        df['bb_percent'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        
        return df
    
    def ma(self, data: pd.DataFrame,
           periods: Optional[list] = None) -> pd.DataFrame:
        """
        计算移动平均线
        
        Args:
            data: OHLCV 数据
            periods: 周期列表，如 [5, 10, 20, 60]
        
        Returns:
            pd.DataFrame: 添加 ma{period} 列
        """
        df = data.copy()
        periods = periods or [5, 10, 20, 60]
        
        for period in periods:
            df[f'ma{period}'] = df['close'].rolling(window=period).mean()
        
        return df
    
    def ema(self, data: pd.DataFrame,
            periods: Optional[list] = None) -> pd.DataFrame:
        """
        计算指数移动平均线
        
        Args:
            data: OHLCV 数据
            periods: 周期列表
        
        Returns:
            pd.DataFrame: 添加 ema{period} 列
        """
        df = data.copy()
        periods = periods or [12, 26]
        
        for period in periods:
            df[f'ema{period}'] = df['close'].ewm(span=period, adjust=False).mean()
        
        return df
    
    def kdj(self, data: pd.DataFrame,
            n: int = 9,
            m1: int = 3,
            m2: int = 3) -> pd.DataFrame:
        """
        计算 KDJ 指标
        
        Args:
            data: OHLCV 数据
            n: RSV 周期
            m1: K 值平滑周期
            m2: D 值平滑周期
        
        Returns:
            pd.DataFrame: 添加 k, d, j 列
        """
        df = data.copy()
        
        # 计算 RSV
        low_min = df['low'].rolling(window=n).min()
        high_max = df['high'].rolling(window=n).max()
        
        rsv = (df['close'] - low_min) / (high_max - low_min) * 100
        
        # 计算 K 和 D
        df['k'] = rsv.ewm(span=m1, adjust=False).mean()
        df['d'] = df['k'].ewm(span=m2, adjust=False).mean()
        df['j'] = 3 * df['k'] - 2 * df['d']
        
        return df
    
    def atr(self, data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        计算 ATR（平均真实波幅）
        
        Args:
            data: OHLCV 数据
            period: 计算周期
        
        Returns:
            pd.DataFrame: 添加 atr 列
        """
        df = data.copy()
        
        # 计算真实波幅
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift(1))
        low_close = abs(df['low'] - df['close'].shift(1))
        
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # 计算 ATR
        df['atr'] = tr.rolling(window=period).mean()
        
        return df
    
    def volume_ma(self, data: pd.DataFrame,
                  periods: Optional[list] = None) -> pd.DataFrame:
        """
        计算成交量均线
        
        Args:
            data: OHLCV 数据
            periods: 周期列表
        
        Returns:
            pd.DataFrame: 添加 vol_ma{period} 和 vol_ratio 列
        """
        df = data.copy()
        periods = periods or [5, 20]
        
        for period in periods:
            df[f'vol_ma{period}'] = df['volume'].rolling(window=period).mean()
        
        # 成交量比率（相对于20日均量）
        if 20 in periods:
            df['vol_ratio'] = df['volume'] / df['vol_ma20']
        
        return df
    
    def trend_strength(self, data: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """
        计算趋势强度
        
        使用 ADX（平均方向指数）衡量趋势强度
        
        Args:
            data: OHLCV 数据
            period: 计算周期
        
        Returns:
            pd.DataFrame: 添加 adx, plus_di, minus_di 列
        """
        df = data.copy()
        
        # 计算 +DM 和 -DM
        up_move = df['high'].diff()
        down_move = -df['low'].diff()
        
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)
        
        # 计算 ATR
        df = self.atr(df, period)
        
        # 计算 +DI 和 -DI
        plus_di = 100 * plus_dm.ewm(span=period, adjust=False).mean() / df['atr']
        minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / df['atr']
        
        df['plus_di'] = plus_di
        df['minus_di'] = minus_di
        
        # 计算 DX 和 ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        df['adx'] = dx.ewm(span=period, adjust=False).mean()
        
        return df
    
    def support_resistance(self, data: pd.DataFrame, 
                           lookback: int = 20) -> Dict[str, float]:
        """
        计算支撑位和阻力位
        
        Args:
            data: OHLCV 数据
            lookback: 回溯周期
        
        Returns:
            Dict: 包含 support 和 resistance
        """
        recent = data.tail(lookback)
        
        return {
            'resistance': recent['high'].max(),
            'support': recent['low'].min(),
            'pivot': (recent['high'].max() + recent['low'].min() + recent['close'].iloc[-1]) / 3
        }
