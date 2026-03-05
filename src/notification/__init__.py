"""
通知模块
支持邮件、Webhook（企业微信/钉钉/飞书）等通知方式
"""
from .base import BaseNotifier, NotifyMessage
from .email_notifier import EmailNotifier
from .webhook_notifier import WebhookNotifier

__all__ = ['BaseNotifier', 'NotifyMessage', 'EmailNotifier', 'WebhookNotifier']
