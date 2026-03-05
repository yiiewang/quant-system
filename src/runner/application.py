"""
持久化的应用运行器
持有引擎、通知、监控、事件总线等组件
"""
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
import logging

from src.config.loader import Config, RunParams
from src.strategy.registry import get_registry
from src.strategy.base import BaseStrategy
from src.core.models import EngineConfig, EngineMode
from src.core.metrics import BacktestResult
from src.core.engine import TradingEngine
from src.core.event_bus import get_event_bus, EventType

logger = logging.getLogger(__name__)


class ApplicationRunner:
    """
    持久化的应用运行器
    
    职责:
    - 持有 TradingEngine 实例
    - 持有 EventBus (全局事件总线)
    - 持有 Notification (通知组件)
    - 持有 Monitor (监控组件)
    - 生命周期管理 (启动/停止/重启)
    
    Usage:
        runner = ApplicationRunner(config, params)
        runner.start('backtest')  # 启动回测模式
        runner.stop()  # 停止
    """
    
    def __init__(self, config: Config, params: RunParams):
        """
        初始化应用运行器
        
        Args:
            config: 系统配置
            params: 运行参数
        """
        self.config = config
        self.params = params
        
        # 核心组件
        self._engine: Optional[TradingEngine] = None
        self._event_bus = get_event_bus()
        self._notifier = None
        self._monitor = None
        
        # 应用状态
        self._running = False
        self._current_mode: Optional[str] = None
        self._progress_callback: Optional[Callable[[float], None]] = None
        
        logger.info("应用运行器初始化完成")
    
    def start(self, mode: str, progress_callback: Optional[Callable[[float], None]] = None) -> Any:
        """
        启动应用
        
        Args:
            mode: 运行模式 ('backtest', 'live', 'paper', 'analyze', 'monitor')
            progress_callback: 进度回调函数（回测模式）
        
        Returns:
            模式相关的返回值（如 BacktestResult）
        """
        if self._running:
            logger.warning("应用已在运行中")
            return None
        
        self._current_mode = mode
        self._progress_callback = progress_callback
        logger.info(f"启动应用: {mode} 模式")
        
        try:
            # 初始化引擎
            self._init_engine()
            
            # 初始化通知
            self._init_notifier()
            
            # 订阅事件通知
            self._subscribe_events()
            
            # 根据模式运行
            result = self._run_mode(mode)
            
            self._running = False
            return result
            
        except Exception as e:
            logger.error(f"应用启动失败: {e}")
            self._running = False
            raise
    
    def stop(self) -> None:
        """停止应用"""
        if not self._running:
            return
        
        logger.info("正在停止应用...")
        
        # 停止引擎
        if self._engine:
            self._engine.stop()
        
        self._running = False
        self._current_mode = None
        
        logger.info("应用已停止")
    
    def pause(self) -> None:
        """暂停应用"""
        if self._engine:
            self._engine.pause()
    
    def resume(self) -> None:
        """恢复应用"""
        if self._engine:
            self._engine.resume()
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取应用状态
        
        Returns:
            Dict: 状态信息
        """
        engine_status = self._engine.get_status() if self._engine else {}
        
        return {
            'running': self._running,
            'mode': self._current_mode,
            'notifier_enabled': self._notifier is not None,
            'engine': engine_status
        }
    
    def _init_engine(self) -> None:
        """初始化交易引擎"""
        # 创建策略实例
        strategy = self._create_strategy()
        
        # 构建引擎配置
        # 从 YAML 配置中获取 symbols
        yaml_symbols = self.config.get_raw('engine', 'symbols', default=[])
        symbols = self.params.symbols if self.params.symbols else yaml_symbols
        
        # EngineConfig.mode 只接受 paper 或 live，其他模式由 run_* 方法处理
        engine_mode = 'paper'  # 默认使用模拟模式
        
        engine_config = EngineConfig(
            symbols=symbols or ['000001.SZ'],  # 默认值
            strategy_name=self.config.strategy.name,
            mode=engine_mode,
            initial_capital=self.params.initial_capital,
            poll_interval=self.params.interval or 60,
            max_positions=10,  # 固定值，RiskConfig 中没有这个字段
            enable_risk_check=True,
            commission=self.config.strategy.commission if hasattr(self.config.strategy, 'commission') else 0.0003,
            slippage=self.config.strategy.slippage if hasattr(self.config.strategy, 'slippage') else 0.001,
        )
        
        # 创建引擎
        self._engine = TradingEngine(engine_config, self._event_bus)
        self._engine._strategy = strategy
        
        logger.info(f"交易引擎已初始化: {engine_config.strategy_name}")
    
    def _create_strategy(self) -> BaseStrategy:
        """创建策略实例"""
        registry = get_registry()
        strategy_name = self.config.strategy.name
        strategy_params = self.config.strategy.params
        
        strategy = registry.create(strategy_name, params=strategy_params)
        logger.info(f"策略已加载: {strategy.name} v{strategy.version}")
        
        return strategy
    
    def _init_notifier(self) -> None:
        """初始化通知服务"""
        if not self.params.notify:
            logger.info("通知服务未启用 (--notify=false)")
            return
        
        notif_config = self.config.notification
        if not notif_config or not notif_config.enabled:
            logger.info("通知配置未启用")
            return
        
        notifiers = []
        
        # 邮件通知
        try:
            email_cfg = notif_config.email if notif_config.email else {}
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
            webhook_cfg = notif_config.webhook if notif_config.webhook else {}
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
            logger.info("无可用通知渠道")
            return
        
        if len(notifiers) == 1:
            self._notifier = notifiers[0]
        else:
            self._notifier = _MultiNotifier(notifiers)
    
    def _subscribe_events(self) -> None:
        """订阅事件以发送通知"""
        if not self._notifier:
            return
        
        # 订阅订单成交事件
        def on_order_filled(event_data):
            try:
                self._notifier.send_signal(**event_data.get('order', {}))
            except Exception as e:
                logger.error(f"发送通知失败: {e}")
        
        self._event_bus.subscribe(EventType.ORDER_FILLED, on_order_filled)
        logger.info("事件通知已订阅")
    
    def _run_mode(self, mode: str) -> Any:
        """
        根据模式运行引擎
        
        Args:
            mode: 运行模式
        
        Returns:
            模式相关的返回值
        """
        self._running = True
        
        if mode == 'backtest':
            # 解析日期
            if not self.params.start_date or not self.params.end_date:
                raise ValueError("回测模式需要指定 --start 和 --end 日期")
            
            start_date = datetime.strptime(self.params.start_date, '%Y-%m-%d')
            end_date = datetime.strptime(self.params.end_date, '%Y-%m-%d')
            
            return self._engine.run_backtest(start_date, end_date, self._progress_callback)
        
        elif mode == 'live':
            return self._engine.run_live()
        
        elif mode == 'paper':
            self._engine.run_paper()
            return None
        
        elif mode == 'analyze':
            symbols = self.params.symbols or self.config.strategy.symbols
            if not symbols:
                raise ValueError("分析模式需要指定标的")
            return self._engine.run_analyze(symbols[0], self.params.days or 60)
        
        elif mode == 'monitor':
            symbols = self.params.symbols or self.config.strategy.symbols
            if not symbols:
                raise ValueError("监控模式需要指定标的")
            
            # 定义通知回调
            notify_callback = None
            if self._notifier:
                notify_callback = lambda data: self._notifier.send_signal(**data)
            
            self._engine.run_monitor(symbols, self.params.interval or 60, notify_callback)
            return None
        
        else:
            raise ValueError(f"未知的运行模式: {mode}")


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
