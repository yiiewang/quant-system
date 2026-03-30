"""
数据层集成测试

测试场景：
- EnhancedMarketDataService 初始化（db_path 用临时目录）
- _init_db() 建表验证（ohlcv + ohlcv_minute 表存在）
- _do_persist() 写入日线数据后 _query_from_db() 读回，验证数据一致性
- get_latest() / get_history() 从本地 SQLite 读取（source=DataSource.LOCAL，不发真实网络请求）
- close() 资源释放验证
- ProviderHealthMonitor 健康状态更新和转换
- SmartDataAdapter 顺序降级逻辑（mock provider 模拟失败）
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
import pandas as pd
import tempfile
import sqlite3
import time

from src.data.health_monitor import ProviderHealthMonitor, HealthStatus, HealthRecord
from src.data.smart_adapter import SmartDataAdapter, DataSourceConfig
from src.data.market import BaseDataProvider, DataSource, Frequency
from src.data.market_enhanced import EnhancedMarketDataService


# ═══════════════════════════════════════════════════════════════════════════
# Mock Provider（不发真实网络请求）
# ═══════════════════════════════════════════════════════════════════════════

class MockProvider(BaseDataProvider):
    """模拟数据提供者"""

    def __init__(self, name, success=True, delay=0, data=None):
        self.name = name
        self.success = success
        self.delay = delay
        self.data = data

    def fetch(self, symbol, start_date, end_date, frequency):
        time.sleep(self.delay)
        if not self.success:
            raise Exception("Mock provider {} failed".format(self.name))
        return self.data

    def fetch_realtime(self, symbol):
        return {'price': 100, 'symbol': symbol}


def create_test_data(symbol='000001.SZ', rows=5):
    """创建测试用的 OHLCV 数据"""
    dates = pd.date_range(end=datetime.now(), periods=rows, freq='D')
    df = pd.DataFrame({
        'symbol': [symbol] * rows,
        'date': dates,
        'open': [100.0 + i for i in range(rows)],
        'high': [101.0 + i for i in range(rows)],
        'low': [99.0 + i for i in range(rows)],
        'close': [100.5 + i for i in range(rows)],
        'volume': [1000000 + i * 10000 for i in range(rows)],
        'amount': [100000000.0 + i * 1000000 for i in range(rows)]
    })
    return df


# ═══════════════════════════════════════════════════════════════════════════
# ProviderHealthMonitor 测试
# ═══════════════════════════════════════════════════════════════════════════

class TestProviderHealthMonitor:
    """健康监控器测试"""

    def test_register_source(self):
        """测试数据源注册"""
        monitor = ProviderHealthMonitor()
        monitor.register('tushare')
        monitor.register('akshare')

        # 注册后状态应为 HEALTHY
        assert monitor.get_status('tushare') == HealthStatus.HEALTHY
        assert monitor.get_status('akshare') == HealthStatus.HEALTHY
        # 未注册的数据源默认可用
        assert monitor.is_available('unknown') is True

    def test_mark_failure_status_escalation(self):
        """测试失败标记后的状态升级"""
        monitor = ProviderHealthMonitor(['test_source'])

        # 初始状态
        assert monitor.get_status('test_source') == HealthStatus.HEALTHY

        # 第一次失败 -> DEGRADED
        monitor.mark_failure('test_source', 'error 1')
        assert monitor.get_status('test_source') == HealthStatus.DEGRADED
        assert monitor.is_available('test_source') is True

        # 第二次失败 -> UNHEALTHY
        monitor.mark_failure('test_source', 'error 2')
        assert monitor.get_status('test_source') == HealthStatus.UNHEALTHY
        assert monitor.is_available('test_source') is True

        # 第三次失败 -> OFFLINE
        monitor.mark_failure('test_source', 'error 3')
        assert monitor.get_status('test_source') == HealthStatus.OFFLINE
        assert monitor.is_available('test_source') is False

    def test_mark_success_recovery(self):
        """测试成功恢复"""
        monitor = ProviderHealthMonitor(['test_source'])

        # 先标记为 OFFLINE
        for _ in range(3):
            monitor.mark_failure('test_source', 'error')

        assert monitor.get_status('test_source') == HealthStatus.OFFLINE

        # 重置后恢复
        monitor.reset_source('test_source')
        assert monitor.get_status('test_source') == HealthStatus.HEALTHY

    def test_health_report(self):
        """测试健康报告生成"""
        monitor = ProviderHealthMonitor(['source1', 'source2'])

        monitor.mark_success('source1', 0.5)
        monitor.mark_failure('source2', 'error')

        report = monitor.get_health_report()

        assert 'source1' in report
        assert 'source2' in report
        assert report['source1']['status'] == 'HEALTHY'
        assert report['source1']['available'] is True
        assert report['source1']['avg_response_time'] > 0

    def test_should_skip(self):
        """测试跳过逻辑"""
        monitor = ProviderHealthMonitor(['test_source'])

        # 正常状态不应跳过
        assert monitor.should_skip('test_source') is False

        # 标记为 OFFLINE 后应跳过
        for _ in range(3):
            monitor.mark_failure('test_source', 'error')

        assert monitor.should_skip('test_source') is True


# ═══════════════════════════════════════════════════════════════════════════
# SmartDataAdapter 测试
# ═══════════════════════════════════════════════════════════════════════════

class TestSmartDataAdapter:
    """智能数据适配器测试"""

    def test_sequential_fallback(self):
        """测试顺序降级逻辑"""
        test_data = create_test_data(rows=3)

        # 主数据源失败，备选成功
        failing_provider = MockProvider('primary', success=False)
        fallback_provider = MockProvider('fallback', success=True, data=test_data)

        monitor = ProviderHealthMonitor()
        configs = [
            DataSourceConfig('primary', failing_provider, priority=1),
            DataSourceConfig('fallback', fallback_provider, priority=2),
        ]

        adapter = SmartDataAdapter(
            sources_config=configs,
            health_monitor=monitor,
            parallel_fetch=False,  # 顺序模式
            primary_source='primary'
        )

        start_date = datetime.now() - timedelta(days=10)
        end_date = datetime.now()

        data = adapter.fetch('000001.SZ', start_date, end_date, Frequency.DAILY)

        # 应该从 fallback 获取成功
        assert data is not None
        assert len(data) == 3
        # primary 被标记为 DEGRADED
        assert monitor.get_status('primary') == HealthStatus.DEGRADED
        # fallback 成功
        assert monitor.get_status('fallback') == HealthStatus.HEALTHY

    def test_all_providers_fail(self):
        """测试所有数据源都失败"""
        failing_provider = MockProvider('failing', success=False)

        monitor = ProviderHealthMonitor()
        configs = [
            DataSourceConfig('source1', failing_provider, priority=1),
            DataSourceConfig('source2', failing_provider, priority=2),
        ]

        adapter = SmartDataAdapter(
            sources_config=configs,
            health_monitor=monitor,
            parallel_fetch=False,
            primary_source='source1'
        )

        start_date = datetime.now() - timedelta(days=10)
        end_date = datetime.now()

        data = adapter.fetch('000001.SZ', start_date, end_date, Frequency.DAILY)

        # 应该返回 None
        assert data is None

    def test_get_primary_provider(self):
        """测试获取主数据源"""
        provider = MockProvider('primary', success=True)
        monitor = ProviderHealthMonitor()
        configs = [DataSourceConfig('primary', provider, priority=1)]

        adapter = SmartDataAdapter(
            sources_config=configs,
            health_monitor=monitor,
            primary_source='primary'
        )

        primary = adapter.get_primary_provider()
        assert primary is not None
        assert primary.name == 'primary'


# ═══════════════════════════════════════════════════════════════════════════
# EnhancedMarketDataService 测试
# ═══════════════════════════════════════════════════════════════════════════

class TestEnhancedMarketDataService:
    """增强版市场数据服务测试"""

    def test_init_with_temp_db(self):
        """测试使用临时目录初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'market.db')

            service = EnhancedMarketDataService(
                source=DataSource.LOCAL,
                db_path=db_path
            )

            # 验证数据库文件已创建
            assert os.path.exists(db_path)

            service.close()

    def test_init_db_tables_created(self):
        """测试建表验证（ohlcv + ohlcv_minute 表存在）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'market.db')

            service = EnhancedMarketDataService(
                source=DataSource.LOCAL,
                db_path=db_path
            )

            # 查询表是否存在
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()

            assert 'ohlcv' in tables
            assert 'ohlcv_minute' in tables

            service.close()

    def test_persist_and_query_consistency(self):
        """测试 _do_persist() 写入后 _query_from_db() 读回数据一致性"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'market.db')

            service = EnhancedMarketDataService(
                source=DataSource.LOCAL,
                db_path=db_path
            )

            # 创建测试数据
            test_data = create_test_data(symbol='000001.SZ', rows=10)

            # 直接调用 _do_persist 写入
            service._do_persist('000001.SZ', test_data, Frequency.DAILY)

            # 通过 _query_from_db 读回
            retrieved = service._query_from_db('000001.SZ')

            # 验证数据一致性
            assert len(retrieved) == len(test_data)
            # 验证关键列
            assert list(retrieved['close'].values) == list(test_data['close'].values)
            assert list(retrieved['volume'].values) == list(test_data['volume'].values)

            service.close()

    def test_get_latest_from_local(self):
        """测试 get_latest() 从本地 SQLite 读取（不发真实网络请求）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'market.db')

            service = EnhancedMarketDataService(
                source=DataSource.LOCAL,
                db_path=db_path
            )

            # 写入测试数据
            test_data = create_test_data(symbol='000002.SZ', rows=50)
            service._do_persist('000002.SZ', test_data, Frequency.DAILY)

            # 清除缓存确保从数据库读取
            service.clear_cache()

            # 获取最新数据
            result = service.get_latest('000002.SZ')

            # 验证数据
            assert not result.empty

            service.close()

    def test_get_history_from_local(self):
        """测试 get_history() 从本地 SQLite 读取（不发真实网络请求）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'market.db')

            service = EnhancedMarketDataService(
                source=DataSource.LOCAL,
                db_path=db_path
            )

            # 写入测试数据
            test_data = create_test_data(symbol='000003.SZ', rows=20)
            service._do_persist('000003.SZ', test_data, Frequency.DAILY)

            # 清除缓存
            service.clear_cache()

            # 获取历史数据
            start_date = datetime.now() - timedelta(days=30)
            end_date = datetime.now()
            result = service.get_history('000003.SZ', start_date, end_date)

            # 验证数据
            assert not result.empty

            service.close()

    def test_close_releases_resources(self):
        """测试 close() 资源释放"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'market.db')

            service = EnhancedMarketDataService(
                source=DataSource.LOCAL,
                db_path=db_path
            )

            # 先建立只读连接
            conn = service._get_read_conn()
            assert conn is not None

            # 关闭服务
            service.close()

            # 验证只读连接已关闭
            assert service._read_conn is None

    def test_context_manager(self):
        """测试 with 语法自动关闭"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'market.db')

            with EnhancedMarketDataService(
                source=DataSource.LOCAL,
                db_path=db_path
            ) as service:
                # 验证服务可用
                assert service is not None
                # 写入并读取数据
                test_data = create_test_data(symbol='000004.SZ', rows=5)
                service._do_persist('000004.SZ', test_data, Frequency.DAILY)
                result = service._query_from_db('000004.SZ')
                assert not result.empty

            # 退出 with 块后资源应已释放

    def test_get_health_report(self):
        """测试获取健康报告"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'market.db')

            service = EnhancedMarketDataService(
                source=DataSource.LOCAL,
                db_path=db_path
            )

            report = service.get_health_report()
            assert isinstance(report, dict)

            service.close()

    def test_get_active_sources(self):
        """测试获取活跃数据源"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'market.db')

            service = EnhancedMarketDataService(
                source=DataSource.LOCAL,
                db_path=db_path
            )

            active = service.get_active_sources()
            assert isinstance(active, list)

            service.close()


# ═══════════════════════════════════════════════════════════════════════════
# HealthRecord 单元测试
# ═══════════════════════════════════════════════════════════════════════════

class TestHealthRecord:
    """健康记录测试"""

    def test_mark_success_updates_response_time(self):
        """测试成功标记更新响应时间"""
        record = HealthRecord()

        record.mark_success(0.5)
        assert record.avg_response_time == 0.5
        assert record.success_count == 1

        record.mark_success(0.3)
        # 滑动平均: 0.5 * 0.8 + 0.3 * 0.2 = 0.46
        assert abs(record.avg_response_time - 0.46) < 0.01

    def test_mark_failure_increments_count(self):
        """测试失败标记增加计数"""
        record = HealthRecord()

        record.mark_failure('error')
        assert record.failure_count == 1
        assert record.status == HealthStatus.DEGRADED

    def test_is_available_with_offline(self):
        """测试 OFFLINE 状态不可用"""
        record = HealthRecord()
        record.status = HealthStatus.OFFLINE

        assert record.is_available() is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
