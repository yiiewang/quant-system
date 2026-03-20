"""
通知模块

统一入口：NotificationManager
支持邮件、Webhook（企业微信/钉钉/飞书）等通知方式

Usage:
    from src.notification import NotificationManager
    from src.config import load_config, Config

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

    # 发送告警
    notifier.send_alert(title="系统错误", message="连接超时")
"""

from .manager import NotificationManager

__all__ = ['NotificationManager']
