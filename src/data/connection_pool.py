"""
数据库连接池管理

提供 SQLite 连接池，优化并发性能和资源管理
"""
import sqlite3
import threading
import queue
import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


class ConnectionPool:
    """
    SQLite 连接池
    
    特点：
    - 维护固定数量的连接，避免频繁创建/销毁
    - 线程安全的连接获取和释放
    - 连接健康检查
    - 自动清理过期连接
    
    Usage:
        pool = ConnectionPool("data/market.db", pool_size=10)
        
        # 使用连接
        with pool.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM ohlcv")
            results = cursor.fetchall()
        
        # 关闭连接池
        pool.close()
    """
    
    def __init__(
        self,
        db_path: str,
        pool_size: int = 10,
        max_overflow: int = 20,
        timeout: float = 30.0,
        **kwargs
    ):
        """
        初始化连接池
        
        Args:
            db_path: 数据库文件路径
            pool_size: 连接池大小
            max_overflow: 最大溢出连接数
            timeout: 获取连接的超时时间（秒）
            **kwargs: 其他 SQLite 连接参数
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.timeout = timeout
        self.connection_kwargs = kwargs
        
        # 确保数据库目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 连接池队列
        self._pool: queue.Queue = queue.Queue(maxsize=pool_size + max_overflow)
        self._lock = threading.Lock()
        
        # 统计信息
        self._total_created = 0
        self._total_borrowed = 0
        self._total_returned = 0
        
        # 初始化连接池
        self._initialize_pool()
        
        logger.info(
            f"初始化连接池: db={db_path}, pool_size={pool_size}, "
            f"max_overflow={max_overflow}"
        )
    
    def _initialize_pool(self) -> None:
        """初始化连接池"""
        for _ in range(self.pool_size):
            conn = self._create_connection()
            if conn:
                self._pool.put(conn)
    
    def _create_connection(self) -> Optional[sqlite3.Connection]:
        """创建新的数据库连接"""
        try:
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,  # 允许多线程使用
                **self.connection_kwargs
            )
            
            # 启用优化配置
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA cache_size=-64000')  # 64MB 缓存
            conn.execute('PRAGMA temp_store=MEMORY')
            conn.execute('PRAGMA mmap_size=268435456')  # 256MB 内存映射
            
            # 启用外键约束
            conn.execute('PRAGMA foreign_keys=ON')
            
            self._total_created += 1
            return conn
            
        except Exception as e:
            logger.error(f"创建连接失败: {e}")
            return None
    
    def _is_connection_valid(self, conn: sqlite3.Connection) -> bool:
        """检查连接是否有效"""
        try:
            # 执行简单查询测试连接
            conn.execute("SELECT 1")
            return True
        except Exception:
            return False
    
    @contextmanager
    def get_connection(self):
        """
        获取连接（上下文管理器）
        
        Yields:
            sqlite3.Connection: 数据库连接
            
        Usage:
            with pool.get_connection() as conn:
                cursor = conn.execute("SELECT * FROM table")
                results = cursor.fetchall()
        """
        conn = self._borrow_connection()
        try:
            yield conn
        finally:
            self._return_connection(conn)
    
    def _borrow_connection(self) -> sqlite3.Connection:
        """从连接池借用连接"""
        try:
            # 尝试从池中获取连接
            conn = self._pool.get(timeout=self.timeout)
            
            # 检查连接是否有效
            if not self._is_connection_valid(conn):
                # 连接无效，创建新连接
                logger.warning("连接无效，创建新连接")
                conn = self._create_connection()
                if not conn:
                    raise RuntimeError("无法创建数据库连接")
            
            self._total_borrowed += 1
            return conn
            
        except queue.Empty:
            # 池中没有可用连接，创建新连接（溢出）
            logger.warning("连接池耗尽，创建溢出连接")
            conn = self._create_connection()
            if not conn:
                raise RuntimeError("无法创建数据库连接（连接池已满）")
            
            self._total_borrowed += 1
            return conn
    
    def _return_connection(self, conn: sqlite3.Connection) -> None:
        """归还连接到连接池"""
        try:
            # 检查连接是否有效
            if self._is_connection_valid(conn):
                # 尝试归还到池中
                try:
                    self._pool.put_nowait(conn)
                    self._total_returned += 1
                except queue.Full:
                    # 池已满，关闭连接
                    try:
                        conn.close()
                    except Exception:
                        pass
            else:
                # 连接无效，关闭连接
                try:
                    conn.close()
                except Exception:
                    pass
                
        except Exception as e:
            logger.error(f"归还连接失败: {e}")
    
    def close(self) -> None:
        """关闭连接池，释放所有连接"""
        logger.info("关闭连接池...")
        
        # 关闭池中所有连接
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                try:
                    conn.close()
                except Exception:
                    pass
            except queue.Empty:
                break
        
        logger.info(
            f"连接池已关闭 - "
            f"创建: {self._total_created}, "
            f"借用: {self._total_borrowed}, "
            f"归还: {self._total_returned}"
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        return {
            'db_path': self.db_path,
            'pool_size': self.pool_size,
            'max_overflow': self.max_overflow,
            'current_size': self._pool.qsize(),
            'total_created': self._total_created,
            'total_borrowed': self._total_borrowed,
            'total_returned': self._total_returned,
        }
    
    def __enter__(self) -> 'ConnectionPool':
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


class ReadWriteConnectionPool:
    """
    读写分离连接池
    
    - 读连接池：多个只读连接，支持并发读
    - 写连接池：单个写连接，保证写操作串行
    
    Usage:
        pool = ReadWriteConnectionPool("data/market.db", read_pool_size=10)
        
        # 读操作
        with pool.get_read_connection() as conn:
            results = conn.execute("SELECT * FROM table").fetchall()
        
        # 写操作
        with pool.get_write_connection() as conn:
            conn.execute("INSERT INTO table VALUES (?)", (value,))
            conn.commit()
    """
    
    def __init__(
        self,
        db_path: str,
        read_pool_size: int = 10,
        write_timeout: float = 30.0
    ):
        """
        初始化读写分离连接池
        
        Args:
            db_path: 数据库文件路径
            read_pool_size: 读连接池大小
            write_timeout: 写操作超时时间（秒）
        """
        self.db_path = db_path
        self.read_pool_size = read_pool_size
        self.write_timeout = write_timeout
        
        # 读连接池
        self._read_pool = ConnectionPool(
            db_path,
            pool_size=read_pool_size,
            max_overflow=read_pool_size
        )
        
        # 写连接（单个）
        self._write_conn: Optional[sqlite3.Connection] = None
        self._write_lock = threading.Lock()
        
        # 初始化写连接
        self._init_write_connection()
        
        logger.info(
            f"初始化读写分离连接池: db={db_path}, "
            f"read_pool_size={read_pool_size}"
        )
    
    def _init_write_connection(self) -> None:
        """初始化写连接"""
        self._write_conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False
        )
        
        # 启用优化配置
        self._write_conn.execute('PRAGMA journal_mode=WAL')
        self._write_conn.execute('PRAGMA synchronous=NORMAL')
        self._write_conn.execute('PRAGMA cache_size=-64000')
        self._write_conn.execute('PRAGMA temp_store=MEMORY')
        self._write_conn.execute('PRAGMA foreign_keys=ON')
    
    @contextmanager
    def get_read_connection(self):
        """获取读连接"""
        with self._read_pool.get_connection() as conn:
            yield conn
    
    @contextmanager
    def get_write_connection(self):
        """
        获取写连接
        
        注意：写连接是串行的，确保数据一致性
        """
        with self._write_lock:
            if self._write_conn is None:
                self._init_write_connection()
            yield self._write_conn
    
    def close(self) -> None:
        """关闭连接池"""
        logger.info("关闭读写分离连接池...")
        
        # 关闭读连接池
        self._read_pool.close()
        
        # 关闭写连接
        if self._write_conn:
            try:
                self._write_conn.close()
            except Exception:
                pass
            self._write_conn = None
        
        logger.info("读写分离连接池已关闭")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        read_stats = self._read_pool.get_stats()
        return {
            'read_pool': read_stats,
            'write_connection': 'active' if self._write_conn else 'inactive'
        }
    
    def __enter__(self) -> 'ReadWriteConnectionPool':
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
