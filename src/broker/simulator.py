"""
模拟执行器
用于回测和模拟交易
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from collections import defaultdict
import uuid
import logging

from .base import BaseExecutor, OrderError
from src.core.models import (
    Order, OrderStatus, OrderSide, OrderType,
    Position, Portfolio, Trade
)

logger = logging.getLogger(__name__)


class SimulatedExecutor(BaseExecutor):
    """
    模拟执行器
    
    实现完整的模拟交易功能，包括:
    - 订单提交和成交模拟
    - 持仓管理
    - 手续费计算
    - 滑点模拟
    
    Attributes:
        initial_capital: 初始资金
        commission_rate: 手续费率
        slippage: 滑点比例
        min_commission: 最低手续费
    """
    
    def __init__(self, initial_capital: float = 100000,
                 commission_rate: float = 0.0003,
                 slippage: float = 0.001,
                 min_commission: float = 5.0,
                 config: Dict[str, Any] = None):
        """
        初始化模拟执行器
        
        Args:
            initial_capital: 初始资金
            commission_rate: 手续费率（默认万三）
            slippage: 滑点比例（默认0.1%）
            min_commission: 最低手续费
            config: 其他配置
        """
        super().__init__(config)
        
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage
        self.min_commission = min_commission
        
        # 内部状态
        self._cash = initial_capital
        self._positions: Dict[str, Position] = {}
        self._orders: Dict[str, Order] = {}
        self._trades: List[Trade] = []
        self._daily_pnl = 0.0
        self._total_pnl = 0.0
        
        # 当前价格缓存（用于计算市值）
        self._price_cache: Dict[str, float] = {}
        
        logger.info(f"初始化模拟执行器: 资金={initial_capital}, 费率={commission_rate}")
    
    def submit_order(self, order: Order) -> Order:
        """
        提交订单
        
        模拟订单执行逻辑:
        1. 验证订单有效性
        2. 检查资金/持仓是否充足
        3. 模拟成交（考虑滑点）
        4. 更新持仓和现金
        
        Args:
            order: 订单对象
        
        Returns:
            Order: 执行后的订单
        """
        logger.info(f"提交订单: {order.symbol} {order.side.value} {order.quantity}")
        
        # 验证订单
        self._validate_order(order)
        
        # 保存订单
        self._orders[order.order_id] = order
        order.status = OrderStatus.SUBMITTED
        order.updated_at = datetime.now()
        
        # 模拟成交
        try:
            self._execute_order(order)
        except Exception as e:
            order.status = OrderStatus.REJECTED
            order.message = str(e)
            logger.error(f"订单执行失败: {e}")
            self._emit_order_event('rejected', order)
        
        return order
    
    def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        order = self._orders.get(order_id)
        
        if not order:
            logger.warning(f"订单不存在: {order_id}")
            return False
        
        if not order.is_active:
            logger.warning(f"订单无法取消，当前状态: {order.status.value}")
            return False
        
        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.now()
        self._emit_order_event('cancelled', order)
        
        logger.info(f"订单已取消: {order_id}")
        return True
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单"""
        return self._orders.get(order_id)
    
    def get_orders(self, status: OrderStatus = None,
                   symbol: str = None,
                   limit: int = 100) -> List[Order]:
        """获取订单列表"""
        orders = list(self._orders.values())
        
        if status:
            orders = [o for o in orders if o.status == status]
        
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        
        # 按时间倒序
        orders.sort(key=lambda x: x.created_at, reverse=True)
        
        return orders[:limit]
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓"""
        position = self._positions.get(symbol)
        
        if position and position.quantity > 0:
            # 更新当前价格
            if symbol in self._price_cache:
                position.update_price(self._price_cache[symbol])
            return position
        
        return None
    
    def get_positions(self) -> List[Position]:
        """获取所有持仓"""
        positions = []
        
        for symbol, position in self._positions.items():
            if position.quantity > 0:
                # 更新当前价格
                if symbol in self._price_cache:
                    position.update_price(self._price_cache[symbol])
                positions.append(position)
        
        return positions
    
    def get_portfolio(self) -> Portfolio:
        """获取投资组合"""
        positions = {s: p for s, p in self._positions.items() if p.quantity > 0}
        
        # 计算持仓市值
        position_value = sum(p.market_value for p in positions.values())
        
        return Portfolio(
            cash=self._cash,
            total_value=self._cash + position_value,
            positions=positions,
            daily_pnl=self._daily_pnl,
            total_pnl=self._total_pnl,
            initial_capital=self.initial_capital
        )
    
    def get_trades(self, symbol: str = None,
                   start_date: datetime = None,
                   end_date: datetime = None,
                   limit: int = 100) -> List[Trade]:
        """获取成交记录"""
        trades = self._trades.copy()
        
        if symbol:
            trades = [t for t in trades if t.symbol == symbol]
        
        if start_date:
            trades = [t for t in trades if t.timestamp >= start_date]
        
        if end_date:
            trades = [t for t in trades if t.timestamp <= end_date]
        
        # 按时间倒序
        trades.sort(key=lambda x: x.timestamp, reverse=True)
        
        return trades[:limit]
    
    def update_price(self, symbol: str, price: float) -> None:
        """
        更新价格缓存
        
        Args:
            symbol: 股票代码
            price: 最新价格
        """
        self._price_cache[symbol] = price
        
        # 更新持仓浮动盈亏
        if symbol in self._positions:
            self._positions[symbol].update_price(price)
    
    def reset_daily(self) -> None:
        """重置每日统计"""
        self._daily_pnl = 0.0
    
    def reset(self) -> None:
        """重置所有状态"""
        self._cash = self.initial_capital
        self._positions.clear()
        self._orders.clear()
        self._trades.clear()
        self._daily_pnl = 0.0
        self._total_pnl = 0.0
        self._price_cache.clear()
        
        logger.info("模拟执行器已重置")
    
    def _validate_order(self, order: Order) -> None:
        """
        验证订单有效性
        
        Args:
            order: 待验证订单
        
        Raises:
            OrderError: 订单无效时抛出
        """
        # 检查数量
        if order.quantity <= 0:
            raise OrderError("订单数量必须为正数", order)
        
        # A股必须是100的整数倍
        if order.quantity % 100 != 0:
            raise OrderError("订单数量必须是100的整数倍", order)
        
        # 买入检查资金
        if order.side == OrderSide.BUY:
            price = order.price or self._price_cache.get(order.symbol, 0)
            if price <= 0:
                raise OrderError("无法获取股票价格", order)
            
            required = price * order.quantity * (1 + self.slippage)
            if required > self._cash:
                raise OrderError(f"资金不足: 需要 {required:.2f}, 可用 {self._cash:.2f}", order)
        
        # 卖出检查持仓
        elif order.side == OrderSide.SELL:
            position = self._positions.get(order.symbol)
            if not position or position.quantity < order.quantity:
                available = position.quantity if position else 0
                raise OrderError(f"持仓不足: 需要 {order.quantity}, 可用 {available}", order)
    
    def _execute_order(self, order: Order) -> None:
        """
        执行订单
        
        Args:
            order: 待执行订单
        """
        # 获取执行价格
        base_price = order.price or self._price_cache.get(order.symbol, 0)
        
        if base_price <= 0:
            raise OrderError("无法获取执行价格", order)
        
        # 计算滑点
        if order.side == OrderSide.BUY:
            exec_price = base_price * (1 + self.slippage)
        else:
            exec_price = base_price * (1 - self.slippage)
        
        # 计算手续费
        commission = max(
            self.min_commission,
            exec_price * order.quantity * self.commission_rate
        )
        
        # 卖出额外印花税（千分之一）
        if order.side == OrderSide.SELL:
            commission += exec_price * order.quantity * 0.001
        
        # 更新订单状态
        order.filled_quantity = order.quantity
        order.filled_price = exec_price
        order.commission = commission
        order.status = OrderStatus.FILLED
        order.updated_at = datetime.now()
        
        # 创建成交记录
        trade = Trade(
            trade_id=str(uuid.uuid4())[:8].upper(),
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=exec_price,
            commission=commission
        )
        self._trades.append(trade)
        
        # 更新持仓和现金
        if order.side == OrderSide.BUY:
            self._process_buy(order, trade)
        else:
            self._process_sell(order, trade)
        
        logger.info(
            f"订单成交: {order.symbol} {order.side.value} "
            f"{order.quantity}@{exec_price:.2f} 手续费={commission:.2f}"
        )
        
        self._emit_order_event('filled', order)
    
    def _process_buy(self, order: Order, trade: Trade) -> None:
        """
        处理买入成交
        
        Args:
            order: 订单
            trade: 成交记录
        """
        cost = trade.quantity * trade.price + trade.commission
        
        # 扣除现金
        self._cash -= cost
        
        # 更新持仓
        if order.symbol in self._positions:
            position = self._positions[order.symbol]
            # 计算新的平均成本
            total_cost = position.avg_cost * position.quantity + cost
            total_quantity = position.quantity + trade.quantity
            position.avg_cost = total_cost / total_quantity
            position.quantity = total_quantity
        else:
            self._positions[order.symbol] = Position(
                symbol=order.symbol,
                quantity=trade.quantity,
                avg_cost=trade.price + trade.commission / trade.quantity,
                current_price=trade.price
            )
        
        # 更新价格缓存
        self._price_cache[order.symbol] = trade.price
    
    def _process_sell(self, order: Order, trade: Trade) -> None:
        """
        处理卖出成交
        
        Args:
            order: 订单
            trade: 成交记录
        """
        proceeds = trade.quantity * trade.price - trade.commission
        
        # 增加现金
        self._cash += proceeds
        
        # 更新持仓
        position = self._positions[order.symbol]
        
        # 计算已实现盈亏
        realized_pnl = (trade.price - position.avg_cost) * trade.quantity - trade.commission
        position.realized_pnl += realized_pnl
        self._daily_pnl += realized_pnl
        self._total_pnl += realized_pnl
        
        # 减少持仓
        position.quantity -= trade.quantity
        
        # 如果持仓为0，可以选择删除
        if position.quantity == 0:
            # 保留记录但数量为0
            pass
        
        # 更新价格缓存
        self._price_cache[order.symbol] = trade.price
