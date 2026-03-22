"""
查询优化测试
"""
import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta
import pandas as pd

from src.data.query_optimizer import (
    QueryCache,
    BatchQueryOptimizer,
    QueryPerformanceMonitor
)


class TestQueryCache:
    """查询缓存测试"""
    
    def test_cache_set_get(self):
        """测试缓存设置和获取"""
        cache = QueryCache(maxsize=10, ttl=60)
        
        # 创建测试数据
        df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
        
        # 设置缓存
        cache.set("SELECT * FROM table", (1, 2), df)
        
        # 获取缓存
        cached_df = cache.get("SELECT * FROM table", (1, 2))
        
        assert cached_df is not None
        assert cached_df.equals(df)
    
    def test_cache_miss(self):
        """测试缓存未命中"""
        cache = QueryCache(maxsize=10, ttl=60)
        
        result = cache.get("SELECT * FROM non_existent", ())
        assert result is None
    
    def test_cache_expiry(self):
        """测试缓存过期"""
        cache = QueryCache(maxsize=10, ttl=1)  # 1 秒过期
        
        df = pd.DataFrame({'a': [1, 2, 3]})
        cache.set("SELECT * FROM table", (), df)
        
        # 立即获取，应该命中
        cached = cache.get("SELECT * FROM table", ())
        assert cached is not None
        
        # 等待过期
        import time
        time.sleep(2)
        
        # 再次获取，应该未命中
        cached = cache.get("SELECT * FROM table", ())
        assert cached is None
    
    def test_cache_lru_eviction(self):
        """测试 LRU 淘汰"""
        cache = QueryCache(maxsize=3, ttl=3600)
        
        # 添加 3 个缓存项
        for i in range(3):
            df = pd.DataFrame({'value': [i]})
            cache.set(f"query_{i}", (), df)
        
        # 添加第 4 个，应该淘汰第一个
        df4 = pd.DataFrame({'value': [4]})
        cache.set("query_3", (), df4)
        
        # query_0 应该被淘汰
        cached = cache.get("query_0", ())
        assert cached is None
        
        # query_1 应该还在
        cached = cache.get("query_1", ())
        assert cached is not None
    
    def test_cache_stats(self):
        """测试缓存统计"""
        cache = QueryCache(maxsize=10, ttl=60)
        
        df = pd.DataFrame({'a': [1, 2, 3]})
        cache.set("query", (), df)
        
        # 命中
        cache.get("query", ())
        
        # 未命中
        cache.get("query2", ())
        
        stats = cache.get_stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['hit_rate'] == '50.00%'
    
    def test_cache_clear(self):
        """测试清空缓存"""
        cache = QueryCache(maxsize=10, ttl=60)
        
        df = pd.DataFrame({'a': [1, 2, 3]})
        cache.set("query", (), df)
        
        cache.clear()
        
        assert cache.get("query", ()) is None


class TestBatchQueryOptimizer:
    """批量查询优化器测试"""
    
    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        # 创建测试表并插入数据
        conn = sqlite3.connect(path)
        conn.execute('''
            CREATE TABLE ohlcv (
                symbol TEXT,
                date TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER
            )
        ''')
        
        # 插入测试数据
        symbols = ['AAPL', 'GOOGL', 'MSFT']
        base_date = datetime(2024, 1, 1)
        
        for symbol in symbols:
            for i in range(5):
                date = (base_date + timedelta(days=i)).strftime('%Y-%m-%d')
                conn.execute('''
                    INSERT INTO ohlcv 
                    (symbol, date, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (symbol, date, 100 + i, 110 + i, 90 + i, 105 + i, 1000000))
        
        conn.commit()
        conn.close()
        
        yield path
        
        # 清理
        os.unlink(path)
    
    def test_build_in_clause(self):
        """测试 IN 子句构建"""
        items = ['AAPL', 'GOOGL', 'MSFT']
        clause = BatchQueryOptimizer.build_in_clause(items)
        
        assert clause == "IN (?,?,?)"
    
    def test_batch_query_symbols(self, temp_db):
        """测试批量查询"""
        conn = sqlite3.connect(temp_db)
        
        symbols = ['AAPL', 'GOOGL', 'MSFT']
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 5)
        
        result = BatchQueryOptimizer.batch_query_symbols(
            conn=conn,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            frequency='daily',
            table='ohlcv'
        )
        
        conn.close()
        
        # 验证结果
        assert len(result) == 3
        assert 'AAPL' in result
        assert 'GOOGL' in result
        assert 'MSFT' in result
        
        # 验证数据
        for symbol in symbols:
            df = result[symbol]
            assert len(df) == 5
            assert 'date' in df.columns
            assert df['symbol'].iloc[0] == symbol
    
    def test_batch_query_with_date_filter(self, temp_db):
        """测试带日期过滤的批量查询"""
        conn = sqlite3.connect(temp_db)
        
        symbols = ['AAPL', 'GOOGL']
        start_date = datetime(2024, 1, 2)
        end_date = datetime(2024, 1, 4)
        
        result = BatchQueryOptimizer.batch_query_symbols(
            conn=conn,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            frequency='daily',
            table='ohlcv'
        )
        
        conn.close()
        
        # 验证日期范围
        for symbol in symbols:
            df = result[symbol]
            assert len(df) == 3  # 3 天的数据


class TestQueryPerformanceMonitor:
    """查询性能监控测试"""
    
    def test_monitor_slow_query(self):
        """测试慢查询监控"""
        monitor = QueryPerformanceMonitor(slow_query_threshold=0.5)
        
        import time
        
        # 模拟慢查询
        with monitor.monitor("SELECT * FROM large_table"):
            time.sleep(1.0)
        
        # 检查统计
        stats = monitor.get_stats()
        assert "SELECT * FROM large_table" in stats
        
        # 检查慢查询列表
        slow_queries = monitor.get_slow_queries()
        assert len(slow_queries) > 0
    
    def test_monitor_fast_query(self):
        """测试快速查询监控"""
        monitor = QueryPerformanceMonitor(slow_query_threshold=1.0)
        
        with monitor.monitor("SELECT 1"):
            pass
        
        stats = monitor.get_stats()
        assert "SELECT 1" in stats
        
        # 不应该是慢查询
        slow_queries = monitor.get_slow_queries()
        assert len(slow_queries) == 0
    
    def test_monitor_stats(self):
        """测试统计信息"""
        monitor = QueryPerformanceMonitor(slow_query_threshold=1.0)
        
        # 执行多次查询
        for _ in range(5):
            with monitor.monitor("query1"):
                pass
        
        for _ in range(3):
            with monitor.monitor("query2"):
                pass
        
        stats = monitor.get_stats()
        
        assert stats["query1"]["count"] == 5
        assert stats["query2"]["count"] == 3
