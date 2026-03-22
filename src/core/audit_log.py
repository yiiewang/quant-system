"""
审计日志系统

提供完整的审计日志记录功能，满足合规要求和可追溯性
"""
import json
import sqlite3
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
import threading

logger = logging.getLogger(__name__)


class AuditAction(Enum):
    """审计操作类型"""
    # 用户相关
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"
    
    # 策略相关
    STRATEGY_CREATE = "strategy.create"
    STRATEGY_UPDATE = "strategy.update"
    STRATEGY_DELETE = "strategy.delete"
    STRATEGY_RUN = "strategy.run"
    STRATEGY_STOP = "strategy.stop"
    
    # 交易相关
    ORDER_CREATE = "order.create"
    ORDER_CANCEL = "order.cancel"
    ORDER_EXECUTE = "order.execute"
    
    # 数据相关
    DATA_FETCH = "data.fetch"
    DATA_IMPORT = "data.import"
    DATA_EXPORT = "data.export"
    DATA_DELETE = "data.delete"
    
    # 系统相关
    SYSTEM_START = "system.start"
    SYSTEM_STOP = "system.stop"
    SYSTEM_CONFIG = "system.config"
    
    # API 相关
    API_REQUEST = "api.request"
    API_ERROR = "api.error"


class AuditResult(Enum):
    """审计结果"""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


@dataclass
class AuditLog:
    """审计日志条目"""
    timestamp: datetime
    action: str
    resource: str
    result: str
    user: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class AuditLogger:
    """
    审计日志记录器
    
    功能：
    - 记录关键操作
    - 持久化到数据库
    - 支持查询和导出
    - 自动记录 IP、用户代理等信息
    
    Usage:
        audit_logger = AuditLogger("data/audit.db")
        
        # 记录用户登录
        audit_logger.log_action(
            action=AuditAction.USER_LOGIN,
            resource="user/admin",
            result=AuditResult.SUCCESS,
            user="admin",
            request=request
        )
    """
    
    def __init__(self, db_path: str = "data/audit.db"):
        """
        初始化审计日志记录器
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._lock = threading.Lock()
        
        # 确保目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库
        self._init_database()
        
        logger.info(f"审计日志系统已初始化: {db_path}")
    
    def _init_database(self) -> None:
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    result TEXT NOT NULL,
                    user TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    details TEXT,
                    error_message TEXT,
                    
                    -- 索引字段
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建索引
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
                ON audit_logs(timestamp)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_audit_action 
                ON audit_logs(action)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_audit_user 
                ON audit_logs(user)
            ''')
            
            conn.commit()
    
    def log_action(
        self,
        action: AuditAction,
        resource: str,
        result: AuditResult,
        user: Optional[str] = None,
        request: Optional[Any] = None,
        details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> int:
        """
        记录审计日志
        
        Args:
            action: 操作类型
            resource: 资源标识
            result: 操作结果
            user: 用户名
            request: HTTP 请求对象（用于提取 IP 和 User-Agent）
            details: 详细信息
            error_message: 错误消息（失败时）
        
        Returns:
            int: 日志 ID
        """
        # 提取请求信息
        ip_address = None
        user_agent = None
        
        if request:
            ip_address = getattr(request.client, 'host', None)
            user_agent = request.headers.get("user-agent")
        
        # 创建审计日志
        audit_log = AuditLog(
            timestamp=datetime.utcnow(),
            action=action.value,
            resource=resource,
            result=result.value,
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
            error_message=error_message
        )
        
        # 写入数据库
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    INSERT INTO audit_logs 
                    (timestamp, action, resource, result, user, ip_address, 
                     user_agent, details, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    audit_log.timestamp.isoformat(),
                    audit_log.action,
                    audit_log.resource,
                    audit_log.result,
                    audit_log.user,
                    audit_log.ip_address,
                    audit_log.user_agent,
                    json.dumps(audit_log.details) if audit_log.details else None,
                    audit_log.error_message
                ))
                
                log_id = cursor.lastrowid
                conn.commit()
        
        # 输出日志
        log_msg = f"[AUDIT] {action.value} - {resource} - {result.value}"
        if user:
            log_msg += f" (user: {user})"
        if ip_address:
            log_msg += f" (ip: {ip_address})"
        
        if result == AuditResult.FAILURE:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)
        
        return log_id
    
    def query_logs(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        action: Optional[AuditAction] = None,
        user: Optional[str] = None,
        result: Optional[AuditResult] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        查询审计日志
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            action: 操作类型
            user: 用户名
            result: 操作结果
            limit: 返回数量限制
        
        Returns:
            List[Dict]: 日志列表
        """
        query = "SELECT * FROM audit_logs WHERE 1=1"
        params: List[Any] = []
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        if action:
            query += " AND action = ?"
            params.append(action.value)
        
        if user:
            query += " AND user = ?"
            params.append(user)
        
        if result:
            query += " AND result = ?"
            params.append(result.value)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
        
        logs = []
        for row in rows:
            log = dict(row)
            if log['details']:
                log['details'] = json.loads(log['details'])
            logs.append(log)
        
        return logs
    
    def get_user_activity(
        self,
        user: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        获取用户活动统计
        
        Args:
            user: 用户名
            days: 统计天数
        
        Returns:
            Dict: 用户活动统计
        """
        start_time = datetime.utcnow() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # 总操作数
            cursor = conn.execute('''
                SELECT COUNT(*) as count
                FROM audit_logs
                WHERE user = ? AND timestamp >= ?
            ''', (user, start_time.isoformat()))
            total_count = cursor.fetchone()['count']
            
            # 成功/失败统计
            cursor = conn.execute('''
                SELECT result, COUNT(*) as count
                FROM audit_logs
                WHERE user = ? AND timestamp >= ?
                GROUP BY result
            ''', (user, start_time.isoformat()))
            result_stats = {row['result']: row['count'] for row in cursor.fetchall()}
            
            # 操作类型统计
            cursor = conn.execute('''
                SELECT action, COUNT(*) as count
                FROM audit_logs
                WHERE user = ? AND timestamp >= ?
                GROUP BY action
                ORDER BY count DESC
                LIMIT 10
            ''', (user, start_time.isoformat()))
            action_stats = {row['action']: row['count'] for row in cursor.fetchall()}
        
        return {
            'user': user,
            'period_days': days,
            'total_actions': total_count,
            'success_count': result_stats.get('success', 0),
            'failure_count': result_stats.get('failure', 0),
            'top_actions': action_stats
        }
    
    def export_logs(
        self,
        output_path: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        format: str = 'json'
    ) -> int:
        """
        导出审计日志
        
        Args:
            output_path: 输出文件路径
            start_time: 开始时间
            end_time: 结束时间
            format: 导出格式（json/csv）
        
        Returns:
            int: 导出的日志数量
        """
        logs = self.query_logs(
            start_time=start_time,
            end_time=end_time,
            limit=10000
        )
        
        if format == 'json':
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
        elif format == 'csv':
            import csv
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                if logs:
                    writer = csv.DictWriter(f, fieldnames=logs[0].keys())
                    writer.writeheader()
                    writer.writerows(logs)
        else:
            raise ValueError(f"不支持的导出格式: {format}")
        
        logger.info(f"导出审计日志: {len(logs)} 条 -> {output_path}")
        return len(logs)
    
    def cleanup_old_logs(self, days: int = 365) -> int:
        """
        清理过期日志
        
        Args:
            days: 保留天数
        
        Returns:
            int: 删除的日志数量
        """
        cutoff_time = datetime.utcnow() - timedelta(days=days)
        
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    DELETE FROM audit_logs
                    WHERE timestamp < ?
                ''', (cutoff_time.isoformat(),))
                
                deleted_count = cursor.rowcount
                conn.commit()
        
        logger.info(f"清理过期审计日志: 删除 {deleted_count} 条（{days} 天前）")
        return deleted_count


# 全局审计日志记录器
from datetime import timedelta

audit_logger = AuditLogger()
