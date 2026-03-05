"""
监控 Runner
循环: 获取数据 -> 计算指标 -> 分析状态 -> 判断通知 -> 等待
"""
from datetime import datetime, timedelta
import time as time_module
import click
import logging

from .base import BaseRunner
from src.core.models import Portfolio
from src.strategy.base import StrategyContext

logger = logging.getLogger(__name__)


class MonitorRunner(BaseRunner):
    """
    监控模式 Runner
    
    循环监控指定标的，信号变化时发送通知。
    策略通过 should_notify() 决定是否通知。
    """
    
    def execute(self) -> None:
        """执行监控"""
        click.echo("=" * 60)
        click.echo("实时监控模式")
        click.echo("=" * 60)
        click.echo(f"策略: {self._strategy.name} v{self._strategy.version}")
        click.echo(f"监控标的: {self.params.symbols}")
        click.echo(f"检查间隔: {self.params.interval}s")
        click.echo(f"数据源: {self.params.source}")
        
        if self._notifier:
            click.echo("通知服务已启用")
        else:
            click.echo("通知服务未配置，仅控制台输出")
        
        click.echo("")
        click.echo("按 Ctrl+C 停止监控")
        click.echo("-" * 60)
        
        last_signals = {}
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.params.days)
        
        while True:
            try:
                now = datetime.now()
                click.echo(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 检查中...")
                
                for symbol in self.params.symbols:
                    try:
                        self._check_symbol(
                            symbol, start_date, now, last_signals
                        )
                    except Exception as e:
                        click.echo(f"  {symbol}: 处理失败 - {e}")
                        if self.params.verbose:
                            import traceback
                            traceback.print_exc()
                
                time_module.sleep(self.params.interval)
                
            except KeyboardInterrupt:
                break
        
        click.echo("\n监控已停止")
    
    def _check_symbol(
        self, symbol: str, start_date, end_date,
        last_signals: dict
    ) -> None:
        """检查单个标的"""
        data = self._data_service.get_history(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if data is None or data.empty:
            click.echo(f"  {symbol}: 无法获取数据")
            return
        
        # 计算指标
        data = self._strategy.calculate_indicators(data)
        
        # 分析状态
        analysis = self._strategy.analyze_status(data, symbol)
        
        click.echo(
            f"  {symbol}: "
            f"状态={analysis.status}, "
            f"建议={analysis.action}, "
            f"置信度={analysis.confidence:.0%}"
        )
        
        # 生成信号用于通知判断
        portfolio = Portfolio(cash=0, total_value=0)
        context = StrategyContext(symbol=symbol, portfolio=portfolio)
        signal = self._strategy.generate_signal(data, context)
        
        # 策略决定是否通知
        last_signal = last_signals.get(symbol)
        if self._strategy.should_notify(signal, last_signal):
            click.echo(f"  >>> {symbol} 信号变化: {signal.signal_type.name} - {signal.reason}")
            
            if self._notifier:
                try:
                    self._notifier.send_signal(
                        symbol=symbol,
                        signal_type=signal.signal_type.name,
                        price=signal.price,
                        reason=signal.reason,
                        additional_info=analysis.indicators,
                    )
                    click.echo(f"  >>> 通知已发送")
                except Exception as e:
                    click.echo(f"  >>> 通知发送失败: {e}")
        
        last_signals[symbol] = signal
