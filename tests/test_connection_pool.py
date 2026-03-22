"""
连接池测试
"""
import pytest
import sqlite3
import tempfile
import os
from pathlib import Path

from src.data.connection_pool import ConnectionPool, ReadWriteConnectionPool


class TestConnectionPool:
    """连接池测试"""
    
    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        # 创建测试表
        conn = sqlite3.connect(path)
        conn.execute('''
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT
            )
        ''')
        conn.commit()
        conn.close()
        
        yield path
        
        # 清理
        os.unlink(path)
    
    def test_init_pool(self, temp_db):
        """测试初始化连接池"""
        pool = ConnectionPool(temp_db, pool_size=5)
        
        assert pool.pool_size == 5
        assert pool.db_path == temp_db
        assert pool._pool.qsize() == 5
        
        pool.close()
    
    def test_get_connection(self, temp_db):
        """测试获取连接"""
        pool = ConnectionPool(temp_db, pool_size=3)
        
        with pool.get_connection() as conn:
            assert conn is not None
            # 测试查询
            cursor = conn.execute("SELECT 1")
            result = cursor.fetchone()
            assert result == (1,)
        
        pool.close()
    
    def test_connection_reuse(self, temp_db):
        """测试连接复用"""
        pool = ConnectionPool(temp_db, pool_size=2)
        
        # 获取并归还连接
        with pool.get_connection() as conn1:
            conn_id1 = id(conn1)
        
        # 再次获取连接
        with pool.get_connection() as conn2:
            conn_id2 = id(conn2)
        
        # 应该是同一个连接（被复用）
        assert conn_id1 == conn_id2
        
        pool.close()
    
    def test_pool_exhaustion(self, temp_db):
        """测试连接池耗尽"""
        pool = ConnectionPool(temp_db, pool_size=2, max_overflow=0, timeout=1.0)
        
        # 借用所有连接
        conn1 = pool._borrow_connection()
        conn2 = pool._borrow_connection()
        
        # 第三个请求应该超时
        with pytest.raises(Exception):
            pool._borrow_connection()
        
        # 归还连接
        pool._return_connection(conn1)
        pool._return_connection(conn2)
        
        pool.close()
    
    def test_pool_stats(self, temp_db):
        """测试统计信息"""
        pool = ConnectionPool(temp_db, pool_size=3)
        
        with pool.get_connection() as conn:
            conn.execute("INSERT INTO test_table (name) VALUES (?)", ('test',))
            conn.commit()
        
        stats = pool.get_stats()
        assert stats['pool_size'] == 3
        assert stats['total_borrowed'] == 1
        assert stats['total_returned'] == 1
        
        pool.close()
    
    def test_context_manager(self, temp_db):
        """测试上下文管理器"""
        with ConnectionPool(temp_db, pool_size=2) as pool:
            with pool.get_connection() as conn:
                cursor = conn.execute("SELECT 1")
                assert cursor.fetchone() == (1,)
        
        # 连接池应该已关闭


class TestReadWriteConnectionPool:
    """读写分离连接池测试"""
    
    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        # 创建测试表
        conn = sqlite3.connect(path)
        conn.execute('''
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT
            )
        ''')
        conn.commit()
        conn.close()
        
        yield path
        
        # 清理
        os.unlink(path)
    
    def test_init_pool(self, temp_db):
        """测试初始化"""
        pool = ReadWriteConnectionPool(temp_db, read_pool_size=5)
        
        assert pool.read_pool_size == 5
        assert pool.db_path == temp_db
        
        pool.close()
    
    def test_read_connection(self, temp_db):
        """测试读连接"""
        pool = ReadWriteConnectionPool(temp_db, read_pool_size=3)
        
        # 先插入数据
        with pool.get_write_connection() as conn:
            conn.execute("INSERT INTO test_table (name) VALUES (?)", ('test',))
            conn.commit()
        
        # 读取数据
        with pool.get_read_connection() as conn:
            cursor = conn.execute("SELECT * FROM test_table")
            rows = cursor.fetchall()
            assert len(rows) == 1
            assert rows[0][1] == 'test'
        
        pool.close()
    
    def test_write_connection(self, temp_db):
        """测试写连接"""
        pool = ReadWriteConnectionPool(temp_db, read_pool_size=3)
        
        with pool.get_write_connection() as conn:
            conn.execute("INSERT INTO test_table (name) VALUES (?)", ('test1',))
            conn.commit()
        
        with pool.get_write_connection() as conn:
            conn.execute("INSERT INTO test_table (name) VALUES (?)", ('test2',))
            conn.commit()
        
        # 验证数据
        with pool.get_read_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM test_table")
            count = cursor.fetchone()[0]
            assert count == 2
        
        pool.close()
    
    def test_concurrent_reads(self, temp_db):
        """测试并发读"""
        import threading
        
        pool = ReadWriteConnectionPool(temp_db, read_pool_size=5)
        
        # 插入数据
        with pool.get_write_connection() as conn:
            conn.execute("INSERT INTO test_table (name) VALUES (?)", ('test',))
            conn.commit()
        
        # 并发读
        results = []
        
        def read_data():
            with pool.get_read_connection() as conn:
                cursor = conn.execute("SELECT * FROM test_table")
                results.append(cursor.fetchall())
        
        threads = [threading.Thread(target=read_data) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(results) == 5
        assert all(len(r) == 1 for r in results)
        
        pool.close()
    
    def test_stats(self, temp_db):
        """测试统计信息"""
        pool = ReadWriteConnectionPool(temp_db, read_pool_size=3)
        
        with pool.get_read_connection() as conn:
            conn.execute("SELECT 1")
        
        with pool.get_write_connection() as conn:
            conn.execute("INSERT INTO test_table (name) VALUES (?)", ('test',))
            conn.commit()
        
        stats = pool.get_stats()
        assert 'read_pool' in stats
        assert 'write_connection' in stats
        
        pool.close()
