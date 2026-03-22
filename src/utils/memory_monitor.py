"""
内存监控工具

提供内存使用监控和限制功能
"""

import psutil
import logging
from typing import Optional, Callable
from functools import wraps
import time

logger = logging.getLogger(__name__)


class MemoryMonitor:
    """内存监控器"""
    
    def __init__(self, max_memory_percent: float = 80.0, warning_threshold: float = 70.0):
        """
        初始化内存监控器
        
        Args:
            max_memory_percent: 最大内存使用百分比（超过将触发警告）
            warning_threshold: 警告阈值百分比
        """
        self.max_memory_percent = max_memory_percent
        self.warning_threshold = warning_threshold
        self._callbacks: list[Callable] = []
    
    def get_memory_info(self) -> dict:
        """获取内存信息"""
        process = psutil.Process()
        mem_info = process.memory_info()
        system_mem = psutil.virtual_memory()
        
        return {
            'rss_mb': mem_info.rss / 1024 / 1024,
            'vms_mb': mem_info.vms / 1024 / 1024,
            'percent': (mem_info.rss / system_mem.total) * 100,
            'system_percent': system_mem.percent,
            'system_available_mb': system_mem.available / 1024 / 1024,
        }
    
    def check_memory(self) -> bool:
        """
        检查内存使用情况
        
        Returns:
            True if memory usage is within limits, False otherwise
        """
        info = self.get_memory_info()
        
        if info['percent'] > self.max_memory_percent:
            logger.warning(
                f"内存使用超过限制: {info['percent']:.1f}% "
                f"(限制: {self.max_memory_percent}%)"
            )
            for callback in self._callbacks:
                callback(info)
            return False
        
        if info['percent'] > self.warning_threshold:
            logger.warning(
                f"内存使用接近限制: {info['percent']:.1f}% "
                f"(警告阈值: {self.warning_threshold}%)"
            )
        
        return True
    
    def register_callback(self, callback: Callable):
        """注册内存超限回调函数"""
        self._callbacks.append(callback)
    
    def log_memory_usage(self, label: str = ""):
        """记录内存使用情况"""
        info = self.get_memory_info()
        prefix = f"[{label}] " if label else ""
        logger.info(
            f"{prefix}内存使用: RSS={info['rss_mb']:.2f}MB, "
            f"VMS={info['vms_mb']:.2f}MB, "
            f"使用率={info['percent']:.1f}%"
        )


def memory_limited(max_memory_percent: float = 80.0):
    """
    内存限制装饰器
    
    当内存使用超过限制时，抛出 MemoryError
    
    Args:
        max_memory_percent: 最大内存使用百分比
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            monitor = MemoryMonitor(max_memory_percent=max_memory_percent)
            if not monitor.check_memory():
                raise MemoryError(
                    f"内存使用超过限制 ({max_memory_percent}%), "
                    f"无法执行 {func.__name__}"
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator


def log_memory_usage(label: Optional[str] = None):
    """
    内存使用日志装饰器
    
    记录函数执行前后的内存使用情况
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            monitor = MemoryMonitor()
            func_name = label or func.__name__
            
            monitor.log_memory_usage(f"{func_name} 开始")
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                elapsed = time.time() - start_time
                monitor.log_memory_usage(f"{func_name} 结束")
                logger.info(f"{func_name} 执行时间: {elapsed:.3f}s")
        return wrapper
    return decorator


class MemoryOptimizedDataFrame:
    """内存优化的 DataFrame 包装器"""
    
    @staticmethod
    def optimize(df) -> 'pd.DataFrame':
        """
        优化 DataFrame 内存使用
        
        Args:
            df: pandas DataFrame
            
        Returns:
            优化后的 DataFrame
        """
        import pandas as pd
        
        start_mem = df.memory_usage().sum() / 1024 / 1024
        
        for col in df.columns:
            col_type = df[col].dtype
            
            if col_type != object:
                c_min = df[col].min()
                c_max = df[col].max()
                
                if str(col_type)[:3] == 'int':
                    if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                        df[col] = df[col].astype(np.int8)
                    elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                        df[col] = df[col].astype(np.int16)
                    elif c_min > np.iinfo(np.int32).min and c_max < np.iinfo(np.int32).max:
                        df[col] = df[col].astype(np.int32)
                else:
                    if c_min > np.finfo(np.float32).min and c_max < np.finfo(np.float32).max:
                        df[col] = df[col].astype(np.float32)
        
        end_mem = df.memory_usage().sum() / 1024 / 1024
        logger.debug(f"DataFrame 内存优化: {start_mem:.2f}MB -> {end_mem:.2f}MB")
        
        return df


# 全局内存监控器实例
_global_monitor: Optional[MemoryMonitor] = None


def get_memory_monitor() -> MemoryMonitor:
    """获取全局内存监控器"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = MemoryMonitor()
    return _global_monitor
