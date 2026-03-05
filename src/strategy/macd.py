# pyright: reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false
"""
MACD 策略实现
基于 MACD 指标的趋势跟踪策略
"""
from typing import Dict, Any
import pandas as pd
import logging

from .base import (
    BaseStrategy, StrategyContext,
    create_buy_signal, create_sell_signal, create_hold_signal
)
from src.core.models import Signal, AnalysisResult

logger = logging.getLogger(__name__)


class MACDStrategy(BaseStrategy):
    """
    MACD 策略
    
    策略逻辑:
    1. MACD 金叉（MACD 上穿 Signal）且 MACD < 0 时买入
    2. MACD 死叉（MACD 下穿 Signal）且 MACD > 0 时卖出
    3. 可选配合成交量确认
    
    参数:
    - fast_period: 快速EMA周期（默认12）
    - slow_period: 慢速EMA周期（默认26）
    - signal_period: 信号线周期（默认9）
    - volume_confirm: 是否启用成交量确认（默认True）
    - volume_ratio: 成交量放大倍数阈值（默认1.5）
    """
    
    name = "MACD"
    version = "1.0.0"
    author = "Quant Team"
    description = "基于 MACD 指标的趋势跟踪策略"
    
    @classmethod
    def default_params(cls) -> Dict[str, Any]:
        """默认参数"""
        return {
            'fast_period': 12,
            'slow_period': 26,
            'signal_period': 9,
            'volume_confirm': True,
            'volume_ratio': 1.5,
            'min_data_length': 60,  # 最小数据长度
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
            'volume_confirm': {
                'type': 'bool',
                'default': True,
                'description': '是否启用成交量确认'
            },
            'volume_ratio': {
                'type': 'float',
                'default': 1.5,
                'min': 1.0,
                'max': 5.0,
                'description': '成交量放大倍数阈值'
            },
        }
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        计算 MACD 指标
        
        Args:
            data: OHLCV 数据
        
        Returns:
            pd.DataFrame: 添加了以下列:
                - ema_fast: 快速EMA
                - ema_slow: 慢速EMA
                - macd: MACD线 (DIF)
                - signal: 信号线 (DEA)
                - histogram: MACD柱 (MACD Bar)
                - volume_ma: 成交量均线
                - volume_ratio: 成交量比率
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
        df['histogram'] = 2 * (df['macd'] - df['signal'])  # MACD Bar (乘2是A股习惯)
        
        # 计算成交量指标
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # 计算金叉/死叉信号
        df['macd_cross'] = 0
        df.loc[(df['macd'] > df['signal']) & (df['macd'].shift(1) <= df['signal'].shift(1)), 'macd_cross'] = 1  # 金叉
        df.loc[(df['macd'] < df['signal']) & (df['macd'].shift(1) >= df['signal'].shift(1)), 'macd_cross'] = -1  # 死叉
        
        # 保存指标值供后续使用
        self.set_indicator('macd', df['macd'].iloc[-1])
        self.set_indicator('signal', df['signal'].iloc[-1])
        self.set_indicator('histogram', df['histogram'].iloc[-1])
        
        return df
    
    def generate_signal(self, data: pd.DataFrame, context: StrategyContext) -> Signal:
        """
        生成交易信号
        
        策略逻辑:
        1. 金叉 + MACD < 0（零轴下方）+ 成交量放大 -> 买入
        2. 死叉 + MACD > 0（零轴上方）-> 卖出
        3. 持仓止损/止盈检查
        
        Args:
            data: 包含指标的数据
            context: 策略上下文
        
        Returns:
            Signal: 交易信号
        """
        if len(data) < self.params['min_data_length']:
            logger.warning(f"数据不足: {len(data)} < {self.params['min_data_length']}")
            return create_hold_signal(context.symbol, data['close'].iloc[-1], "数据不足")
        
        # 获取最新数据
        current = data.iloc[-1]
        _ = data.iloc[-2]  # prev，保留以备后续使用
        
        price = current['close']
        macd = current['macd']
        signal_line = current['signal']
        histogram = current['histogram']
        macd_cross = current['macd_cross']
        volume_ratio = current['volume_ratio']
        
        # 构建元数据
        metadata = {
            'macd': round(macd, 4),
            'signal': round(signal_line, 4),
            'histogram': round(histogram, 4),
            'volume_ratio': round(volume_ratio, 2),
        }
        
        # ===== 买入信号 =====
        if macd_cross == 1:  # 金叉
            # 条件1: 零轴下方金叉（更强的买入信号）
            if macd < 0:
                # 检查成交量确认
                volume_confirmed = (
                    not self.params['volume_confirm'] or 
                    volume_ratio >= self.params['volume_ratio']
                )
                
                if volume_confirmed:
                    # 计算信号强度
                    strength = self._calculate_buy_strength(data)
                    
                    return create_buy_signal(
                        symbol=context.symbol,
                        price=price,
                        strength=strength,
                        reason=f"MACD金叉(零轴下方), MACD={macd:.4f}, 量比={volume_ratio:.2f}",
                        **metadata
                    )
                else:
                    logger.debug(f"金叉但成交量不足: {volume_ratio:.2f} < {self.params['volume_ratio']}")
        
        # ===== 卖出信号 =====
        if macd_cross == -1:  # 死叉
            # 有持仓时才考虑卖出
            if context.position and context.position.quantity > 0:
                # 条件1: 零轴上方死叉
                if macd > 0:
                    strength = self._calculate_sell_strength(data)
                    
                    return create_sell_signal(
                        symbol=context.symbol,
                        price=price,
                        strength=strength,
                        reason=f"MACD死叉(零轴上方), MACD={macd:.4f}",
                        **metadata
                    )
        
        # ===== 持仓管理 =====
        if context.position and context.position.quantity > 0:
            # 检查止盈止损
            pnl_pct = context.position.profit_pct
            
            # 顶背离检测（价格新高但MACD未新高）
            if self._check_top_divergence(data):
                return create_sell_signal(
                    symbol=context.symbol,
                    price=price,
                    strength=0.8,
                    reason=f"顶背离信号, 盈亏={pnl_pct:.2%}",
                    **metadata
                )
        
        # 无信号
        return create_hold_signal(context.symbol, price, "无明显信号")
    
    def analyze_status(self, data: pd.DataFrame, symbol: str) -> AnalysisResult:
        """
        分析当前 MACD 状态
        
        根据 MACD 指标判断当前处于什么阶段，给出操作建议。
        """
        from datetime import datetime
        
        if len(data) < self.params['min_data_length']:
            return AnalysisResult(
                symbol=symbol,
                timestamp=datetime.now(),
                status="数据不足",
                action="观望",
                reason=f"数据不足，当前 {len(data)} 条，需要 {self.params['min_data_length']} 条",
                confidence=0.0,
            )
        
        current = data.iloc[-1]
        prev = data.iloc[-2]
        price = current['close']
        macd = current['macd']
        signal_line = current['signal']
        histogram = current['histogram']
        macd_cross = current['macd_cross']
        volume_ratio = current.get('volume_ratio', 1.0)
        
        # 判断趋势状态
        is_golden = macd > signal_line  # 金叉状态
        macd_rising = macd > prev['macd']
        hist_expanding = abs(histogram) > abs(prev['histogram'])
        above_zero = macd > 0
        
        # 综合判断状态和建议
        if is_golden and above_zero and macd_rising:
            status = "强势多头"
            action = "持有" if hist_expanding else "注意减仓"
            confidence = 0.85
            reason = (f"MACD 在零轴上方金叉状态，DIF={macd:.4f}，DEA={signal_line:.4f}，"
                     f"MACD柱{'扩张' if hist_expanding else '收缩'}。"
                     f"趋势向上{'，动能充足' if hist_expanding else '，但动能减弱注意风险'}。")
        elif is_golden and not above_zero and macd_rising:
            status = "底部回升"
            action = "买入"
            confidence = 0.75
            reason = (f"MACD 在零轴下方金叉，DIF={macd:.4f} 向上回升，"
                     f"DEA={signal_line:.4f}。处于底部反弹阶段，"
                     f"量比={volume_ratio:.2f}。建议关注金叉后的放量确认。")
        elif is_golden and not macd_rising:
            status = "多头减弱"
            action = "观望"
            confidence = 0.6
            reason = (f"MACD 处于金叉状态但 DIF 开始回落，DIF={macd:.4f}，"
                     f"MACD柱收缩。多头动能减弱，注意死叉风险。")
        elif not is_golden and above_zero and not macd_rising:
            status = "高位死叉"
            action = "卖出"
            confidence = 0.8
            reason = (f"MACD 在零轴上方死叉，DIF={macd:.4f} < DEA={signal_line:.4f}。"
                     f"趋势由多转空，建议减仓或清仓。")
        elif not is_golden and not above_zero and not macd_rising:
            status = "空头趋势"
            action = "观望"
            confidence = 0.7
            reason = (f"MACD 在零轴下方死叉状态，DIF={macd:.4f}，"
                     f"空头趋势延续。建议空仓等待底部金叉信号。")
        elif not is_golden and not above_zero and macd_rising:
            status = "空头收敛"
            action = "关注"
            confidence = 0.55
            reason = (f"MACD 在零轴下方但 DIF 开始回升，DIF={macd:.4f}，"
                     f"空头力量减弱，可能即将金叉。建议密切关注。")
        else:
            status = "震荡"
            action = "观望"
            confidence = 0.4
            reason = f"MACD 无明确方向，DIF={macd:.4f}，DEA={signal_line:.4f}，建议观望。"
        
        # 补充金叉/死叉转折信号
        if macd_cross == 1:
            action = "买入"
            reason = f"【金叉信号】{reason}"
            confidence = min(1.0, confidence + 0.15)
        elif macd_cross == -1:
            action = "卖出"
            reason = f"【死叉信号】{reason}"
            confidence = min(1.0, confidence + 0.15)
        
        indicators = {
            'DIF(MACD)': round(macd, 4),
            'DEA(Signal)': round(signal_line, 4),
            'MACD柱': round(histogram, 4),
            '量比': round(volume_ratio, 2),
            '收盘价': round(price, 2),
            '金叉状态': '是' if is_golden else '否',
            'DIF趋势': '上升' if macd_rising else '下降',
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
    
    def _calculate_buy_strength(self, data: pd.DataFrame) -> float:
        """
        计算买入信号强度
        
        基于多个因素综合评估:
        - MACD 位置（越低越强）
        - 成交量放大程度
        - 趋势方向
        
        Returns:
            float: 信号强度 (0.0-1.0)
        """
        current = data.iloc[-1]
        
        strength = 0.5  # 基础强度
        
        # 因素1: MACD 位置
        # 零轴下方越深，反弹空间越大
        macd_min = data['macd'].rolling(60).min().iloc[-1]
        macd_range = abs(macd_min) if macd_min < 0 else 0.01
        macd_position = abs(current['macd']) / macd_range
        strength += min(0.2, macd_position * 0.1)
        
        # 因素2: 成交量
        if current['volume_ratio'] >= 2.0:
            strength += 0.15
        elif current['volume_ratio'] >= 1.5:
            strength += 0.1
        
        # 因素3: 价格位置（相对20日均线）
        ma20 = data['close'].rolling(20).mean().iloc[-1]
        if current['close'] < ma20:
            strength += 0.1  # 价格在均线下方，超跌反弹
        
        return min(1.0, strength)
    
    def _calculate_sell_strength(self, data: pd.DataFrame) -> float:
        """
        计算卖出信号强度
        
        Returns:
            float: 信号强度 (0.0-1.0)
        """
        current = data.iloc[-1]
        
        strength = 0.6  # 基础强度
        
        # 因素1: MACD 位置
        if current['macd'] > 0:
            strength += 0.1
        
        # 因素2: histogram 变化（动能减弱）
        hist_prev = data['histogram'].iloc[-2]
        if current['histogram'] < hist_prev:
            strength += 0.15
        
        return min(1.0, strength)
    
    def _check_top_divergence(self, data: pd.DataFrame, lookback: int = 20) -> bool:
        """
        检测顶背离
        
        价格创新高但 MACD 未创新高
        
        Args:
            data: K线数据
            lookback: 回溯周期
        
        Returns:
            bool: 是否存在顶背离
        """
        if len(data) < lookback:
            return False
        
        recent = data.iloc[-lookback:]
        
        # 找到价格高点
        price_high_idx = recent['close'].idxmax()
        current_idx = recent.index[-1]
        
        # 如果当前不是最高点，跳过
        if price_high_idx != current_idx:
            return False
        
        # 检查 MACD 是否同步创新高
        macd_high_idx = recent['macd'].idxmax()
        
        # 价格新高但 MACD 未新高 = 顶背离
        if macd_high_idx != current_idx:
            current_price = recent['close'].iloc[-1]
            price_at_macd_high = recent.loc[macd_high_idx, 'close']
            
            # 价格确实创了新高
            if current_price > price_at_macd_high:
                logger.info(f"检测到顶背离: 价格新高 {current_price:.2f} > {price_at_macd_high:.2f}")
                return True
        
        return False
    
    def _check_bottom_divergence(self, data: pd.DataFrame, lookback: int = 20) -> bool:
        """
        检测底背离
        
        价格创新低但 MACD 未创新低
        
        Args:
            data: K线数据
            lookback: 回溯周期
        
        Returns:
            bool: 是否存在底背离
        """
        if len(data) < lookback:
            return False
        
        recent = data.iloc[-lookback:]
        
        # 找到价格低点
        price_low_idx = recent['close'].idxmin()
        current_idx = recent.index[-1]
        
        if price_low_idx != current_idx:
            return False
        
        # 检查 MACD 是否同步创新低
        macd_low_idx = recent['macd'].idxmin()
        
        if macd_low_idx != current_idx:
            current_price = recent['close'].iloc[-1]
            price_at_macd_low = recent.loc[macd_low_idx, 'close']
            
            if current_price < price_at_macd_low:
                logger.info(f"检测到底背离: 价格新低 {current_price:.2f} < {price_at_macd_low:.2f}")
                return True
        
        return False
