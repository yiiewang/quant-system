"""
分析 Runner
获取数据 -> 计算指标 -> 分析状态 -> 输出结果
"""
from datetime import datetime, timedelta
import click
import logging

from .base import BaseRunner

logger = logging.getLogger(__name__)


class AnalyzeRunner(BaseRunner):
    """
    分析模式 Runner
    
    对指定标的进行一次性分析，输出当前市场状态和建议操作。
    """
    
    def execute(self) -> None:
        """执行分析"""
        click.echo("=" * 60)
        click.echo("市场状态分析")
        click.echo("=" * 60)
        click.echo(f"策略: {self._strategy.name} v{self._strategy.version}")
        click.echo(f"数据源: {self.params.source}")
        click.echo(f"分析标的: {self.params.symbols}")
        click.echo("")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.params.days)
        
        for symbol in self.params.symbols:
            click.echo("-" * 60)
            click.echo(f"分析 {symbol}...")
            
            try:
                data = self._data_service.get_history(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date
                )
                
                if data is None or data.empty:
                    click.echo(f"  无法获取 {symbol} 的数据，跳过")
                    continue
                
                click.echo(f"  数据范围: {data.index[0]} ~ {data.index[-1]} ({len(data)} 条)")
                
                # 计算指标
                data = self._strategy.calculate_indicators(data)
                
                # 分析状态
                result = self._strategy.analyze_status(data, symbol)
                
                # 输出结果
                click.echo("")
                click.echo(f"  股票代码: {result.symbol}")
                click.echo(f"  当前状态: {result.status}")
                click.echo(f"  建议操作: {result.action}")
                click.echo(f"  置信度:   {result.confidence:.0%}")
                click.echo("")
                click.echo(f"  分析理由:")
                for line in result.reason.split('\n'):
                    click.echo(f"    {line.strip()}")
                click.echo("")
                click.echo(f"  关键指标:")
                for key, value in result.indicators.items():
                    click.echo(f"    {key}: {value}")
                click.echo("")
                
            except Exception as e:
                click.echo(f"  分析 {symbol} 失败: {e}")
                if self.params.verbose:
                    import traceback
                    traceback.print_exc()
        
        click.echo("=" * 60)
        click.echo("分析完成")
        click.echo("=" * 60)
