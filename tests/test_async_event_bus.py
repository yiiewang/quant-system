"""
异步事件总线测试
"""
import pytest
import asyncio
from datetime import datetime

from src.core.async_event_bus import AsyncEventBus, get_async_event_bus
from src.core.event_bus import EventType, Event


class TestAsyncEventBus:
    """异步事件总线测试"""
    
    @pytest.fixture
    async def bus(self):
        """创建测试用的事件总线"""
        bus = AsyncEventBus(max_workers=2, queue_size=100)
        yield bus
        await bus.shutdown()
    
    @pytest.mark.asyncio
    async def test_subscribe_async_handler(self, bus):
        """测试订阅异步处理器"""
        results = []
        
        async def handler(event: Event):
            await asyncio.sleep(0.01)
            results.append(event.data['value'])
        
        bus.subscribe(EventType.SIGNAL_GENERATED, handler, is_async=True)
        
        await bus.emit_async(EventType.SIGNAL_GENERATED, value=1)
        await bus.emit_async(EventType.SIGNAL_GENERATED, value=2)
        
        # 等待处理完成
        await asyncio.sleep(0.1)
        
        assert len(results) == 2
        assert 1 in results
        assert 2 in results
    
    @pytest.mark.asyncio
    async def test_subscribe_sync_handler(self, bus):
        """测试订阅同步处理器"""
        results = []
        
        def handler(event: Event):
            results.append(event.data['value'])
        
        bus.subscribe(EventType.ORDER_FILLED, handler, is_async=False)
        
        await bus.emit_async(EventType.ORDER_FILLED, value=100)
        await asyncio.sleep(0.1)
        
        assert len(results) == 1
        assert results[0] == 100
    
    @pytest.mark.asyncio
    async def test_multiple_handlers(self, bus):
        """测试多个处理器"""
        results = []
        
        async def handler1(event: Event):
            results.append(('handler1', event.data['value']))
        
        async def handler2(event: Event):
            results.append(('handler2', event.data['value']))
        
        bus.subscribe(EventType.BAR_RECEIVED, handler1, is_async=True)
        bus.subscribe(EventType.BAR_RECEIVED, handler2, is_async=True)
        
        await bus.emit_async(EventType.BAR_RECEIVED, value=42)
        await asyncio.sleep(0.1)
        
        assert len(results) == 2
        assert ('handler1', 42) in results
        assert ('handler2', 42) in results
    
    @pytest.mark.asyncio
    async def test_decorator_subscribe(self, bus):
        """测试装饰器订阅"""
        results = []
        
        @bus.on(EventType.ENGINE_STARTED, is_async=True)
        async def handler(event: Event):
            results.append(event.data['status'])
        
        await bus.emit_async(EventType.ENGINE_STARTED, status='running')
        await asyncio.sleep(0.1)
        
        assert len(results) == 1
        assert results[0] == 'running'
    
    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus):
        """测试取消订阅"""
        results = []
        
        async def handler(event: Event):
            results.append(event.data['value'])
        
        bus.subscribe(EventType.DATA_UPDATED, handler, is_async=True)
        await bus.emit_async(EventType.DATA_UPDATED, value=1)
        await asyncio.sleep(0.1)
        
        assert len(results) == 1
        
        # 取消订阅
        bus.unsubscribe(EventType.DATA_UPDATED, handler)
        await bus.emit_async(EventType.DATA_UPDATED, value=2)
        await asyncio.sleep(0.1)
        
        # 结果不应该增加
        assert len(results) == 1
    
    @pytest.mark.asyncio
    async def test_once_handler(self, bus):
        """测试一次性处理器"""
        results = []
        
        async def handler(event: Event):
            results.append(event.data['value'])
        
        bus.once(EventType.POSITION_OPENED, handler, is_async=True)
        
        await bus.emit_async(EventType.POSITION_OPENED, value=1)
        await asyncio.sleep(0.1)
        
        assert len(results) == 1
        
        # 第二次不应该触发
        await bus.emit_async(EventType.POSITION_OPENED, value=2)
        await asyncio.sleep(0.1)
        
        assert len(results) == 1
    
    @pytest.mark.asyncio
    async def test_handler_error(self, bus):
        """测试处理器异常"""
        results = []
        
        async def error_handler(event: Event):
            raise ValueError("测试异常")
        
        async def normal_handler(event: Event):
            results.append(event.data['value'])
        
        bus.subscribe(EventType.RISK_WARNING, error_handler, is_async=True)
        bus.subscribe(EventType.RISK_WARNING, normal_handler, is_async=True)
        
        # 发送事件，即使一个处理器失败，另一个也应该执行
        await bus.emit_async(EventType.RISK_WARNING, value=42)
        await asyncio.sleep(0.2)
        
        # 正常处理器应该执行
        assert len(results) == 1
        assert results[0] == 42
    
    @pytest.mark.asyncio
    async def test_event_history(self, bus):
        """测试事件历史"""
        await bus.emit_async(EventType.SIGNAL_GENERATED, symbol='AAPL')
        await bus.emit_async(EventType.ORDER_FILLED, order_id='123')
        await asyncio.sleep(0.1)
        
        history = bus.get_event_history()
        assert len(history) == 2
        
        # 按类型查询
        signal_history = bus.get_event_history(event_type=EventType.SIGNAL_GENERATED)
        assert len(signal_history) == 1
        assert signal_history[0].data['symbol'] == 'AAPL'
    
    @pytest.mark.asyncio
    async def test_stats(self, bus):
        """测试统计信息"""
        async def handler(event: Event):
            pass
        
        bus.subscribe(EventType.SIGNAL_GENERATED, handler, is_async=True)
        
        # 发布多个事件
        for i in range(5):
            await bus.emit_async(EventType.SIGNAL_GENERATED, value=i)
        
        await asyncio.sleep(0.2)
        
        stats = bus.get_stats()
        assert stats['events_published'] == 5
        assert stats['events_processed'] == 5
        assert stats['processing_time_ms'] > 0
    
    @pytest.mark.asyncio
    async def test_clear(self, bus):
        """测试清除订阅"""
        results = []
        
        async def handler(event: Event):
            results.append(1)
        
        bus.subscribe(EventType.ENGINE_STOPPED, handler, is_async=True)
        
        # 清除特定类型的订阅
        bus.clear(EventType.ENGINE_STOPPED)
        
        await bus.emit_async(EventType.ENGINE_STOPPED)
        await asyncio.sleep(0.1)
        
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_concurrent_events(self, bus):
        """测试并发事件处理"""
        results = []
        
        async def slow_handler(event: Event):
            await asyncio.sleep(0.05)
            results.append(event.data['value'])
        
        bus.subscribe(EventType.BAR_RECEIVED, slow_handler, is_async=True)
        
        # 并发发送多个事件
        tasks = [
            bus.emit_async(EventType.BAR_RECEIVED, value=i)
            for i in range(10)
        ]
        await asyncio.gather(*tasks)
        await asyncio.sleep(0.3)
        
        # 所有事件都应该被处理
        assert len(results) == 10
    
    @pytest.mark.asyncio
    async def test_mixed_handlers(self, bus):
        """测试混合同步和异步处理器"""
        results = []
        
        async def async_handler(event: Event):
            await asyncio.sleep(0.01)
            results.append(('async', event.data['value']))
        
        def sync_handler(event: Event):
            results.append(('sync', event.data['value']))
        
        bus.subscribe(EventType.ORDER_SUBMITTED, async_handler, is_async=True)
        bus.subscribe(EventType.ORDER_SUBMITTED, sync_handler, is_async=False)
        
        await bus.emit_async(EventType.ORDER_SUBMITTED, value=100)
        await asyncio.sleep(0.1)
        
        assert len(results) == 2
        assert ('async', 100) in results
        assert ('sync', 100) in results


class TestGlobalAsyncEventBus:
    """全局异步事件总线测试"""
    
    @pytest.mark.asyncio
    async def test_get_global_bus(self):
        """测试获取全局事件总线"""
        bus1 = get_async_event_bus()
        bus2 = get_async_event_bus()
        
        # 应该是同一个实例
        assert bus1 is bus2
        
        await bus1.shutdown()
