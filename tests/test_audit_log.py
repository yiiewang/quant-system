"""
审计日志测试
"""
import pytest
import tempfile
import os
from datetime import datetime, timedelta

from src.core.audit_log import (
    AuditLogger,
    AuditAction,
    AuditResult
)


class TestAuditLogger:
    """审计日志测试"""
    
    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        yield path
        
        # 清理
        os.unlink(path)
    
    def test_log_action(self, temp_db):
        """测试记录审计日志"""
        logger = AuditLogger(temp_db)
        
        log_id = logger.log_action(
            action=AuditAction.USER_LOGIN,
            resource="user/admin",
            result=AuditResult.SUCCESS,
            user="admin"
        )
        
        assert log_id > 0
    
    def test_log_with_request(self, temp_db):
        """测试带请求信息的日志"""
        logger = AuditLogger(temp_db)
        
        # 模拟请求对象
        class MockRequest:
            class Client:
                host = "192.168.1.1"
            client = Client()
            
            def headers(self):
                return {"user-agent": "TestAgent"}
            
            def get(self, key, default=None):
                return {"user-agent": "TestAgent"}.get(key, default)
        
        request = MockRequest()
        
        log_id = logger.log_action(
            action=AuditAction.API_REQUEST,
            resource="/api/data",
            result=AuditResult.SUCCESS,
            user="test_user",
            request=request,
            details={'method': 'GET'}
        )
        
        assert log_id > 0
    
    def test_log_failure(self, temp_db):
        """测试记录失败日志"""
        logger = AuditLogger(temp_db)
        
        log_id = logger.log_action(
            action=AuditAction.USER_LOGIN,
            resource="user/admin",
            result=AuditResult.FAILURE,
            user="admin",
            error_message="密码错误"
        )
        
        assert log_id > 0
    
    def test_query_logs(self, temp_db):
        """测试查询日志"""
        logger = AuditLogger(temp_db)
        
        # 记录多条日志
        logger.log_action(
            action=AuditAction.USER_LOGIN,
            resource="user/admin",
            result=AuditResult.SUCCESS,
            user="admin"
        )
        
        logger.log_action(
            action=AuditAction.STRATEGY_RUN,
            resource="strategy/test_strategy",
            result=AuditResult.SUCCESS,
            user="admin"
        )
        
        # 查询所有日志
        logs = logger.query_logs(limit=10)
        assert len(logs) == 2
        
        # 按用户查询
        logs = logger.query_logs(user="admin")
        assert len(logs) == 2
        
        # 按操作类型查询
        logs = logger.query_logs(action=AuditAction.USER_LOGIN)
        assert len(logs) == 1
        assert logs[0]['action'] == 'user.login'
    
    def test_query_with_time_range(self, temp_db):
        """测试按时间范围查询"""
        logger = AuditLogger(temp_db)
        
        # 记录日志
        logger.log_action(
            action=AuditAction.USER_LOGIN,
            resource="user/admin",
            result=AuditResult.SUCCESS,
            user="admin"
        )
        
        # 查询最近 1 小时
        start_time = datetime.utcnow() - timedelta(hours=1)
        end_time = datetime.utcnow() + timedelta(hours=1)
        
        logs = logger.query_logs(
            start_time=start_time,
            end_time=end_time
        )
        
        assert len(logs) == 1
    
    def test_get_user_activity(self, temp_db):
        """测试获取用户活动统计"""
        logger = AuditLogger(temp_db)
        
        # 记录多条用户活动
        for i in range(5):
            logger.log_action(
                action=AuditAction.USER_LOGIN,
                resource="user/admin",
                result=AuditResult.SUCCESS,
                user="admin"
            )
        
        for i in range(3):
            logger.log_action(
                action=AuditAction.STRATEGY_RUN,
                resource="strategy/test",
                result=AuditResult.SUCCESS,
                user="admin"
            )
        
        for i in range(2):
            logger.log_action(
                action=AuditAction.USER_LOGIN,
                resource="user/admin",
                result=AuditResult.FAILURE,
                user="admin"
            )
        
        # 获取统计
        activity = logger.get_user_activity("admin", days=1)
        
        assert activity['user'] == "admin"
        assert activity['total_actions'] == 10
        assert activity['success_count'] == 8
        assert activity['failure_count'] == 2
        assert 'user.login' in activity['top_actions']
        assert 'strategy.run' in activity['top_actions']
    
    def test_export_logs_json(self, temp_db):
        """测试导出日志为 JSON"""
        logger = AuditLogger(temp_db)
        
        # 记录日志
        logger.log_action(
            action=AuditAction.USER_LOGIN,
            resource="user/admin",
            result=AuditResult.SUCCESS,
            user="admin"
        )
        
        # 导出
        output_path = temp_db.replace('.db', '_export.json')
        count = logger.export_logs(output_path, format='json')
        
        assert count == 1
        
        # 验证文件
        import json
        with open(output_path, 'r') as f:
            data = json.load(f)
        
        assert len(data) == 1
        assert data[0]['action'] == 'user.login'
        
        # 清理
        os.unlink(output_path)
    
    def test_export_logs_csv(self, temp_db):
        """测试导出日志为 CSV"""
        logger = AuditLogger(temp_db)
        
        # 记录日志
        logger.log_action(
            action=AuditAction.USER_LOGIN,
            resource="user/admin",
            result=AuditResult.SUCCESS,
            user="admin"
        )
        
        # 导出
        output_path = temp_db.replace('.db', '_export.csv')
        count = logger.export_logs(output_path, format='csv')
        
        assert count == 1
        
        # 验证文件
        import csv
        with open(output_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        assert len(rows) == 1
        assert rows[0]['action'] == 'user.login'
        
        # 清理
        os.unlink(output_path)
    
    def test_cleanup_old_logs(self, temp_db):
        """测试清理过期日志"""
        logger = AuditLogger(temp_db)
        
        # 记录日志
        logger.log_action(
            action=AuditAction.USER_LOGIN,
            resource="user/admin",
            result=AuditResult.SUCCESS,
            user="admin"
        )
        
        # 清理（保留 0 天，即清理所有）
        deleted_count = logger.cleanup_old_logs(days=0)
        
        assert deleted_count == 1
        
        # 验证已清空
        logs = logger.query_logs()
        assert len(logs) == 0


class TestAuditActions:
    """审计操作类型测试"""
    
    def test_audit_actions(self):
        """测试审计操作类型"""
        assert AuditAction.USER_LOGIN.value == "user.login"
        assert AuditAction.USER_LOGOUT.value == "user.logout"
        assert AuditAction.STRATEGY_RUN.value == "strategy.run"
        assert AuditAction.ORDER_CREATE.value == "order.create"
        assert AuditAction.DATA_FETCH.value == "data.fetch"
    
    def test_audit_results(self):
        """测试审计结果"""
        assert AuditResult.SUCCESS.value == "success"
        assert AuditResult.FAILURE.value == "failure"
        assert AuditResult.PARTIAL.value == "partial"
