"""
数据库查询优化模块

提供查询缓存、批量查询、性能监控等功能
"""
import sqlite3
import hashlib
import logging
import time
from functools import wraps
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
from contextlib import contextmanager

import pandas as pd

logger = logging.getLogger(__name__)


# ==================== 查询缓存 ====================

class QueryCache:
    """
    查询结果缓存
    
    特点：
    - LRU 缓存策略
    - TTL 过期机制
    - 缓存命中率统计
    """
    
    def __init__(self, maxsize: int = 1000, ttl: int = 3600):
        """
        初始化查询缓存
        
        Args:
            maxsize: 最大缓存数量
            ttl: 缓存过期时间（秒）
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_order: List[str] = []
        
        # 统计信息
        self._hits = 0
        self._misses = 0
    
    def _generate_key(self, query: str, params: tuple = ()) -> str:
        """生成缓存键"""
        content = f"{query}:{params}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def get(self, query: str, params: tuple = ()) -> Optional[pd.DataFrame]:
        """
        从缓存获取查询结果
        
        Args:
            query: SQL 查询语句
            params: 查询参数
        
        Returns:
            缓存的结果，如果不存在或已过期则返回 None
        """
        key = self._generate_key(query, params)
        
        if key in self._cache:
            entry = self._cache[key]
            
            # 检查是否过期
            if time.time() - entry['timestamp'] < self.ttl:
                # 更新访问顺序
                self._access_order.remove(key)
                self._access_order.append(key)
                
                self._hits += 1
                logger.debug(f"缓存命中: {key[:8]}")
                return entry['data']
            else:
                # 过期，删除
                del self._cache[key]
                self._access_order.remove(key)
        
        self._misses += 1
        return None
    
    def set(self, query: str, params: tuple, data: pd.DataFrame) -> None:
        """
        设置缓存
        
        Args:
            query: SQL 查询语句
            params: 查询参数
            data: 查询结果
        """
        key = self._generate_key(query, params)
        
        # 检查是否需要淘汰
        if len(self._cache) >= self.maxsize and key not in self._cache:
            # 删除最久未使用的项
            oldest_key = self._access_order.pop(0)
            del self._cache[oldest_key]
            logger.debug(f"缓存淘汰: {oldest_key[:8]}")
        
        # 添加到缓存
        self._cache[key] = {
            'data': data,
            'timestamp': time.time()
        }
        
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)
        
        logger.debug(f"缓存设置: {key[:8]}")
    
    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._access_order.clear()
        logger.info("查询缓存已清空")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0
        
        return {
            'size': len(self._cache),
            'maxsize': self.maxsize,
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': f"{hit_rate:.2%}",
            'ttl': self.ttl
        }


# 全局查询缓存
query_cache = QueryCache(maxsize=1000, ttl=3600)


# ==================== 批量查询优化 ====================

class BatchQueryOptimizer:
    """
    批量查询优化器
    
    使用 IN 子句批量查询多个标的数据，减少数据库访问次数
    """
    
    @staticmethod
    def build_in_clause(items: List[str]) -> str:
        """
        构建 IN 子句
        
        Args:
            items: 项目列表
        
        Returns:
            str: IN 子句字符串
        """
        if not items:
            return ""
        
        # 使用参数占位符
        placeholders = ','.join(['?' for _ in items])
        return f"IN ({placeholders})"
    
    @staticmethod
    def batch_query_symbols(
        conn: sqlite3.Connection,
        symbols: List[str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        frequency: str = 'daily',
        table: str = 'ohlcv'
    ) -> Dict[str, pd.DataFrame]:
        """
        批量查询多个标的数据
        
        Args:
            conn: 数据库连接
            symbols: 标的列表
            start_date: 开始日期
            end_date: 结束日期
            frequency: 数据频率
            table: 表名
        
        Returns:
            Dict[str, pd.DataFrame]: {symbol: DataFrame}
        """
        if not symbols:
            return {}
        
        # 构建查询
        in_clause = BatchQueryOptimizer.build_in_clause(symbols)
        
        if table == 'ohlcv_minute':
            # 分钟数据
            query = f"""
                SELECT * FROM {table}
                WHERE symbol {in_clause}
                AND frequency = ?
            """
            params: List[Any] = list(symbols) + [frequency]
            
            if start_date:
                query += " AND datetime >= ?"
                params.append(start_date.strftime('%Y-%m-%d %H:%M:%S'))
            
            if end_date:
                query += " AND datetime <= ?"
                params.append(end_date.strftime('%Y-%m-%d %H:%M:%S'))
            
            query += " ORDER BY symbol, datetime ASC"
        else:
            # 日线数据
            query = f"""
                SELECT * FROM {table}
                WHERE symbol {in_clause}
            """
            params = list(symbols)
            
            if start_date:
                query += " AND date >= ?"
                params.append(start_date.strftime('%Y-%m-%d'))
            
            if end_date:
                query += " AND date <= ?"
                params.append(end_date.strftime('%Y-%m-%d'))
            
            query += " ORDER BY symbol, date ASC"
        
        # 执行查询
        df = pd.read_sql_query(query, conn, params=params)
        
        # 按标的分组
        result = {}
        for symbol in symbols:
            symbol_df = df[df['symbol'] == symbol].copy()
            if not symbol_df.empty:
                if table == 'ohlcv':
                    symbol_df['date'] = pd.to_datetime(symbol_df['date'])
                else:
                    symbol_df['datetime'] = pd.to_datetime(symbol_df['datetime'])
            result[symbol] = symbol_df.reset_index(drop=True)
        
        return result


# ==================== 查询性能监控 ====================

class QueryPerformanceMonitor:
    """
    查询性能监控
    
    记录查询执行时间，识别慢查询
    """
    
    def __init__(self, slow_query_threshold: float = 1.0):
        """
        初始化性能监控
        
        Args:
            slow_query_threshold: 慢查询阈值（秒）
        """
        self.slow_query_threshold = slow_query_threshold
        self._query_stats: Dict[str, Dict[str, Any]] = {}
    
    @contextmanager
    def monitor(self, query: str):
        """
        监控查询性能的上下文管理器
        
        Usage:
            with monitor.monitor("SELECT * FROM table"):
                # 执行查询
                ...
        """
        start_time = time.time()
        
        try:
            yield
        finally:
            elapsed = time.time() - start_time
            
            # 记录统计信息
            query_key = query[:100]  # 使用前 100 字符作为键
            
            if query_key not in self._query_stats:
                self._query_stats[query_key] = {
                    'count': 0,
                    'total_time': 0.0,
                    'max_time': 0.0,
                    'min_time': float('inf')
                }
            
            stats = self._query_stats[query_key]
            stats['count'] += 1
            stats['total_time'] += elapsed
            stats['max_time'] = max(stats['max_time'], elapsed)
            stats['min_time'] = min(stats['min_time'], elapsed)
            
            # 检查慢查询
            if elapsed > self.slow_query_threshold:
                logger.warning(
                    f"慢查询检测: {elapsed:.2f}s\n"
                    f"Query: {query[:200]}..."
                )
            else:
                logger.debug(f"查询完成: {elapsed:.4f}s")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取查询统计信息"""
        stats = {}
        
        for query, data in self._query_stats.items():
            avg_time = data['total_time'] / data['count'] if data['count'] > 0 else 0
            stats[query] = {
                'count': data['count'],
                'total_time': f"{data['total_time']:.2f}s",
                'avg_time': f"{avg_time:.4f}s",
                'max_time': f"{data['max_time']:.4f}s",
                'min_time': f"{data['min_time']:.4f}s"
            }
        
        return stats
    
    def get_slow_queries(self) -> List[Dict[str, Any]]:
        """获取慢查询列表"""
        slow_queries = []
        
        for query, data in self._query_stats.items():
            avg_time = data['total_time'] / data['count'] if data['count'] > 0 else 0
            if avg_time > self.slow_query_threshold:
                slow_queries.append({
                    'query': query,
                    'avg_time': avg_time,
                    'count': data['count']
                })
        
        return sorted(slow_queries, key=lambda x: x['avg_time'], reverse=True)


# 全局性能监控器
performance_monitor = QueryPerformanceMonitor(slow_query_threshold=1.0)


# ==================== 装饰器 ====================

def cached_query(cache: QueryCache = query_cache):
    """
    查询缓存装饰器
    
    Usage:
        @cached_query()
        def query_data(symbol: str, start_date: datetime):
            # 查询逻辑
            return df
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = (func.__name__, args, tuple(sorted(kwargs.items())))
            
            # 尝试从缓存获取
            query_str = str(cache_key)
            cached_result = cache.get(query_str)
            
            if cached_result is not None:
                return cached_result
            
            # 执行查询
            result = func(*args, **kwargs)
            
            # 缓存结果
            if isinstance(result, pd.DataFrame) and not result.empty:
                cache.set(query_str, (), result)
            
            return result
        
        return wrapper
    return decorator


def monitored_query(func: Callable) -> Callable:
    """
    查询性能监控装饰器
    
    Usage:
        @monitored_query
        def query_data(symbol: str):
            # 查询逻辑
            return df
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        query_name = func.__name__
        
        with performance_monitor.monitor(query_name):
            result = func(*args, **kwargs)
        
        return result
    
    return wrapper
