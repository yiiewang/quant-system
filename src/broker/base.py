"""
执行器基类
定义订单执行的接口规范
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
import logging

from src.core.models import Order, OrderStatus, OrderSide, OrderType, Position, Portfolio, Trade

logger = logging.getLogger(__name__)


class BaseExecutor(ABC):
    """
    执行器基类
    
    定义订单提交、取消、查询等操作的接口
    子类需要实现具体的执行逻辑（模拟交易或对接券商API）
    
    Usage:
        executor = SimulatedExecutor(initial_capital=100000)
        
        # 提交订单
        order = Order(
            symbol='000001.SZ',
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100
        )
        result = executor.submit_order(order)
        
        # 查询持仓
        positions = executor.get_positions()
        
        # 查询组合
        portfolio = executor.get_portfolio()
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化执行器
        
        Args:
            config: 配置参数
        """
        self.config = config or {}
        self._order_handlers: Dict[str, List[Callable]] = {}
    
    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        """
        提交订单
        
        Args:
            order: 订单对象
        
        Returns:
            Order: 更新后的订单（包含执行结果）
        
        Raises:
            OrderError: 订单执行失败时抛出
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        取消订单
        
        Args:
            order_id: 订单ID
        
        Returns:
            bool: 是否成功取消
        """
        pass
    
    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Order]:
        """
        获取订单状态
        
        Args:
            order_id: 订单ID
        
        Returns:
            Optional[Order]: 订单对象，不存在返回 None
        """
        pass
    
    @abstractmethod
    def get_orders(self, status: OrderStatus = None, 
                   symbol: str = None,
                   limit: int = 100) -> List[Order]:
        """
        获取订单列表
        
        Args:
            status: 订单状态过滤
            symbol: 股票代码过滤
            limit: 返回数量限制
        
        Returns:
            List[Order]: 订单列表
        """
        pass
    
    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        获取指定持仓
        
        Args:
            symbol: 股票代码
        
        Returns:
            Optional[Position]: 持仓对象，无持仓返回 None
        """
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Position]:
        """
        获取所有持仓
        
        Returns:
            List[Position]: 持仓列表
        """
        pass
    
    @abstractmethod
    def get_portfolio(self) -> Portfolio:
        """
        获取投资组合
        
        Returns:
            Portfolio: 投资组合对象
        """
        pass
    
    @abstractmethod
    def get_trades(self, symbol: str = None, 
                   start_date: datetime = None,
                   end_date: datetime = None,
                   limit: int = 100) -> List[Trade]:
        """
        获取成交记录
        
        Args:
            symbol: 股票代码过滤
            start_date: 开始日期
            end_date: 结束日期
            limit: 返回数量限制
        
        Returns:
            List[Trade]: 成交记录列表
        """
        pass
    
    def get_pending_orders(self) -> List[Order]:
        """
        获取待执行订单
        
        Returns:
            List[Order]: 待执行订单列表
        """
        return self.get_orders(status=OrderStatus.SUBMITTED)
    
    def cancel_all_orders(self, symbol: str = None) -> int:
        """
        取消所有待执行订单
        
        Args:
            symbol: 股票代码（可选，为空则取消所有）
        
        Returns:
            int: 取消的订单数量
        """
        pending = self.get_pending_orders()
        
        if symbol:
            pending = [o for o in pending if o.symbol == symbol]
        
        cancelled = 0
        for order in pending:
            if self.cancel_order(order.order_id):
                cancelled += 1
        
        return cancelled
    
    def has_position(self, symbol: str) -> bool:
        """
        是否持有某股票
        
        Args:
            symbol: 股票代码
        
        Returns:
            bool: 是否持有
        """
        position = self.get_position(symbol)
        return position is not None and position.quantity > 0
    
    def get_available_cash(self) -> float:
        """
        获取可用现金
        
        Returns:
            float: 可用现金
        """
        return self.get_portfolio().cash
    
    def on_order_event(self, event_type: str, handler: Callable) -> None:
        """
        注册订单事件处理器
        
        Args:
            event_type: 事件类型 (filled/cancelled/rejected)
            handler: 处理函数
        """
        if event_type not in self._order_handlers:
            self._order_handlers[event_type] = []
        self._order_handlers[event_type].append(handler)
    
    def _emit_order_event(self, event_type: str, order: Order) -> None:
        """
        触发订单事件
        
        Args:
            event_type: 事件类型
            order: 订单对象
        """
        handlers = self._order_handlers.get(event_type, [])
        for handler in handlers:
            try:
                handler(order)
            except Exception as e:
                logger.error(f"订单事件处理异常: {e}")


class OrderError(Exception):
    """订单错误"""
    
    def __init__(self, message: str, order: Order = None):
        super().__init__(message)
        self.order = order
