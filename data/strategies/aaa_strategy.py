"""
AAA 策略

请在此处添加策略说明
"""
from dataclasses import dataclass, field
from typing import Dict, Any
import pandas as pd

from src.strategy.base import BaseStrategy
from src.core.models import StrategyContext, StrategyDecision, SignalType


# ──────────────────────────────────────────────────────────────────
# 策略配置结构定义
# ──────────────────────────────────────────────────────────────────

@dataclass
class AaaParamsConfig:
    """AAA 策略参数配置"""
    period: int = 20
    threshold: float = 0.02


@dataclass
class AaaRiskConfig:
    """AAA 风控配置"""
    max_position_pct: float = 0.3
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.15
    max_drawdown: float = 0.2


@dataclass
class AaaTradingConfig:
    """AAA 交易配置"""
    commission: float = 0.0003
    slippage: float = 0.001


@dataclass
class AaaBacktestConfig:
    """AAA 回测配置"""
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_capital: int = 1000000


@dataclass
class AaaConfig:
    """AAA 策略完整配置"""
    strategy: Dict[str, Any] = field(default_factory=dict)
    params: AaaParamsConfig = field(default_factory=AaaParamsConfig)
    risk: AaaRiskConfig = field(default_factory=AaaRiskConfig)
    trading: AaaTradingConfig = field(default_factory=AaaTradingConfig)
    backtest: AaaBacktestConfig = field(default_factory=AaaBacktestConfig)


# ──────────────────────────────────────────────────────────────────
# 策略实现
# ──────────────────────────────────────────────────────────────────

class AaaStrategy(BaseStrategy):
    """AAA 策略实现
    
    使用方式：
        # 在策略方法中访问配置
        self.config.params.period      # 参数配置
        self.config.risk.stop_loss_pct  # 风控配置
        self.config.trading.commission  # 交易配置
    """
    
    name = "aaa"
    ConfigClass = AaaConfig  # 指定配置类
    
    def on_start(self, deps):
        """策略启动时调用（可选实现）"""
        config = self.config  # type: AaaConfig
        
        # 打印完整配置
        self._strategy_logger.info("=" * 50)
        self._strategy_logger.info("AAA 策略配置加载完成:")
        self._strategy_logger.info(f"  参数配置: period={config.params.period}, threshold={config.params.threshold}")
        self._strategy_logger.info(f"  风控配置: max_position={config.risk.max_position_pct}, "
                                   f"stop_loss={config.risk.stop_loss_pct}, take_profit={config.risk.take_profit_pct}")
        self._strategy_logger.info(f"  交易配置: commission={config.trading.commission}, slippage={config.trading.slippage}")
        self._strategy_logger.info(f"  回测配置: {config.backtest.start_date} ~ {config.backtest.end_date}, "
                                   f"capital={config.backtest.initial_capital}")
        self._strategy_logger.info("=" * 50)
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算 MACD 指标"""
        config = self.config  # type: AaaConfig
        result = data.copy()
        
        # MACD 参数
        fast_period = 12
        slow_period = 26
        signal_period = 9
        
        # 计算 EMA
        ema_fast = result['close'].ewm(span=fast_period, adjust=False).mean()
        ema_slow = result['close'].ewm(span=slow_period, adjust=False).mean()
        
        # MACD 线 = 快线 - 慢线
        result['macd'] = ema_fast - ema_slow
        
        # 信号线 = MACD 的 EMA
        result['signal'] = result['macd'].ewm(span=signal_period, adjust=False).mean()
        
        # 柱状图 = MACD - 信号线
        result['histogram'] = result['macd'] - result['signal']
        
        self._strategy_logger.debug(f"MACD 指标计算完成: MACD={result['macd'].iloc[-1]:.4f}, "
                                    f"Signal={result['signal'].iloc[-1]:.4f}")
        return result
    
    def evaluate(self, data: pd.DataFrame, context: StrategyContext) -> StrategyDecision:
        """
        MACD 金叉死叉策略
        
        - 金叉：MACD 上穿信号线 → 买入
        - 死叉：MACD 下穿信号线 → 卖出
        """
        config = self.config  # type: AaaConfig
        
        # 打印最新一条K线数据
        if not data.empty:
            latest = data.iloc[-1]
            open_val = f"{latest['open']:.2f}" if 'open' in latest else 'N/A'
            high_val = f"{latest['high']:.2f}" if 'high' in latest else 'N/A'
            low_val = f"{latest['low']:.2f}" if 'low' in latest else 'N/A'
            close_val = f"{latest['close']:.2f}" if 'close' in latest else 'N/A'
            volume_val = latest.get('volume', 'N/A')
            self._strategy_logger.info(
                f"最新K线 [{context.symbol}]: "
                f"open={open_val}, high={high_val}, low={low_val}, close={close_val}, volume={volume_val}"
            )
        
        price = data['close'].iloc[-1] if not data.empty else 0.0
        
        # 需要至少 2 条数据判断交叉
        if len(data) < 2:
            return StrategyDecision.hold(context.symbol, "数据不足")
        
        # 获取最近两天的指标
        macd_curr = data['macd'].iloc[-1]
        macd_prev = data['macd'].iloc[-2]
        signal_curr = data['signal'].iloc[-1]
        signal_prev = data['signal'].iloc[-2]
        histogram = data['histogram'].iloc[-1]
        
        # 金叉：MACD 从下方上穿信号线
        if macd_prev <= signal_prev and macd_curr > signal_curr:
            self._strategy_logger.info(f"检测到金叉: {context.symbol} @ {price:.2f}")
            return StrategyDecision.buy(
                symbol=context.symbol,
                price=price,
                reason="MACD 金叉",
                status="多头信号",
                indicators={
                    "macd": round(macd_curr, 4),
                    "signal": round(signal_curr, 4),
                    "histogram": round(histogram, 4)
                }
            )
        
        # 死叉：MACD 从上方下穿信号线
        if macd_prev >= signal_prev and macd_curr < signal_curr:
            self._strategy_logger.info(f"检测到死叉: {context.symbol} @ {price:.2f}")
            return StrategyDecision.sell(
                symbol=context.symbol,
                price=price,
                reason="MACD 死叉",
                status="空头信号",
                indicators={
                    "macd": round(macd_curr, 4),
                    "signal": round(signal_curr, 4),
                    "histogram": round(histogram, 4)
                }
            )
        
        # 无信号
        return StrategyDecision.hold(
            context.symbol, 
            f"观望 (MACD={macd_curr:.4f}, Signal={signal_curr:.4f})"
        )
    
    def should_notify(self, decision: StrategyDecision, last_decision: StrategyDecision = None) -> bool:
        """
        决定是否发送通知
        
        只在买点/卖点时发送通知，持有信号不通知
        """

        self._strategy_logger.info("发送通知")
        return True 
        # return decision.signal_type in (SignalType.BUY, SignalType.SELL)
