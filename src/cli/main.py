"""
CLI 主入口
提供命令行接口

新架构:
  - 系统配置 (config/default.yaml): 日志、存储、通知等
  - 策略配置 (src/strategy/configs/*.yaml): 策略参数、风控、引擎等
  - 支持同时运行多个策略，每个策略指定自己的配置文件

示例:
    # 单策略运行
    python -m src.main strategy --strategy-config src/strategy/configs/macd.yaml -m analyze

    # 多策略同时运行
    python -m src.main strategy --strategy-config src/strategy/configs/macd.yaml --strategy-config src/strategy/configs/weekly.yaml -m monitor

    # 指定系统配置
    python -m src.main strategy -c config/default.yaml --strategy-config src/strategy/configs/macd.yaml -m backtest
"""
import click
import logging
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """配置日志"""
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding='utf-8'))
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers,
        force=True
    )


def _ensure_strategies_registered():
    """确保所有内置策略已注册到注册表"""
    from src.strategy.registry import get_registry
    registry = get_registry()
    if not registry.has('macd'):
        import src.strategy  # noqa: F401 - 触发 __init__.py 中的注册


@click.group()
@click.version_option(version="1.0.0", prog_name="MACD Trading System")
@click.option('-v', '--verbose', is_flag=True, help='启用详细输出')
@click.pass_context
def cli(ctx, verbose):
    """
    MACD 量化交易系统
    
    支持模拟交易、历史回测和数据管理
    
    \b
    配置体系:
      系统配置: config/default.yaml (日志/存储/通知)
      策略配置: src/strategy/configs/*.yaml (策略参数/风控)
    
    \b
    推荐使用统一入口:
      strategy --strategy-config src/strategy/configs/macd.yaml -m analyze
      strategy --strategy-config macd.yaml --strategy-config weekly.yaml -m monitor  (多策略同时运行)
    """
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    
    if verbose:
        setup_logging("DEBUG")


# ============= strategy 统一入口 =============

@cli.command('strategy')
@click.option('--strategy-config', 'config_paths', multiple=True,
              type=click.Path(), help='策略配置文件路径（可多次指定以同时运行多个策略）')
@click.option('-c', '--config', 'sys_config_path', default=None,
              type=click.Path(), help='系统配置文件路径（默认 config/default.yaml）')
@click.option('-m', '--mode', required=True,
              type=click.Choice(['analyze', 'monitor', 'backtest']),
              help='运行模式: analyze(分析) / monitor(监控) / backtest(回测)')
@click.option('-s', '--symbols', default=None,
              help='交易标的，逗号分隔（覆盖所有策略的 YAML 配置）')
@click.option('--start', 'start_date', default=None,
              help='开始日期 YYYY-MM-DD (回测必填)')
@click.option('--end', 'end_date', default=None,
              help='结束日期 YYYY-MM-DD (回测必填)')
@click.option('--days', default=365, type=int,
              help='历史数据天数 (analyze/monitor)')
@click.option('--source', default='baostock',
              type=click.Choice(['tushare', 'akshare', 'baostock']),
              help='数据源')
@click.option('--interval', default=60, type=int,
              help='监控间隔秒数 (monitor)')
@click.option('--notify/--no-notify', default=True,
              help='是否启用通知 (monitor)')
@click.option('-o', '--output', 'output_dir', default='output',
              type=click.Path(), help='输出目录')
@click.option('--initial-capital', default=1000000, type=float,
              help='初始资金 (backtest)')
@click.option('--dry-run', is_flag=True, help='试运行，不执行实际操作')
@click.option('--list', 'list_strategies', is_flag=True,
              help='列出所有可用策略')
@click.pass_context
def strategy_cmd(ctx, config_paths, sys_config_path, mode, symbols, start_date,
                 end_date, days, source, interval, notify, output_dir,
                 initial_capital, dry_run, list_strategies):
    """
    统一策略运行入口
    
    \b
    支持同时运行多个策略，每个策略指定自己的配置文件。
    系统配置（通知/日志/存储）与策略配置分离。
    
    \b
    示例:
      # 单策略分析
      strategy --strategy-config src/strategy/configs/macd.yaml -m analyze -s 000001.SZ
    
      # 多策略同时监控
      strategy --strategy-config src/strategy/configs/macd.yaml --strategy-config src/strategy/configs/weekly.yaml -m monitor
    
      # 回测（指定系统配置）
      strategy -c config/default.yaml --strategy-config src/strategy/configs/macd.yaml -m backtest --start 2024-01-01 --end 2024-12-31
    """
    try:
        _ensure_strategies_registered()
        
        from src.strategy.registry import get_registry
        from src.config.loader import (
            load_system_config, load_strategy_config, load_config,
            RunParams,
        )
        
        # 列出策略
        if list_strategies:
            registry = get_registry()
            click.echo("可用策略:")
            click.echo("-" * 60)
            for info in registry.list_strategies():
                click.echo(f"  {info['name']:<20} {info['description']}")
                if info['default_params']:
                    click.echo(f"  {'':20} 默认参数: {info['default_params']}")
            return
        
        # 默认策略配置
        if not config_paths:
            config_paths = ('src/strategy/configs/default.yaml',)
        
        # 加载系统配置（全局共享）
        sys_config = load_system_config(sys_config_path)
        click.echo(f"系统配置: {sys_config_path or 'config/default.yaml (自动检测)'}")
        
        # 解析 CLI symbols
        symbol_list = [s.strip() for s in symbols.split(',')] if symbols else []
        
        # 为每个策略配置创建运行任务
        tasks: List[Tuple[str, object, RunParams]] = []
        
        for config_path in config_paths:
            config = load_config(config_path, sys_config_path)
            click.echo(f"策略配置: {config_path} -> 策略: {config.strategy.name}")
            
            params = RunParams(
                mode=mode,
                symbols=list(symbol_list),  # 复制一份，避免共享引用
                start_date=start_date,
                end_date=end_date,
                days=days,
                source=source,
                interval=interval,
                notify=notify,
                output_dir=output_dir,
                initial_capital=initial_capital,
                verbose=ctx.obj.get('verbose', False),
                dry_run=dry_run,
            )
            params.merge_with_config(config)
            
            tasks.append((config_path, config, params))
        
        if dry_run:
            click.echo(f"\n[试运行] 模式={mode}, 策略数量={len(tasks)}")
            for config_path, config, params in tasks:
                click.echo(f"  策略: {config.strategy.name}, 标的: {params.symbols}")
                click.echo(f"    参数: {config.strategy.params}")
            return
        
        # 选择运行模式
        from src.runner.application import ApplicationRunner
        
        # 执行所有策略
        if len(tasks) == 1:
            # 单策略：直接运行
            _, config, params = tasks[0]
            runner = ApplicationRunner(config=config, params=params)
            runner.start(mode)
        else:
            # 多策略：依次运行（后续可扩展为并发）
            click.echo(f"\n{'=' * 60}")
            click.echo(f"同时运行 {len(tasks)} 个策略")
            click.echo(f"{'=' * 60}")
            
            for i, (config_path, config, params) in enumerate(tasks, 1):
                click.echo(f"\n{'─' * 60}")
                click.echo(f"[{i}/{len(tasks)}] 策略: {config.strategy.name} ({config_path})")
                click.echo(f"{'─' * 60}")
                
                try:
                    runner = ApplicationRunner(config=config, params=params)
                    runner.start(mode)
                except Exception as e:
                    click.echo(f"策略 {config.strategy.name} 执行失败: {e}", err=True)
                    if ctx.obj.get('verbose'):
                        import traceback
                        traceback.print_exc()
        
    except KeyError as e:
        click.echo(f"错误: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"执行失败: {e}", err=True)
        if ctx.obj.get('verbose'):
            import traceback
            traceback.print_exc()
        sys.exit(1)


# ============= run 命令组 (原有，保留) =============

@cli.command()
@click.option('-c', '--config', 'config_path', default='src/strategy/configs/default.yaml',
              type=click.Path(), help='策略配置文件路径')
@click.option('-s', '--symbols', default=None, help='交易标的，逗号分隔')
@click.option('-m', '--mode', default='simulation',
              type=click.Choice(['simulation', 'paper', 'live']),
              help='交易模式')
@click.option('--dry-run', is_flag=True, help='试运行，不执行实际交易')
@click.pass_context
def run(ctx, config_path, symbols, mode, dry_run):
    """启动交易系统"""
    click.echo("=" * 50)
    click.echo("MACD 量化交易系统")
    click.echo("=" * 50)
    
    try:
        from src.config.loader import load_config, RunParams
        from src.runner.application import ApplicationRunner
        
        # 加载配置文件
        config = load_config(config_path)
        click.echo(f"加载配置: {config_path}")
        
        # 获取交易标的
        if symbols:
            symbol_list = [s.strip() for s in symbols.split(',')]
        else:
            symbol_list = config.strategy.symbols if hasattr(config.strategy, 'symbols') else ['000001.SZ']
        
        click.echo(f"交易标的: {symbol_list}")
        click.echo(f"交易模式: {mode}")
        
        if dry_run:
            click.echo("[试运行模式] 不执行实际交易")
            return
        
        # 构建运行参数
        params = RunParams(
            mode=mode,
            symbols=symbol_list,
            verbose=ctx.obj.get('verbose', False),
        )
        
        # 创建运行器
        runner = ApplicationRunner(config=config, params=params)
        
        click.echo("\n启动交易引擎...")
        runner.start(mode)
        
    except ImportError as e:
        click.echo(f"模块导入失败: {e}", err=True)
        click.echo("请确保已安装所有依赖: pip install -r requirements.txt", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"启动失败: {e}", err=True)
        if ctx.obj.get('verbose'):
            import traceback
            traceback.print_exc()
        sys.exit(1)


# ============= backtest 命令组 =============

@cli.command()
@click.option('-s', '--start', 'start_date', required=True,
              help='开始日期 (YYYY-MM-DD)')
@click.option('-e', '--end', 'end_date', required=True,
              help='结束日期 (YYYY-MM-DD)')
@click.option('--symbols', default='000001.SZ',
              help='回测标的，逗号分隔')
@click.option('--initial-capital', default=1000000, type=float,
              help='初始资金')
@click.option('-o', '--output', 'output_dir', default='output/backtest',
              type=click.Path(), help='输出目录')
@click.option('-c', '--config', 'config_path', default='src/strategy/configs/default.yaml',
              type=click.Path(), help='策略配置文件路径')
@click.option('--strategy', 'strategy_name', default='macd',
              type=click.Choice(['macd', 'multi_timeframe', 'weekly']),
              help='策略类型: macd(单周期) / multi_timeframe(多周期共振) / weekly(周线级别)')
@click.pass_context
def backtest(ctx, start_date, end_date, symbols, initial_capital, output_dir, config_path, strategy_name):
    """运行历史回测"""
    try:
        from src.config.loader import load_config, RunParams
        from src.runner.application import ApplicationRunner
        
        click.echo("=" * 50)
        click.echo("历史回测")
        click.echo("=" * 50)
        click.echo(f"回测区间: {start_date} ~ {end_date}")
        click.echo(f"回测标的: {symbols}")
        click.echo(f"初始资金: {initial_capital:,.0f}")
        click.echo(f"策略类型: {strategy_name}")
        
        # 加载配置
        config = load_config(config_path)
        config.strategy.name = strategy_name
        
        # 构建运行参数
        params = RunParams(
            mode='backtest',
            symbols=[s.strip() for s in symbols.split(',')],
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            output_dir=output_dir,
            verbose=ctx.obj.get('verbose', False),
        )
        
        # 创建运行器
        runner = ApplicationRunner(config=config, params=params)
        
        # 进度条
        import logging
        root_logger = logging.getLogger()
        console_handlers = [h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)]
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
                
                # 传递进度回调
                result = runner.start('backtest', progress_callback)
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
        if output_dir:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            # 从 runner 的引擎获取数据
            equity_df = runner._engine.get_equity_curve()
            if not equity_df.empty:
                equity_path = Path(output_dir) / 'equity_curve.csv'
                equity_df.to_csv(equity_path, index=False)
                click.echo(f"\n权益曲线已保存: {equity_path}")
            
            trades_df = runner._engine.get_trades()
            if not trades_df.empty:
                trades_path = Path(output_dir) / 'trades.csv'
                trades_df.to_csv(trades_path, index=False)
                click.echo(f"交易记录已保存: {trades_path}")
        
    except Exception as e:
        click.echo(f"回测失败: {e}", err=True)
        if ctx.obj.get('verbose'):
            import traceback
            traceback.print_exc()
        sys.exit(1)


# ============= analyze 命令 =============

@cli.command()
@click.option('--symbols', required=True, help='分析标的，逗号分隔')
@click.option('--days', default=365, type=int, help='加载历史数据天数')
@click.option('-c', '--config', 'config_path', default='src/strategy/configs/default.yaml',
              type=click.Path(), help='策略配置文件路径')
@click.option('--strategy', 'strategy_name', default='macd',
              type=click.Choice(['macd', 'multi_timeframe', 'weekly']),
              help='策略类型')
@click.option('--source', default='baostock',
              type=click.Choice(['tushare', 'akshare', 'baostock']),
              help='数据源')
@click.pass_context
def analyze(ctx, symbols, days, config_path, strategy_name, source):
    """分析当前市场状态，给出操作建议"""
    try:
        from src.config.loader import load_config, RunParams
        from src.runner.application import ApplicationRunner
        
        symbol_list = [s.strip() for s in symbols.split(',')]
        
        click.echo("=" * 60)
        click.echo("市场状态分析")
        click.echo("=" * 60)
        click.echo(f"分析标的: {symbol_list}")
        click.echo(f"回溯天数: {days}")
        click.echo(f"策略类型: {strategy_name}")
        click.echo("")
        
        # 加载配置
        config = load_config(config_path)
        config.strategy.name = strategy_name
        
        # 构建运行参数
        params = RunParams(
            mode='analyze',
            symbols=symbol_list,
            days=days,
            source=source,
            verbose=ctx.obj.get('verbose', False),
        )
        
        # 创建运行器
        runner = ApplicationRunner(config=config, params=params)
        
        # 执行分析
        for symbol in symbol_list:
            click.echo("-" * 60)
            click.echo(f"分析 {symbol}...")
            
            result = runner._engine.run_analyze(symbol, days)
            
            if 'error' in result:
                click.echo(f"  {result['error']}")
                continue
            
            click.echo("")
            click.echo(f"  股票代码: {result['symbol']}")
            click.echo(f"  当前状态: {result['status']}")
            click.echo(f"  建议操作: {result['action']}")
            click.echo(f"  置信度:   {result['confidence']:.0%}")
            click.echo("")
            click.echo(f"  分析理由:")
            for line in result.get('reason', '').split('\n'):
                click.echo(f"    {line.strip()}")
            click.echo("")
            click.echo(f"  关键指标:")
            for key, value in result.get('indicators', {}).items():
                click.echo(f"    {key}: {value}")
            click.echo("")
        
        click.echo("=" * 60)
        click.echo("分析完成")
        click.echo("=" * 60)
        
    except Exception as e:
        click.echo(f"分析失败: {e}", err=True)
        if ctx.obj.get('verbose'):
            import traceback
            traceback.print_exc()
        sys.exit(1)


# ============= monitor 命令 =============

@cli.command()
@click.option('--symbols', required=True, help='监控标的，逗号分隔')
@click.option('-c', '--config', 'config_path', default='src/strategy/configs/default.yaml',
              type=click.Path(), help='策略配置文件路径')
@click.option('--strategy', 'strategy_name', default='macd',
              type=click.Choice(['macd', 'multi_timeframe', 'weekly']),
              help='策略类型')
@click.option('--interval', default=60, type=int, help='检查间隔(秒)')
@click.option('--source', default='baostock',
              type=click.Choice(['tushare', 'akshare', 'baostock']),
              help='数据源')
@click.option('--notify/--no-notify', default=True, help='是否启用通知')
@click.pass_context
def monitor(ctx, symbols, config_path, strategy_name, interval, source, notify):
    """实时监控，计算信号并发送通知"""
    try:
        from src.config.loader import load_config, RunParams
        from src.runner.application import ApplicationRunner
        
        symbol_list = [s.strip() for s in symbols.split(',')]
        
        click.echo("=" * 60)
        click.echo("实时监控模式")
        click.echo("=" * 60)
        click.echo(f"监控标的: {symbol_list}")
        click.echo(f"检查间隔: {interval}s")
        click.echo(f"策略类型: {strategy_name}")
        click.echo(f"数据源: {source}")
        click.echo(f"通知: {'启用' if notify else '禁用'}")
        click.echo("")
        click.echo("按 Ctrl+C 停止监控")
        click.echo("-" * 60)
        
        # 加载配置
        config = load_config(config_path)
        config.strategy.name = strategy_name
        
        # 构建运行参数
        params = RunParams(
            mode='monitor',
            symbols=symbol_list,
            interval=interval,
            source=source,
            notify=notify,
            verbose=ctx.obj.get('verbose', False),
        )
        
        # 创建运行器
        runner = ApplicationRunner(config=config, params=params)
        
        # 执行监控
        runner.start('monitor')
        
    except KeyboardInterrupt:
        click.echo("\n监控已停止")
    except Exception as e:
        click.echo(f"监控失败: {e}", err=True)
        if ctx.obj.get('verbose'):
            import traceback
            traceback.print_exc()
        sys.exit(1)


def _init_notifier_from_sys_config(sys_config):
    """
    从系统配置初始化通知服务
    
    Args:
        sys_config: SystemConfig 对象
    
    Returns:
        通知器实例，未配置则返回 None
    """
    notif_config = sys_config.notification
    if not notif_config.enabled:
        return None
    
    notifiers = []
    
    # SMTP 邮件通知
    try:
        from src.notification.email_notifier import EmailNotifier, EmailConfig
        
        email_cfg = notif_config.email
        if email_cfg.get('enabled', False):
            recipients = email_cfg.get('recipients', [])
            if recipients:
                config = EmailConfig(recipients=recipients)
                if config.username and config.password:
                    notifiers.append(EmailNotifier(config))
                    logger.info("邮件通知已启用")
                else:
                    logger.warning("未设置 SMTP_USER / SMTP_PASS 环境变量，邮件通知不可用")
    except Exception as e:
        logger.warning(f"初始化邮件通知失败: {e}")
    
    # Webhook 通知
    try:
        from src.notification.webhook_notifier import WebhookNotifier, WebhookConfig
        
        webhook_cfg = notif_config.webhook
        webhook_url = webhook_cfg.get('url', '')
        if webhook_url:
            wh_config = WebhookConfig(
                url=webhook_url,
                type=webhook_cfg.get('type', ''),
            )
            notifiers.append(WebhookNotifier(wh_config))
            logger.info(f"Webhook 通知已启用")
    except Exception as e:
        logger.warning(f"初始化 Webhook 通知失败: {e}")
    
    if not notifiers:
        return None
    if len(notifiers) == 1:
        return notifiers[0]
    
    return _MultiNotifier(notifiers)


class _MultiNotifier:
    """组合多个通知渠道，统一调用"""
    
    def __init__(self, notifiers: list):
        self._notifiers = notifiers
    
    def send_signal(self, **kwargs) -> bool:
        return all(n.send_signal(**kwargs) for n in self._notifiers)
    
    def send_daily_summary(self, **kwargs) -> bool:
        return all(n.send_daily_summary(**kwargs) for n in self._notifiers)
    
    def send_alert(self, title: str, message: str) -> bool:
        return all(n.send_alert(title, message) for n in self._notifiers)


# ============= data 命令组 =============

@cli.group()
def data():
    """数据管理命令"""
    pass


@data.command('sync')
@click.option('--symbols', required=True, help='股票代码，逗号分隔')
@click.option('--days', default=365, type=int, help='同步天数')
@click.option('--start', 'start_date', default=None, help='开始日期 (YYYY-MM-DD)')
@click.option('--end', 'end_date', default=None, help='结束日期 (YYYY-MM-DD)')
@click.option('--source', default='baostock',
              type=click.Choice(['tushare', 'akshare', 'baostock']),
              help='数据源')
@click.option('--freq', default='daily',
              type=click.Choice(['daily', '5min', '15min', '30min', '60min']),
              help='数据频率: daily(日线) / 5min / 15min / 30min / 60min')
@click.pass_context
def data_sync(ctx, symbols, days, start_date, end_date, source, freq):
    """同步行情数据（支持日线和分时数据）"""
    click.echo("=" * 50)
    click.echo("数据同步")
    click.echo("=" * 50)
    
    try:
        symbol_list = [s.strip() for s in symbols.split(',')]
        
        # 分时数据默认只同步 5 天
        default_days = days if freq == 'daily' else min(days, 5)
        
        if start_date:
            start = datetime.strptime(start_date, '%Y-%m-%d')
        else:
            start = datetime.now() - timedelta(days=default_days)
        
        if end_date:
            end = datetime.strptime(end_date, '%Y-%m-%d')
        else:
            end = datetime.now()
        
        click.echo(f"数据源: {source}")
        click.echo(f"频率:   {freq}")
        click.echo(f"股票:   {symbol_list}")
        click.echo(f"日期范围: {start.date()} ~ {end.date()}")
        
        from src.data.market import MarketDataService, DataSource, Frequency
        
        freq_map = {
            'daily': Frequency.DAILY,
            '5min': Frequency.MIN_5,
            '15min': Frequency.MIN_15,
            '30min': Frequency.MIN_30,
            '60min': Frequency.MIN_60,
        }
        frequency = freq_map[freq]
        
        if source == 'tushare':
            data_source = DataSource.TUSHARE
            token = os.environ.get('TUSHARE_TOKEN', '')
            config = {'tushare_token': token}
            if not token:
                click.echo("警告: 未设置 TUSHARE_TOKEN 环境变量", err=True)
        elif source == 'baostock':
            data_source = DataSource.BAOSTOCK
            config = {}
        else:
            data_source = DataSource.AKSHARE
            config = {}
        
        service = MarketDataService(source=data_source, config=config)
        
        with click.progressbar(length=100, label='同步进度') as bar:
            last_progress = 0
            
            def progress_callback(progress):
                nonlocal last_progress
                delta = int(progress) - last_progress
                if delta > 0:
                    bar.update(delta)
                    last_progress = int(progress)
            
            count = service.sync(
                symbols=symbol_list,
                start_date=start,
                end_date=end,
                progress_callback=progress_callback,
                frequency=frequency
            )
            bar.update(100 - last_progress)
        
        click.echo(f"\n同步完成: {count} 条数据")
        
    except ImportError as e:
        click.echo(f"模块导入失败: {e}", err=True)
        click.echo("请安装数据源依赖:", err=True)
        click.echo("  - Tushare: pip install tushare", err=True)
        click.echo("  - AKShare: pip install akshare (需要 Python 3.8+)", err=True)
        click.echo("  - BaoStock: pip install baostock (推荐，免费)", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"同步失败: {e}", err=True)
        if ctx.obj.get('verbose'):
            import traceback
            traceback.print_exc()
        sys.exit(1)


@data.command('info')
@click.option('--symbol', default=None, help='股票代码（可选）')
@click.pass_context
def data_info(ctx, symbol):
    """查看数据信息"""
    try:
        from src.data.market import MarketDataService, DataSource
        
        service = MarketDataService(source=DataSource.LOCAL)
        
        # 日线数据统计
        stats = service.get_data_stats(symbol)
        
        if stats:
            click.echo("=" * 60)
            click.echo("日线数据")
            click.echo("=" * 60)
            click.echo(f"{'股票代码':<15} {'数据条数':<10} {'开始日期':<12} {'结束日期':<12}")
            click.echo("-" * 60)
            for item in stats:
                click.echo(
                    f"{item['symbol']:<15} "
                    f"{item['count']:<10} "
                    f"{item['start_date']:<12} "
                    f"{item['end_date']:<12}"
                )
        
        # 分时数据统计
        minute_stats = service.get_minute_stats(symbol)
        
        if minute_stats:
            click.echo("")
            click.echo("=" * 70)
            click.echo("分时数据")
            click.echo("=" * 70)
            click.echo(f"{'股票代码':<12} {'频率':<8} {'数据条数':<10} {'开始时间':<20} {'结束时间':<20}")
            click.echo("-" * 70)
            for item in minute_stats:
                click.echo(
                    f"{item['symbol']:<12} "
                    f"{item['frequency']:<8} "
                    f"{item['count']:<10} "
                    f"{item['start_time']:<20} "
                    f"{item['end_time']:<20}"
                )
        
        if not stats and not minute_stats:
            click.echo("暂无数据")
        
    except Exception as e:
        click.echo(f"查询失败: {e}", err=True)
        sys.exit(1)


@data.command('clean')
@click.option('--symbol', default=None, help='股票代码（可选）')
@click.option('--before', 'before_date', default=None, help='删除此日期之前的数据')
@click.option('--all', 'clean_all', is_flag=True, help='清理所有数据')
@click.confirmation_option(prompt='确认清理数据?')
@click.pass_context
def data_clean(ctx, symbol, before_date, clean_all):
    """清理数据缓存"""
    try:
        from src.data.market import MarketDataService, DataSource
        
        service = MarketDataService(source=DataSource.LOCAL)
        
        before = None
        if before_date:
            before = datetime.strptime(before_date, '%Y-%m-%d')
        
        if clean_all:
            symbol = None
            before = None
        
        count = service.clean(symbol=symbol, before_date=before)
        click.echo(f"已清理 {count} 条数据")
        
    except Exception as e:
        click.echo(f"清理失败: {e}", err=True)
        sys.exit(1)


# ============= report 命令组 =============

@cli.group()
def report():
    """报告查询命令"""
    pass


@report.command('positions')
@click.option('-c', '--config', 'config_path', default='src/strategy/configs/default.yaml',
              type=click.Path(), help='策略配置文件路径')
@click.pass_context
def report_positions(ctx, config_path):
    """查看当前持仓"""
    try:
        from src.config.loader import load_config
        from src.data.portfolio import PortfolioManager
        
        config = load_config(config_path)
        manager = PortfolioManager(config)
        
        positions = manager.get_positions()
        
        if not positions:
            click.echo("当前无持仓")
            return
        
        click.echo("=" * 70)
        click.echo(f"{'股票代码':<12} {'数量':<10} {'成本价':<10} {'现价':<10} {'盈亏':<10} {'盈亏率':<10}")
        click.echo("=" * 70)
        
        total_value = 0
        total_pnl = 0
        
        for pos in positions:
            pnl = (pos.current_price - pos.cost_basis) * pos.quantity
            pnl_pct = (pos.current_price / pos.cost_basis - 1) if pos.cost_basis > 0 else 0
            value = pos.current_price * pos.quantity
            
            total_value += value
            total_pnl += pnl
            
            click.echo(
                f"{pos.symbol:<12} "
                f"{pos.quantity:<10} "
                f"{pos.cost_basis:<10.2f} "
                f"{pos.current_price:<10.2f} "
                f"{pnl:<10.2f} "
                f"{pnl_pct:<10.2%}"
            )
        
        click.echo("=" * 70)
        click.echo(f"总市值: {total_value:,.2f}  总盈亏: {total_pnl:,.2f}")
        
    except Exception as e:
        click.echo(f"查询失败: {e}", err=True)
        if ctx.obj.get('verbose'):
            import traceback
            traceback.print_exc()
        sys.exit(1)


@report.command('trades')
@click.option('--days', default=7, type=int, help='查询天数')
@click.option('--symbol', default=None, help='股票代码（可选）')
@click.option('-o', '--output', 'output_file', default=None,
              type=click.Path(), help='导出到文件')
@click.pass_context
def report_trades(ctx, days, symbol, output_file):
    """查看交易记录"""
    try:
        from src.config.loader import load_config
        from src.data.portfolio import PortfolioManager
        
        config = load_config()
        manager = PortfolioManager(config)
        
        start_date = datetime.now() - timedelta(days=days)
        trades = manager.get_trades(start_date=start_date, symbol=symbol)
        
        if not trades:
            click.echo(f"最近 {days} 天无交易记录")
            return
        
        click.echo("=" * 80)
        click.echo(f"{'日期':<12} {'股票':<12} {'方向':<6} {'数量':<10} {'价格':<10} {'金额':<12}")
        click.echo("=" * 80)
        
        for trade in trades:
            click.echo(
                f"{trade['date']:<12} "
                f"{trade['symbol']:<12} "
                f"{trade['side']:<6} "
                f"{trade['quantity']:<10} "
                f"{trade['price']:<10.2f} "
                f"{trade['amount']:<12.2f}"
            )
        
        if output_file:
            import pandas as pd
            df = pd.DataFrame(trades)
            df.to_csv(output_file, index=False)
            click.echo(f"\n已导出到: {output_file}")
        
    except Exception as e:
        click.echo(f"查询失败: {e}", err=True)
        sys.exit(1)


@report.command('daily')
@click.option('--start', 'start_date', required=True, help='开始日期 (YYYY-MM-DD)')
@click.option('--end', 'end_date', default=None, help='结束日期 (YYYY-MM-DD)')
@click.pass_context
def report_daily(ctx, start_date, end_date):
    """查看每日汇总"""
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d') if end_date else datetime.now()
        
        from src.config.loader import load_config
        from src.data.portfolio import PortfolioManager
        
        config = load_config()
        manager = PortfolioManager(config)
        
        daily_stats = manager.get_daily_stats(start, end)
        
        if not daily_stats:
            click.echo("无数据")
            return
        
        click.echo("=" * 70)
        click.echo(f"{'日期':<12} {'净值':<12} {'日收益':<10} {'日收益率':<10} {'累计收益率':<10}")
        click.echo("=" * 70)
        
        for stat in daily_stats:
            click.echo(
                f"{stat['date']:<12} "
                f"{stat['nav']:<12.2f} "
                f"{stat['daily_pnl']:<10.2f} "
                f"{stat['daily_return']:<10.2%} "
                f"{stat['cum_return']:<10.2%}"
            )
        
    except Exception as e:
        click.echo(f"查询失败: {e}", err=True)
        sys.exit(1)


# ============= 配置命令 =============

@cli.command('config')
@click.option('--show', is_flag=True, help='显示当前配置')
@click.option('--init', is_flag=True, help='生成默认配置文件')
@click.option('-o', '--output', 'output_path', default='src/strategy/configs/default.yaml',
              type=click.Path(), help='输出路径')
@click.pass_context
def config_cmd(ctx, show, init, output_path):
    """配置管理"""
    try:
        from src.config.loader import load_config, get_default_config_content, save_config
        
        if init:
            content = get_default_config_content()
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            click.echo(f"配置文件已生成: {output_path}")
        
        elif show:
            config = load_config(output_path)
            click.echo("当前配置:")
            click.echo("-" * 40)
            
            config_dict = config.to_dict()
            for section, values in config_dict.items():
                click.echo(f"\n[{section}]")
                if isinstance(values, dict):
                    for key, value in values.items():
                        click.echo(f"  {key}: {value}")
                else:
                    click.echo(f"  {values}")
        
        else:
            click.echo("使用 --show 查看配置或 --init 生成默认配置")
        
    except Exception as e:
        click.echo(f"操作失败: {e}", err=True)
        sys.exit(1)


# ============= client 命令 (交互式客户端) =============

@cli.command('client')
@click.option('--server', default='localhost:8000',
              help='API 服务地址 (host:port)')
@click.pass_context
def client(ctx, server):
    """以交互式客户端连接到 API 服务

    \b
    连接到运行中的 HTTP API 服务，在终端中持续发送指令。
    需要先通过 serve 命令启动服务。

    \b
    内置命令:
      health        检查服务状态
      strategies    列出可用策略
      analyze       分析标的
      backtest      运行回测
      monitor       监控管理 (start/stop/status)
      status        查看监控状态
      sync          同步数据 (支持分时)
      data          查看数据信息
      help          显示帮助
      exit          退出

    \b
    示例:
      python -m src.main client                        # 连接 localhost:8000
      python -m src.main client --server 10.0.0.1:9000 # 连接远程服务

    \b
    交互示例:
      macd> analyze 000001.SZ --strategy macd --days 180
      macd> backtest 002050.SZ --start 2024-01-01 --end 2025-01-01
      macd> monitor start 000001.SZ,002050.SZ --interval 60
      macd> status
    """
    from src.cli.client import start_client
    start_client(server)


# ============= serve 命令 (HTTP API 服务) =============

@cli.command('serve')
@click.option('-H', '--host', default='0.0.0.0', help='监听地址')
@click.option('-p', '--port', default=8000, type=int, help='监听端口')
@click.option('--reload', 'auto_reload', is_flag=True, help='开发模式，代码变更自动重载')
@click.option('--workers', default=1, type=int, help='工作进程数')
@click.option('--log-level', 'log_level', default='info',
              type=click.Choice(['debug', 'info', 'warning', 'error']),
              help='日志级别')
@click.pass_context
def serve(ctx, host, port, auto_reload, workers, log_level):
    """以 HTTP API 服务形式启动系统

    \b
    提供 RESTful API 接口，支持:
      - POST /api/analyze       分析标的
      - POST /api/backtest      运行回测
      - POST /api/monitor/start 启动监控
      - POST /api/monitor/stop  停止监控
      - GET  /api/monitor/status 监控状态
      - POST /api/data/sync     同步数据 (支持分时)
      - GET  /api/data/info     数据统计
      - GET  /api/strategies    策略列表
      - GET  /api/health        健康检查

    \b
    示例:
      python -m src.main serve                    # 默认 0.0.0.0:8000
      python -m src.main serve -p 9000 --reload   # 开发模式
    """
    click.echo("=" * 60)
    click.echo("MACD 量化交易系统 - HTTP API 服务")
    click.echo("=" * 60)
    click.echo(f"  地址:   http://{host}:{port}")
    click.echo(f"  文档:   http://{host}:{port}/docs")
    click.echo(f"  重载:   {'开启' if auto_reload else '关闭'}")
    click.echo(f"  进程数: {workers}")
    click.echo("=" * 60)

    try:
        import uvicorn
    except ImportError:
        click.echo("错误: 需要安装 uvicorn 和 fastapi", err=True)
        click.echo("  pip install fastapi uvicorn[standard]", err=True)
        sys.exit(1)

    uvicorn.run(
        "src.api.server:app",
        host=host,
        port=port,
        reload=auto_reload,
        workers=workers if not auto_reload else 1,
        log_level=log_level,
    )


# ============= 版本信息 =============

@cli.command('info')
def info():
    """显示系统信息"""
    click.echo("=" * 50)
    click.echo("MACD 量化交易系统")
    click.echo("=" * 50)
    click.echo(f"版本: 1.0.0")
    click.echo(f"Python: {sys.version}")
    click.echo(f"工作目录: {os.getcwd()}")
    click.echo("")
    
    click.echo("依赖检查:")
    
    dependencies = [
        ('pandas', 'pandas'),
        ('numpy', 'numpy'),
        ('click', 'click'),
        ('yaml', 'pyyaml'),
        ('tushare', 'tushare'),
        ('akshare', 'akshare'),
    ]
    
    for module, package in dependencies:
        try:
            __import__(module)
            click.echo(f"  + {package}")
        except ImportError:
            click.echo(f"  - {package} (未安装)")


if __name__ == '__main__':
    cli()
