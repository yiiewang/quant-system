"""
邮件通知模块
发送交易信号和操作建议到指定邮箱
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import List, Optional, Dict, Any
from datetime import datetime

from src.core.models import BaseNotifier, NotifyMessage, AnalysisResult
from src.config.schema import EmailConfig

logger = logging.getLogger(__name__)


class EmailNotifier(BaseNotifier):
    """
    邮件通知器
    
    继承 BaseNotifier 框架接口，实现邮件渠道的通知发送。
    
    Usage:
        config = EmailConfig(
            smtp_server="smtp.qq.com",
            smtp_port=465,
            username="your_email@qq.com",
            password="your_auth_code",
            recipients=["target@email.com"]
        )
        
        notifier = EmailNotifier(config)
        notifier.send_signal("002050.SZ", "BUY", 20.5, "MACD金叉")
    """
    
    def __init__(self, config: EmailConfig):
        self.config = config
        self._last_send_time: Dict[str, datetime] = {}
        self._min_interval = 60  # 同一股票最小通知间隔（秒）
    
    def send(self, message: NotifyMessage) -> bool:
        """
        发送通用通知消息 (BaseNotifier 接口实现)
        
        Args:
            message: 通知消息对象
        
        Returns:
            bool: 是否发送成功
        """
        body = message.content if message.content else f"<p>{message.content}</p>"
        return self._send_email(message.title, body)
        
    def send_signal(
        self,
        symbol: str,
        signal_type: str,  # BUY / SELL / HOLD
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
            signal_type: 信号类型 (BUY/SELL)
            price: 当前价格
            reason: 信号原因
            additional_info: 额外信息（如指标数据）
        
        Returns:
            bool: 是否发送成功
        """
        # 检查频率限制
        key = f"{symbol}_{signal_type}"
        now = datetime.now()
        
        if key in self._last_send_time:
            elapsed = (now - self._last_send_time[key]).total_seconds()
            if elapsed < self._min_interval:
                logger.debug(f"跳过发送，距上次通知仅 {elapsed:.0f}s")
                return False
        
        # 构建邮件内容
        subject = self._build_subject(symbol, signal_type, price)
        body = self._build_body(symbol, signal_type, price, reason, indicators, additional_info)
        
        # 发送邮件
        success = self._send_email(subject, body)
        
        if success:
            self._last_send_time[key] = now
            logger.info(f"信号通知已发送: {symbol} {signal_type}")
        
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
        """
        subject = f"📊 MACD交易系统 - 每日报告 {datetime.now().strftime('%Y-%m-%d')}"
        
        body = self._build_daily_summary_body(
            portfolio_value, daily_pnl, positions, signals
        )
        
        return self._send_email(subject, body)
    
    def send_alert(self, title: str, message: str) -> bool:
        """
        发送告警通知
        
        Args:
            title: 告警标题
            message: 告警内容
        """
        subject = f"⚠️ MACD交易系统告警 - {title}"
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="background-color: #fff3cd; border: 1px solid #ffc107; 
                        padding: 15px; border-radius: 5px; margin: 20px;">
                <h2 style="color: #856404; margin-top: 0;">⚠️ {title}</h2>
                <p style="color: #856404;">{message}</p>
                <p style="color: #999; font-size: 12px;">
                    时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </p>
            </div>
        </body>
        </html>
        """
        
        return self._send_email(subject, body)
    
    def _build_subject(self, symbol: str, signal_type: str, price: float) -> str:
        """构建邮件主题"""
        emoji = "🟢" if signal_type == "BUY" else "🔴" if signal_type == "SELL" else "⚪"
        action = "买入" if signal_type == "BUY" else "卖出" if signal_type == "SELL" else "持有"
        return f"{emoji} [{symbol}] {action}信号 @ {price:.2f}"
    
    def _build_body(
        self,
        symbol: str,
        signal_type: str,
        price: float,
        reason: str,
        indicators: Optional[Dict[str, Any]] = None,
        additional_info: Optional[Dict[str, Any]] = None
    ) -> str:
        """构建邮件正文（HTML格式）"""
        
        # 根据信号类型设置颜色
        if signal_type == "BUY":
            color = "#28a745"  # 绿色
            bg_color = "#d4edda"
            action = "买入"
            icon = "🟢"
        elif signal_type == "SELL":
            color = "#dc3545"  # 红色
            bg_color = "#f8d7da"
            action = "卖出"
            icon = "🔴"
        else:
            color = "#6c757d"  # 灰色
            bg_color = "#e2e3e5"
            action = "观望"
            icon = "⚪"
        
        # 指标信息表格
        info_rows = ""
        info_data = indicators or additional_info or {}
        if info_data:
            for key, value in info_data.items():
                if isinstance(value, float):
                    value = f"{value:.4f}"
                info_rows += f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd; color: #666;">{key}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{value}</td>
                </tr>
                """
        
        body = f"""
        <html>
        <head>
            <meta charset="utf-8">
        </head>
        <body style="font-family: 'Microsoft YaHei', Arial, sans-serif; background-color: #f5f5f5; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; 
                        border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                
                <!-- 头部 -->
                <div style="background-color: {color}; color: white; padding: 20px; text-align: center;">
                    <h1 style="margin: 0; font-size: 24px;">{icon} {action}信号</h1>
                </div>
                
                <!-- 主体信息 -->
                <div style="padding: 20px;">
                    <div style="background-color: {bg_color}; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="font-size: 14px; color: #666;">股票代码</td>
                                <td style="font-size: 20px; font-weight: bold; text-align: right;">{symbol}</td>
                            </tr>
                            <tr>
                                <td style="font-size: 14px; color: #666; padding-top: 10px;">当前价格</td>
                                <td style="font-size: 20px; font-weight: bold; color: {color}; text-align: right;">
                                    ¥{price:.2f}
                                </td>
                            </tr>
                        </table>
                    </div>
                    
                    <!-- 信号原因 -->
                    <div style="margin-bottom: 20px;">
                        <h3 style="color: #333; margin-bottom: 10px;">📝 信号原因</h3>
                        <p style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; 
                                  border-left: 4px solid {color}; margin: 0; color: #555;">
                            {reason}
                        </p>
                    </div>
                    
                    <!-- 技术指标 -->
                    {"" if not additional_info else f'''
                    <div style="margin-bottom: 20px;">
                        <h3 style="color: #333; margin-bottom: 10px;">📊 技术指标</h3>
                        <table style="width: 100%; border-collapse: collapse; background-color: #f8f9fa; 
                                      border-radius: 5px; overflow: hidden;">
                            {info_rows}
                        </table>
                    </div>
                    '''}
                    
                    <!-- 操作建议 -->
                    <div style="background-color: #e7f3ff; border-radius: 8px; padding: 15px;">
                        <h3 style="color: #0056b3; margin: 0 0 10px 0;">💡 操作建议</h3>
                        <p style="margin: 0; color: #004085;">
                            {self._get_suggestion(signal_type, price)}
                        </p>
                    </div>
                </div>
                
                <!-- 底部 -->
                <div style="background-color: #f8f9fa; padding: 15px; text-align: center; 
                            border-top: 1px solid #dee2e6;">
                    <p style="margin: 0; color: #999; font-size: 12px;">
                        发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
                        <span style="color: #dc3545;">⚠️ 本信号仅供参考，不构成投资建议，请自行判断风险</span>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return body
    
    def _build_daily_summary_body(
        self,
        portfolio_value: float,
        daily_pnl: float,
        positions: List[Dict],
        signals: List[Dict]
    ) -> str:
        """构建每日汇总报告正文"""
        
        pnl_color = "#28a745" if daily_pnl >= 0 else "#dc3545"
        pnl_emoji = "📈" if daily_pnl >= 0 else "📉"
        
        # 持仓表格
        positions_rows = ""
        for pos in positions:
            pnl = pos.get('pnl', 0)
            pnl_pct = pos.get('pnl_pct', 0)
            row_color = "#28a745" if pnl >= 0 else "#dc3545"
            positions_rows += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;">{pos.get('symbol', '')}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;">{pos.get('quantity', 0)}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;">¥{pos.get('cost', 0):.2f}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;">¥{pos.get('price', 0):.2f}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd; color: {row_color};">
                    ¥{pnl:.2f} ({pnl_pct:.2%})
                </td>
            </tr>
            """
        
        # 今日信号
        signals_rows = ""
        for sig in signals:
            sig_type = sig.get('type', 'HOLD')
            sig_color = "#28a745" if sig_type == "BUY" else "#dc3545" if sig_type == "SELL" else "#6c757d"
            sig_text = "买入" if sig_type == "BUY" else "卖出" if sig_type == "SELL" else "观望"
            signals_rows += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;">{sig.get('time', '')}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;">{sig.get('symbol', '')}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd; color: {sig_color}; font-weight: bold;">
                    {sig_text}
                </td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;">¥{sig.get('price', 0):.2f}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;">{sig.get('reason', '')}</td>
            </tr>
            """
        
        body = f"""
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: 'Microsoft YaHei', Arial, sans-serif; background-color: #f5f5f5; padding: 20px;">
            <div style="max-width: 800px; margin: 0 auto; background-color: white; 
                        border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                
                <div style="background-color: #007bff; color: white; padding: 20px; text-align: center;">
                    <h1 style="margin: 0;">📊 每日交易报告</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">{datetime.now().strftime('%Y-%m-%d')}</p>
                </div>
                
                <div style="padding: 20px;">
                    <!-- 账户概览 -->
                    <div style="display: flex; justify-content: space-around; margin-bottom: 30px;">
                        <div style="text-align: center; padding: 20px; background-color: #f8f9fa; 
                                    border-radius: 10px; flex: 1; margin: 0 10px;">
                            <p style="margin: 0; color: #666; font-size: 14px;">账户总值</p>
                            <p style="margin: 10px 0 0 0; font-size: 28px; font-weight: bold; color: #333;">
                                ¥{portfolio_value:,.2f}
                            </p>
                        </div>
                        <div style="text-align: center; padding: 20px; background-color: #f8f9fa; 
                                    border-radius: 10px; flex: 1; margin: 0 10px;">
                            <p style="margin: 0; color: #666; font-size: 14px;">今日盈亏 {pnl_emoji}</p>
                            <p style="margin: 10px 0 0 0; font-size: 28px; font-weight: bold; color: {pnl_color};">
                                {"+" if daily_pnl >= 0 else ""}¥{daily_pnl:,.2f}
                            </p>
                        </div>
                    </div>
                    
                    <!-- 当前持仓 -->
                    {f'''
                    <h2 style="color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px;">📦 当前持仓</h2>
                    <table style="width: 100%; border-collapse: collapse; margin-bottom: 30px;">
                        <thead>
                            <tr style="background-color: #f8f9fa;">
                                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #dee2e6;">股票</th>
                                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #dee2e6;">数量</th>
                                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #dee2e6;">成本</th>
                                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #dee2e6;">现价</th>
                                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #dee2e6;">盈亏</th>
                            </tr>
                        </thead>
                        <tbody>
                            {positions_rows if positions_rows else '<tr><td colspan="5" style="padding: 20px; text-align: center; color: #999;">当前无持仓</td></tr>'}
                        </tbody>
                    </table>
                    ''' if positions else ''}
                    
                    <!-- 今日信号 -->
                    <h2 style="color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px;">📡 今日信号</h2>
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="background-color: #f8f9fa;">
                                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #dee2e6;">时间</th>
                                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #dee2e6;">股票</th>
                                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #dee2e6;">信号</th>
                                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #dee2e6;">价格</th>
                                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #dee2e6;">原因</th>
                            </tr>
                        </thead>
                        <tbody>
                            {signals_rows if signals_rows else '<tr><td colspan="5" style="padding: 20px; text-align: center; color: #999;">今日无交易信号</td></tr>'}
                        </tbody>
                    </table>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 15px; text-align: center;">
                    <p style="margin: 0; color: #999; font-size: 12px;">
                        MACD量化交易系统 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return body
    
    def _get_suggestion(self, signal_type: str, price: float) -> str:
        """根据信号类型生成操作建议"""
        if signal_type == "BUY":
            return f"""
            建议在 ¥{price:.2f} 附近分批建仓，设置止损位为成本价下方 8%，
            即 ¥{price * 0.92:.2f}。建议首次建仓不超过计划仓位的 50%，
            等待回调确认后再加仓。
            """
        elif signal_type == "SELL":
            return f"""
            建议在 ¥{price:.2f} 附近减仓或清仓。如果当前持仓盈利，
            可以考虑分批卖出锁定利润；如果亏损，建议止损出局，
            避免更大损失。
            """
        else:
            return "当前无明确信号，建议观望等待更好的入场机会。"
    
    def _send_email(self, subject: str, body: str) -> bool:
        """
        发送邮件
        
        Args:
            subject: 邮件主题
            body: 邮件正文（HTML）
        
        Returns:
            bool: 是否发送成功
        """
        if not self.config.recipients:
            logger.warning("未配置收件人，跳过发送")
            return False
        
        if not self.config.username or not self.config.password:
            logger.warning("未配置邮箱账号或密码，跳过发送")
            return False
        
        logger.info(f"准备发送邮件: {subject}")
        logger.info(f"  SMTP服务器: {self.config.smtp_server}:{self.config.smtp_port}")
        logger.info(f"  发件人: {self.config.username}")
        logger.info(f"  收件人: {self.config.recipients}")
        
        try:
            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = formataddr((self.config.sender_name, self.config.username))
            msg['To'] = ', '.join(self.config.recipients)
            
            # 添加HTML正文
            html_part = MIMEText(body, 'html', 'utf-8')
            msg.attach(html_part)
            
            logger.info("  正在连接 SMTP 服务器...")
            
            # 发送邮件
            if self.config.use_ssl:
                server = smtplib.SMTP_SSL(
                    self.config.smtp_server,
                    self.config.smtp_port
                )
            else:
                server = smtplib.SMTP(
                    self.config.smtp_server,
                    self.config.smtp_port
                )
                server.starttls()
            
            logger.info("  正在登录...")
            server.login(self.config.username, self.config.password)
            
            logger.info("  正在发送邮件...")
            server.sendmail(
                self.config.username,
                self.config.recipients,
                msg.as_string()
            )
            server.quit()
            
            logger.info(f"✓ 邮件发送成功: {subject} -> {self.config.recipients}")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"邮箱认证失败，请检查用户名和授权码: {e}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP错误: {e}")
            return False
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False
    
    def test_connection(self) -> bool:
        """
        测试邮箱连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            if self.config.use_ssl:
                server = smtplib.SMTP_SSL(
                    self.config.smtp_server,
                    self.config.smtp_port,
                    timeout=10
                )
            else:
                server = smtplib.SMTP(
                    self.config.smtp_server,
                    self.config.smtp_port,
                    timeout=10
                )
                server.starttls()
            
            server.login(self.config.username, self.config.password)
            server.quit()
            
            logger.info("邮箱连接测试成功")
            return True
            
        except Exception as e:
            logger.error(f"邮箱连接测试失败: {e}")
            return False
