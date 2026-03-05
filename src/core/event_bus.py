"""
事件总线
提供简单的发布-订阅模式，用于模块间解耦通信
"""
import logging
from typing import Callable, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Lock

logger = logging.getLogger(__name__)


class EventType(Enum):
    """事件类型"""
    # 引擎事件
    ENGINE_STARTED = "engine.started"
    ENGINE_STOPPED = "engine.stopped"
    ENGINE_PAUSED = "engine.paused"
    ENGINE_RESUMED = "engine.resumed"
    ENGINE_ERROR = "engine.error"
    
    # 信号事件
    SIGNAL_GENERATED = "signal.generated"
    SIGNAL_REJECTED = "signal.rejected"
    
    # 订单事件
    ORDER_SUBMITTED = "order.submitted"
    ORDER_FILLED = "order.filled"
    ORDER_PARTIAL = "order.partial"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_REJECTED = "order.rejected"
    
    # 持仓事件
    POSITION_OPENED = "position.opened"
    POSITION_CLOSED = "position.closed"
    POSITION_UPDATED = "position.updated"
    
    # 数据事件
    DATA_UPDATED = "data.updated"
    BAR_RECEIVED = "bar.received"
    
    # 风控事件
    RISK_WARNING = "risk.warning"
    RISK_BREACH = "risk.breach"


@dataclass
class Event:
    """
    事件对象
    
    Attributes:
        event_type: 事件类型
        data: 事件数据
        timestamp: 事件时间
        source: 事件来源
    """
    event_type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""
    
    def __str__(self) -> str:
        return f"Event({self.event_type.value}, source={self.source}, data={self.data})"


# 事件处理器类型
EventHandler = Callable[[Event], None]


class EventBus:
    """
    事件总线
    
    提供事件的发布和订阅功能，支持同步和异步处理
    
    Usage:
        bus = EventBus()
        
        # 订阅事件
        def on_signal(event: Event):
            print(f"收到信号: {event.data}")
        
        bus.subscribe(EventType.SIGNAL_GENERATED, on_signal)
        
        # 发布事件
        bus.publish(EventType.SIGNAL_GENERATED, {'symbol': '000001.SZ'})
    """
    
    def __init__(self):
        self._handlers: Dict[EventType, List[EventHandler]] = {}
        self._lock = Lock()
        self._event_history: List[Event] = []
        self._max_history = 1000
    
    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """
        订阅事件
        
        Args:
            event_type: 事件类型
            handler: 事件处理函数
        """
        with self._lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            
            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)
                logger.debug(f"订阅事件: {event_type.value}")
    
    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """
        取消订阅
        
        Args:
            event_type: 事件类型
            handler: 事件处理函数
        """
        with self._lock:
            if event_type in self._handlers:
                if handler in self._handlers[event_type]:
                    self._handlers[event_type].remove(handler)
                    logger.debug(f"取消订阅: {event_type.value}")
    
    def publish(self, event_type: EventType, data: Dict[str, Any] = None, 
                source: str = "") -> None:
        """
        发布事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
            source: 事件来源
        """
        event = Event(
            event_type=event_type,
            data=data or {},
            source=source
        )
        
        # 记录历史
        self._record_event(event)
        
        # 获取处理器
        handlers = self._handlers.get(event_type, [])
        
        if not handlers:
            logger.debug(f"事件无订阅者: {event_type.value}")
            return
        
        # 同步执行所有处理器
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"事件处理器异常: {event_type.value}, error={e}")
    
    def emit(self, event_type: EventType, **kwargs) -> None:
        """
        发布事件（简化版本）
        
        Args:
            event_type: 事件类型
            **kwargs: 事件数据
        """
        self.publish(event_type, kwargs)
    
    def on(self, event_type: EventType) -> Callable:
        """
        装饰器方式订阅事件
        
        Usage:
            @bus.on(EventType.SIGNAL_GENERATED)
            def handle_signal(event: Event):
                print(event.data)
        """
        def decorator(func: EventHandler) -> EventHandler:
            self.subscribe(event_type, func)
            return func
        return decorator
    
    def once(self, event_type: EventType, handler: EventHandler) -> None:
        """
        订阅一次性事件（触发后自动取消）
        
        Args:
            event_type: 事件类型
            handler: 事件处理函数
        """
        def wrapper(event: Event):
            handler(event)
            self.unsubscribe(event_type, wrapper)
        
        self.subscribe(event_type, wrapper)
    
    def clear(self, event_type: EventType = None) -> None:
        """
        清除订阅
        
        Args:
            event_type: 事件类型，为空则清除所有
        """
        with self._lock:
            if event_type:
                self._handlers.pop(event_type, None)
            else:
                self._handlers.clear()
    
    def get_subscribers(self, event_type: EventType) -> List[EventHandler]:
        """获取事件订阅者列表"""
        return self._handlers.get(event_type, []).copy()
    
    def get_event_history(self, event_type: EventType = None, 
                          limit: int = 100) -> List[Event]:
        """
        获取事件历史
        
        Args:
            event_type: 事件类型，为空则返回所有
            limit: 返回数量限制
        
        Returns:
            List[Event]: 事件列表
        """
        with self._lock:
            events = self._event_history.copy()
        
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        return events[-limit:]
    
    def _record_event(self, event: Event) -> None:
        """记录事件到历史"""
        with self._lock:
            self._event_history.append(event)
            
            # 限制历史数量
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]


# 全局事件总线实例
_global_bus: EventBus = None


def get_event_bus() -> EventBus:
    """获取全局事件总线实例"""
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus
