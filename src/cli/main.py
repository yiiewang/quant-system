"""
CLI 主入口
提供命令行接口

新架构:
  - 系统配置 (config/system.yaml): 日志、存储、通知等
  - 策略配置 (data/strategies/*.yaml): 策略参数、风控、引擎等
  - 每次运行一个策略，指定一个标的

示例:
    # 单策略分析
    python -m src.main strategy -s aaa --strategy-config data/strategies/aaa.yaml -m analyze --symbols 000001.SZ

    # 单策略回测
    python -m src.main strategy --sys-config config/system.yaml -s aaa --strategy-config data/strategies/aaa.yaml -m backtest --start 2024-01-01 --end 2024-12-31

    # 单策略实时监控
    python -m src.main strategy -s aaa --strategy-config data/strategies/aaa.yaml -m live --symbols 000001.SZ
"""

import click
import logging
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple

# 加载 .env 文件
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")


# ==================== 终端颜色支持 ====================


class Colors:
    """终端颜色"""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

    @staticmethod
    def enable():
        """启用颜色输出"""
        # 检查是否支持颜色
        if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
            return False
        return True


# 如果不支持颜色，将所有颜色代码置空
if not Colors.enable():
    for attr in dir(Colors):
        if not attr.startswith("_") and attr.isupper():
            setattr(Colors, attr, "")

logger = logging.getLogger(__name__)


# 从策略引擎导入策略管理器
from src.strategy.manager import get_strategy_manager


@click.group()
@click.version_option(version="1.0.0", prog_name="MACD Trading System")
@click.option("-v", "--verbose", is_flag=True, help="启用详细输出")
@click.pass_context
def cli(ctx, verbose):
    """
    MACD 量化交易系统

    所有运行模式统一通过 strategy 命令，每次运行一个策略:
      strategy -s 策略名 --strategy-config 配置路径 -m analyze    分析市场状态
      strategy -s 策略名 --strategy-config 配置路径 -m backtest   历史回测
      strategy -s 策略名 --strategy-config 配置路径 -m live       实时监控

    \b
    示例:
      strategy -s aaa --strategy-config data/strategies/aaa.yaml -m backtest --symbols 002050.SZ --start 2024-01-01 --end 2025-03-20
      strategy -s aaa --strategy-config data/strategies/aaa.yaml -m analyze --symbols 000001.SZ --days 180
      strategy -s aaa --strategy-config data/strategies/aaa.yaml -m live --symbols 000001.SZ --interval 60
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


# ============= strategy 统一入口 =============


@cli.command("strategy")
@click.option("-s", "--strategy", required=True, help="策略名称，如 -s macd")
@click.option(
    "--strategy-config",
    required=True,
    help="策略配置路径，如 --strategy-config data/strategies/macd.yaml",
)
@click.option(
    "--sys-config",
    "sys_config_path",
    default=None,
    type=click.Path(),
    help="系统配置文件路径（默认 config/system.yaml）",
)
@click.option(
    "-m",
    "--mode",
    required=True,
    type=click.Choice(["analyze", "live", "backtest"]),
    help="运行模式: analyze(分析) / live(实时) / backtest(回测)",
)
@click.option( "--symbol", default="000001.SZ", help="交易标的如 --symbols 000001.SZ",)
@click.option(
    "--start", "start_date", default=None, help="开始日期 YYYY-MM-DD (回测必填)"
)
@click.option("--end", "end_date", default=None, help="结束日期 YYYY-MM-DD (回测必填)")
@click.option("--days", default=365, type=int, help="历史数据天数 (analyze)")
@click.option(
    "--source",
    default="baostock",
    type=click.Choice(["tushare", "akshare", "baostock"]),
    help="数据源",
)
@click.option("--interval", default=60, type=int, help="检查间隔秒数 (live)")
@click.option("--notify/--no-notify", default=True, help="是否启用通知 (live)")
@click.option(
    "-o", "--output", "output_dir", default="output", type=click.Path(), help="输出目录"
)
@click.option(
    "--initial-capital", default=1000000, type=float, help="初始资金 (backtest)"
)
@click.option("--dry-run", is_flag=True, help="试运行，不执行实际操作")
@click.option("--list", "list_strategies", is_flag=True, help="列出所有可用策略")
@click.pass_context
def strategy_cmd(
    ctx,
    strategy,
    strategy_config,
    sys_config_path,
    mode,
    symbol,
    start_date,
    end_date,
    days,
    source,
    interval,
    notify,
    output_dir,
    initial_capital,
    dry_run,
    list_strategies,
):
    """
    统一策略运行入口

    \b
    每次运行一个策略：
      -s 策略名 --strategy-config 配置路径

    \b
    示例:
      # 单策略分析
      strategy -s aaa --strategy-config data/strategies/aaa.yaml -m analyze --symbols 000001.SZ

    \b
      # 单策略回测
      strategy --sys-config config/system.yaml -s aaa --strategy-config data/strategies/aaa.yaml -m backtest --start 2024-01-01 --end 2024-12-31
    """
    try:
        from src.config.base import load_config
        from src.config.schema import Config
        from src.runner.application import ApplicationRunner
        from .execution_modes import create_mode

        # 加载系统配置以获取日志配置
        sys_config = load_config(Config, sys_config_path)

        # 初始化日志系统
        from src.utils.logging_config import setup_logging

        # CLI 参数优先级高于配置文件
        log_level = (
            "DEBUG" if ctx.obj.get("verbose", False) else str(sys_config.log.level)
        )

        setup_logging(
            log_dir=sys_config.log.dir,
            level=log_level,
            console_output=sys_config.log.console,
            backup_count=sys_config.log.backup_count,
        )

        logger.info(f"CLI 启动，模式: {mode}")

        # 加载策略配置
        config = load_config(Config, strategy_config)

        if dry_run:
            click.echo(f"\n[试运行] 模式={mode}, 策略={strategy}, 配置={strategy_config}, 标的={symbol}")
            return

        # 创建 Runner 和 CommandMode
        runner = ApplicationRunner(config=config)
        cmd_mode = create_mode("command", runner=runner)

        # 调用统一的 run 命令
        result = cmd_mode.execute(
            "run",
            None,  # args 参数
            mode=mode,
            symbol=[symbol],
            strategy=strategy,
            strategy_config=strategy_config,
            start_date=start_date,
            end_date=end_date,
            days=days,
            source=source,
            interval=interval,
            initial_capital=initial_capital,
            notify=notify,
        )

        if not result.success:
            click.echo(f"执行失败: {result.error}", err=True)
        elif result.message:
            click.echo(f"{result.message}")
        elif result.data:
            _print_result(mode, result.data, output_dir)

    except Exception as e:
        click.echo(f"执行失败: {e}", err=True)
        if ctx.obj.get("verbose"):
            import traceback

            traceback.print_exc()
        sys.exit(1)


def _print_result(mode: str, data, output_dir: str = None):
    """格式化输出结果"""
    if mode == "analyze":
        # 分析结果
        if isinstance(data, list):
            for item in data:
                click.echo(f"\n股票: {item.get('symbol')}")
                click.echo(f"  状态: {item.get('status')}")
                click.echo(f"  建议: {item.get('action')}")
        else:
            click.echo(data)

    elif mode == "backtest":
        # 回测结果
        if isinstance(data, dict):
            click.echo("\n" + "=" * 50)
            click.echo("回测结果")
            click.echo("=" * 50)
            click.echo(f"总收益率: {data.get('total_return', 0):.2%}")
            click.echo(f"年化收益: {data.get('annual_return', 0):.2%}")
            click.echo(f"最大回撤: {data.get('max_drawdown', 0):.2%}")
            click.echo(f"夏普比率: {data.get('sharpe_ratio', 0):.2f}")
            click.echo(f"交易次数: {data.get('trade_count', 0)}")
            click.echo(f"胜率: {data.get('win_rate', 0):.2%}")

    else:
        click.echo(data)


# ============= run 命令组 (原有，保留) =============


@cli.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    default="data/strategies/aaa.yaml",
    type=click.Path(),
    help="策略配置文件路径",
)
@click.option("-s", "--symbols", default=None, help="交易标的，逗号分隔")
@click.option(
    "-m",
    "--mode",
    default="live",
    type=click.Choice(["live", "simulation"]),
    help="运行模式",
)
@click.option("--dry-run", is_flag=True, help="试运行模式")
@click.pass_context
def run(ctx, config_path, symbols, mode, dry_run):
    """启动实时监控系统"""
    click.echo("=" * 50)
    click.echo("MACD 量化交易系统")
    click.echo("=" * 50)

    try:
        from src.config.base import load_config
        from src.config.schema import Config
        from src.runner.application import ApplicationRunner
        from .execution_modes import create_mode

        # 加载配置
        config = load_config(Config, config_path)
        click.echo(f"加载配置: {config_path}")

        # 获取交易标的
        symbol_list = (
            [s.strip() for s in symbols.split(",")] if symbols else ["000001.SZ"]
        )
        click.echo(f"交易标的: {symbol_list}")
        click.echo(f"交易模式: {mode}")

        if dry_run:
            click.echo("[试运行模式] 不执行实际交易")
            return

        # 创建 Runner 和 CommandMode
        params = {
            "mode": mode,
            "symbols": symbol_list,
            "verbose": ctx.obj.get("verbose", False),
        }
        runner = ApplicationRunner(config=config, params=params)

        click.echo("\n启动交易引擎...")
        runner.start(mode)

    except ImportError as e:
        click.echo(f"模块导入失败: {e}", err=True)
        click.echo("请确保已安装所有依赖: pip install -r requirements.txt", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"启动失败: {e}", err=True)
        if ctx.obj.get("verbose"):
            import traceback

            traceback.print_exc()
        sys.exit(1)


# ============= data 命令组 =============


@cli.group()
def data():
    """数据管理命令"""
    pass


@data.command("sync")
@click.option("--symbols", required=True, help="股票代码，逗号分隔")
@click.option("--days", default=365, type=int, help="同步天数")
@click.option("--start", "start_date", default=None, help="开始日期 (YYYY-MM-DD)")
@click.option("--end", "end_date", default=None, help="结束日期 (YYYY-MM-DD)")
@click.option(
    "--source",
    default="baostock",
    type=click.Choice(["tushare", "akshare", "baostock"]),
    help="数据源",
)
@click.option(
    "--freq",
    default="daily",
    type=click.Choice(["daily", "5min", "15min", "30min", "60min"]),
    help="数据频率: daily(日线) / 5min / 15min / 30min / 60min",
)
@click.pass_context
def data_sync(ctx, symbols, days, start_date, end_date, source, freq):
    """同步行情数据（支持日线和分时数据）"""
    click.echo("=" * 50)
    click.echo("数据同步")
    click.echo("=" * 50)

    try:
        from src.config.base import load_config
        from src.config.schema import Config
        from src.runner.application import ApplicationRunner
        from .execution_modes import create_mode

        symbol_list = [s.strip() for s in symbols.split(",")]

        # 分时数据默认只同步 5 天
        default_days = days if freq == "daily" else min(days, 5)

        if start_date:
            start = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start = datetime.now() - timedelta(days=default_days)

        if end_date:
            end = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            end = datetime.now()

        click.echo(f"数据源: {source}")
        click.echo(f"频率:   {freq}")
        click.echo(f"股票:   {symbol_list}")
        click.echo(f"日期范围: {start.date()} ~ {end.date()}")

        # 直接调用数据服务
        config = load_config(Config)
        runner = ApplicationRunner(config=config)
        cmd_mode = create_mode("command", runner=runner)

        result = cmd_mode.execute(
            "sync",
            None,  # args 参数
            symbols=symbol_list,
            frequency=freq,
            days=days,
        )

        if result.success:
            click.echo(f"\n{result.message}")
            if result.data:
                for symbol, info in result.data.items():
                    if "error" in info:
                        click.echo(f"  {symbol}: 失败 - {info['error']}")
                    else:
                        click.echo(f"  {symbol}: 成功")
        else:
            click.echo(f"同步失败: {result.error}", err=True)

    except ImportError as e:
        click.echo(f"模块导入失败: {e}", err=True)
        click.echo("请安装数据源依赖:", err=True)
        click.echo("  - Tushare: pip install tushare", err=True)
        click.echo("  - AKShare: pip install akshare (需要 Python 3.8+)", err=True)
        click.echo("  - BaoStock: pip install baostock (推荐，免费)", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"同步失败: {e}", err=True)
        if ctx.obj.get("verbose"):
            import traceback

            traceback.print_exc()
        sys.exit(1)


@data.command("info")
@click.option("--symbol", default=None, help="股票代码（可选）")
@click.pass_context
def data_info(ctx, symbol):
    """查看数据信息"""
    try:
        from src.config.base import load_config
        from src.config.schema import Config
        from src.runner.application import ApplicationRunner
        from .execution_modes import create_mode

        # 创建 Runner 和 CommandMode
        config = load_config(Config)
        runner = ApplicationRunner(config=config)
        cmd_mode = create_mode("command", runner=runner)

        # 执行查询
        result = cmd_mode.execute("data", None, symbol=symbol)

        if result.success and result.data:
            # 日线数据统计
            if "daily" in result.data:
                stats = result.data["daily"]
                click.echo("=" * 60)
                click.echo("日线数据")
                click.echo("=" * 60)
                click.echo(
                    f"{'股票代码':<15} {'数据条数':<10} {'开始日期':<12} {'结束日期':<12}"
                )
                click.echo("-" * 60)
                for item in stats:
                    click.echo(
                        f"{item['symbol']:<15} "
                        f"{item['count']:<10} "
                        f"{item['start_date']:<12} "
                        f"{item['end_date']:<12}"
                    )

            # 分时数据统计
            if "minute" in result.data:
                minute_stats = result.data["minute"]
                click.echo("")
                click.echo("=" * 70)
                click.echo("分时数据")
                click.echo("=" * 70)
                click.echo(
                    f"{'股票代码':<12} {'频率':<8} {'数据条数':<10} {'开始时间':<20} {'结束时间':<20}"
                )
                click.echo("-" * 70)
                for item in minute_stats:
                    click.echo(
                        f"{item['symbol']:<12} "
                        f"{item['frequency']:<8} "
                        f"{item['count']:<10} "
                        f"{item['start_time']:<20} "
                        f"{item['end_time']:<20}"
                    )

            if not result.data:
                click.echo("暂无数据")
        else:
            click.echo(f"查询失败: {result.error}", err=True)

    except Exception as e:
        click.echo(f"查询失败: {e}", err=True)
        sys.exit(1)


@data.command("clean")
@click.option("--symbol", default=None, help="股票代码（可选）")
@click.option("--before", "before_date", default=None, help="删除此日期之前的数据")
@click.option("--all", "clean_all", is_flag=True, help="清理所有数据")
@click.confirmation_option(prompt="确认清理数据?")
@click.pass_context
def data_clean(ctx, symbol, before_date, clean_all):
    """清理数据缓存"""
    try:
        from src.data.market import MarketDataService, DataSource

        service = MarketDataService(source=DataSource.LOCAL)

        before = None
        if before_date:
            before = datetime.strptime(before_date, "%Y-%m-%d")

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


@report.command("positions")
@click.option(
    "-c",
    "--config",
    "config_path",
    default="data/strategies/aaa.yaml",
    type=click.Path(),
    help="策略配置文件路径",
)
@click.pass_context
def report_positions(ctx, config_path):
    """查看当前持仓"""
    try:
        from src.config.base import load_config
        from src.config.schema import Config
        from src.data.portfolio import PortfolioManager

        config = load_config(Config, config_path)
        manager = PortfolioManager(config.data.db_path)

        positions = manager.get_positions()

        if not positions:
            click.echo("当前无持仓")
            return

        click.echo("=" * 70)
        click.echo(
            f"{'股票代码':<12} {'数量':<10} {'成本价':<10} {'现价':<10} {'盈亏':<10} {'盈亏率':<10}"
        )
        click.echo("=" * 70)

        total_value = 0
        total_pnl = 0

        for pos in positions:
            pnl = (pos.current_price - pos.cost_basis) * pos.quantity
            pnl_pct = (
                (pos.current_price / pos.cost_basis - 1) if pos.cost_basis > 0 else 0
            )
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
        if ctx.obj.get("verbose"):
            import traceback

            traceback.print_exc()
        sys.exit(1)


@report.command("trades")
@click.option("--days", default=7, type=int, help="查询天数")
@click.option("--symbol", default=None, help="股票代码（可选）")
@click.option(
    "-o", "--output", "output_file", default=None, type=click.Path(), help="导出到文件"
)
@click.pass_context
def report_trades(ctx, days, symbol, output_file):
    """查看交易记录"""
    try:
        from src.config.base import load_config
        from src.config.schema import Config
        from src.data.portfolio import PortfolioManager

        config = load_config(Config)
        manager = PortfolioManager(config.data.db_path)

        start_date = datetime.now() - timedelta(days=days)
        trades = manager.get_trades(start_date=start_date, symbol=symbol)

        if not trades:
            click.echo(f"最近 {days} 天无交易记录")
            return

        click.echo("=" * 80)
        click.echo(
            f"{'日期':<12} {'股票':<12} {'方向':<6} {'数量':<10} {'价格':<10} {'金额':<12}"
        )
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


@report.command("daily")
@click.option("--start", "start_date", required=True, help="开始日期 (YYYY-MM-DD)")
@click.option("--end", "end_date", default=None, help="结束日期 (YYYY-MM-DD)")
@click.pass_context
def report_daily(ctx, start_date, end_date):
    """查看每日汇总"""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()

        from src.config.base import load_config
        from src.config.schema import Config
        from src.data.portfolio import PortfolioManager

        config = load_config(Config)
        manager = PortfolioManager(config.data.db_path)

        daily_stats = manager.get_daily_stats(start, end)

        if not daily_stats:
            click.echo("无数据")
            return

        click.echo("=" * 70)
        click.echo(
            f"{'日期':<12} {'净值':<12} {'日收益':<10} {'日收益率':<10} {'累计收益率':<10}"
        )
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


@cli.command("config")
@click.option("--show", is_flag=True, help="显示当前配置")
@click.option("--init", is_flag=True, help="生成默认配置文件")
@click.option(
    "-o",
    "--output",
    "output_path",
    default="data/strategies/default.yaml",
    type=click.Path(),
    help="输出路径",
)
@click.pass_context
def config_cmd(ctx, show, init, output_path):
    """配置管理"""
    try:
        from src.config.base import load_config
        from src.config.schema import Config

        if init:
            default_content = """# 默认策略配置
data:
  source: local
  db_path: data/market.db
"""
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(default_content)
            click.echo(f"配置文件已生成: {output_path}")

        elif show:
            config = load_config(Config, output_path)
            click.echo("当前配置:")
            click.echo("-" * 40)
            click.echo(f"数据源: {config.data.source}")
            click.echo(f"数据库路径: {config.data.db_path}")
            click.echo(f"日志级别: {config.log.level}")
            click.echo(f"API端口: {config.api.port}")

        else:
            click.echo("使用 --show 查看配置或 --init 生成默认配置")

    except Exception as e:
        click.echo(f"操作失败: {e}", err=True)
        sys.exit(1)


# ============= client 命令 (交互式客户端) =============


@cli.command("client")
@click.option("--server", default="localhost:8000", help="API 服务地址 (host:port)")
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
      live          实时运行管理 (start/stop/status)
      status        查看运行状态
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
    # 使用新的 ExecutionMode 架构
    from .execution_modes import create_mode

    mode = create_mode("client", server=server)
    mode.start()


# ============= serve 命令 (HTTP API 服务) =============


@cli.command("serve")
@click.option("-H", "--host", default="0.0.0.0", help="监听地址")
@click.option("-p", "--port", default=8000, type=int, help="监听端口")
@click.option(
    "--reload", "auto_reload", is_flag=True, help="开发模式，代码变更自动重载"
)
@click.option("--workers", default=1, type=int, help="工作进程数")
@click.option(
    "--log-level",
    "log_level",
    default="info",
    type=click.Choice(["debug", "info", "warning", "error"]),
    help="日志级别",
)
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


@cli.command("info")
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
        ("pandas", "pandas"),
        ("numpy", "numpy"),
        ("click", "click"),
        ("yaml", "pyyaml"),
        ("tushare", "tushare"),
        ("akshare", "akshare"),
    ]

    for module, package in dependencies:
        try:
            __import__(module)
            click.echo(f"  + {package}")
        except ImportError:
            click.echo(f"  - {package} (未安装)")


# ============= interactive 命令 (交互式模式) =============


@cli.command("interactive")
@click.pass_context
def interactive(ctx):
    """交互式模式：在终端中持续执行命令

    \b
    内置命令:
      strategies            列出所有可用策略
      list-strategy-files   列出策略文件
      create-strategy       创建新策略模板
      delete-strategy       软删除策略
      reload-strategies     重新加载策略
      analyze               分析标的 (使用参数: <symbol> --strategy <name> --days <n> --source <src>)
      backtest              运行回测 (使用参数: <symbol> --start <date> --end <date> --strategy <name>)
      help                  显示帮助
      clear                 清屏
      exit                  退出交互模式

    \b
    示例:
      analyze 000001.SZ --strategy macd --days 30 --source baostock
      backtest 000001.SZ --start 2024-01-01 --end 2024-12-31 --strategy rsi
      create-strategy my_strategy
      delete-strategy my_strategy

    \b
    退出: 输入 'exit' 或按 Ctrl+D
    """
    # 初始化日志系统
    from src.config.base import load_config
    from src.config.schema import Config
    from src.utils.logging_config import setup_logging

    sys_config = load_config(Config)
    setup_logging(
        log_dir=sys_config.log.dir,
        level="DEBUG" if ctx.obj.get("verbose", False) else str(sys_config.log.level),
        console_output=sys_config.log.console,
        backup_count=sys_config.log.backup_count,
    )

    # 使用新的 ExecutionMode 架构
    from .execution_modes import create_mode

    mode = create_mode("interactive")
    mode.start()


if __name__ == "__main__":
    cli()
