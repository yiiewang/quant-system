"""
数据提供者健康监控器

监控各个数据源的健康状态，支持自动标记异常和恢复监测
"""
import time
import logging
from enum import Enum, auto
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """数据源健康状态"""
    HEALTHY = auto()      # 正常
    DEGRADED = auto()     # 性能降级
    UNHEALTHY = auto()    # 暂时故障
    OFFLINE = auto()      # 完全离线


@dataclass
class HealthRecord:
    """数据源健康记录"""
    status: HealthStatus = HealthStatus.HEALTHY
    last_check: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    avg_response_time: float = 0.0
    
    def mark_success(self, response_time: float):
        """标记请求成功"""
        self.status = HealthStatus.HEALTHY
        self.last_check = datetime.now()
        self.success_count += 1
        
        # 更新平均响应时间（滑动平均）
        if self.avg_response_time == 0:
            self.avg_response_time = response_time
        else:
            self.avg_response_time = self.avg_response_time * 0.8 + response_time * 0.2
            
        # 如果之前有失败记录，减少失败计数
        if self.failure_count > 0:
            self.failure_count = max(0, self.failure_count - 1)
    
    def mark_failure(self, error_msg: Optional[str] = None):
        """标记请求失败"""
        self.last_check = datetime.now()
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        # 根据失败次数调整状态
        if self.failure_count >= 3:
            self.status = HealthStatus.OFFLINE
            logger.warning(f"数据源标记为离线: {error_msg}")
        elif self.failure_count >= 2:
            self.status = HealthStatus.UNHEALTHY
            logger.info(f"数据源标记为不健康: {error_msg}")
        elif self.failure_count >= 1:
            self.status = HealthStatus.DEGRADED
            logger.info(f"数据源标记为降级: {error_msg}")
    
    def is_available(self) -> bool:
        """检查数据源是否可用"""
        if self.status == HealthStatus.OFFLINE:
            return False
            
        # 如果最近有失败，但已超过冷却时间，尝试恢复
        if self.last_failure_time:
            cooldown = timedelta(minutes=5 if self.status == HealthStatus.UNHEALTHY else 1)
            if datetime.now() - self.last_failure_time > cooldown:
                # 自动恢复为降级状态，等待下次验证
                self.status = HealthStatus.DEGRADED
                return True
                
        return self.status != HealthStatus.OFFLINE
    
    def should_skip(self) -> bool:
        """是否应该跳过此数据源"""
        return self.status == HealthStatus.OFFLINE
    
    def reset(self):
        """重置健康状态"""
        self.status = HealthStatus.HEALTHY
        self.failure_count = 0
        self.last_failure_time = None


class ProviderHealthMonitor:
    """
    数据提供者健康状态监控器（线程安全）
    """
    
    def __init__(self, initial_sources: Optional[list] = None):
        """
        初始化健康监控器
        
        Args:
            initial_sources: 初始数据源列表
        """
        self._records: Dict[str, HealthRecord] = {}
        self._lock = Lock()
        
        if initial_sources:
            for source in initial_sources:
                self.register(source)
    
    def register(self, source_name: str) -> None:
        """注册数据源"""
        with self._lock:
            if source_name not in self._records:
                self._records[source_name] = HealthRecord()
                logger.debug(f"注册数据源监控: {source_name}")
    
    def mark_success(self, source_name: str, response_time: float):
        """标记请求成功"""
        with self._lock:
            if source_name in self._records:
                self._records[source_name].mark_success(response_time)
    
    def mark_failure(self, source_name: str, error_msg: Optional[str] = None):
        """标记请求失败"""
        with self._lock:
            if source_name in self._records:
                self._records[source_name].mark_failure(error_msg)
    
    def is_available(self, source_name: str) -> bool:
        """检查数据源是否可用"""
        with self._lock:
            record = self._records.get(source_name)
            if not record:
                # 未注册的数据源默认可用
                return True
            return record.is_available()
    
    def should_skip(self, source_name: str) -> bool:
        """是否应该跳过此数据源"""
        with self._lock:
            record = self._records.get(source_name)
            if not record:
                return False
            return record.should_skip()
    
    def get_status(self, source_name: str) -> HealthStatus:
        """获取数据源状态"""
        with self._lock:
            record = self._records.get(source_name)
            if not record:
                return HealthStatus.HEALTHY
            return record.status
    
    def reset_source(self, source_name: str):
        """重置指定数据源状态"""
        with self._lock:
            if source_name in self._records:
                self._records[source_name].reset()
                logger.info(f"重置数据源状态: {source_name}")
    
    def get_health_report(self) -> Dict:
        """获取健康状态报告"""
        with self._lock:
            report = {}
            for source, record in self._records.items():
                report[source] = {
                    'status': record.status.name,
                    'success_count': record.success_count,
                    'failure_count': record.failure_count,
                    'last_failure': record.last_failure_time.isoformat() if record.last_failure_time else None,
                    'avg_response_time': record.avg_response_time,
                    'available': record.is_available()
                }
            return report

    def failure_count(self, source_name: str) -> int:
        """获取数据源失败次数"""
        with self._lock:
            record = self._records.get(source_name)
            if not record:
                return 0
            return record.failure_count

