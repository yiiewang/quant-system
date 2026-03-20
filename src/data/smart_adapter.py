"""
智能数据适配器

支持多数据源的智能选择、并行请求和自动降级
"""
import threading
import time
import queue
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

import pandas as pd

from src.config.schema import DataSource
from .provider import BaseDataProvider, Frequency
from .health_monitor import ProviderHealthMonitor

logger = logging.getLogger(__name__)


class DataSourceConfig:
    """数据源配置"""
    
    def __init__(self, name: str, provider: BaseDataProvider, 
                 priority: int = 0, timeout: float = 10.0,
                 enabled: bool = True):
        """
        初始化数据源配置
        
        Args:
            name: 数据源名称
            provider: 数据提供者实例
            priority: 优先级（数字越小优先级越高）
            timeout: 单个请求超时时间（秒）
            enabled: 是否启用
        """
        self.name = name
        self.provider = provider
        self.priority = priority
        self.timeout = timeout
        self.enabled = enabled


class SmartDataAdapter:
    """
    智能数据适配器
    
    支持特性：
    1. 多数据源并行请求
    2. 自动降级和故障转移
    3. 健康状态监控
    4. 响应时间优化
    5. 根据股票代码智能选择数据源
    
    Usage:
        adapter = SmartDataAdapter()  # 使用默认配置
        
        # 或自定义配置
        adapter = SmartDataAdapter(
            sources_config=[
                DataSourceConfig('tushare', tushare_provider, priority=1),
                DataSourceConfig('akshare', akshare_provider, priority=2),
            ],
            health_monitor=health_monitor,
            parallel_fetch=True,
            primary_source='tushare'
        )
        
        # 获取数据（自动选择最佳数据源）
        data = adapter.fetch(symbol='000001.SZ', start=start_date, end=end_date)
    """
    
    def __init__(self,
                 sources_config: Optional[List[DataSourceConfig]] = None,
                 health_monitor: Optional[ProviderHealthMonitor] = None,
                 parallel_fetch: bool = True,
                 primary_source: Optional[str] = None,
                 max_workers: int = 3):
        """
        初始化智能适配器
        
        Args:
            sources_config: 数据源配置列表（为空时使用默认配置）
            health_monitor: 健康监控器（为空时自动创建）
            parallel_fetch: 是否并行请求
            primary_source: 主数据源名称
            max_workers: 并行工作线程数
        """
        # 如果没有提供配置，使用默认配置
        if sources_config is None:
            sources_config = self._create_default_sources()
        
        # 如果没有提供健康监控器，创建一个
        if health_monitor is None:
            health_monitor = ProviderHealthMonitor()
        
        # 创建数据源映射
        self.sources: Dict[str, DataSourceConfig] = {}
        for config in sources_config:
            if config.enabled:
                self.sources[config.name] = config
                health_monitor.register(config.name)
        
        self.health_monitor = health_monitor
        self.parallel_fetch = parallel_fetch
        self.max_workers = max_workers
        
        # 确定主数据源
        if primary_source and primary_source in self.sources:
            self.primary_source = primary_source
        elif sources_config:
            # 按优先级排序，选优先级最高的作为主数据源
            sorted_configs = sorted(sources_config, key=lambda x: x.priority)
            self.primary_source = sorted_configs[0].name
        else:
            self.primary_source = None
        
        logger.info(f"初始化SmartDataAdapter: {len(self.sources)}个数据源, 主数据源={self.primary_source}")
    
    def _create_default_sources(self) -> List[DataSourceConfig]:
        """创建默认数据源配置"""
        sources = []
        
        # 尝试添加 yfinance（用于美股、港股、加密货币）
        try:
            from .market import YFinanceProvider
            sources.append(DataSourceConfig(
                'yfinance', 
                YFinanceProvider(), 
                priority=1,  # 最高优先级（用于非A股）
                timeout=15.0
            ))
        except ImportError:
            logger.warning("yfinance 未安装，跳过该数据源")
        
        # 尝试添加 baostock（A股）
        try:
            from .market import BaostockProvider
            sources.append(DataSourceConfig(
                'baostock', 
                BaostockProvider(), 
                priority=2,
                timeout=10.0
            ))
        except ImportError:
            logger.warning("baostock 未安装，跳过该数据源")
        
        # 尝试添加 akshare
        try:
            from .market import AkshareProvider
            sources.append(DataSourceConfig(
                'akshare', 
                AkshareProvider(), 
                priority=3,
                timeout=10.0
            ))
        except ImportError:
            logger.warning("akshare 未安装，跳过该数据源")
        
        return sources
    
    def fetch(self,
              symbol: str,
              start_date: datetime,
              end_date: datetime,
              frequency: str = Frequency.DAILY,
              timeout: Optional[float] = None) -> Optional[Any]:
        """
        获取数据（自动选择最佳数据源）

        Args:
            symbol: 股票代码
            start_date: 开始时间
            end_date: 结束时间
            frequency: 数据频率
            timeout: 总超时时间（默认使用各数据源配置的超时时间）

        Returns:
            获取到的数据，如果都失败则返回None
        """
        # 1. 根据股票代码智能选择数据源
        preferred_source = self._get_preferred_source(symbol)
        available_sources = self._get_available_sources()

        if preferred_source:
            # 将首选数据源排到最前面
            available_sources = sorted(
                available_sources,
                key=lambda x: (0 if x.name == preferred_source else 1, x.priority)
            )

        if not available_sources:
            logger.error("没有可用的数据源")
            return None

        # 2. 并行或顺序获取
        if self.parallel_fetch and len(available_sources) > 1:
            return self._fetch_parallel(available_sources, symbol, start_date,
                                       end_date, frequency, timeout)
        else:
            return self._fetch_sequential(available_sources, symbol, start_date,
                                         end_date, frequency, timeout)

    def _get_preferred_source(self, symbol: str) -> Optional[str]:
        """
        根据股票代码判断应该使用哪个数据源

        规则:
        - 美股 (AAPL, MSFT, GOOGL 等) -> yfinance
        - 港股 (0700.HK, 9988.HK 等) -> yfinance
        - 加密货币 (BTC-USD, ETH-USD) -> yfinance
        - A股 (000001.SZ, 600036.SH 等) -> tushare/akshare/baostock
        """
        # 港股格式: 数字.HK
        if symbol.endswith('.HK'):
            return 'yfinance'

        # 加密货币格式: XXX-USD, XXX-USDT
        if '-USD' in symbol or '-USDT' in symbol:
            return 'yfinance'

        # 美股格式: 纯大写字母，无后缀 (AAPL, MSFT)
        # 或者带 .US 后缀
        if symbol.isalpha() and symbol.isupper() and len(symbol) <= 5:
            return 'yfinance'
        if symbol.endswith('.US'):
            return 'yfinance'

        # A股格式: 数字.交易所 (000001.SZ, 600036.SH)
        if '.' in symbol:
            exchange = symbol.split('.')[1].upper()
            if exchange in ['SZ', 'SH', 'BJ']:
                return None  # 使用默认数据源

        return None

    def _get_available_sources(self) -> List[DataSourceConfig]:
        """
        获取可用数据源（按优先级排序）
        """
        # 过滤掉健康监控标记为不可用的数据源
        available = []
        for name, config in self.sources.items():
            if self.health_monitor.is_available(name):
                available.append(config)
        
        # 按优先级排序
        available.sort(key=lambda x: x.priority)
        return available
    
    def _fetch_sequential(self,
                         sources: List[DataSourceConfig],
                         symbol: str,
                         start_date: datetime,
                         end_date: datetime,
                         frequency: str,
                         total_timeout: Optional[float] = None) -> Optional[Any]:
        """
        顺序获取（一个失败后尝试下一个）
        """
        for config in sources:
            source_name = config.name
            if self.health_monitor.should_skip(source_name):
                continue
                
            start_time = time.time()
            try:
                data = self._fetch_single_with_timeout(
                    config, symbol, start_date, end_date, frequency, 
                    config.timeout
                )
                if data is not None and self._is_valid_data(data):
                    # 成功
                    response_time = time.time() - start_time
                    self.health_monitor.mark_success(source_name, response_time)
                    logger.info(f"数据源 {source_name} 成功获取 {symbol} 数据")
                    return data
            except Exception as e:
                # 失败
                self.health_monitor.mark_failure(source_name, str(e))
                logger.warning(f"数据源 {source_name} 失败: {e}")
                continue
        
        # 所有数据源都失败
        logger.error(f"所有数据源都失败: {symbol}")
        return None
    
    def _fetch_parallel(self,
                       sources: List[DataSourceConfig],
                       symbol: str,
                       start_date: datetime,
                       end_date: datetime,
                       frequency: str,
                       total_timeout: Optional[float] = None) -> Optional[Any]:
        """
        并行获取（取最快成功的）
        """
        if total_timeout is None:
            # 使用最长超时时间+额外缓冲
            total_timeout = max(config.timeout for config in sources) + 2.0
        
        results_queue = queue.Queue()
        
        def _worker(config: DataSourceConfig):
            """工作线程函数"""
            source_name = config.name
            if self.health_monitor.should_skip(source_name):
                return
                
            start_time = time.time()
            try:
                data = self._fetch_single_with_timeout(
                    config, symbol, start_date, end_date, frequency,
                    config.timeout
                )
                if data is not None and self._is_valid_data(data):
                    # 成功
                    response_time = time.time() - start_time
                    self.health_monitor.mark_success(source_name, response_time)
                    # 放入结果队列
                    results_queue.put((source_name, data, response_time))
            except Exception as e:
                # 失败
                self.health_monitor.mark_failure(source_name, str(e))
                logger.debug(f"数据源 {source_name} 并行请求失败: {e}")
        
        # 启动工作线程
        threads = []
        for config in sources:
            thread = threading.Thread(target=_worker, args=(config,))
            thread.daemon = True
            thread.start()
            threads.append(thread)
        
        # 等待结果或超时
        try:
            # 尝试从队列获取第一个成功结果
            result = results_queue.get(timeout=total_timeout)
            source_name, data, response_time = result
            logger.info(f"并行获取成功: {source_name} 耗时{response_time:.2f}s")
            return data
        except queue.Empty:
            # 超时，所有数据源都失败或未完成
            logger.warning(f"并行获取超时: {total_timeout}s")
        finally:
            # 等待所有线程结束（如果有存活线程）
            for thread in threads:
                if thread.is_alive():
                    thread.join(timeout=1.0)
        
        return None
    
    def _fetch_single_with_timeout(self,
                                  config: DataSourceConfig,
                                  symbol: str,
                                  start_date: datetime,
                                  end_date: datetime,
                                  frequency: str,
                                  timeout: float) -> Optional[Any]:
        """
        单个数据源获取（带超时控制）
        """
        result: List[Any] = [None]  # 使用列表以便在内层函数修改
        exception: List[Optional[Exception]] = [None]

        def _fetch():
            """实际的获取函数"""
            try:
                result[0] = config.provider.fetch(symbol, start_date, end_date, frequency)
            except Exception as e:
                exception[0] = e
        
        # 创建线程执行获取
        thread = threading.Thread(target=_fetch)
        thread.daemon = True
        thread.start()
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            # 超时，线程仍在运行
            logger.warning(f"数据源 {config.name} 获取超时: {timeout}s")
            raise TimeoutError(f"数据源 {config.name} 超时")
        
        if exception[0]:
            raise exception[0]
            
        return result[0]
    
    def _is_valid_data(self, data: Any) -> bool:
        """
        验证数据是否有效
        
        Args:
            data: 获取的数据
            
        Returns:
            数据是否有效
        """
        if data is None:
            return False
        
        # 对于pandas DataFrame，检查是否为空
        if hasattr(data, 'empty'):
            return not data.empty
        
        # 对于列表，检查是否非空
        if isinstance(data, (list, tuple)):
            return len(data) > 0
        
        # 默认认为有效
        return True
    
    def get_primary_provider(self) -> Optional[BaseDataProvider]:
        """获取主数据源提供者"""
        if self.primary_source in self.sources:
            return self.sources[self.primary_source].provider
        return None
    
    def get_health_report(self) -> Dict:
        """获取健康报告"""
        return self.health_monitor.get_health_report()
    
    def get_latest(self, symbol: str, lookback: int = 100,
                   frequency: str = Frequency.DAILY) -> 'pd.DataFrame':
        """
        获取最新数据（兼容 MarketDataService 接口）

        根据股票代码智能选择数据源，然后调用对应 Provider 的 fetch 方法。

        Args:
            symbol: 股票代码
            lookback: 回溯条数
            frequency: 数据频率

        Returns:
            pd.DataFrame: OHLCV 数据
        """
        from datetime import timedelta

        # 计算时间范围
        end_date = datetime.now()
        if frequency in [Frequency.MIN_1, Frequency.MIN_5, Frequency.MIN_15,
                         Frequency.MIN_30, Frequency.MIN_60]:
            start_date = end_date - timedelta(days=7)
        elif frequency == Frequency.WEEKLY:
            start_date = end_date - timedelta(days=lookback * 7 * 2)
        elif frequency == Frequency.MONTHLY:
            start_date = end_date - timedelta(days=lookback * 30 * 2)
        else:
            start_date = end_date - timedelta(days=max(lookback * 2, 365))

        # 调用 fetch 方法获取数据
        data = self.fetch(symbol, start_date, end_date, frequency)

        if data is not None and not data.empty:
            return data.tail(lookback)

        return pd.DataFrame()

