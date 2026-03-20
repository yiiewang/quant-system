"""
通知管理器

封装邮件和 Webhook 通知渠道，对外提供统一接口。
"""
from typing import Optional, Dict, Any, List
import logging

from src.config.schema import NotificationConfig
from src.core.models import NotifyMessage
from .email_notifier import EmailNotifier
from .webhook_notifier import WebhookNotifier

logger = logging.getLogger(__name__)


class NotificationManager:
    """
    统一通知管理器

    封装邮件和 Webhook 通知渠道，对外提供统一接口。
    根据 NotificationConfig 自动初始化和路由通知。

    Usage:
        from src.config import load_config, Config
        from src.notification import NotificationManager

        # 从配置初始化
        config = load_config(Config)
        notifier = NotificationManager(config.notification)

        # 发送交易信号
        notifier.send_signal(
            symbol="000001.SZ",
            signal_type="BUY",
            price=10.5,
            reason="MACD金叉"
        )

        # 发送每日汇总
        notifier.send_daily_summary(
            portfolio_value=100000,
            daily_pnl=5000,
            positions=[...],
            signals=[...]
        )
    """

    def __init__(self, config: NotificationConfig):
        """
        初始化通知管理器

        Args:
            config: 通知配置
        """
        self.config = config
        self._email_notifier: Optional[EmailNotifier] = None
        self._webhook_notifier: Optional[WebhookNotifier] = None

        if config.enabled:
            # 初始化邮件通知器
            if config.email.recipients:
                self._email_notifier = EmailNotifier(config.email)
                logger.info(f"邮件通知已启用: {config.email.recipients}")

            # 初始化 Webhook 通知器
            if config.webhook.url:
                self._webhook_notifier = WebhookNotifier(config.webhook)
                logger.info(f"Webhook通知已启用: {config.webhook.type or 'custom'}")
        else:
            logger.info("通知功能已禁用")

    def send_signal(
        self,
        symbol: str,
        signal_type: str,
        price: float,
        reason: str,
        indicators: Optional[Dict[str, Any]] = None,
        additional_info: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> bool:
        """
        发送交易信号通知

        Args:
            symbol: 股票代码
            signal_type: 信号类型 (BUY/SELL/HOLD)
            price: 当前价格
            reason: 信号原因
            indicators: 指标数据
            additional_info: 额外信息

        Returns:
            bool: 是否有至少一个渠道发送成功
        """
        if not self.config.enabled:
            return False

        success = False

        if self._email_notifier:
            try:
                if self._email_notifier.send_signal(
                    symbol, signal_type, price, reason, indicators, additional_info, **kwargs
                ):
                    success = True
            except Exception as e:
                logger.error(f"邮件发送信号失败: {e}")

        if self._webhook_notifier:
            try:
                if self._webhook_notifier.send_signal(
                    symbol, signal_type, price, reason, indicators, additional_info, **kwargs
                ):
                    success = True
            except Exception as e:
                logger.error(f"Webhook发送信号失败: {e}")

        return success

    def send_daily_summary(
        self,
        portfolio_value: float,
        daily_pnl: float,
        positions: List[Dict],
        signals: List[Dict]
    ) -> bool:
        """
        发送每日汇总报告

        Args:
            portfolio_value: 组合总值
            daily_pnl: 当日盈亏
            positions: 持仓列表
            signals: 今日信号列表

        Returns:
            bool: 是否有至少一个渠道发送成功
        """
        if not self.config.enabled:
            return False

        success = False

        if self._email_notifier:
            try:
                if self._email_notifier.send_daily_summary(
                    portfolio_value, daily_pnl, positions, signals
                ):
                    success = True
            except Exception as e:
                logger.error(f"邮件发送每日汇总失败: {e}")

        if self._webhook_notifier:
            try:
                if self._webhook_notifier.send_daily_summary(
                    portfolio_value, daily_pnl, positions, signals
                ):
                    success = True
            except Exception as e:
                logger.error(f"Webhook发送每日汇总失败: {e}")

        return success

    def send_alert(self, title: str, message: str) -> bool:
        """
        发送告警通知

        Args:
            title: 告警标题
            message: 告警内容

        Returns:
            bool: 是否有至少一个渠道发送成功
        """
        if not self.config.enabled:
            return False

        success = False

        if self._email_notifier:
            try:
                if self._email_notifier.send_alert(title, message):
                    success = True
            except Exception as e:
                logger.error(f"邮件发送告警失败: {e}")

        if self._webhook_notifier:
            try:
                if self._webhook_notifier.send_alert(title, message):
                    success = True
            except Exception as e:
                logger.error(f"Webhook发送告警失败: {e}")

        return success

    def send(self, message: NotifyMessage) -> bool:
        """
        发送通用通知消息

        Args:
            message: 通知消息对象

        Returns:
            bool: 是否有至少一个渠道发送成功
        """
        if not self.config.enabled:
            return False

        success = False

        if self._email_notifier:
            try:
                if self._email_notifier.send(message):
                    success = True
            except Exception as e:
                logger.error(f"邮件发送消息失败: {e}")

        if self._webhook_notifier:
            try:
                if self._webhook_notifier.send(message):
                    success = True
            except Exception as e:
                logger.error(f"Webhook发送消息失败: {e}")

        return success

    def test_connections(self) -> Dict[str, bool]:
        """
        测试所有通知渠道的连接

        Returns:
            Dict: 各渠道连接状态
        """
        results = {}

        if self._email_notifier:
            results['email'] = self._email_notifier.test_connection()
        else:
            results['email'] = False

        if self._webhook_notifier:
            # Webhook 没有 test_connection 方法，通过发送测试消息验证
            try:
                results['webhook'] = self._webhook_notifier.send_alert(
                    "连接测试", "这是一条测试消息"
                )
            except Exception:
                results['webhook'] = False
        else:
            results['webhook'] = False

        return results

    def is_enabled(self) -> bool:
        """检查通知是否启用"""
        return self.config.enabled

    def has_email(self) -> bool:
        """检查是否配置了邮件通知"""
        return self._email_notifier is not None

    def has_webhook(self) -> bool:
        """检查是否配置了 Webhook 通知"""
        return self._webhook_notifier is not None
