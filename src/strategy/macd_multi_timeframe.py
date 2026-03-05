# pyright: reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false
"""
多周期共振 MACD 策略实现
基于月线、周线、日线三重过滤的趋势跟踪策略

策略核心思想：
- 月线金叉区域 → 确认大趋势向上
- 周线金叉区域 → 确认中期趋势向上  
- 日线金叉信号 → 精确入场时机
- 只在大周期上升期间操作，顺势而为
"""
from typing import Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np
import logging

from .base import (
    BaseStrategy, StrategyContext,
    create_buy_signal, create_sell_signal, create_hold_signal
)
from src.core.models import Signal, AnalysisResult

logger = logging.getLogger(__name__)


class MultiTimeframeMACDStrategy(BaseStrategy):
    """
    多周期共振 MACD 策略
    
    策略逻辑:
    1. 月线处于金叉状态（MACD > Signal）→ 大趋势向上
    2. 周线处于金叉状态（MACD > Signal）→ 中期趋势向上
    3. 日线出现金叉信号 → 触发买入
    4. 任一大周期死叉 → 触发卖出/暂停交易
    
    特点:
    - 多重过滤，减少假信号
    - 顺势交易，只在上升趋势中操作
    - 风险可控，大周期转弱立即退出
    
    参数:
    - fast_period: 快速EMA周期（默认12）
    - slow_period: 慢速EMA周期（默认26）
    - signal_period: 信号线周期（默认9）
    - require_monthly_golden: 是否要求月线金叉（默认True）
    - require_weekly_golden: 是否要求周线金叉（默认True）
    - exit_on_weekly_death: 周线死叉时是否退出（默认True）
    - exit_on_monthly_death: 月线死叉时是否退出（默认True）
    """
    
    name = "MultiTimeframeMACD"
    version = "1.0.0"
    author = "Quant Team"
    description = "基于月线/周线/日线多周期共振的MACD趋势策略"
    
    @classmethod
    def default_params(cls) -> Dict[str, Any]:
        """默认参数"""
        return {
            'fast_period': 12,
            'slow_period': 26,
            'signal_period': 9,
            'volume_confirm': True,
            'volume_ratio': 1.3,
            'min_data_length': 60,
            # 多周期参数
            'require_monthly_golden': True,   # 要求月线金叉
            'require_weekly_golden': True,    # 要求周线金叉
            'exit_on_weekly_death': True,     # 周线死叉退出
            'exit_on_monthly_death': True,    # 月线死叉退出
            # 信号强度权重
            'monthly_weight': 0.4,            # 月线权重
            'weekly_weight': 0.35,            # 周线权重
            'daily_weight': 0.25,             # 日线权重
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
            'require_monthly_golden': {
                'type': 'bool',
                'default': True,
                'description': '是否要求月线处于金叉状态'
            },
            'require_weekly_golden': {
                'type': 'bool',
                'default': True,
                'description': '是否要求周线处于金叉状态'
            },
            'exit_on_weekly_death': {
                'type': 'bool',
                'default': True,
                'description': '周线死叉时是否退出'
            },
            'exit_on_monthly_death': {
                'type': 'bool',
                'default': True,
                'description': '月线死叉时是否退出'
            },
        }
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        """初始化策略"""
        super().__init__(params)
        # 缓存多周期数据
        self._weekly_data: Optional[pd.DataFrame] = None
        self._monthly_data: Optional[pd.DataFrame] = None
        self._weekly_indicators: Dict[str, Any] = {}
        self._monthly_indicators: Dict[str, Any] = {}
    
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
        
        # 重采样规则
        weekly = df.resample('W').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        return weekly
    
    def resample_to_monthly(self, daily_data: pd.DataFrame) -> pd.DataFrame:
        """
        将日线数据重采样为月线数据
        
        Args:
            daily_data: 日线OHLCV数据
        
        Returns:
            月线OHLCV数据
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
        
        # 重采样为月线 (使用月末)
        # 兼容不同版本的 pandas: ME(>=2.0) 或 M(<2.0)
        try:
            monthly = df.resample('ME').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
        except ValueError:
            # 旧版本 pandas 使用 'M'
            monthly = df.resample('M').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
        
        return monthly
    
    def calculate_macd(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        计算MACD指标（通用方法）
        
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
        计算所有周期的指标
        
        Args:
            data: 日线OHLCV数据
        
        Returns:
            添加了日线指标的DataFrame
        """
        # 1. 计算日线指标
        df = self.calculate_macd(data)
        
        # 计算日线成交量指标
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # 2. 生成周线数据并计算指标
        try:
            self._weekly_data = self.resample_to_weekly(data)
            if len(self._weekly_data) >= self.params['slow_period']:
                self._weekly_data = self.calculate_macd(self._weekly_data)
                self._weekly_indicators = {
                    'macd': self._weekly_data['macd'].iloc[-1],
                    'signal': self._weekly_data['signal'].iloc[-1],
                    'is_golden': self._weekly_data['is_golden'].iloc[-1],
                    'golden_cross': self._weekly_data['golden_cross'].iloc[-1],
                    'death_cross': self._weekly_data['death_cross'].iloc[-1],
                }
            else:
                logger.warning(f"周线数据不足: {len(self._weekly_data)} 条")
                self._weekly_indicators = {'is_golden': True}  # 默认允许
        except Exception as e:
            logger.error(f"计算周线指标失败: {e}")
            self._weekly_indicators = {'is_golden': True}
        
        # 3. 生成月线数据并计算指标
        try:
            self._monthly_data = self.resample_to_monthly(data)
            if len(self._monthly_data) >= self.params['slow_period']:
                self._monthly_data = self.calculate_macd(self._monthly_data)
                self._monthly_indicators = {
                    'macd': self._monthly_data['macd'].iloc[-1],
                    'signal': self._monthly_data['signal'].iloc[-1],
                    'is_golden': self._monthly_data['is_golden'].iloc[-1],
                    'golden_cross': self._monthly_data['golden_cross'].iloc[-1],
                    'death_cross': self._monthly_data['death_cross'].iloc[-1],
                }
            else:
                logger.warning(f"月线数据不足: {len(self._monthly_data)} 条")
                self._monthly_indicators = {'is_golden': True}  # 默认允许
        except Exception as e:
            logger.error(f"计算月线指标失败: {e}")
            self._monthly_indicators = {'is_golden': True}
        
        # 保存指标
        self.set_indicator('daily_macd', df['macd'].iloc[-1])
        self.set_indicator('weekly_macd', self._weekly_indicators.get('macd', 0))
        self.set_indicator('monthly_macd', self._monthly_indicators.get('macd', 0))
        
        return df
    
    def check_multi_timeframe_trend(self) -> Tuple[bool, str]:
        """
        检查多周期趋势状态
        
        Returns:
            (is_uptrend, description): 是否处于上升趋势及描述
        """
        monthly_golden = self._monthly_indicators.get('is_golden', False)
        weekly_golden = self._weekly_indicators.get('is_golden', False)
        
        # 构建趋势描述
        status = []
        if monthly_golden:
            status.append("月线金叉✓")
        else:
            status.append("月线死叉✗")
        
        if weekly_golden:
            status.append("周线金叉✓")
        else:
            status.append("周线死叉✗")
        
        description = " | ".join(status)
        
        # 判断是否满足多周期上升条件
        is_uptrend = True
        
        if self.params['require_monthly_golden'] and not monthly_golden:
            is_uptrend = False
        
        if self.params['require_weekly_golden'] and not weekly_golden:
            is_uptrend = False
        
        return is_uptrend, description
    
    def generate_signal(self, data: pd.DataFrame, context: StrategyContext) -> Signal:
        """
        生成交易信号
        
        多周期共振策略逻辑:
        1. 月线金叉状态 + 周线金叉状态 + 日线金叉信号 → 买入
        2. 周线死叉 或 月线死叉 → 卖出
        3. 日线死叉（有持仓时）→ 可选择性卖出
        
        Args:
            data: 包含指标的日线数据
            context: 策略上下文
        
        Returns:
            Signal: 交易信号
        """
        min_length = max(self.params['min_data_length'], 252)  # 至少1年数据
        if len(data) < min_length:
            logger.warning(f"数据不足: {len(data)} < {min_length}，需要足够数据计算月线")
            return create_hold_signal(context.symbol, data['close'].iloc[-1], "数据不足")
        
        # 获取最新日线数据
        current = data.iloc[-1]
        price = current['close']
        daily_macd = current['macd']
        daily_is_golden = current['is_golden']
        daily_golden_cross = current.get('golden_cross', False)
        daily_death_cross = current.get('death_cross', False)
        volume_ratio = current.get('volume_ratio', 1.0)
        
        # 检查多周期趋势
        is_uptrend, trend_desc = self.check_multi_timeframe_trend()
        
        # 构建元数据
        metadata = {
            'daily_macd': round(daily_macd, 4),
            'weekly_macd': round(self._weekly_indicators.get('macd', 0), 4),
            'monthly_macd': round(self._monthly_indicators.get('macd', 0), 4),
            'monthly_golden': self._monthly_indicators.get('is_golden', False),
            'weekly_golden': self._weekly_indicators.get('is_golden', False),
            'daily_golden': daily_is_golden,
            'trend_status': trend_desc,
            'volume_ratio': round(volume_ratio, 2),
        }
        
        # ===== 卖出信号优先检查 =====
        if context.position and context.position.quantity > 0:
            # 月线死叉 - 强制卖出
            if self.params['exit_on_monthly_death']:
                if self._monthly_indicators.get('death_cross', False):
                    return create_sell_signal(
                        symbol=context.symbol,
                        price=price,
                        strength=1.0,
                        reason=f"月线死叉，大趋势转弱！{trend_desc}",
                        **metadata
                    )
                # 月线处于死叉状态
                if not self._monthly_indicators.get('is_golden', True):
                    return create_sell_signal(
                        symbol=context.symbol,
                        price=price,
                        strength=0.9,
                        reason=f"月线处于死叉状态，退出持仓！{trend_desc}",
                        **metadata
                    )
            
            # 周线死叉 - 卖出
            if self.params['exit_on_weekly_death']:
                if self._weekly_indicators.get('death_cross', False):
                    return create_sell_signal(
                        symbol=context.symbol,
                        price=price,
                        strength=0.85,
                        reason=f"周线死叉，中期趋势转弱！{trend_desc}",
                        **metadata
                    )
                # 周线处于死叉状态
                if not self._weekly_indicators.get('is_golden', True):
                    return create_sell_signal(
                        symbol=context.symbol,
                        price=price,
                        strength=0.75,
                        reason=f"周线处于死叉状态，减仓/退出！{trend_desc}",
                        **metadata
                    )
            
            # 日线死叉（零轴上方）
            if daily_death_cross and daily_macd > 0:
                return create_sell_signal(
                    symbol=context.symbol,
                    price=price,
                    strength=0.6,
                    reason=f"日线死叉(零轴上方)，短期回调！{trend_desc}",
                    **metadata
                )
        
        # ===== 买入信号 =====
        # 只有在多周期上升趋势中才考虑买入
        if not is_uptrend:
            return create_hold_signal(
                context.symbol, 
                price, 
                f"大周期趋势不满足: {trend_desc}"
            )
        
        # 日线金叉信号
        if daily_golden_cross:
            # 检查成交量确认
            volume_confirmed = (
                not self.params['volume_confirm'] or 
                volume_ratio >= self.params['volume_ratio']
            )
            
            if volume_confirmed:
                # 计算综合信号强度
                strength = self._calculate_multi_tf_strength(data)
                
                reason_parts = [
                    "多周期共振买入!",
                    trend_desc,
                    f"日线金叉, MACD={daily_macd:.4f}",
                    f"量比={volume_ratio:.2f}"
                ]
                
                return create_buy_signal(
                    symbol=context.symbol,
                    price=price,
                    strength=strength,
                    reason=" | ".join(reason_parts),
                    **metadata
                )
            else:
                logger.debug(f"日线金叉但成交量不足: {volume_ratio:.2f}")
        
        # 无信号
        return create_hold_signal(
            context.symbol, 
            price, 
            f"等待入场时机 | {trend_desc}"
        )
    
    def analyze_status(self, data: pd.DataFrame, symbol: str) -> AnalysisResult:
        """
        分析多周期共振状态
        """
        from datetime import datetime
        
        min_length = max(self.params.get('min_data_length', 60), 252)
        if len(data) < min_length:
            return AnalysisResult(
                symbol=symbol,
                timestamp=datetime.now(),
                status="数据不足",
                action="观望",
                reason=f"数据不足，当前 {len(data)} 条，需要至少 {min_length} 条",
                confidence=0.0,
            )
        
        current = data.iloc[-1]
        price = current['close']
        daily_macd = current['macd']
        daily_is_golden = current['is_golden']
        
        # 获取多周期趋势
        is_uptrend, trend_desc = self.check_multi_timeframe_trend()
        
        monthly_golden = self._monthly_indicators.get('is_golden', False)
        weekly_golden = self._weekly_indicators.get('is_golden', False)
        monthly_macd = self._monthly_indicators.get('macd', 0)
        weekly_macd = self._weekly_indicators.get('macd', 0)
        
        # 综合判断
        if monthly_golden and weekly_golden and daily_is_golden:
            status = "三周期共振多头"
            action = "买入/持有"
            confidence = 0.9
            reason = (f"月线、周线、日线均处于金叉状态，三周期共振向上！\n"
                     f"月线DIF={monthly_macd:.4f}，周线DIF={weekly_macd:.4f}，"
                     f"日线DIF={daily_macd:.4f}。\n"
                     f"这是最强的多头信号，建议积极持有或加仓。")
        elif monthly_golden and weekly_golden and not daily_is_golden:
            status = "大周期多头，日线调整"
            action = "关注买点"
            confidence = 0.7
            reason = (f"月线和周线均处于金叉状态，大趋势向上。\n"
                     f"日线处于死叉状态，DIF={daily_macd:.4f}，短期回调中。\n"
                     f"建议等待日线金叉信号作为入场点。")
        elif monthly_golden and not weekly_golden:
            status = "月线多头，周线调整"
            action = "观望"
            confidence = 0.5
            reason = (f"月线处于金叉状态(DIF={monthly_macd:.4f})，大趋势尚可。\n"
                     f"但周线处于死叉(DIF={weekly_macd:.4f})，中期趋势走弱。\n"
                     f"建议等待周线金叉后再操作。")
        elif not monthly_golden and weekly_golden:
            status = "月线走弱，周线反弹"
            action = "谨慎观望"
            confidence = 0.35
            reason = (f"月线处于死叉状态(DIF={monthly_macd:.4f})，大趋势偏空。\n"
                     f"周线虽有金叉(DIF={weekly_macd:.4f})，但可能是反弹而非反转。\n"
                     f"建议谨慎，不宜重仓。")
        else:
            status = "多周期空头"
            action = "空仓观望"
            confidence = 0.8
            reason = (f"月线、周线均处于死叉状态，多周期共振向下。\n"
                     f"月线DIF={monthly_macd:.4f}，周线DIF={weekly_macd:.4f}。\n"
                     f"强烈建议空仓等待，直到至少月线金叉。")
        
        indicators = {
            '月线DIF': round(monthly_macd, 4),
            '月线金叉': '是' if monthly_golden else '否',
            '周线DIF': round(weekly_macd, 4),
            '周线金叉': '是' if weekly_golden else '否',
            '日线DIF': round(daily_macd, 4),
            '日线金叉': '是' if daily_is_golden else '否',
            '多周期趋势': trend_desc,
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
    
    def _calculate_multi_tf_strength(self, data: pd.DataFrame) -> float:
        """
        计算多周期综合信号强度
        
        考虑因素:
        - 月线趋势强度
        - 周线趋势强度
        - 日线位置和形态
        - 成交量配合
        
        Returns:
            float: 综合信号强度 (0.0-1.0)
        """
        strength = 0.0
        
        # 月线贡献 (权重 0.4)
        monthly_weight = self.params['monthly_weight']
        if self._monthly_indicators.get('is_golden', False):
            monthly_strength = 1.0
            # 如果月线MACD向上走，额外加分
            if (self._monthly_data is not None and 
                len(self._monthly_data) >= 2 and 
                'macd' in self._monthly_data.columns):
                if self._monthly_data['macd'].iloc[-1] > self._monthly_data['macd'].iloc[-2]:
                    monthly_strength = 1.0
                else:
                    monthly_strength = 0.7  # 金叉但动能减弱
            strength += monthly_weight * monthly_strength
        
        # 周线贡献 (权重 0.35)
        weekly_weight = self.params['weekly_weight']
        if self._weekly_indicators.get('is_golden', False):
            weekly_strength = 1.0
            # 如果周线是新金叉，加分
            if self._weekly_indicators.get('golden_cross', False):
                weekly_strength = 1.0
            elif (self._weekly_data is not None and 
                  len(self._weekly_data) >= 2 and 
                  'macd' in self._weekly_data.columns):
                if self._weekly_data['macd'].iloc[-1] > self._weekly_data['macd'].iloc[-2]:
                    weekly_strength = 0.9
                else:
                    weekly_strength = 0.6
            strength += weekly_weight * weekly_strength
        
        # 日线贡献 (权重 0.25)
        daily_weight = self.params['daily_weight']
        current = data.iloc[-1]
        
        daily_strength = 0.7  # 基础分（日线金叉触发）
        
        # 零轴下方金叉，反弹空间大
        if current['macd'] < 0:
            daily_strength += 0.2
        
        # 成交量配合
        if current.get('volume_ratio', 1) >= 2.0:
            daily_strength += 0.1
        
        strength += daily_weight * min(1.0, daily_strength)
        
        return min(1.0, strength)
    
    def get_trend_analysis(self) -> Dict[str, Any]:
        """
        获取多周期趋势分析报告
        
        Returns:
            趋势分析详情
        """
        return {
            'monthly': {
                'is_golden': self._monthly_indicators.get('is_golden', None),
                'macd': self._monthly_indicators.get('macd', None),
                'signal': self._monthly_indicators.get('signal', None),
                'trend': '上升' if self._monthly_indicators.get('is_golden') else '下降'
            },
            'weekly': {
                'is_golden': self._weekly_indicators.get('is_golden', None),
                'macd': self._weekly_indicators.get('macd', None),
                'signal': self._weekly_indicators.get('signal', None),
                'trend': '上升' if self._weekly_indicators.get('is_golden') else '下降'
            },
            'recommendation': self._get_recommendation()
        }
    
    def _get_recommendation(self) -> str:
        """生成操作建议"""
        monthly_golden = self._monthly_indicators.get('is_golden', False)
        weekly_golden = self._weekly_indicators.get('is_golden', False)
        
        if monthly_golden and weekly_golden:
            return "🟢 多周期共振向上，可积极寻找日线买点"
        elif monthly_golden and not weekly_golden:
            return "🟡 月线向上但周线调整，等待周线金叉"
        elif not monthly_golden and weekly_golden:
            return "🟠 月线走弱，周线反弹可能是诱多，谨慎操作"
        else:
            return "🔴 多周期共振向下，建议观望或空仓"
