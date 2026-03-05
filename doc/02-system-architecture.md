# 系统架构设计（命令行无头模式）

## 1. 整体架构

```
┌────────────────────────────────────────────────────────────────────┐
│                          命令行接口层 (CLI)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   策略运行    │  │   回测命令    │  │  数据管理    │              │
│  │  run/start   │  │   backtest   │  │  data sync   │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│                          核心服务层 (Core)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   策略引擎    │  │   回测引擎    │  │  交易执行器   │              │
│  │   Strategy   │  │  Backtest    │  │   Executor   │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   风控模块    │  │   调度器      │  │  事件总线    │              │
│  │    Risk      │  │  Scheduler   │  │  EventBus    │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│                          数据服务层 (Data)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   行情服务    │  │   指标计算    │  │  持仓管理    │              │
│  │  MarketData  │  │  Indicator   │  │  Portfolio   │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│                          基础设施层 (Infra)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   SQLite     │  │   日志系统    │  │  配置管理    │              │
│  │  (轻量存储)   │  │   Logging    │  │   Config    │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│                          外部接口层 (External)                      │
│  ┌──────────────┐  ┌──────────────┐                                │
│  │  行情数据源   │  │   券商 API   │                                │
│  │ Tushare/AKS  │  │  交易接口    │                                │
│  └──────────────┘  └──────────────┘                                │
└────────────────────────────────────────────────────────────────────┘
```

## 2. 项目目录结构

```
quant-macd/
├── cli/                      # 命令行入口
│   ├── __init__.py
│   ├── main.py               # CLI 主入口
│   ├── commands/
│   │   ├── run.py            # 运行策略
│   │   ├── backtest.py       # 回测命令
│   │   ├── data.py           # 数据管理
│   │   └── report.py         # 报告生成
│   └── utils.py
│
├── core/                     # 核心模块
│   ├── __init__.py
│   ├── engine.py             # 策略引擎
│   ├── executor.py           # 交易执行器
│   ├── scheduler.py          # 调度器
│   └── event_bus.py          # 事件总线
│
├── strategy/                 # 策略实现
│   ├── __init__.py
│   ├── base.py               # 策略基类
│   └── macd.py               # MACD 策略
│
├── risk/                     # 风控模块
│   ├── __init__.py
│   └── manager.py
│
├── data/                     # 数据服务
│   ├── __init__.py
│   ├── market.py             # 行情数据
│   ├── indicator.py          # 指标计算
│   └── portfolio.py          # 持仓管理
│
├── broker/                   # 券商接口
│   ├── __init__.py
│   ├── base.py               # 接口基类
│   └── simulator.py          # 模拟交易
│
├── backtest/                 # 回测框架
│   ├── __init__.py
│   ├── engine.py
│   └── metrics.py
│
├── config/                   # 配置文件
│   ├── default.yaml
│   └── strategy/
│       └── macd.yaml
│
├── logs/                     # 日志目录
├── data/                     # 数据存储
│   └── market.db             # SQLite 数据库
│
├── main.py                   # 程序入口
├── requirements.txt
└── README.md
```

## 3. 命令行接口设计 (CLI)

### 3.1 CLI 主入口

```python
# cli/main.py

import click
import logging
from pathlib import Path
from datetime import datetime

from cli.commands import run, backtest, data, report

@click.group()
@click.option('--config', '-c', type=click.Path(), default='config/default.yaml',
              help='配置文件路径')
@click.option('--log-level', '-l', 
              type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
              default='INFO', help='日志级别')
@click.option('--log-file', type=click.Path(), help='日志文件路径')
@click.pass_context
def cli(ctx, config, log_level, log_file):
    """
    MACD 量化交易系统 - 命令行工具
    
    使用示例:
    
        # 运行策略（实时模式）
        python main.py run --symbols 000001.SZ,600000.SH
        
        # 运行回测
        python main.py backtest --start 2024-01-01 --end 2024-12-31
        
        # 同步数据
        python main.py data sync --symbols 000001.SZ
    """
    ctx.ensure_object(dict)
    ctx.obj['config'] = config
    
    # 配置日志
    setup_logging(log_level, log_file)

def setup_logging(level: str, log_file: str = None):
    """配置日志系统"""
    handlers = [logging.StreamHandler()]
    
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=getattr(logging, level),
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers
    )

# 注册子命令
cli.add_command(run.run)
cli.add_command(backtest.backtest)
cli.add_command(data.data)
cli.add_command(report.report)

if __name__ == '__main__':
    cli()
```

### 3.2 策略运行命令

```python
# cli/commands/run.py

import click
import signal
import sys
from typing import List

@click.command()
@click.option('--symbols', '-s', required=True, help='股票代码，逗号分隔')
@click.option('--strategy', default='macd', help='策略名称')
@click.option('--mode', type=click.Choice(['live', 'paper']), default='paper',
              help='运行模式: live=实盘, paper=模拟')
@click.option('--capital', default=100000.0, help='初始资金')
@click.option('--interval', default=60, help='行情轮询间隔（秒）')
@click.option('--daemon', '-d', is_flag=True, help='后台运行模式')
@click.pass_context
def run(ctx, symbols: str, strategy: str, mode: str, capital: float, 
        interval: int, daemon: bool):
    """
    运行交易策略
    
    示例:
    
        # 模拟交易
        python main.py run -s 000001.SZ,600000.SH --mode paper
        
        # 实盘交易（需要配置券商 API）
        python main.py run -s 000001.SZ --mode live
        
        # 后台运行
        python main.py run -s 000001.SZ -d
    """
    from core.engine import TradingEngine
    from config.loader import load_config
    
    config = load_config(ctx.obj['config'])
    symbol_list = [s.strip() for s in symbols.split(',')]
    
    click.echo(f"🚀 启动交易系统")
    click.echo(f"   策略: {strategy}")
    click.echo(f"   标的: {symbol_list}")
    click.echo(f"   模式: {mode}")
    click.echo(f"   资金: {capital:,.0f}")
    
    engine = TradingEngine(
        config=config,
        symbols=symbol_list,
        strategy_name=strategy,
        mode=mode,
        initial_capital=capital,
        poll_interval=interval
    )
    
    # 优雅退出
    def signal_handler(sig, frame):
        click.echo("\n⏹️  收到停止信号，正在安全退出...")
        engine.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        engine.start()
    except KeyboardInterrupt:
        engine.stop()
```

### 3.3 回测命令

```python
# cli/commands/backtest.py

import click
from datetime import datetime
from pathlib import Path

@click.command()
@click.option('--symbols', '-s', required=True, help='股票代码，逗号分隔')
@click.option('--strategy', default='macd', help='策略名称')
@click.option('--start', required=True, help='开始日期 (YYYY-MM-DD)')
@click.option('--end', required=True, help='结束日期 (YYYY-MM-DD)')
@click.option('--capital', default=100000.0, help='初始资金')
@click.option('--commission', default=0.0003, help='手续费率')
@click.option('--slippage', default=0.001, help='滑点')
@click.option('--output', '-o', type=click.Path(), help='报告输出路径')
@click.option('--format', 'output_format', 
              type=click.Choice(['text', 'json', 'html']),
              default='text', help='输出格式')
@click.pass_context
def backtest(ctx, symbols: str, strategy: str, start: str, end: str,
             capital: float, commission: float, slippage: float,
             output: str, output_format: str):
    """
    运行策略回测
    
    示例:
    
        # 基础回测
        python main.py backtest -s 000001.SZ --start 2024-01-01 --end 2024-12-31
        
        # 多标的回测，输出 JSON
        python main.py backtest -s 000001.SZ,600000.SH \\
            --start 2024-01-01 --end 2024-12-31 \\
            --format json -o results/backtest.json
        
        # 自定义参数
        python main.py backtest -s 000001.SZ \\
            --start 2024-01-01 --end 2024-12-31 \\
            --capital 500000 --commission 0.0005
    """
    from backtest.engine import BacktestEngine
    from config.loader import load_config
    
    config = load_config(ctx.obj['config'])
    symbol_list = [s.strip() for s in symbols.split(',')]
    
    start_date = datetime.strptime(start, '%Y-%m-%d')
    end_date = datetime.strptime(end, '%Y-%m-%d')
    
    click.echo(f"📊 开始回测")
    click.echo(f"   策略: {strategy}")
    click.echo(f"   标的: {symbol_list}")
    click.echo(f"   区间: {start} ~ {end}")
    click.echo(f"   资金: {capital:,.0f}")
    click.echo("")
    
    engine = BacktestEngine(
        config=config,
        symbols=symbol_list,
        strategy_name=strategy,
        start_date=start_date,
        end_date=end_date,
        initial_capital=capital,
        commission=commission,
        slippage=slippage
    )
    
    # 运行回测
    with click.progressbar(length=100, label='回测进度') as bar:
        result = engine.run(progress_callback=lambda p: bar.update(p))
    
    # 输出结果
    click.echo("")
    display_result(result, output_format, output)

def display_result(result, format: str, output_path: str = None):
    """显示/保存回测结果"""
    
    if format == 'text':
        output = format_text_report(result)
        click.echo(output)
        
    elif format == 'json':
        import json
        output = json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
        
    elif format == 'html':
        output = format_html_report(result)
    
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(output, encoding='utf-8')
        click.echo(f"📁 报告已保存: {output_path}")

def format_text_report(result) -> str:
    """格式化文本报告"""
    return f"""
╔══════════════════════════════════════════════════════════════╗
║                        回测结果报告                           ║
╠══════════════════════════════════════════════════════════════╣
║  📈 收益指标                                                  ║
║  ├─ 总收益率:      {result.total_return:>10.2%}                      ║
║  ├─ 年化收益率:    {result.annual_return:>10.2%}                      ║
║  ├─ 基准收益率:    {result.benchmark_return:>10.2%}                      ║
║  └─ 超额收益:      {result.alpha:>10.2%}                      ║
╠══════════════════════════════════════════════════════════════╣
║  📉 风险指标                                                  ║
║  ├─ 最大回撤:      {result.max_drawdown:>10.2%}                      ║
║  ├─ 波动率:        {result.volatility:>10.2%}                      ║
║  └─ 下行波动率:    {result.downside_vol:>10.2%}                      ║
╠══════════════════════════════════════════════════════════════╣
║  📊 风险调整收益                                              ║
║  ├─ 夏普比率:      {result.sharpe_ratio:>10.2f}                       ║
║  ├─ 索提诺比率:    {result.sortino_ratio:>10.2f}                       ║
║  └─ 卡玛比率:      {result.calmar_ratio:>10.2f}                       ║
╠══════════════════════════════════════════════════════════════╣
║  🔄 交易统计                                                  ║
║  ├─ 交易次数:      {result.trade_count:>10}                       ║
║  ├─ 胜率:          {result.win_rate:>10.2%}                      ║
║  ├─ 盈亏比:        {result.profit_factor:>10.2f}                       ║
║  └─ 平均持仓天数:  {result.avg_holding_days:>10.1f}                       ║
╚══════════════════════════════════════════════════════════════╝
"""
```

### 3.4 数据管理命令

```python
# cli/commands/data.py

import click
from datetime import datetime, timedelta

@click.group()
def data():
    """数据管理命令"""
    pass

@data.command()
@click.option('--symbols', '-s', help='股票代码（为空则同步全部）')
@click.option('--start', help='开始日期')
@click.option('--end', help='结束日期')
@click.option('--source', default='tushare', 
              type=click.Choice(['tushare', 'akshare']),
              help='数据源')
@click.pass_context
def sync(ctx, symbols: str, start: str, end: str, source: str):
    """
    同步行情数据
    
    示例:
    
        # 同步指定股票最近一年数据
        python main.py data sync -s 000001.SZ,600000.SH
        
        # 同步指定日期范围
        python main.py data sync -s 000001.SZ --start 2020-01-01 --end 2024-12-31
        
        # 使用 akshare 数据源
        python main.py data sync -s 000001.SZ --source akshare
    """
    from data.market import MarketDataService
    from config.loader import load_config
    
    config = load_config(ctx.obj['config'])
    
    symbol_list = None
    if symbols:
        symbol_list = [s.strip() for s in symbols.split(',')]
    
    start_date = datetime.strptime(start, '%Y-%m-%d') if start else datetime.now() - timedelta(days=365)
    end_date = datetime.strptime(end, '%Y-%m-%d') if end else datetime.now()
    
    service = MarketDataService(config, source=source)
    
    click.echo(f"📥 开始同步数据")
    click.echo(f"   数据源: {source}")
    click.echo(f"   区间: {start_date.date()} ~ {end_date.date()}")
    
    with click.progressbar(symbol_list or ['全部'], label='同步进度') as bar:
        for symbol in bar:
            service.sync(symbol if symbol != '全部' else None, start_date, end_date)
    
    click.echo("✅ 数据同步完成")

@data.command()
@click.option('--symbols', '-s', help='股票代码')
def info(symbols: str):
    """
    查看数据状态
    
    示例:
    
        # 查看所有数据状态
        python main.py data info
        
        # 查看指定股票
        python main.py data info -s 000001.SZ
    """
    from data.market import MarketDataService
    
    service = MarketDataService()
    stats = service.get_data_stats(symbols)
    
    click.echo("\n📊 数据状态:")
    click.echo("-" * 60)
    click.echo(f"{'股票代码':<15} {'数据条数':>10} {'起始日期':>12} {'结束日期':>12}")
    click.echo("-" * 60)
    
    for stat in stats:
        click.echo(
            f"{stat['symbol']:<15} "
            f"{stat['count']:>10} "
            f"{stat['start_date']:>12} "
            f"{stat['end_date']:>12}"
        )

@data.command()
@click.option('--symbols', '-s', help='股票代码')
@click.option('--before', help='删除此日期之前的数据')
@click.confirmation_option(prompt='确定要删除数据吗？')
def clean(symbols: str, before: str):
    """
    清理数据
    
    示例:
    
        # 清理指定股票数据
        python main.py data clean -s 000001.SZ
        
        # 清理旧数据
        python main.py data clean --before 2020-01-01
    """
    from data.market import MarketDataService
    
    service = MarketDataService()
    
    before_date = datetime.strptime(before, '%Y-%m-%d') if before else None
    count = service.clean(symbols, before_date)
    
    click.echo(f"✅ 已删除 {count} 条数据")
```

### 3.5 报告命令

```python
# cli/commands/report.py

import click
from datetime import datetime

@click.group()
def report():
    """报告生成命令"""
    pass

@report.command()
@click.option('--period', default='daily',
              type=click.Choice(['daily', 'weekly', 'monthly']),
              help='报告周期')
@click.option('--date', help='报告日期 (默认今天)')
@click.option('--format', 'output_format',
              type=click.Choice(['text', 'json', 'markdown']),
              default='text', help='输出格式')
@click.option('--output', '-o', type=click.Path(), help='输出文件路径')
def generate(period: str, date: str, output_format: str, output: str):
    """
    生成交易报告
    
    示例:
    
        # 生成今日报告
        python main.py report generate
        
        # 生成周报
        python main.py report generate --period weekly
        
        # 输出 Markdown 格式
        python main.py report generate --format markdown -o reports/daily.md
    """
    from core.reporter import ReportGenerator
    
    target_date = datetime.strptime(date, '%Y-%m-%d') if date else datetime.now()
    
    generator = ReportGenerator()
    report_data = generator.generate(period, target_date)
    
    if output_format == 'text':
        output_content = format_text_report(report_data)
        click.echo(output_content)
    elif output_format == 'json':
        import json
        output_content = json.dumps(report_data, indent=2, ensure_ascii=False)
    elif output_format == 'markdown':
        output_content = format_markdown_report(report_data)
    
    if output:
        from pathlib import Path
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(output_content, encoding='utf-8')
        click.echo(f"📁 报告已保存: {output}")

@report.command()
def positions():
    """
    显示当前持仓
    
    示例:
    
        python main.py report positions
    """
    from data.portfolio import PortfolioManager
    
    pm = PortfolioManager()
    positions = pm.get_positions()
    
    click.echo("\n📊 当前持仓:")
    click.echo("-" * 80)
    click.echo(
        f"{'股票代码':<12} {'股票名称':<10} {'持仓数量':>10} "
        f"{'成本价':>10} {'现价':>10} {'盈亏':>10} {'盈亏%':>8}"
    )
    click.echo("-" * 80)
    
    total_value = 0
    total_pnl = 0
    
    for pos in positions:
        pnl = (pos['current_price'] - pos['avg_cost']) * pos['quantity']
        pnl_pct = (pos['current_price'] / pos['avg_cost'] - 1) * 100
        value = pos['current_price'] * pos['quantity']
        
        total_value += value
        total_pnl += pnl
        
        click.echo(
            f"{pos['symbol']:<12} {pos['name']:<10} {pos['quantity']:>10} "
            f"{pos['avg_cost']:>10.2f} {pos['current_price']:>10.2f} "
            f"{pnl:>10.2f} {pnl_pct:>7.2f}%"
        )
    
    click.echo("-" * 80)
    click.echo(f"{'总计':<22} {'':>10} {'':>10} {total_value:>10.2f} {total_pnl:>10.2f}")

@report.command()
@click.option('--limit', default=20, help='显示条数')
def trades(limit: int):
    """
    显示交易记录
    
    示例:
    
        python main.py report trades --limit 50
    """
    from data.portfolio import PortfolioManager
    
    pm = PortfolioManager()
    trade_list = pm.get_trades(limit=limit)
    
    click.echo("\n📋 交易记录:")
    click.echo("-" * 90)
    click.echo(
        f"{'时间':<20} {'股票':<12} {'方向':<6} "
        f"{'数量':>8} {'价格':>10} {'金额':>12} {'策略':<10}"
    )
    click.echo("-" * 90)
    
    for trade in trade_list:
        direction = '买入' if trade['side'] == 'buy' else '卖出'
        amount = trade['quantity'] * trade['price']
        
        click.echo(
            f"{trade['timestamp']:<20} {trade['symbol']:<12} {direction:<6} "
            f"{trade['quantity']:>8} {trade['price']:>10.2f} {amount:>12.2f} "
            f"{trade['strategy']:<10}"
        )
```

## 4. 核心接口设计 (Core API)

### 4.1 策略引擎接口

```python
# core/engine.py

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class EngineState(Enum):
    """引擎状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"

@dataclass
class EngineConfig:
    """引擎配置"""
    symbols: List[str]
    strategy_name: str
    mode: str = "paper"  # paper / live
    initial_capital: float = 100000.0
    poll_interval: int = 60  # 秒
    max_positions: int = 10
    enable_risk_check: bool = True

class TradingEngine:
    """交易引擎"""
    
    def __init__(self, config: EngineConfig):
        self.config = config
        self.state = EngineState.IDLE
        
        self._strategy = None
        self._executor = None
        self._risk_manager = None
        self._data_service = None
        self._scheduler = None
        
        self._event_handlers: Dict[str, List[Callable]] = {}
        
    def start(self) -> None:
        """启动引擎"""
        if self.state == EngineState.RUNNING:
            logger.warning("引擎已在运行中")
            return
        
        logger.info("正在启动交易引擎...")
        
        try:
            self._initialize_components()
            self.state = EngineState.RUNNING
            self._emit('engine.started', {'timestamp': datetime.now()})
            
            logger.info("交易引擎启动成功")
            self._run_loop()
            
        except Exception as e:
            self.state = EngineState.ERROR
            logger.error(f"引擎启动失败: {e}")
            raise
    
    def stop(self) -> None:
        """停止引擎"""
        if self.state != EngineState.RUNNING:
            return
        
        logger.info("正在停止交易引擎...")
        self.state = EngineState.STOPPED
        
        # 清理资源
        if self._scheduler:
            self._scheduler.stop()
        
        self._emit('engine.stopped', {'timestamp': datetime.now()})
        logger.info("交易引擎已停止")
    
    def pause(self) -> None:
        """暂停引擎"""
        if self.state == EngineState.RUNNING:
            self.state = EngineState.PAUSED
            logger.info("交易引擎已暂停")
    
    def resume(self) -> None:
        """恢复引擎"""
        if self.state == EngineState.PAUSED:
            self.state = EngineState.RUNNING
            logger.info("交易引擎已恢复")
    
    def on(self, event: str, handler: Callable) -> None:
        """注册事件处理器"""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)
    
    def _emit(self, event: str, data: Dict) -> None:
        """触发事件"""
        handlers = self._event_handlers.get(event, [])
        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                logger.error(f"事件处理器异常: {event}, {e}")
    
    def _initialize_components(self) -> None:
        """初始化组件"""
        from strategy.loader import load_strategy
        from broker.simulator import SimulatedExecutor
        from broker.live import LiveExecutor
        from risk.manager import RiskManager
        from data.market import MarketDataService
        from core.scheduler import Scheduler
        
        # 加载策略
        self._strategy = load_strategy(self.config.strategy_name)
        
        # 初始化执行器
        if self.config.mode == 'paper':
            self._executor = SimulatedExecutor(self.config.initial_capital)
        else:
            self._executor = LiveExecutor()
        
        # 初始化风控
        self._risk_manager = RiskManager()
        
        # 初始化数据服务
        self._data_service = MarketDataService()
        
        # 初始化调度器
        self._scheduler = Scheduler(interval=self.config.poll_interval)
    
    def _run_loop(self) -> None:
        """主循环"""
        while self.state == EngineState.RUNNING:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"Tick 异常: {e}")
                self._emit('engine.error', {'error': str(e)})
            
            self._scheduler.wait()
    
    def _tick(self) -> None:
        """单次循环"""
        for symbol in self.config.symbols:
            # 获取行情
            data = self._data_service.get_latest(symbol)
            
            # 计算指标
            data = self._strategy.calculate_indicators(data)
            
            # 生成信号
            signal = self._strategy.generate_signal(data)
            
            if signal.signal_type != SignalType.HOLD:
                self._process_signal(signal)
    
    def _process_signal(self, signal) -> None:
        """处理交易信号"""
        logger.info(f"收到信号: {signal}")
        self._emit('signal.generated', {'signal': signal})
        
        # 风控检查
        portfolio = self._executor.get_portfolio()
        passed, reason = self._risk_manager.check_signal(signal, portfolio)
        
        if not passed:
            logger.warning(f"风控拦截: {reason}")
            self._emit('signal.rejected', {'signal': signal, 'reason': reason})
            return
        
        # 计算仓位
        position_size = self._risk_manager.calculate_position_size(
            signal, portfolio
        )
        
        # 生成订单
        order = self._create_order(signal, position_size)
        
        # 执行订单
        result = self._executor.submit_order(order)
        
        self._emit('order.executed', {'order': result})
        logger.info(f"订单执行完成: {result}")
```

### 4.2 策略接口

```python
# strategy/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import pandas as pd

class SignalType(Enum):
    """信号类型"""
    BUY = 1
    SELL = -1
    HOLD = 0

@dataclass
class Signal:
    """交易信号"""
    symbol: str
    signal_type: SignalType
    price: float
    timestamp: datetime
    strength: float = 1.0
    reason: str = ""
    metadata: Dict[str, Any] = None

class BaseStrategy(ABC):
    """策略基类 - 所有策略必须继承此类"""
    
    # 策略元信息
    name: str = "BaseStrategy"
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    
    def __init__(self, params: Dict[str, Any] = None):
        self.params = {**self.default_params(), **(params or {})}
        self._indicators = {}
    
    @classmethod
    def default_params(cls) -> Dict[str, Any]:
        """
        默认参数 - 子类可覆盖
        
        Returns:
            Dict[str, Any]: 参数字典
        """
        return {}
    
    @abstractmethod
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        计算技术指标
        
        Args:
            data: OHLCV 数据，包含 open/high/low/close/volume 列
        
        Returns:
            pd.DataFrame: 添加指标列后的数据
        """
        pass
    
    @abstractmethod
    def generate_signal(self, data: pd.DataFrame) -> Signal:
        """
        生成交易信号
        
        Args:
            data: 包含指标的 OHLCV 数据
        
        Returns:
            Signal: 交易信号
        """
        pass
    
    def validate_data(self, data: pd.DataFrame) -> bool:
        """验证数据有效性"""
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        return all(col in data.columns for col in required_columns)
    
    def on_start(self) -> None:
        """策略启动时回调"""
        pass
    
    def on_stop(self) -> None:
        """策略停止时回调"""
        pass
    
    def on_bar(self, bar: Dict) -> Optional[Signal]:
        """
        每根 K 线回调（可选实现）
        
        Args:
            bar: 当前 K 线数据
        
        Returns:
            Optional[Signal]: 交易信号
        """
        return None
    
    def get_indicator(self, name: str) -> Any:
        """获取已计算的指标"""
        return self._indicators.get(name)
    
    def set_indicator(self, name: str, value: Any) -> None:
        """设置指标值"""
        self._indicators[name] = value
```

### 4.3 执行器接口

```python
# broker/base.py

from abc import ABC, abstractmethod
from typing import Optional, List, Dict
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import uuid

class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"

class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

@dataclass
class Order:
    """订单对象"""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    order_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0
    filled_price: float = 0
    commission: float = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    message: str = ""

@dataclass
class Position:
    """持仓对象"""
    symbol: str
    quantity: float
    avg_cost: float
    current_price: float = 0
    unrealized_pnl: float = 0
    realized_pnl: float = 0

@dataclass 
class Portfolio:
    """组合对象"""
    cash: float
    total_value: float
    positions: Dict[str, Position] = field(default_factory=dict)
    daily_pnl: float = 0
    total_pnl: float = 0

class BaseExecutor(ABC):
    """执行器基类"""
    
    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        """
        提交订单
        
        Args:
            order: 订单对象
        
        Returns:
            Order: 更新后的订单（包含执行结果）
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        取消订单
        
        Args:
            order_id: 订单ID
        
        Returns:
            bool: 是否成功
        """
        pass
    
    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单状态"""
        pass
    
    @abstractmethod
    def get_orders(self, status: OrderStatus = None) -> List[Order]:
        """获取订单列表"""
        pass
    
    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓"""
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Position]:
        """获取所有持仓"""
        pass
    
    @abstractmethod
    def get_portfolio(self) -> Portfolio:
        """获取投资组合"""
        pass
```

### 4.4 风控接口

```python
# risk/manager.py

from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any
from dataclasses import dataclass

@dataclass
class RiskConfig:
    """风控配置"""
    max_position_pct: float = 0.3       # 单票最大仓位
    max_total_position: float = 0.8     # 总仓位上限
    stop_loss_pct: float = 0.05         # 止损比例
    take_profit_pct: float = 0.15       # 止盈比例
    max_drawdown: float = 0.2           # 最大回撤
    max_daily_loss: float = 0.05        # 单日最大亏损
    min_order_value: float = 1000       # 最小订单金额
    max_order_value: float = 100000     # 最大订单金额

class RiskManager:
    """风控管理器"""
    
    def __init__(self, config: RiskConfig = None):
        self.config = config or RiskConfig()
        self._daily_stats = {'pnl': 0, 'trade_count': 0}
        self._peak_equity = 0
    
    def check_signal(self, signal, portfolio) -> Tuple[bool, str]:
        """
        信号风控检查
        
        Args:
            signal: 交易信号
            portfolio: 投资组合
        
        Returns:
            Tuple[bool, str]: (是否通过, 原因)
        """
        checks = [
            self._check_position_limit,
            self._check_total_position,
            self._check_daily_loss,
            self._check_max_drawdown,
            self._check_order_value,
        ]
        
        for check in checks:
            passed, reason = check(signal, portfolio)
            if not passed:
                return False, reason
        
        return True, "通过所有风控检查"
    
    def calculate_position_size(self, signal, portfolio) -> float:
        """
        计算仓位大小
        
        Args:
            signal: 交易信号
            portfolio: 投资组合
        
        Returns:
            float: 建议仓位数量
        """
        # 可用资金
        available = portfolio.cash * self.config.max_position_pct
        
        # 按信号强度调整
        adjusted = available * signal.strength
        
        # 计算股数（按手取整，1手=100股）
        shares = int(adjusted / signal.price / 100) * 100
        
        return max(shares, 0)
    
    def get_stop_loss_price(self, entry_price: float, side: str) -> float:
        """计算止损价"""
        if side == 'buy':
            return entry_price * (1 - self.config.stop_loss_pct)
        return entry_price * (1 + self.config.stop_loss_pct)
    
    def get_take_profit_price(self, entry_price: float, side: str) -> float:
        """计算止盈价"""
        if side == 'buy':
            return entry_price * (1 + self.config.take_profit_pct)
        return entry_price * (1 - self.config.take_profit_pct)
    
    def _check_position_limit(self, signal, portfolio) -> Tuple[bool, str]:
        """检查单票仓位限制"""
        if portfolio.total_value == 0:
            return True, ""
        
        existing = portfolio.positions.get(signal.symbol)
        existing_value = existing.quantity * existing.current_price if existing else 0
        new_value = signal.price * 100  # 最小1手
        
        position_pct = (existing_value + new_value) / portfolio.total_value
        
        if position_pct > self.config.max_position_pct:
            return False, f"超过单票仓位限制 ({self.config.max_position_pct:.0%})"
        
        return True, ""
    
    def _check_total_position(self, signal, portfolio) -> Tuple[bool, str]:
        """检查总仓位限制"""
        if portfolio.total_value == 0:
            return True, ""
        
        position_value = sum(
            p.quantity * p.current_price 
            for p in portfolio.positions.values()
        )
        
        position_pct = position_value / portfolio.total_value
        
        if position_pct > self.config.max_total_position:
            return False, f"超过总仓位限制 ({self.config.max_total_position:.0%})"
        
        return True, ""
    
    def _check_daily_loss(self, signal, portfolio) -> Tuple[bool, str]:
        """检查当日亏损限制"""
        if portfolio.total_value == 0:
            return True, ""
        
        daily_loss_pct = -self._daily_stats['pnl'] / portfolio.total_value
        
        if daily_loss_pct >= self.config.max_daily_loss:
            return False, f"当日亏损已达上限 ({self.config.max_daily_loss:.0%})"
        
        return True, ""
    
    def _check_max_drawdown(self, signal, portfolio) -> Tuple[bool, str]:
        """检查最大回撤"""
        if self._peak_equity == 0:
            self._peak_equity = portfolio.total_value
            return True, ""
        
        self._peak_equity = max(self._peak_equity, portfolio.total_value)
        drawdown = (self._peak_equity - portfolio.total_value) / self._peak_equity
        
        if drawdown >= self.config.max_drawdown:
            return False, f"最大回撤已触及 ({self.config.max_drawdown:.0%})"
        
        return True, ""
    
    def _check_order_value(self, signal, portfolio) -> Tuple[bool, str]:
        """检查订单金额"""
        order_value = signal.price * 100  # 最小1手
        
        if order_value < self.config.min_order_value:
            return False, f"订单金额过小 (最小 {self.config.min_order_value})"
        
        if order_value > self.config.max_order_value:
            return False, f"订单金额过大 (最大 {self.config.max_order_value})"
        
        return True, ""
```

### 4.5 数据服务接口

```python
# data/market.py

from abc import ABC, abstractmethod
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import pandas as pd

class MarketDataService:
    """行情数据服务"""
    
    def __init__(self, config: Dict = None, source: str = 'tushare'):
        self.config = config or {}
        self.source = source
        self._cache = {}
        self._db = self._init_db()
    
    def get_latest(self, symbol: str, 
                   lookback: int = 100) -> pd.DataFrame:
        """
        获取最新行情数据
        
        Args:
            symbol: 股票代码
            lookback: 回溯条数
        
        Returns:
            pd.DataFrame: OHLCV 数据
        """
        # 先查缓存
        cache_key = f"{symbol}_{lookback}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # 查数据库
        data = self._query_from_db(symbol, lookback)
        
        # 如果数据不足，从数据源获取
        if len(data) < lookback:
            self._fetch_and_save(symbol)
            data = self._query_from_db(symbol, lookback)
        
        self._cache[cache_key] = data
        return data
    
    def get_history(self, symbol: str,
                    start_date: datetime,
                    end_date: datetime) -> pd.DataFrame:
        """
        获取历史数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            pd.DataFrame: OHLCV 数据
        """
        return self._query_from_db(
            symbol, 
            start_date=start_date, 
            end_date=end_date
        )
    
    def sync(self, symbols: List[str] = None,
             start_date: datetime = None,
             end_date: datetime = None) -> int:
        """
        同步数据
        
        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            int: 同步记录数
        """
        if symbols is None:
            symbols = self._get_all_symbols()
        
        total = 0
        for symbol in symbols:
            count = self._fetch_and_save(symbol, start_date, end_date)
            total += count
        
        return total
    
    def get_data_stats(self, symbols: str = None) -> List[Dict]:
        """获取数据统计信息"""
        query = "SELECT symbol, COUNT(*) as count, MIN(date) as start, MAX(date) as end FROM ohlcv"
        if symbols:
            symbol_list = [s.strip() for s in symbols.split(',')]
            query += f" WHERE symbol IN ({','.join(['?']*len(symbol_list))})"
        query += " GROUP BY symbol"
        
        # 执行查询并返回结果
        pass
    
    def clean(self, symbols: str = None, 
              before: datetime = None) -> int:
        """清理数据"""
        pass
    
    def _init_db(self):
        """初始化数据库"""
        import sqlite3
        conn = sqlite3.connect('data/market.db')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS ohlcv (
                symbol TEXT,
                date DATE,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                PRIMARY KEY (symbol, date)
            )
        ''')
        return conn
```

## 5. 配置管理

### 5.1 配置文件结构

```yaml
# config/default.yaml

# 系统配置
system:
  log_level: INFO
  log_dir: logs/
  data_dir: data/

# 数据源配置
data_source:
  provider: tushare  # tushare / akshare
  tushare_token: ${TUSHARE_TOKEN}

# 交易配置
trading:
  mode: paper  # paper / live
  initial_capital: 100000
  commission: 0.0003
  slippage: 0.001

# 风控配置
risk:
  max_position_pct: 0.3
  max_total_position: 0.8
  stop_loss_pct: 0.05
  take_profit_pct: 0.15
  max_drawdown: 0.2
  max_daily_loss: 0.05

# 策略配置
strategy:
  name: macd
  params:
    fast_period: 12
    slow_period: 26
    signal_period: 9

# 调度配置  
scheduler:
  poll_interval: 60  # 秒
  trading_hours:
    start: "09:30"
    end: "15:00"
```

### 5.2 配置加载器

```python
# config/loader.py

import os
import yaml
from pathlib import Path
from typing import Dict, Any

def load_config(config_path: str) -> Dict[str, Any]:
    """
    加载配置文件
    
    支持环境变量替换: ${ENV_VAR}
    """
    path = Path(config_path)
    
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换环境变量
    content = _substitute_env_vars(content)
    
    config = yaml.safe_load(content)
    
    return config

def _substitute_env_vars(content: str) -> str:
    """替换环境变量"""
    import re
    
    pattern = r'\$\{(\w+)\}'
    
    def replace(match):
        var_name = match.group(1)
        return os.environ.get(var_name, '')
    
    return re.sub(pattern, replace, content)
```

## 6. 使用示例

### 6.1 完整使用流程

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置数据源 Token
export TUSHARE_TOKEN=your_token_here

# 3. 同步历史数据
python main.py data sync -s 000001.SZ,600000.SH --start 2023-01-01

# 4. 运行回测
python main.py backtest \
    -s 000001.SZ \
    --start 2024-01-01 \
    --end 2024-12-31 \
    --format json \
    -o results/backtest_result.json

# 5. 启动模拟交易
python main.py run \
    -s 000001.SZ,600000.SH \
    --mode paper \
    --capital 100000

# 6. 查看持仓
python main.py report positions

# 7. 查看交易记录
python main.py report trades --limit 50

# 8. 生成日报
python main.py report generate --period daily -o reports/daily.md
```

### 6.2 后台运行

```bash
# 使用 nohup 后台运行
nohup python main.py run -s 000001.SZ --mode paper > trading.log 2>&1 &

# 或使用 screen
screen -S trading
python main.py run -s 000001.SZ --mode paper
# Ctrl+A, D 退出

# 查看日志
tail -f logs/trading.log
```

## 7. 技术选型

| 模块 | 技术方案 | 说明 |
|------|----------|------|
| CLI 框架 | Click | 强大的命令行工具库 |
| 策略引擎 | Python + Pandas | 快速原型开发 |
| 数据存储 | SQLite | 轻量级，无需额外服务 |
| 配置管理 | PyYAML | YAML 配置文件 |
| 日志系统 | Python logging | 内置日志模块 |
| 进度显示 | Click progressbar | CLI 进度条 |
