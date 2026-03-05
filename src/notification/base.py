"""
通知服务基类
定义通知渠道的统一接口，框架层提供。

所有通知渠道（邮件、企业微信等）必须继承 BaseNotifier。
框架负责调用通知，策略通过 should_notify() 决定是否通知。
"""
from src.core.models import BaseNotifier, NotifyMessage, AnalysisResult

__all__ = ['BaseNotifier', 'NotifyMessage', 'AnalysisResult']
