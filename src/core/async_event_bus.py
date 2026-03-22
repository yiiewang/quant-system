"""
异步事件总线

提供异步事件处理能力，提升高并发场景下的性能
"""
import asyncio
import logging
from typing import Callable, Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import queue
import threading

logger = logging.getLogger(__name__)


# 导入原有的事件类型
from src.core.event_bus import EventType, Event


# 异步事件处理器类型
AsyncEventHandler = Callable[[Event], Any]  # 可以是同步或异步函数


@dataclass
class EventTask:
    """事件任务"""
    event: Event
    handler: AsyncEventHandler
    priority: int = 0  # 优先级，数值越大优先级越高
    created_at: datetime = field(default_factory=datetime.now)


class AsyncEventBus:
    """
    异步事件总线
    
    特点：
    - 支持异步事件处理
    - 线程池处理同步处理器
    - 事件队列缓冲
    - 优先级调度
    - 错误隔离和重试
    
    Usage:
        bus = AsyncEventBus(max_workers=4)
        
        # 订阅异步事件
        @bus.on(EventType.SIGNAL_GENERATED)
        async def handle_signal(event: Event):
            await process_signal(event.data)
        
        # 发布事件（异步）
        await bus.emit_async(EventType.SIGNAL_GENERATED, symbol='000001.SZ')
        
        # 关闭
        await bus.shutdown()
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        queue_size: int = 10000,
        retry_attempts: int = 3
    ):
        """
        初始化异步事件总线
        
        Args:
            max_workers: 线程池最大工作线程数
            queue_size: 事件队列大小
            retry_attempts: 失败重试次数
        """
        self._handlers: Dict[EventType, List[AsyncEventHandler]] = {}
        self._async_handlers: Dict[EventType, List[AsyncEventHandler]] = {}
        self._lock = threading.Lock()
        
        # 线程池（用于同步处理器）
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # 事件队列
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        
        # 重试配置
        self.retry_attempts = retry_attempts
        
        # 统计信息
        self._stats = {
            'events_published': 0,
            'events_processed': 0,
            'events_failed': 0,
            'processing_time_ms': 0.0
        }
        
        # 事件历史
        self._event_history: List[Event] = []
        self._max_history = 1000
        
        # 工作任务
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(f"初始化异步事件总线: max_workers={max_workers}, queue_size={queue_size}")
    
    def subscribe(
        self,
        event_type: EventType,
        handler: AsyncEventHandler,
        is_async: bool = False
    ) -> None:
        """
        订阅事件
        
        Args:
            event_type: 事件类型
            handler: 事件处理函数
            is_async: 是否为异步处理器
        """
        with self._lock:
            if is_async:
                if event_type not in self._async_handlers:
                    self._async_handlers[event_type] = []
                
                if handler not in self._async_handlers[event_type]:
                    self._async_handlers[event_type].append(handler)
                    logger.debug(f"订阅异步事件: {event_type.value}")
            else:
                if event_type not in self._handlers:
                    self._handlers[event_type] = []
                
                if handler not in self._handlers[event_type]:
                    self._handlers[event_type].append(handler)
                    logger.debug(f"订阅同步事件: {event_type.value}")
    
    def unsubscribe(
        self,
        event_type: EventType,
        handler: AsyncEventHandler
    ) -> None:
        """取消订阅"""
        with self._lock:
            if event_type in self._handlers and handler in self._handlers[event_type]:
                self._handlers[event_type].remove(handler)
            
            if event_type in self._async_handlers and handler in self._async_handlers[event_type]:
                self._async_handlers[event_type].remove(handler)
    
    async def publish_async(
        self,
        event_type: EventType,
        data: Dict[str, Any] = None,
        source: str = "",
        priority: int = 0
    ) -> None:
        """
        异步发布事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
            source: 事件来源
            priority: 优先级
        """
        event = Event(
            event_type=event_type,
            data=data or {},
            source=source
        )
        
        # 记录历史
        self._record_event(event)
        
        # 更新统计
        self._stats['events_published'] += 1
        
        # 获取处理器
        sync_handlers = self._handlers.get(event_type, [])
        async_handlers = self._async_handlers.get(event_type, [])
        
        if not sync_handlers and not async_handlers:
            logger.debug(f"事件无订阅者: {event_type.value}")
            return
        
        # 创建任务列表
        tasks = []
        
        # 处理异步处理器
        for handler in async_handlers:
            task = self._execute_async_handler(handler, event)
            tasks.append(task)
        
        # 处理同步处理器（在线程池中执行）
        for handler in sync_handlers:
            task = self._execute_sync_handler(handler, event)
            tasks.append(task)
        
        # 并发执行所有处理器
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _execute_async_handler(
        self,
        handler: AsyncEventHandler,
        event: Event
    ) -> None:
        """执行异步处理器"""
        for attempt in range(self.retry_attempts):
            try:
                import time
                start_time = time.time()
                
                # 执行异步处理器
                await handler(event)
                
                # 更新统计
                elapsed_ms = (time.time() - start_time) * 1000
                self._stats['processing_time_ms'] += elapsed_ms
                self._stats['events_processed'] += 1
                
                logger.debug(
                    f"异步处理器执行成功: {event.event_type.value}, "
                    f"耗时: {elapsed_ms:.2f}ms"
                )
                return
                
            except Exception as e:
                logger.error(
                    f"异步处理器执行失败 (attempt {attempt + 1}/{self.retry_attempts}): "
                    f"{event.event_type.value}, error={e}"
                )
                
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(0.1 * (attempt + 1))  # 指数退避
                else:
                    self._stats['events_failed'] += 1
                    logger.error(f"处理器最终失败: {event.event_type.value}")
    
    async def _execute_sync_handler(
        self,
        handler: AsyncEventHandler,
        event: Event
    ) -> None:
        """执行同步处理器（在线程池中）"""
        for attempt in range(self.retry_attempts):
            try:
                import time
                start_time = time.time()
                
                # 在线程池中执行同步处理器
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(self._executor, handler, event)
                
                # 更新统计
                elapsed_ms = (time.time() - start_time) * 1000
                self._stats['processing_time_ms'] += elapsed_ms
                self._stats['events_processed'] += 1
                
                logger.debug(
                    f"同步处理器执行成功: {event.event_type.value}, "
                    f"耗时: {elapsed_ms:.2f}ms"
                )
                return
                
            except Exception as e:
                logger.error(
                    f"同步处理器执行失败 (attempt {attempt + 1}/{self.retry_attempts}): "
                    f"{event.event_type.value}, error={e}"
                )
                
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(0.1 * (attempt + 1))
                else:
                    self._stats['events_failed'] += 1
                    logger.error(f"处理器最终失败: {event.event_type.value}")
    
    def emit(self, event_type: EventType, **kwargs) -> None:
        """
        发布事件（同步版本，用于兼容）
        
        注意：在异步上下文中应使用 emit_async
        """
        # 尝试获取事件循环
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在已有事件循环中，创建任务
                asyncio.create_task(
                    self.publish_async(event_type, kwargs)
                )
            else:
                # 运行新的事件循环
                loop.run_until_complete(
                    self.publish_async(event_type, kwargs)
                )
        except RuntimeError:
            # 没有事件循环，创建新的
            asyncio.run(self.publish_async(event_type, kwargs))
    
    async def emit_async(self, event_type: EventType, **kwargs) -> None:
        """发布事件（异步版本）"""
        await self.publish_async(event_type, kwargs)
    
    def on(self, event_type: EventType, is_async: bool = True) -> Callable:
        """
        装饰器方式订阅事件
        
        Args:
            event_type: 事件类型
            is_async: 是否为异步处理器
        
        Usage:
            @bus.on(EventType.SIGNAL_GENERATED, is_async=True)
            async def handle_signal(event: Event):
                await process(event)
        """
        def decorator(func: AsyncEventHandler) -> AsyncEventHandler:
            self.subscribe(event_type, func, is_async=is_async)
            return func
        return decorator
    
    def once(
        self,
        event_type: EventType,
        handler: AsyncEventHandler,
        is_async: bool = False
    ) -> None:
        """订阅一次性事件"""
        async def async_wrapper(event: Event):
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
            self.unsubscribe(event_type, async_wrapper)
        
        def sync_wrapper(event: Event):
            handler(event)
            self.unsubscribe(event_type, sync_wrapper)
        
        wrapper = async_wrapper if is_async else sync_wrapper
        self.subscribe(event_type, wrapper, is_async=is_async)
    
    def clear(self, event_type: EventType = None) -> None:
        """清除订阅"""
        with self._lock:
            if event_type:
                self._handlers.pop(event_type, None)
                self._async_handlers.pop(event_type, None)
            else:
                self._handlers.clear()
                self._async_handlers.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self._stats.copy()
        
        if stats['events_processed'] > 0:
            stats['avg_processing_time_ms'] = (
                stats['processing_time_ms'] / stats['events_processed']
            )
        
        stats['sync_handlers_count'] = sum(
            len(handlers) for handlers in self._handlers.values()
        )
        stats['async_handlers_count'] = sum(
            len(handlers) for handlers in self._async_handlers.values()
        )
        
        return stats
    
    def get_event_history(
        self,
        event_type: EventType = None,
        limit: int = 100
    ) -> List[Event]:
        """获取事件历史"""
        with self._lock:
            events = self._event_history.copy()
        
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        return events[-limit:]
    
    def _record_event(self, event: Event) -> None:
        """记录事件到历史"""
        with self._lock:
            self._event_history.append(event)
            
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]
    
    async def shutdown(self) -> None:
        """关闭事件总线"""
        logger.info("关闭异步事件总线...")
        
        # 等待队列处理完成
        if not self._event_queue.empty():
            logger.info(f"等待队列中的 {self._event_queue.qsize()} 个事件处理完成...")
            await self._event_queue.join()
        
        # 关闭线程池
        self._executor.shutdown(wait=True)
        
        # 打印统计信息
        stats = self.get_stats()
        logger.info(
            f"事件总线统计: "
            f"发布={stats['events_published']}, "
            f"处理={stats['events_processed']}, "
            f"失败={stats['events_failed']}, "
            f"平均耗时={stats.get('avg_processing_time_ms', 0):.2f}ms"
        )
        
        logger.info("异步事件总线已关闭")


# 全局异步事件总线实例
_global_async_bus: Optional[AsyncEventBus] = None


def get_async_event_bus(
    max_workers: int = 4,
    queue_size: int = 10000
) -> AsyncEventBus:
    """获取全局异步事件总线实例"""
    global _global_async_bus
    if _global_async_bus is None:
        _global_async_bus = AsyncEventBus(
            max_workers=max_workers,
            queue_size=queue_size
        )
    return _global_async_bus
