"""
智能数据适配器测试

测试多数据源降级、并行请求和健康监控功能
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
import pandas as pd
import time

from src.data.health_monitor import ProviderHealthMonitor, HealthStatus
from src.data.smart_adapter import SmartDataAdapter, DataSourceConfig
from src.data.market import BaseDataProvider, Frequency


class MockProvider(BaseDataProvider):
    """模拟数据提供者"""
    
    def __init__(self, name, success=True, delay=0, data=None):
        self.name = name
        self.success = success
        self.delay = delay
        self.data = data or pd.DataFrame({'close': [100, 101, 102]})
    
    def fetch(self, symbol, start_date, end_date, frequency):
        time.sleep(self.delay)
        if not self.success:
            raise Exception(f"Mock provider {self.name} failed")
        return self.data
    
    def fetch_realtime(self, symbol):
        return {'price': 100}


class TestHealthMonitor:
    """健康监控器测试"""
    
    def test_register_and_status(self):
        """测试注册和状态获取"""
        monitor = ProviderHealthMonitor()
        monitor.register('tushare')
        
        # 初始状态应为HEALTHY
        assert monitor.get_status('tushare') == HealthStatus.HEALTHY
        assert monitor.is_available('tushare') == True
        
        # 测试未注册的数据源
        assert monitor.is_available('unknown') == True  # 默认可用
    
    def test_mark_failure_escalation(self):
        """测试失败标记升级"""
        monitor = ProviderHealthMonitor(['test_source'])
        
        # 第一次失败 -> DEGRADED
        monitor.mark_failure('test_source', 'test error 1')
        assert monitor.get_status('test_source') == HealthStatus.DEGRADED
        assert monitor.is_available('test_source') == True
        
        # 第二次失败 -> UNHEALTHY
        monitor.mark_failure('test_source', 'test error 2')
        assert monitor.get_status('test_source') == HealthStatus.UNHEALTHY
        assert monitor.is_available('test_source') == True
        
        # 第三次失败 -> OFFLINE
        monitor.mark_failure('test_source', 'test error 3')
        assert monitor.get_status('test_source') == HealthStatus.OFFLINE
        assert monitor.is_available('test_source') == False
    
    def test_mark_success_recovery(self):
        """测试成功恢复"""
        monitor = ProviderHealthMonitor(['test_source'])
        
        # 先标记失败
        monitor.mark_failure('test_source', 'test error')
        assert monitor.get_status('test_source') == HealthStatus.DEGRADED
        
        # 标记成功恢复
        monitor.mark_success('test_source', 0.1)
        assert monitor.get_status('test_source') == HealthStatus.HEALTHY
        assert monitor.failure_count('test_source') == 0


class TestSmartDataAdapter:
    """智能数据适配器测试"""
    
    def setup_method(self):
        """测试准备"""
        # 创建模拟provider
        self.primary_provider = MockProvider('primary', success=True, delay=0.1)
        self.fallback_provider = MockProvider('fallback', success=True, delay=0.05)
        self.failing_provider = MockProvider('failing', success=False)
        
        # 健康监控器
        self.monitor = ProviderHealthMonitor()
        
        # 数据源配置
        self.configs = [
            DataSourceConfig('primary', self.primary_provider, priority=1),
            DataSourceConfig('fallback', self.fallback_provider, priority=2),
        ]
        
        # 创建适配器
        self.adapter = SmartDataAdapter(
            sources_config=self.configs,
            health_monitor=self.monitor,
            parallel_fetch=True,
            primary_source='primary',
            max_workers=2
        )
    
    def test_sequential_fallback(self):
        """测试顺序降级"""
        # 配置主数据源失败、备选成功的场景
        failing_config = DataSourceConfig('primary', self.failing_provider, priority=1)
        fallback_config = DataSourceConfig('fallback', self.fallback_provider, priority=2)
        
        adapter = SmartDataAdapter(
            sources_config=[failing_config, fallback_config],
            health_monitor=self.monitor,
            parallel_fetch=False,  # 顺序模式
            primary_source='primary'
        )
        
        # 获取数据，应该降级到fallback
        start_date = datetime.now() - timedelta(days=10)
        end_date = datetime.now()
        
        # 顺序模式至少调用 4 次 time.time()：primary 开始+结束 + fallback 开始+结束
        # 保守起见提供足够长的序列
        with patch('time.time') as mock_time:
            mock_time.side_effect = [1000, 1000.2, 1000.5, 1000.8, 1001.0, 1001.2]  # 模拟时间序列
            data = adapter.fetch('TEST', start_date, end_date, Frequency.DAILY)
        
        # 应该从fallback获取成功
        assert data is not None
        assert len(data) == 3
        assert self.monitor.get_status('primary') == HealthStatus.DEGRADED
        assert self.monitor.get_status('fallback') == HealthStatus.HEALTHY
    
    def test_parallel_fetch_fastest(self):
        """测试并行获取最快结果"""
        # fallback比primary更快
        slow_provider = MockProvider('slow', success=True, delay=0.2)
        fast_provider = MockProvider('fast', success=True, delay=0.05)
        
        configs = [
            DataSourceConfig('slow', slow_provider, priority=1),
            DataSourceConfig('fast', fast_provider, priority=2),
        ]
        
        adapter = SmartDataAdapter(
            sources_config=configs,
            health_monitor=self.monitor,
            parallel_fetch=True,  # 并行模式
            primary_source='slow'
        )
        
        start_date = datetime.now() - timedelta(days=10)
        end_date = datetime.now()
        
        # 获取数据，应该返回最快的结果（fast）
        data = adapter.fetch('TEST', start_date, end_date, Frequency.DAILY, timeout=0.3)
        
        assert data is not None
        # 由于并行获取，应该是fast返回的
    
    def test_all_providers_fail(self):
        """测试所有数据源都失败"""
        failing_config1 = DataSourceConfig('f1', self.failing_provider, priority=1)
        failing_config2 = DataSourceConfig('f2', self.failing_provider, priority=2)
        
        adapter = SmartDataAdapter(
            sources_config=[failing_config1, failing_config2],
            health_monitor=self.monitor,
            parallel_fetch=False,
            primary_source='f1'
        )
        
        start_date = datetime.now() - timedelta(days=10)
        end_date = datetime.now()
        
        data = adapter.fetch('TEST', start_date, end_date, Frequency.DAILY)
        
        # 应该返回None
        assert data is None
        assert self.monitor.get_status('f1') == HealthStatus.DEGRADED
        assert self.monitor.get_status('f2') == HealthStatus.DEGRADED
    
    def test_health_monitor_integration(self):
        """测试健康监控集成"""
        start_date = datetime.now() - timedelta(days=10)
        end_date = datetime.now()
        
        # 第一次成功请求
        data1 = self.adapter.fetch('TEST', start_date, end_date, Frequency.DAILY)
        assert data1 is not None
        assert self.monitor.get_status('primary') == HealthStatus.HEALTHY
        
        # 模拟primary失败，fallback成功
        with patch.object(self.primary_provider, 'fetch', side_effect=Exception('Test failure')):
            data2 = self.adapter.fetch('TEST', start_date, end_date, Frequency.DAILY)
            assert data2 is not None  # fallback应该成功
            assert self.monitor.get_status('primary') == HealthStatus.DEGRADED
            assert self.monitor.get_status('fallback') == HealthStatus.HEALTHY


class TestEnhancedMarketDataService:
    """增强版市场数据服务测试"""
    
    def test_smoke_test(self):
        """冒烟测试"""
        # 导入需要Mock掉实际的数据源
        with patch('src.data.market_enhanced.TushareProvider') as mock_tushare, \
             patch('src.data.market_enhanced.AkshareProvider') as mock_akshare:
            
            # 设置mock
            mock_tushare_instance = Mock()
            mock_tushare_instance.fetch.return_value = pd.DataFrame({'close': [100, 101]})
            mock_tushare.return_value = mock_tushare_instance
            
            mock_akshare_instance = Mock()
            mock_akshare_instance.fetch.return_value = pd.DataFrame({'close': [102, 103]})
            mock_akshare.return_value = mock_akshare_instance
            
            # 导入并测试
            from src.data.market_enhanced import EnhancedMarketDataService, DataSource
            
            service = EnhancedMarketDataService(
                source=DataSource.TUSHARE,
                fallback_sources=[DataSource.AKSHARE],
                parallel_fetch=True
            )
            
            # 测试健康报告
            report = service.get_health_report()
            assert isinstance(report, dict)
            
            # 测试活跃数据源
            active = service.get_active_sources()
            assert isinstance(active, list)


if __name__ == '__main__':
    # 运行测试
    print("运行健康监控器测试...")
    test_monitor = TestHealthMonitor()
    test_monitor.test_register_and_status()
    test_monitor.test_mark_failure_escalation()
    test_monitor.test_mark_success_recovery()
    print("健康监控器测试通过 ✓")
    
    print("运行智能适配器测试...")
    test_adapter = TestSmartDataAdapter()
    test_adapter.setup_method()
    test_adapter.test_sequential_fallback()
    test_adapter.test_parallel_fetch_fastest()
    test_adapter.test_all_providers_fail()
    test_adapter.test_health_monitor_integration()
    print("智能适配器测试通过 ✓")
    
    print("所有测试通过！ ✓")

