# pyright: reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false
"""
周线级别 MACD 策略实现
只在周线级别进行交易，降低交易频率，捕捉中期趋势

策略核心思想：
- 将日线数据重采样为周线数据
- 基于周线 MACD 金叉/死叉信号进行交易
- 信号产生后在下一周开盘执行
"""
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
import logging

from .base import (
    BaseStrategy, StrategyContext,
    create_buy_signal, create_sell_signal, create_hold_signal
)
from src.core.models import Signal, AnalysisResult

logger = logging.getLogger(__name__)


class WeeklyMACDStrategy(BaseStrategy):
    """
    周线级别 MACD 策略
    
    策略逻辑:
    1. 将日线数据重采样为周线数据
    2. 计算周线 MACD 指标
    3. 周线金叉 → 买入
    4. 周线死叉 → 卖出
    
    特点:
    - 交易频率低，适合中长期投资
    - 过滤日线噪音，捕捉大趋势
    - 持仓周期长，减少手续费损耗
    
    参数:
    - fast_period: 快速EMA周期（默认12）
    - slow_period: 慢速EMA周期（默认26）
    - signal_period: 信号线周期（默认9）
    """
    
    name = "WeeklyMACD"
    version = "1.0.0"
    author = "Quant Team"
    description = "基于周线MACD的中期趋势策略"
    
    @classmethod
    def default_params(cls) -> Dict[str, Any]:
        """默认参数"""
        return {
            'fast_period': 12,
            'slow_period': 26,
            'signal_period': 9,
            'volume_confirm': False,  # 周线不使用量价确认
            'volume_ratio': 1.3,
            'min_data_length': 60,
        }
    
    @classmethod
    def param_schema(cls) -> Dict[str, Any]:
        """参数模式"""
        return {
            'fast_period': {
                'type': 'int',
                'default': 12,
                'min': 2,
                'max': 50,
                'description': '快速EMA周期'
            },
            'slow_period': {
                'type': 'int',
                'default': 26,
                'min': 10,
                'max': 100,
                'description': '慢速EMA周期'
            },
            'signal_period': {
                'type': 'int',
                'default': 9,
                'min': 2,
                'max': 50,
                'description': '信号线周期'
            },
        }
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        """初始化策略"""
        super().__init__(params)
        # 缓存周线数据
        self._weekly_data: Optional[pd.DataFrame] = None
        self._last_weekly_signal: Optional[str] = None  # 记录上一个周线信号
        self._last_week_end: Optional[pd.Timestamp] = None  # 上一周结束日期
    
    def resample_to_weekly(self, daily_data: pd.DataFrame) -> pd.DataFrame:
        """
        将日线数据重采样为周线数据
        
        Args:
            daily_data: 日线OHLCV数据，需要有DatetimeIndex
        
        Returns:
            周线OHLCV数据
        """
        df = daily_data.copy()
        
        # 确保索引是DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')
            elif 'trade_date' in df.columns:
                df['trade_date'] = pd.to_datetime(df['trade_date'])
                df = df.set_index('trade_date')
        
        # 重采样规则 - 使用周五作为周线结束
        weekly = df.resample('W-FRI').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        return weekly
    
    def calculate_macd(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        计算MACD指标
        
        Args:
            data: OHLCV数据
        
        Returns:
            添加了MACD指标的DataFrame
        """
        df = data.copy()
        
        fast = self.params['fast_period']
        slow = self.params['slow_period']
        signal = self.params['signal_period']
        
        # 计算 EMA
        df['ema_fast'] = df['close'].ewm(span=fast, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=slow, adjust=False).mean()
        
        # 计算 MACD
        df['macd'] = df['ema_fast'] - df['ema_slow']  # DIF
        df['signal'] = df['macd'].ewm(span=signal, adjust=False).mean()  # DEA
        df['histogram'] = 2 * (df['macd'] - df['signal'])  # MACD Bar
        
        # 金叉/死叉状态
        df['is_golden'] = df['macd'] > df['signal']  # 金叉状态
        df['is_death'] = df['macd'] < df['signal']   # 死叉状态
        
        # 金叉/死叉信号（转折点）
        df['golden_cross'] = (df['is_golden']) & (~df['is_golden'].shift(1).fillna(False))
        df['death_cross'] = (df['is_death']) & (~df['is_death'].shift(1).fillna(False))
        
        return df
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        计算周线指标
        
        Args:
            data: 日线OHLCV数据
        
        Returns:
            原始日线数据（指标在周线数据上计算）
        """
        # 生成周线数据并计算指标
        try:
            self._weekly_data = self.resample_to_weekly(data)
            if len(self._weekly_data) >= self.params['slow_period']:
                self._weekly_data = self.calculate_macd(self._weekly_data)
                logger.debug(f"周线数据计算完成: {len(self._weekly_data)} 周")
            else:
                logger.warning(f"周线数据不足: {len(self._weekly_data)} 条")
        except Exception as e:
            logger.error(f"计算周线指标失败: {e}")
        
        # 返回原始日线数据（用于获取价格）
        return data
    
    def _get_current_week_end(self, current_date: pd.Timestamp) -> pd.Timestamp:
        """获取当前日期所属周的周末（周五）"""
        # 找到该周的周五
        days_until_friday = (4 - current_date.weekday()) % 7
        if current_date.weekday() > 4:  # 如果是周六或周日
            days_until_friday = 4 - current_date.weekday() + 7
        return current_date + pd.Timedelta(days=days_until_friday)
    
    def generate_signal(self, data: pd.DataFrame, context: StrategyContext) -> Signal:
        """
        生成交易信号
        
        周线策略逻辑:
        1. 只在每周结束时检查周线 MACD 信号
        2. 周线金叉 → 买入
        3. 周线死叉 → 卖出
        
        Args:
            data: 日线数据（用于获取当前价格）
            context: 策略上下文
        
        Returns:
            Signal: 交易信号
        """
        if self._weekly_data is None or len(self._weekly_data) < self.params['slow_period']:
            logger.warning("周线数据不足")
            return create_hold_signal(context.symbol, data['close'].iloc[-1], "周线数据不足")
        
        # 获取当前日期和价格
        current_date = data.index[-1] if isinstance(data.index, pd.DatetimeIndex) else pd.to_datetime(data.iloc[-1].get('date', data.iloc[-1].name))
        price = data['close'].iloc[-1]
        
        # 获取最新的完整周线数据
        # 找到当前日期之前最近的完整周
        weekly_data_before_current = self._weekly_data[self._weekly_data.index <= current_date]
        
        if len(weekly_data_before_current) < 2:
            return create_hold_signal(context.symbol, price, "周线数据不足")
        
        # 获取最新周线指标
        latest_weekly = weekly_data_before_current.iloc[-1]
        weekly_macd = latest_weekly['macd']
        weekly_signal = latest_weekly['signal']
        weekly_is_golden = latest_weekly['is_golden']
        weekly_golden_cross = latest_weekly['golden_cross']
        weekly_death_cross = latest_weekly['death_cross']
        weekly_histogram = latest_weekly['histogram']
        
        # 构建元数据
        metadata = {
            'weekly_macd': round(weekly_macd, 4),
            'weekly_signal': round(weekly_signal, 4),
            'weekly_histogram': round(weekly_histogram, 4),
            'weekly_is_golden': weekly_is_golden,
            'weekly_date': str(weekly_data_before_current.index[-1].date()),
        }
        
        # ===== 卖出信号检查 =====
        if context.position and context.position.quantity > 0:
            # 周线死叉 - 卖出
            if weekly_death_cross:
                return create_sell_signal(
                    symbol=context.symbol,
                    price=price,
                    strength=0.9,
                    reason=f"周线死叉卖出 | MACD={weekly_macd:.4f}",
                    **metadata
                )
            
            # 周线处于死叉状态 - 也卖出
            if not weekly_is_golden:
                return create_sell_signal(
                    symbol=context.symbol,
                    price=price,
                    strength=0.8,
                    reason=f"周线死叉状态，清仓 | MACD={weekly_macd:.4f}",
                    **metadata
                )
        
        # ===== 买入信号检查 =====
        # 周线金叉 - 买入
        if weekly_golden_cross:
            # 计算信号强度
            strength = 0.8
            
            # 零轴下方金叉，强度更高（超卖反弹）
            if weekly_macd < 0:
                strength = 0.9
            
            # MACD 柱向上扩张
            if len(weekly_data_before_current) >= 2:
                prev_hist = weekly_data_before_current.iloc[-2]['histogram']
                if weekly_histogram > prev_hist:
                    strength = min(1.0, strength + 0.1)
            
            return create_buy_signal(
                symbol=context.symbol,
                price=price,
                strength=strength,
                reason=f"周线金叉买入 | MACD={weekly_macd:.4f}",
                **metadata
            )
        
        # 周线处于金叉状态，但已经持有或等待入场
        if weekly_is_golden and not (context.position and context.position.quantity > 0):
            # 如果之前没有持仓且处于金叉状态，考虑入场
            # 但只在刚进入金叉状态时入场（避免追高）
            pass
        
        # 无信号
        status = "金叉状态" if weekly_is_golden else "死叉状态"
        return create_hold_signal(
            context.symbol, 
            price, 
            f"周线{status}，等待信号 | MACD={weekly_macd:.4f}"
        )
    
    def analyze_status(self, data: pd.DataFrame, symbol: str) -> AnalysisResult:
        """
        分析周线 MACD 当前状态
        """
        from datetime import datetime
        
        if self._weekly_data is None or len(self._weekly_data) < self.params['slow_period']:
            return AnalysisResult(
                symbol=symbol,
                timestamp=datetime.now(),
                status="数据不足",
                action="观望",
                reason="周线数据不足，无法分析",
                confidence=0.0,
            )
        
        latest = self._weekly_data.iloc[-1]
        prev = self._weekly_data.iloc[-2]
        price = data['close'].iloc[-1]
        
        weekly_macd = latest['macd']
        weekly_signal = latest['signal']
        weekly_histogram = latest['histogram']
        is_golden = latest['is_golden']
        golden_cross = latest['golden_cross']
        death_cross = latest['death_cross']
        
        macd_rising = weekly_macd > prev['macd']
        hist_expanding = abs(weekly_histogram) > abs(prev['histogram'])
        above_zero = weekly_macd > 0
        
        # 综合判断
        if golden_cross:
            status = "周线金叉"
            action = "买入"
            confidence = 0.85 if weekly_macd < 0 else 0.75
            reason = (f"周线 MACD 金叉信号！DIF={weekly_macd:.4f} 上穿 DEA={weekly_signal:.4f}。"
                     f"{'零轴下方金叉，超卖反弹信号较强。' if weekly_macd < 0 else '零轴上方金叉，趋势延续。'}"
                     f"建议关注下周走势确认。")
        elif death_cross:
            status = "周线死叉"
            action = "卖出"
            confidence = 0.85
            reason = (f"周线 MACD 死叉信号！DIF={weekly_macd:.4f} 下穿 DEA={weekly_signal:.4f}。"
                     f"中期趋势转空，建议减仓或清仓。")
        elif is_golden and macd_rising:
            status = "周线多头运行"
            action = "持有"
            confidence = 0.7
            reason = (f"周线处于金叉状态，DIF={weekly_macd:.4f} 持续上升。"
                     f"MACD柱{'扩张，动能充足' if hist_expanding else '收缩，注意动能变化'}。"
                     f"中期趋势向好。")
        elif is_golden and not macd_rising:
            status = "周线多头减弱"
            action = "注意减仓"
            confidence = 0.6
            reason = (f"周线处于金叉状态但 DIF 开始回落，DIF={weekly_macd:.4f}。"
                     f"多头动能减弱，注意死叉风险。")
        elif not is_golden and not macd_rising:
            status = "周线空头运行"
            action = "观望"
            confidence = 0.7
            reason = (f"周线处于死叉状态，DIF={weekly_macd:.4f} 持续下行。"
                     f"中期趋势偏空，建议空仓等待金叉。")
        elif not is_golden and macd_rising:
            status = "周线空头收敛"
            action = "关注"
            confidence = 0.55
            reason = (f"周线处于死叉状态但 DIF 开始回升，DIF={weekly_macd:.4f}。"
                     f"空头力量减弱，可能即将金叉，密切关注。")
        else:
            status = "周线震荡"
            action = "观望"
            confidence = 0.4
            reason = f"周线 MACD 无明确方向，DIF={weekly_macd:.4f}，建议观望。"
        
        indicators = {
            '周线DIF': round(weekly_macd, 4),
            '周线DEA': round(weekly_signal, 4),
            '周线MACD柱': round(weekly_histogram, 4),
            '金叉状态': '是' if is_golden else '否',
            'DIF趋势': '上升' if macd_rising else '下降',
            '最新周线日期': str(self._weekly_data.index[-1].date()),
            '收盘价': round(price, 2),
        }
        
        return AnalysisResult(
            symbol=symbol,
            timestamp=datetime.now(),
            status=status,
            action=action,
            reason=reason,
            indicators=indicators,
            confidence=confidence,
        )
    
    def get_weekly_analysis(self) -> Dict[str, Any]:
        """
        获取周线分析报告
        
        Returns:
            周线分析详情
        """
        if self._weekly_data is None or len(self._weekly_data) < 2:
            return {'error': '周线数据不足'}
        
        latest = self._weekly_data.iloc[-1]
        prev = self._weekly_data.iloc[-2]
        
        return {
            'latest_week': str(self._weekly_data.index[-1].date()),
            'macd': round(latest['macd'], 4),
            'signal': round(latest['signal'], 4),
            'histogram': round(latest['histogram'], 4),
            'is_golden': latest['is_golden'],
            'macd_trend': '上升' if latest['macd'] > prev['macd'] else '下降',
            'histogram_trend': '扩张' if abs(latest['histogram']) > abs(prev['histogram']) else '收缩',
            'recommendation': self._get_recommendation()
        }
    
    def _get_recommendation(self) -> str:
        """生成操作建议"""
        if self._weekly_data is None or len(self._weekly_data) < 2:
            return "数据不足"
        
        latest = self._weekly_data.iloc[-1]
        prev = self._weekly_data.iloc[-2]
        
        is_golden = latest['is_golden']
        macd_rising = latest['macd'] > prev['macd']
        
        if is_golden and macd_rising:
            return "🟢 周线金叉且 MACD 上升，持有或加仓"
        elif is_golden and not macd_rising:
            return "🟡 周线金叉但 MACD 下降，注意风险"
        elif not is_golden and not macd_rising:
            return "🔴 周线死叉且 MACD 下降，建议空仓"
        else:
            return "🟠 周线死叉但 MACD 回升，等待金叉"
