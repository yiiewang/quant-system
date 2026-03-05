"""
Runner 基类
定义所有 Runner 的通用流程和接口
"""
from abc import ABC, abstractmethod
from typing import Optional
import os
import logging

from src.config.loader import Config, RunParams
from src.strategy.registry import get_registry
from src.strategy.base import BaseStrategy

logger = logging.getLogger(__name__)


class BaseRunner(ABC):
    """
    Runner 基类
    
    统一执行流程:
    1. 加载配置 (Config) + 运行参数 (RunParams)
    2. 通过注册表创建策略实例
    3. 初始化数据服务
    4. 初始化通知服务（可选）
    5. 执行具体逻辑（子类实现）
    """
    
    def __init__(self, config: Config, params: RunParams):
        self.config = config
        self.params = params
        self._strategy: Optional[BaseStrategy] = None
        self._data_service = None
        self._notifier = None
    
    def run(self) -> None:
        """执行 Runner 主流程"""
        self._init_strategy()
        self._init_data_service()
        self._init_notifier()
        self.execute()
    
    def _init_strategy(self) -> None:
        """通过注册表创建策略实例"""
        registry = get_registry()
        strategy_name = self.config.strategy.name
        strategy_params = self.config.strategy.params
        
        self._strategy = registry.create(strategy_name, params=strategy_params)
        logger.info(f"策略已加载: {self._strategy.name} v{self._strategy.version}")
    
    def _init_data_service(self) -> None:
        """初始化数据服务"""
        from src.data.market import MarketDataService, DataSource
        
        source_map = {
            'tushare': DataSource.TUSHARE,
            'akshare': DataSource.AKSHARE,
            'baostock': DataSource.BAOSTOCK,
        }
        data_source = source_map.get(self.params.source, DataSource.BAOSTOCK)
        
        data_config = {}
        if self.params.source == 'tushare':
            data_config['tushare_token'] = os.environ.get('TUSHARE_TOKEN', '')
        
        self._data_service = MarketDataService(source=data_source, config=data_config)
        logger.info(f"数据服务已初始化: {self.params.source}")
    
    def _init_notifier(self) -> None:
        """初始化通知服务"""
        if not self.params.notify:
            return
        
        notif_config = self.config.notification
        if not notif_config.enabled:
            return
        
        notifiers = []
        
        # 邮件通知
        try:
            email_cfg = notif_config.email
            if email_cfg.get('enabled', False):
                from src.notification.email_notifier import EmailNotifier, EmailConfig
                recipients = email_cfg.get('recipients', [])
                if recipients:
                    ec = EmailConfig(recipients=recipients)
                    if ec.username and ec.password:
                        notifiers.append(EmailNotifier(ec))
                        logger.info("邮件通知已启用")
        except Exception as e:
            logger.warning(f"初始化邮件通知失败: {e}")
        
        # Webhook 通知
        try:
            webhook_cfg = notif_config.webhook
            webhook_url = webhook_cfg.get('url', '')
            if webhook_url:
                from src.notification.webhook_notifier import WebhookNotifier, WebhookConfig
                wh_config = WebhookConfig(
                    url=webhook_url,
                    type=webhook_cfg.get('type', ''),
                )
                notifiers.append(WebhookNotifier(wh_config))
                logger.info("Webhook 通知已启用")
        except Exception as e:
            logger.warning(f"初始化 Webhook 通知失败: {e}")
        
        if not notifiers:
            return
        
        if len(notifiers) == 1:
            self._notifier = notifiers[0]
        else:
            self._notifier = _MultiNotifier(notifiers)
    
    @abstractmethod
    def execute(self) -> None:
        """具体执行逻辑（子类实现）"""
        pass


class _MultiNotifier:
    """组合多个通知渠道"""
    
    def __init__(self, notifiers: list):
        self._notifiers = notifiers
    
    def send_signal(self, **kwargs) -> bool:
        return all(n.send_signal(**kwargs) for n in self._notifiers)
    
    def send_daily_summary(self, **kwargs) -> bool:
        return all(n.send_daily_summary(**kwargs) for n in self._notifiers)
    
    def send_alert(self, title: str, message: str) -> bool:
        return all(n.send_alert(title, message) for n in self._notifiers)
