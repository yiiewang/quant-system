"""
风控管理器
提供交易前风险检查和仓位计算功能
"""
from typing import Tuple, Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
import logging

from src.core.models import Signal, SignalType, Portfolio, Position, Order, OrderSide

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskConfig:
    """
    风控配置
    
    Attributes:
        max_position_pct: 单票最大仓位比例
        max_total_position: 总仓位上限
        stop_loss_pct: 止损比例
        take_profit_pct: 止盈比例
        max_drawdown: 最大回撤限制
        max_daily_loss: 单日最大亏损
        min_order_value: 最小订单金额
        max_order_value: 最大订单金额
        max_position_count: 最大持仓数量
        enable_stop_loss: 是否启用止损
        enable_take_profit: 是否启用止盈
    """
    # 仓位控制
    max_position_pct: float = 0.30        # 单票最大仓位30%
    max_total_position: float = 0.80      # 总仓位上限80%
    max_position_count: int = 10          # 最大持仓数量
    
    # 止盈止损
    stop_loss_pct: float = 0.05           # 止损5%
    take_profit_pct: float = 0.15         # 止盈15%
    enable_stop_loss: bool = True
    enable_take_profit: bool = True
    
    # 风险限制
    max_drawdown: float = 0.20            # 最大回撤20%
    max_daily_loss: float = 0.05          # 单日最大亏损5%
    
    # 订单限制
    min_order_value: float = 1000         # 最小订单金额
    max_order_value: float = 100000       # 最大订单金额
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'max_position_pct': self.max_position_pct,
            'max_total_position': self.max_total_position,
            'max_position_count': self.max_position_count,
            'stop_loss_pct': self.stop_loss_pct,
            'take_profit_pct': self.take_profit_pct,
            'max_drawdown': self.max_drawdown,
            'max_daily_loss': self.max_daily_loss,
            'min_order_value': self.min_order_value,
            'max_order_value': self.max_order_value,
        }


@dataclass
class RiskCheckResult:
    """
    风控检查结果
    
    Attributes:
        passed: 是否通过
        rule_name: 规则名称
        message: 结果消息
        level: 风险级别
        details: 详细信息
    """
    passed: bool
    rule_name: str = ""
    message: str = ""
    level: RiskLevel = RiskLevel.LOW
    details: Dict[str, Any] = field(default_factory=dict)
    
    def __bool__(self) -> bool:
        return self.passed


class RiskManager:
    """
    风控管理器
    
    提供以下功能:
    1. 信号风控检查（交易前）
    2. 仓位大小计算
    3. 止盈止损价格计算
    4. 风险指标监控
    
    Usage:
        config = RiskConfig(max_position_pct=0.25)
        risk_mgr = RiskManager(config)
        
        # 检查信号
        result = risk_mgr.check_signal(signal, portfolio)
        if result.passed:
            # 计算仓位
            size = risk_mgr.calculate_position_size(signal, portfolio)
    """
    
    def __init__(self, config: RiskConfig = None):
        """
        初始化风控管理器
        
        Args:
            config: 风控配置
        """
        self.config = config or RiskConfig()
        
        # 运行时统计
        self._daily_stats = {
            'pnl': 0.0,
            'trade_count': 0,
            'date': date.today()
        }
        self._peak_equity = 0.0
        self._current_drawdown = 0.0
        
        # 自定义规则
        self._custom_rules: List[Callable] = []
        
        logger.info(f"初始化风控管理器: {self.config.to_dict()}")
    
    def check_signal(self, signal: Signal, portfolio: Portfolio) -> RiskCheckResult:
        """
        信号风控检查
        
        执行所有风控规则检查
        
        Args:
            signal: 交易信号
            portfolio: 投资组合
        
        Returns:
            RiskCheckResult: 检查结果
        """
        # 只检查买入和卖出信号
        if signal.signal_type == SignalType.HOLD:
            return RiskCheckResult(passed=True, message="持有信号无需检查")
        
        # 内置检查规则
        checks = [
            self._check_position_limit,
            self._check_total_position,
            self._check_position_count,
            self._check_daily_loss,
            self._check_max_drawdown,
            self._check_order_value,
        ]
        
        # 买入特定检查
        if signal.signal_type == SignalType.BUY:
            checks.append(self._check_cash_available)
        
        # 卖出特定检查
        if signal.signal_type == SignalType.SELL:
            checks.append(self._check_position_exists)
        
        # 执行所有检查
        for check_func in checks:
            result = check_func(signal, portfolio)
            if not result.passed:
                logger.warning(f"风控拦截: {result.rule_name} - {result.message}")
                return result
        
        # 执行自定义规则
        for custom_rule in self._custom_rules:
            try:
                result = custom_rule(signal, portfolio)
                if not result.passed:
                    return result
            except Exception as e:
                logger.error(f"自定义规则执行异常: {e}")
        
        return RiskCheckResult(
            passed=True, 
            message="通过所有风控检查",
            rule_name="all"
        )
    
    def calculate_position_size(self, signal: Signal, portfolio: Portfolio) -> int:
        """
        计算建议仓位大小
        
        基于资金管理和风险控制计算合适的仓位
        
        Args:
            signal: 交易信号
            portfolio: 投资组合
        
        Returns:
            int: 建议买入股数（100的整数倍）
        """
        if signal.signal_type != SignalType.BUY:
            return 0
        
        # 可用于该标的的最大资金
        max_position_value = portfolio.total_value * self.config.max_position_pct
        
        # 减去已有持仓
        existing = portfolio.get_position(signal.symbol)
        if existing:
            existing_value = existing.market_value
            max_position_value -= existing_value
        
        # 按信号强度调整
        adjusted_value = max_position_value * signal.strength
        
        # 不能超过可用现金
        adjusted_value = min(adjusted_value, portfolio.cash * 0.95)  # 留5%缓冲
        
        # 不能超过单笔订单上限
        adjusted_value = min(adjusted_value, self.config.max_order_value)
        
        # 计算股数（取整到100股）
        if signal.price <= 0:
            return 0
        
        shares = int(adjusted_value / signal.price / 100) * 100
        
        # 检查最小订单金额
        if shares * signal.price < self.config.min_order_value:
            shares = 0
        
        logger.debug(f"计算仓位: {signal.symbol} 信号强度={signal.strength:.2f} 建议股数={shares}")
        
        return max(0, shares)
    
    def get_stop_loss_price(self, entry_price: float, side: str = 'buy') -> float:
        """
        计算止损价格
        
        Args:
            entry_price: 入场价格
            side: 方向 (buy/sell)
        
        Returns:
            float: 止损价格
        """
        if side == 'buy':
            return entry_price * (1 - self.config.stop_loss_pct)
        return entry_price * (1 + self.config.stop_loss_pct)
    
    def get_take_profit_price(self, entry_price: float, side: str = 'buy') -> float:
        """
        计算止盈价格
        
        Args:
            entry_price: 入场价格
            side: 方向 (buy/sell)
        
        Returns:
            float: 止盈价格
        """
        if side == 'buy':
            return entry_price * (1 + self.config.take_profit_pct)
        return entry_price * (1 - self.config.take_profit_pct)
    
    def check_stop_loss(self, position: Position, current_price: float) -> bool:
        """
        检查是否触发止损
        
        Args:
            position: 持仓
            current_price: 当前价格
        
        Returns:
            bool: 是否应止损
        """
        if not self.config.enable_stop_loss:
            return False
        
        stop_price = self.get_stop_loss_price(position.avg_cost)
        
        if current_price <= stop_price:
            logger.info(
                f"触发止损: {position.symbol} "
                f"成本={position.avg_cost:.2f} 现价={current_price:.2f} 止损价={stop_price:.2f}"
            )
            return True
        
        return False
    
    def check_take_profit(self, position: Position, current_price: float) -> bool:
        """
        检查是否触发止盈
        
        Args:
            position: 持仓
            current_price: 当前价格
        
        Returns:
            bool: 是否应止盈
        """
        if not self.config.enable_take_profit:
            return False
        
        profit_price = self.get_take_profit_price(position.avg_cost)
        
        if current_price >= profit_price:
            logger.info(
                f"触发止盈: {position.symbol} "
                f"成本={position.avg_cost:.2f} 现价={current_price:.2f} 止盈价={profit_price:.2f}"
            )
            return True
        
        return False
    
    def update_equity(self, current_equity: float) -> None:
        """
        更新权益峰值（用于计算回撤）
        
        Args:
            current_equity: 当前权益
        """
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity
        
        if self._peak_equity > 0:
            self._current_drawdown = (self._peak_equity - current_equity) / self._peak_equity
    
    def update_daily_pnl(self, pnl: float) -> None:
        """
        更新日内盈亏
        
        Args:
            pnl: 盈亏金额
        """
        # 检查是否新的一天
        today = date.today()
        if self._daily_stats['date'] != today:
            self._daily_stats = {
                'pnl': 0.0,
                'trade_count': 0,
                'date': today
            }
        
        self._daily_stats['pnl'] += pnl
        self._daily_stats['trade_count'] += 1
    
    def add_custom_rule(self, rule: Callable[[Signal, Portfolio], RiskCheckResult]) -> None:
        """
        添加自定义风控规则
        
        Args:
            rule: 规则函数，接收(signal, portfolio)，返回RiskCheckResult
        """
        self._custom_rules.append(rule)
    
    def get_risk_metrics(self, portfolio: Portfolio) -> Dict[str, Any]:
        """
        获取当前风险指标
        
        Args:
            portfolio: 投资组合
        
        Returns:
            Dict[str, Any]: 风险指标字典
        """
        position_value = portfolio.position_value
        total_value = portfolio.total_value
        
        return {
            'position_ratio': position_value / total_value if total_value > 0 else 0,
            'position_count': portfolio.position_count,
            'daily_pnl': self._daily_stats['pnl'],
            'daily_pnl_pct': self._daily_stats['pnl'] / total_value if total_value > 0 else 0,
            'current_drawdown': self._current_drawdown,
            'peak_equity': self._peak_equity,
        }
    
    def reset_daily(self) -> None:
        """重置每日统计"""
        self._daily_stats = {
            'pnl': 0.0,
            'trade_count': 0,
            'date': date.today()
        }
    
    # ==================== 内置检查规则 ====================
    
    def _check_position_limit(self, signal: Signal, portfolio: Portfolio) -> RiskCheckResult:
        """检查单票仓位限制"""
        if portfolio.total_value <= 0:
            return RiskCheckResult(passed=True, rule_name="position_limit")
        
        # 计算新增后的仓位比例
        existing = portfolio.get_position(signal.symbol)
        existing_value = existing.market_value if existing else 0
        
        # 假设买入最小单位
        new_value = signal.price * 100  # 1手
        total_position_value = existing_value + new_value
        position_pct = total_position_value / portfolio.total_value
        
        if position_pct > self.config.max_position_pct:
            return RiskCheckResult(
                passed=False,
                rule_name="position_limit",
                message=f"超过单票仓位限制 ({position_pct:.1%} > {self.config.max_position_pct:.1%})",
                level=RiskLevel.HIGH,
                details={
                    'current_pct': position_pct,
                    'limit_pct': self.config.max_position_pct
                }
            )
        
        return RiskCheckResult(passed=True, rule_name="position_limit")
    
    def _check_total_position(self, signal: Signal, portfolio: Portfolio) -> RiskCheckResult:
        """检查总仓位限制"""
        if signal.signal_type != SignalType.BUY:
            return RiskCheckResult(passed=True, rule_name="total_position")
        
        if portfolio.total_value <= 0:
            return RiskCheckResult(passed=True, rule_name="total_position")
        
        position_pct = portfolio.position_value / portfolio.total_value
        
        if position_pct >= self.config.max_total_position:
            return RiskCheckResult(
                passed=False,
                rule_name="total_position",
                message=f"总仓位已达上限 ({position_pct:.1%} >= {self.config.max_total_position:.1%})",
                level=RiskLevel.HIGH,
                details={
                    'current_pct': position_pct,
                    'limit_pct': self.config.max_total_position
                }
            )
        
        return RiskCheckResult(passed=True, rule_name="total_position")
    
    def _check_position_count(self, signal: Signal, portfolio: Portfolio) -> RiskCheckResult:
        """检查持仓数量限制"""
        if signal.signal_type != SignalType.BUY:
            return RiskCheckResult(passed=True, rule_name="position_count")
        
        # 如果已有持仓，不计入新增
        if portfolio.has_position(signal.symbol):
            return RiskCheckResult(passed=True, rule_name="position_count")
        
        if portfolio.position_count >= self.config.max_position_count:
            return RiskCheckResult(
                passed=False,
                rule_name="position_count",
                message=f"持仓数量已达上限 ({portfolio.position_count} >= {self.config.max_position_count})",
                level=RiskLevel.MEDIUM,
                details={
                    'current_count': portfolio.position_count,
                    'limit_count': self.config.max_position_count
                }
            )
        
        return RiskCheckResult(passed=True, rule_name="position_count")
    
    def _check_daily_loss(self, signal: Signal, portfolio: Portfolio) -> RiskCheckResult:
        """检查当日亏损限制"""
        if portfolio.total_value <= 0:
            return RiskCheckResult(passed=True, rule_name="daily_loss")
        
        daily_loss_pct = -self._daily_stats['pnl'] / portfolio.total_value
        
        if daily_loss_pct >= self.config.max_daily_loss:
            return RiskCheckResult(
                passed=False,
                rule_name="daily_loss",
                message=f"当日亏损已达限制 ({daily_loss_pct:.1%} >= {self.config.max_daily_loss:.1%})",
                level=RiskLevel.CRITICAL,
                details={
                    'daily_loss': self._daily_stats['pnl'],
                    'daily_loss_pct': daily_loss_pct,
                    'limit_pct': self.config.max_daily_loss
                }
            )
        
        return RiskCheckResult(passed=True, rule_name="daily_loss")
    
    def _check_max_drawdown(self, signal: Signal, portfolio: Portfolio) -> RiskCheckResult:
        """检查最大回撤限制"""
        if self._current_drawdown >= self.config.max_drawdown:
            return RiskCheckResult(
                passed=False,
                rule_name="max_drawdown",
                message=f"回撤已达限制 ({self._current_drawdown:.1%} >= {self.config.max_drawdown:.1%})",
                level=RiskLevel.CRITICAL,
                details={
                    'current_drawdown': self._current_drawdown,
                    'limit_drawdown': self.config.max_drawdown,
                    'peak_equity': self._peak_equity
                }
            )
        
        return RiskCheckResult(passed=True, rule_name="max_drawdown")
    
    def _check_order_value(self, signal: Signal, portfolio: Portfolio) -> RiskCheckResult:
        """检查订单金额限制"""
        order_value = signal.price * 100  # 最小1手
        
        if order_value < self.config.min_order_value:
            return RiskCheckResult(
                passed=False,
                rule_name="order_value",
                message=f"订单金额过小 ({order_value:.0f} < {self.config.min_order_value})",
                level=RiskLevel.LOW,
                details={
                    'order_value': order_value,
                    'min_value': self.config.min_order_value
                }
            )
        
        return RiskCheckResult(passed=True, rule_name="order_value")
    
    def _check_cash_available(self, signal: Signal, portfolio: Portfolio) -> RiskCheckResult:
        """检查现金是否充足"""
        min_required = signal.price * 100 * 1.01  # 1手 + 1%缓冲
        
        if portfolio.cash < min_required:
            return RiskCheckResult(
                passed=False,
                rule_name="cash_available",
                message=f"可用资金不足 ({portfolio.cash:.0f} < {min_required:.0f})",
                level=RiskLevel.HIGH,
                details={
                    'cash': portfolio.cash,
                    'required': min_required
                }
            )
        
        return RiskCheckResult(passed=True, rule_name="cash_available")
    
    def _check_position_exists(self, signal: Signal, portfolio: Portfolio) -> RiskCheckResult:
        """检查是否有持仓可卖"""
        position = portfolio.get_position(signal.symbol)
        
        if not position or position.quantity <= 0:
            return RiskCheckResult(
                passed=False,
                rule_name="position_exists",
                message=f"无持仓可卖: {signal.symbol}",
                level=RiskLevel.MEDIUM
            )
        
        return RiskCheckResult(passed=True, rule_name="position_exists")
