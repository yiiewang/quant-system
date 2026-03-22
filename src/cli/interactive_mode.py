"""
本地交互式模式

在终端持续执行命令，支持历史记录
通过 ITradingRunner 执行业务逻辑
"""
import os
from pathlib import Path
from typing import List, TYPE_CHECKING

from .execution_modes import ExecutionMode, CommandResult

if TYPE_CHECKING:
    from src.runner.interfaces import ITradingRunner


class InteractiveMode(ExecutionMode):
    """
    本地交互式模式
    
    在终端持续执行命令，支持历史记录
    通过 ApplicationRunner 执行业务操作
    """
    
    def __init__(self, runner: "ITradingRunner" = None):
        super().__init__(runner)
        self.running = False
        self._setup_readline()
    
    def _setup_readline(self):
        """配置readline支持历史记录"""
        try:
            import readline
            readline.parse_and_bind("tab: complete")
        except ImportError:
            pass
    
    @property
    def name(self) -> str:
        return "interactive"
    
    @property
    def description(self) -> str:
        return "本地交互式REPL模式"
    
    def execute(self, command: str, args: List[str], **kwargs) -> CommandResult:
        """执行命令（在REPL中）"""
        if not self._runner:
            return CommandResult(success=False, error="Runner 未初始化")
        
        # 解析参数后调用 Runner（与 CommandMode 保持一致）
        dispatch = {
            "strategies": self._cmd_strategies,
            "reload-strategies": self._cmd_reload_strategies,
            "list-strategy-files": self._cmd_list_strategy_files,
            "create-strategy": self._cmd_create_strategy,
            "delete-strategy": self._cmd_delete_strategy,
            "analyze": self._cmd_analyze,
            "backtest": self._cmd_backtest,
            "live": self._cmd_live,
            "sync": self._cmd_sync,
            "data": self._cmd_data,
            "debug": self._cmd_debug,
        }
        
        handler = dispatch.get(command)
        if not handler:
            return CommandResult(success=False, error=f"未知命令: {command}")
        
        return handler(args, **kwargs)
    
    # ──────────────────────────────────────────────────────────────────
    # 策略管理命令
    # ──────────────────────────────────────────────────────────────────
    
    def _cmd_strategies(self, args: List[str], **kwargs) -> CommandResult:
        """列出策略"""
        result = self._runner.list_strategies()
        return CommandResult.from_operation_result(result)
    
    def _cmd_reload_strategies(self, args: List[str], **kwargs) -> CommandResult:
        """重新加载策略"""
        result = self._runner.reload_strategies()
        return CommandResult.from_operation_result(result)
    
    def _cmd_list_strategy_files(self, args: List[str], **kwargs) -> CommandResult:
        """列出策略文件"""
        result = self._runner.list_strategy_files()
        return CommandResult.from_operation_result(result)
    
    def _cmd_create_strategy(self, args: List[str], **kwargs) -> CommandResult:
        """创建策略文件"""
        if not args:
            return CommandResult(success=False, error="缺少策略名称")
        result = self._runner.create_strategy(name=args[0])
        return CommandResult.from_operation_result(result)
    
    def _cmd_delete_strategy(self, args: List[str], **kwargs) -> CommandResult:
        """删除策略文件"""
        if not args:
            return CommandResult(success=False, error="缺少策略名称")
        result = self._runner.delete_strategy(name=args[0])
        return CommandResult.from_operation_result(result)
    
    # ──────────────────────────────────────────────────────────────────
    # 分析与回测命令
    # ──────────────────────────────────────────────────────────────────
    
    def _cmd_analyze(self, args: List[str], **kwargs) -> CommandResult:
        """分析标的"""
        parsed = self._parse_analyze_args(args)
        # kwargs 优先级更高(来自交互式输入)
        parsed.update(kwargs)
        result = self._runner.analyze(**parsed)
        return CommandResult.from_operation_result(result)
    
    def _reload_runner_with_config(self, config_path: str, strategy: str = None):
        """根据配置文件重新创建 Runner（加载通知等配置）"""
        from src.config.base import load_config
        from src.config.schema import Config
        from src.runner.application import ApplicationRunner

        config = load_config(Config, config_path)
        if strategy:
            config.strategy.name = strategy
        params = {}
        self._runner = ApplicationRunner(config, params)
        return config
    
    def _cmd_backtest(self, args: List[str], **kwargs) -> CommandResult:
        """运行回测"""
        # 如果指定了配置文件，重新加载 Runner
        config_path = kwargs.pop('config_path', None)
        if config_path:
            self._reload_runner_with_config(config_path, kwargs.get('strategy'))
        
        # kwargs 已包含完整参数时直接使用（来自 handle_run_interactive）
        if kwargs.get('start_date') and kwargs.get('end_date'):
            result = self._runner.backtest(**kwargs)
            return CommandResult.from_operation_result(result)
        
        parsed = self._parse_backtest_args(args)
        if parsed is None:
            return CommandResult(success=False, error="缺少 --start 或 --end 参数")
        # kwargs 优先级更高
        parsed.update(kwargs)
        result = self._runner.backtest(**parsed)
        return CommandResult.from_operation_result(result)
    
    def _cmd_live(self, args: List[str], **kwargs) -> CommandResult:
        """实时运行"""
        # 如果指定了配置文件，重新加载 Runner
        config_path = kwargs.pop('config_path', None)
        if config_path:
            self._reload_runner_with_config(config_path, kwargs.get('strategy'))
        
        parsed = self._parse_live_args(args)
        parsed.update(kwargs)
        result = self._runner.live(**parsed)
        return CommandResult.from_operation_result(result)

    # ──────────────────────────────────────────────────────────────────
    # 数据命令
    # ──────────────────────────────────────────────────────────────────

    def _cmd_sync(self, args: List[str], **kwargs) -> CommandResult:
        """同步数据"""
        parsed = self._parse_sync_args(args)
        result = self._runner.sync_data(**parsed, **kwargs)
        return CommandResult.from_operation_result(result)
    
    def _cmd_data(self, args: List[str], **kwargs) -> CommandResult:
        """数据信息"""
        symbol = args[0] if args else None
        result = self._runner.get_data_info(symbol=symbol)
        return CommandResult.from_operation_result(result)
    
    def _cmd_debug(self, args: List[str], **kwargs) -> CommandResult:
        """调试命令：测试通知/查看配置等"""
        import os
        import logging
        logger = logging.getLogger(__name__)
        
        subcmd = args[0] if args else "help"
        
        if subcmd == "help":
            help_text = """
调试命令:
  debug notify <symbol> <signal_type> <price>  - 测试发送通知
  debug config                                  - 查看当前配置
  debug env                                     - 查看环境变量
  debug strategy                                - 查看策略通知配置
"""
            return CommandResult(success=True, data=help_text)
        
        elif subcmd == "notify":
            if len(args) < 4:
                return CommandResult(success=False, error="用法: debug notify <symbol> <signal_type> <price> <reason>")
            
            symbol = args[1]
            signal_type = args[2]
            price = float(args[3])
            reason = args[4] if len(args) > 4 else "测试通知"
            
            # 检查通知组件
            if not hasattr(self._runner, '_notifier') or not self._runner._notifier:
                return CommandResult(success=False, error="通知组件未初始化")
            
            logger.info(f"测试发送通知: {symbol} {signal_type} @ {price}")
            
            try:
                success = self._runner._notifier.send_signal(
                    symbol=symbol,
                    signal_type=signal_type,
                    price=price,
                    reason=reason
                )
                return CommandResult(success=success, data=f"通知发送{'成功' if success else '失败'}")
            except Exception as e:
                logger.error(f"发送通知失败: {e}", exc_info=True)
                return CommandResult(success=False, error=str(e))
        
        elif subcmd == "config":
            # 显示当前配置
            config = self._runner.config
            lines = [
                "当前配置:",
                f"  策略名称: {config.strategy.name if config.strategy else 'N/A'}",
                f"  通知开关: {config.notification.enabled if config.notification else 'N/A'}",
            ]
            if hasattr(config.notification, 'email'):
                lines.append(f"  邮件开关: {config.notification.email.enabled if hasattr(config.notification.email, 'enabled') else 'N/A'}")
            return CommandResult(success=True, data="\n".join(lines))
        
        elif subcmd == "env":
            # 显示环境变量
            lines = [
                "环境变量:",
                f"  SMTP_USER: {os.environ.get('SMTP_USER', '未设置')}",
                f"  SMTP_PASS: {'***' if os.environ.get('SMTP_PASS') else '未设置'}",
                f"  SMTP_SERVER: {os.environ.get('SMTP_SERVER', '默认 smtp.qq.com')}",
                f"  SMTP_PORT: {os.environ.get('SMTP_PORT', '默认 465')}",
                f"  WEBHOOK_URL: {os.environ.get('WEBHOOK_URL', '未设置')}",
            ]
            return CommandResult(success=True, data="\n".join(lines))
        
        elif subcmd == "strategy":
            # 显示策略通知配置
            strategy_name = self._runner.config.strategy.name
            if not strategy_name:
                return CommandResult(success=False, error="未选择策略")
            
            strategy_config = self._runner._get_strategy_notification_config() if hasattr(self._runner, '_get_strategy_notification_config') else {}
            strategy_enabled = self._runner._is_strategy_notification_enabled() if hasattr(self._runner, '_is_strategy_notification_enabled') else True
            
            lines = [
                f"策略通知配置 ({strategy_name}):",
                f"  启用: {strategy_enabled}",
                f"  收件人: {strategy_config.get('recipients', [])}",
                f"  Webhook: {strategy_config.get('webhook_url', '未配置')}",
            ]
            return CommandResult(success=True, data="\n".join(lines))
        
        else:
            return CommandResult(success=False, error=f"未知子命令: {subcmd}")
    
    # ──────────────────────────────────────────────────────────────────
    # 参数解析辅助方法
    # ──────────────────────────────────────────────────────────────────
    
    def _parse_analyze_args(self, args: List[str]) -> dict:
        """解析 analyze 命令参数"""
        symbols = []
        strategy = None
        days = 365
        source = "baostock"
        
        i = 0
        while i < len(args):
            if args[i] == "--strategy" and i + 1 < len(args):
                strategy = args[i + 1]
                i += 2
            elif args[i] == "--days" and i + 1 < len(args):
                days = int(args[i + 1])
                i += 2
            elif args[i] == "--source" and i + 1 < len(args):
                source = args[i + 1]
                i += 2
            elif not args[i].startswith("--"):
                symbols.append(args[i])
                i += 1
            else:
                i += 1
        
        return {"symbols": symbols, "strategy": strategy, "days": days, "source": source}
    
    def _parse_backtest_args(self, args: List[str]) -> dict:
        """解析 backtest 命令参数"""
        symbols = []
        start_date = None
        end_date = None
        strategy = None
        initial_capital = 1000000
        
        i = 0
        while i < len(args):
            if args[i] == "--start" and i + 1 < len(args):
                start_date = args[i + 1]
                i += 2
            elif args[i] == "--end" and i + 1 < len(args):
                end_date = args[i + 1]
                i += 2
            elif args[i] == "--strategy" and i + 1 < len(args):
                strategy = args[i + 1]
                i += 2
            elif args[i] == "--capital" and i + 1 < len(args):
                initial_capital = float(args[i + 1])
                i += 2
            elif not args[i].startswith("--"):
                symbols.append(args[i])
                i += 1
            else:
                i += 1
        
        if not start_date or not end_date:
            return None
        
        return {
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
            "strategy": strategy,
            "initial_capital": initial_capital,
        }

    def _parse_live_args(self, args: List[str]) -> dict:
        """解析 live 命令参数"""
        action = args[0] if args else "start"
        rest = args[1:] if len(args) > 1 else []
        
        symbols = []
        strategy = None
        interval = 60
        
        i = 0
        while i < len(rest):
            if rest[i] == "--strategy" and i + 1 < len(rest):
                strategy = rest[i + 1]
                i += 2
            elif rest[i] == "--interval" and i + 1 < len(rest):
                interval = int(rest[i + 1])
                i += 2
            elif not rest[i].startswith("--"):
                symbols.append(rest[i])
                i += 1
            else:
                i += 1
        
        return {"action": action, "symbols": symbols, "strategy": strategy, "interval": interval}
    
    def _parse_sync_args(self, args: List[str]) -> dict:
        """解析 sync 命令参数"""
        symbols = []
        frequency = "daily"
        days = 365
        
        i = 0
        while i < len(args):
            if args[i] == "--freq" and i + 1 < len(args):
                frequency = args[i + 1]
                i += 2
            elif args[i] == "--days" and i + 1 < len(args):
                days = int(args[i + 1])
                i += 2
            elif not args[i].startswith("--"):
                symbols.append(args[i])
                i += 1
            else:
                i += 1
        
        return {"symbols": symbols, "frequency": frequency, "days": days}
    
    def start(self):
        """启动交互式REPL"""
        from .main import Colors
        from src.runner.application import ApplicationRunner
        from src.config.base import load_config
        from src.config.schema import Config

        # 初始化 Runner（如果未设置）
        if not self._runner:
            config = load_config(Config)
            params = {}
            self._runner = ApplicationRunner(config, params)
        
        self.running = True
        
        def print_help():
            """打印帮助信息"""
            print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
            print(f"{Colors.BOLD}量化交易系统 - 交互式模式{Colors.ENDC}")
            print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")
            print(f"{Colors.BOLD}可用命令:{Colors.ENDC}")
            print("  strategies            列出所有可用策略")
            print("  list-strategy-files   列出策略文件")
            print(f"  {Colors.OKCYAN}create-strategy <name>{Colors.ENDC}    创建新策略模板")
            print(f"  {Colors.OKCYAN}delete-strategy <name>{Colors.ENDC}    软删除策略")
            print("  reload-strategies     重新加载策略")
            print(f"  {Colors.OKCYAN}analyze <symbol> [...] {Colors.ENDC}  分析标的")
            print(f"  {Colors.OKCYAN}backtest <symbol> [...] {Colors.ENDC} 运行回测")
            print(f"  {Colors.OKCYAN}live <symbol> [...] {Colors.ENDC}    实时运行")
            print("  help                  显示帮助")
            print("  clear                 清屏")
            print("  exit                  退出\n")
        
        def handle_strategies():
            """处理 strategies 命令"""
            print(f"\n{Colors.BOLD}可用策略列表:{Colors.ENDC}\n")
            result = self._runner.list_strategies()
            if result.success and result.data:
                for strat in result.data:
                    print(f"  {Colors.OKCYAN}• {strat}{Colors.ENDC}")
            print()
        
        def handle_list_strategy_files():
            """处理 list-strategy-files 命令"""
            print(f"\n{Colors.BOLD}策略文件列表:{Colors.ENDC}\n")
            result = self._runner.list_strategy_files()
            if result.success and result.data:
                for f in result.data:
                    type_label = f.get('type', 'unknown')
                    print(f"  {Colors.OKCYAN}• {f['name']}{Colors.ENDC} [{type_label}]")
            print()
        
        def handle_create_strategy(name):
            """处理 create-strategy 命令"""
            result = self._runner.create_strategy(name)
            if result.success:
                print(f"{Colors.OKGREEN}✓ {result.message}{Colors.ENDC}")
                print(f"  {Colors.OKCYAN}请编辑该文件以实现策略逻辑{Colors.ENDC}")
                # 自动重新加载
                self._runner.reload_strategies()
                print(f"  {Colors.OKGREEN}✓ 策略已自动加载{Colors.ENDC}")
            else:
                print(f"{Colors.FAIL}错误: {result.error}{Colors.ENDC}")
        
        def handle_delete_strategy(name):
            """处理 delete-strategy 命令"""
            result = self._runner.delete_strategy(name)
            if result.success:
                print(f"{Colors.OKGREEN}✓ {result.message}{Colors.ENDC}")
            else:
                print(f"{Colors.FAIL}错误: {result.error}{Colors.ENDC}")
        
        def handle_run_interactive():
            """交互式运行策略"""
            # 1. 选择策略
            strategies_result = self._runner.list_strategies()
            if not strategies_result.success or not strategies_result.data:
                print(f"{Colors.FAIL}没有可用的策略{Colors.ENDC}")
                return
            
            print(f"\n{Colors.BOLD}可用策略:{Colors.ENDC}")
            for i, strat in enumerate(strategies_result.data, 1):
                print(f"  {i}. {strat}")
            
            try:
                choice = input(f"\n{Colors.OKCYAN}选择策略 (输入名称或序号): {Colors.ENDC}").strip()
                # 如果是数字,转换为策略名
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(strategies_result.data):
                        strategy_name = strategies_result.data[idx]
                    else:
                        print(f"{Colors.FAIL}无效的选择{Colors.ENDC}")
                        return
                else:
                    strategy_name = choice
            except (EOFError, KeyboardInterrupt):
                print(f"{Colors.WARNING}已取消{Colors.ENDC}")
                return
            
            # 2. 选择配置文件
            config_path = None
            try:
                config_input = input(f"\n{Colors.OKCYAN}配置文件路径 (留空自动查找 {strategy_name}.yaml): {Colors.ENDC}").strip()
                if config_input:
                    config_path = config_input
                else:
                    # 自动查找策略配置文件
                    from pathlib import Path
                    candidates = [
                        f"data/strategies/{strategy_name}.yaml",
                    ]
                    for candidate in candidates:
                        if Path(candidate).exists():
                            config_path = candidate
                            print(f"  {Colors.OKGREEN}✓ 找到配置文件: {config_path}{Colors.ENDC}")
                            break
            except (EOFError, KeyboardInterrupt):
                print(f"{Colors.WARNING}已取消{Colors.ENDC}")
                return
            
            # 3. 选择模式
            print(f"\n{Colors.BOLD}运行模式:{Colors.ENDC}")
            print("  1. analyze  - 分析标的")
            print("  2. backtest - 历史回测")
            print("  3. live     - 实时运行")
            
            try:
                mode_choice = input(f"\n{Colors.OKCYAN}选择模式 (1-3): {Colors.ENDC}").strip()
                mode_map = {'1': 'analyze', '2': 'backtest', '3': 'live'}
                mode = mode_map.get(mode_choice)
                if not mode:
                    print(f"{Colors.FAIL}无效的模式选择{Colors.ENDC}")
                    return
            except (EOFError, KeyboardInterrupt):
                print(f"{Colors.WARNING}已取消{Colors.ENDC}")
                return
            
            # 4. 输入标的
            try:
                symbols_input = input(f"\n{Colors.OKCYAN}输入标的代码 (如 000001.SZ，多个用逗号分隔): {Colors.ENDC}").strip()
                if not symbols_input:
                    print(f"{Colors.FAIL}标的不能为空{Colors.ENDC}")
                    return
                symbols = [s.strip() for s in symbols_input.split(',')]
            except (EOFError, KeyboardInterrupt):
                print(f"{Colors.WARNING}已取消{Colors.ENDC}")
                return
            
            # 5. 根据模式收集额外参数
            kwargs = {'strategy': strategy_name, 'symbols': symbols}
            if config_path:
                kwargs['config_path'] = config_path
            
            if mode == 'backtest':
                try:
                    start = input(f"{Colors.OKCYAN}开始日期 (YYYY-MM-DD): {Colors.ENDC}").strip()
                    end = input(f"{Colors.OKCYAN}结束日期 (YYYY-MM-DD): {Colors.ENDC}").strip()
                    if not start or not end:
                        print(f"{Colors.FAIL}回测模式必须指定日期范围{Colors.ENDC}")
                        return
                    kwargs['start_date'] = start
                    kwargs['end_date'] = end
                    capital = input(f"{Colors.OKCYAN}初始资金 (默认100万): {Colors.ENDC}").strip()
                    if capital:
                        kwargs['initial_capital'] = float(capital)
                except (EOFError, KeyboardInterrupt):
                    print(f"{Colors.WARNING}已取消{Colors.ENDC}")
                    return
            
            elif mode == 'analyze':
                try:
                    days = input(f"{Colors.OKCYAN}分析天数 (默认60): {Colors.ENDC}").strip()
                    if days:
                        kwargs['days'] = int(days)
                except (EOFError, KeyboardInterrupt):
                    print(f"{Colors.WARNING}已取消{Colors.ENDC}")
                    return
            
            elif mode == 'live':
                try:
                    interval = input(f"{Colors.OKCYAN}检查间隔秒数 (默认60): {Colors.ENDC}").strip()
                    if interval:
                        kwargs['interval'] = int(interval)
                    kwargs['action'] = 'start'
                except (EOFError, KeyboardInterrupt):
                    print(f"{Colors.WARNING}已取消{Colors.ENDC}")
                    return
            
            # 6. 执行
            print(f"\n{Colors.BOLD}正在执行...{Colors.ENDC}")
            print(f"  策略: {strategy_name}")
            print(f"  模式: {mode}")
            print(f"  标的: {', '.join(symbols)}")
            if config_path:
                print(f"  配置: {config_path}")
            
            result = self.execute(mode, [], **kwargs)
            
            if result.success:
                print(f"\n{Colors.OKGREEN}✓ 执行成功{Colors.ENDC}")
                if result.message:
                    print(f"  {result.message}")
                if result.data:
                    print(f"\n{Colors.BOLD}结果:{Colors.ENDC}")
                    import json
                    print(json.dumps(result.data, indent=2, ensure_ascii=False, default=str))
            else:
                print(f"\n{Colors.FAIL}✗ 执行失败: {result.error}{Colors.ENDC}")
        
        # 显示欢迎信息
        print_help()
        
        while self.running:
            try:
                cmd_input = input(f"{Colors.OKGREEN}quant> {Colors.ENDC}").strip()
                
                if not cmd_input:
                    continue
                
                # 解析命令
                parts = cmd_input.split()
                command = parts[0].lower()
                args = parts[1:]
                
                # 处理特殊命令
                if command in ('exit', 'quit', 'q'):
                    print(f"\n{Colors.OKGREEN}再见！{Colors.ENDC}\n")
                    self.running = False
                    break
                
                if command == 'help':
                    print_help()
                    continue
                
                if command == 'clear':
                    os.system('clear' if os.name == 'posix' else 'cls')
                    continue
                
                if command == 'strategies':
                    handle_strategies()
                    continue
                
                if command == 'list-strategy-files':
                    handle_list_strategy_files()
                    continue
                
                if command == 'run':
                    handle_run_interactive()
                    continue
                
                if command == 'reload-strategies':
                    # 通过 Runner 重新加载策略
                    result = self._runner.reload_strategies()
                    if result.success:
                        strategies = result.data or []
                        print(f"\n{Colors.OKGREEN}✓ 策略已重新加载{Colors.ENDC}")
                        print(f"  当前可用策略: {', '.join(strategies)}\n")
                    else:
                        print(f"{Colors.FAIL}重新加载失败: {result.error}{Colors.ENDC}")
                    continue
                
                if command == 'create-strategy':
                    if not args:
                        print(f"{Colors.FAIL}用法: create-strategy <name>{Colors.ENDC}")
                    else:
                        handle_create_strategy(args[0])
                    continue
                
                if command == 'delete-strategy':
                    if not args:
                        print(f"{Colors.FAIL}用法: delete-strategy <name>{Colors.ENDC}")
                    else:
                        handle_delete_strategy(args[0])
                    continue
                
                # 执行业务命令（通过 Runner）
                result = self.execute(command, args)
                if not result.success and result.error:
                    print(f"{Colors.FAIL}错误: {result.error}{Colors.ENDC}")
                elif result.message:
                    print(f"{Colors.OKGREEN}{result.message}{Colors.ENDC}")
                elif result.data:
                    print(result.data)
                
            except KeyboardInterrupt:
                print(f"\n{Colors.WARNING}使用 'exit' 命令退出{Colors.ENDC}")
            except EOFError:
                print(f"\n{Colors.OKGREEN}再见！{Colors.ENDC}\n")
                self.running = False
