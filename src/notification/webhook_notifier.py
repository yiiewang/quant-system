"""
Webhook 通知模块
通过企业微信/钉钉/飞书群机器人发送交易信号通知，零配置依赖。
"""
import json
import logging
from urllib import request, error
from typing import Optional, Dict, Any
from datetime import datetime

from src.core.models import BaseNotifier, NotifyMessage
from src.config.schema import WebhookConfig

logger = logging.getLogger(__name__)


class WebhookNotifier(BaseNotifier):
    """
    Webhook 通知器
    
    自动识别 URL 类型（企业微信/钉钉/飞书），按对应格式发送消息。
    只依赖 Python 标准库，无额外依赖。
    """
    
    def __init__(self, config: WebhookConfig):
        self.config = config
        self._type = config.type or self._detect_type(config.url)
    
    @staticmethod
    def _detect_type(url: str) -> str:
        """根据 URL 自动判断平台类型"""
        if "qyapi.weixin.qq.com" in url:
            return "wecom"
        elif "oapi.dingtalk.com" in url:
            return "dingtalk"
        elif "open.feishu.cn" in url or "open.larksuite.com" in url:
            return "feishu"
        return "custom"
    
    def send(self, message: NotifyMessage) -> bool:
        """发送通用通知消息 (BaseNotifier 接口实现)"""
        return self._post(message.title, message.content)
    
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
        """发送交易信号通知"""
        action = {"BUY": "买入", "SELL": "卖出"}.get(signal_type, "观望")
        icon = {"BUY": "🟢", "SELL": "🔴"}.get(signal_type, "⚪")
        
        title = f"{icon} [{symbol}] {action}信号 @ ¥{price:.2f}"
        
        lines = [
            f"**{title}**",
            f"> 原因: {reason}",
        ]
        
        if additional_info:
            for k, v in additional_info.items():
                val = f"{v:.4f}" if isinstance(v, float) else str(v)
                lines.append(f"> {k}: {val}")
        
        lines.append(f"\n_{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_")
        
        return self._post(title, "\n".join(lines))
    
    def send_daily_summary(
        self,
        portfolio_value: float,
        daily_pnl: float,
        positions: list,
        signals: list,
    ) -> bool:
        """发送每日汇总"""
        pnl_icon = "📈" if daily_pnl >= 0 else "📉"
        title = f"📊 每日报告 {datetime.now().strftime('%Y-%m-%d')}"
        
        lines = [
            f"**{title}**",
            f"账户总值: ¥{portfolio_value:,.2f}",
            f"今日盈亏: {pnl_icon} {'+'if daily_pnl>=0 else ''}¥{daily_pnl:,.2f}",
        ]
        
        if positions:
            lines.append("\n**持仓:**")
            for p in positions:
                pnl = p.get('pnl', 0)
                lines.append(
                    f"- {p.get('symbol','')}  {p.get('quantity',0)}股  "
                    f"盈亏 {'+'if pnl>=0 else ''}¥{pnl:.2f}"
                )
        
        if signals:
            lines.append("\n**今日信号:**")
            for s in signals:
                st = {"BUY": "买入", "SELL": "卖出"}.get(s.get('type', ''), '观望')
                lines.append(f"- {s.get('symbol','')} {st} @ ¥{s.get('price',0):.2f}")
        
        return self._post(title, "\n".join(lines))
    
    def send_alert(self, title: str, message: str) -> bool:
        """发送告警"""
        return self._post(f"⚠️ {title}", message)
    
    # ---- 内部方法 ----
    
    def _post(self, title: str, content: str) -> bool:
        """发送 Webhook 请求"""
        if not self.config.url:
            logger.warning("未配置 Webhook URL")
            return False
        
        payload = self._build_payload(title, content)
        
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = request.Request(
                self.config.url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())
                # 各平台成功判断
                ok = (
                    body.get("errcode") == 0        # 企业微信 / 钉钉
                    or body.get("code") == 0         # 飞书
                    or body.get("StatusCode") == 0   # 飞书旧版
                    or resp.status == 200             # 自定义兜底
                )
                if ok:
                    logger.info(f"Webhook 通知已发送: {title}")
                else:
                    logger.warning(f"Webhook 返回异常: {body}")
                return ok
                
        except error.URLError as e:
            logger.error(f"Webhook 请求失败: {e}")
            return False
        except Exception as e:
            logger.error(f"Webhook 发送失败: {e}")
            return False
    
    def _build_payload(self, title: str, content: str) -> dict:
        """根据平台类型构建请求体"""
        if self._type == "wecom":
            return {
                "msgtype": "markdown",
                "markdown": {"content": content},
            }
        elif self._type == "dingtalk":
            return {
                "msgtype": "markdown",
                "markdown": {"title": title, "text": content},
            }
        elif self._type == "feishu":
            return {
                "msg_type": "text",
                "content": {"text": f"{title}\n\n{content}"},
            }
        else:
            # 通用 JSON
            return {"title": title, "content": content}
