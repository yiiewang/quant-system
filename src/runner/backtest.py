"""
回测 Runner
加载数据 -> 运行策略 -> 输出绩效指标
"""
from datetime import datetime
from pathlib import Path
import click
import logging

from .base import BaseRunner

logger = logging.getLogger(__name__)


class BacktestRunner(BaseRunner):
    """
    回测模式 Runner
    
    在历史数据上运行策略，输出收益率、夏普比率等绩效指标。
    """
    
    def execute(self) -> None:
        """执行回测"""
        click.echo("=" * 50)
        click.echo("历史回测")
        click.echo("=" * 50)
        
        # 解析日期
        if not self.params.start_date or not self.params.end_date:
            click.echo("回测模式需要指定 --start 和 --end 日期", err=True)
            return
        
        start = datetime.strptime(self.params.start_date, '%Y-%m-%d')
        end = datetime.strptime(self.params.end_date, '%Y-%m-%d')
        
        click.echo(f"回测区间: {self.params.start_date} ~ {self.params.end_date}")
        click.echo(f"回测标的: {self.params.symbols}")
        click.echo(f"初始资金: {self.params.initial_capital:,.0f}")
        click.echo(f"策略: {self._strategy.name} v{self._strategy.version}")
        
        try:
            from src.backtest.engine import BacktestEngine
            
            engine = BacktestEngine(
                strategy=self._strategy,
                symbols=self.params.symbols,
                start_date=start,
                end_date=end,
                initial_capital=self.params.initial_capital
            )
            
            # 临时降低控制台日志级别
            root_logger = logging.getLogger()
            console_handlers = [
                h for h in root_logger.handlers
                if isinstance(h, logging.StreamHandler)
            ]
            original_levels = {h: h.level for h in console_handlers}
            for handler in console_handlers:
                handler.setLevel(logging.CRITICAL)
            
            try:
                with click.progressbar(length=100, label='回测进度') as bar:
                    last_progress = 0
                    
                    def progress_callback(progress):
                        nonlocal last_progress
                        delta = int(progress) - last_progress
                        if delta > 0:
                            bar.update(delta)
                            last_progress = int(progress)
                    
                    result = engine.run(progress_callback=progress_callback)
                    bar.update(100 - last_progress)
            finally:
                for handler, level in original_levels.items():
                    handler.setLevel(level)
            
            # 输出结果
            click.echo("\n" + "=" * 50)
            click.echo("回测结果")
            click.echo("=" * 50)
            click.echo(f"总收益率: {result.total_return:.2%}")
            click.echo(f"年化收益: {result.annual_return:.2%}")
            click.echo(f"最大回撤: {result.max_drawdown:.2%}")
            click.echo(f"夏普比率: {result.sharpe_ratio:.2f}")
            click.echo(f"交易次数: {result.trade_count}")
            click.echo(f"胜率: {result.win_rate:.2%}")
            
            # 保存结果
            output_dir = self.params.output_dir
            if output_dir:
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                
                equity_df = engine.get_equity_curve()
                if not equity_df.empty:
                    equity_path = Path(output_dir) / 'equity_curve.csv'
                    equity_df.to_csv(equity_path, index=False)
                    click.echo(f"\n权益曲线已保存: {equity_path}")
                
                trades_df = engine.get_trades()
                if not trades_df.empty:
                    trades_path = Path(output_dir) / 'trades.csv'
                    trades_df.to_csv(trades_path, index=False)
                    click.echo(f"交易记录已保存: {trades_path}")
        
        except Exception as e:
            click.echo(f"回测失败: {e}", err=True)
            if self.params.verbose:
                import traceback
                traceback.print_exc()
