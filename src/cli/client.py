"""
交互式客户端模式
连接到 HTTP API 服务，通过命令行终端持续发送指令

使用方式:
    python -m src.main client                     # 连接默认 localhost:8000
    python -m src.main client --server 10.0.0.1:9000  # 连接远程服务
"""
import json
import shlex
import sys
import time
from typing import Optional, Tuple

try:
    import requests
except ImportError:
    requests = None

try:
    import readline  # noqa: F401 - 启用方向键和历史记录
except ImportError:
    pass


# ==================== 命令定义 ====================

COMMANDS = {
    "help":       "显示帮助信息",
    "health":     "检查服务健康状态",
    "strategies": "列出所有可用策略",
    "analyze":    "分析标的  例: analyze 000001.SZ [--strategy macd] [--days 365]",
    "backtest":   "运行回测  例: backtest 000001.SZ --start 2024-01-01 --end 2025-01-01 [--strategy macd] [--capital 1000000]",
    "monitor":    "监控管理  子命令: start / stop / status",
    "status":     "查看监控状态 (等同 monitor status)",
    "sync":       "同步数据  例: sync 000001.SZ [--freq 5min] [--days 5] [--source baostock]",
    "data":       "查看数据信息  例: data [000001.SZ]",
    "clear":      "清屏",
    "exit":       "退出客户端 (也可用 quit / q / Ctrl+D)",
}


# ==================== 解析辅助 ====================

def _parse_kv(args: list) -> dict:
    """从参数列表中解析 --key value 对"""
    result = {}
    i = 0
    positional = []
    while i < len(args):
        if args[i].startswith("--"):
            key = args[i][2:].replace("-", "_")
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                result[key] = args[i + 1]
                i += 2
            else:
                result[key] = True
                i += 1
        else:
            positional.append(args[i])
            i += 1
    return result, positional


def _parse_symbols(positional: list) -> list:
    """从位置参数中解析 symbols (逗号或空格分隔)"""
    symbols = []
    for arg in positional:
        for s in arg.split(","):
            s = s.strip()
            if s:
                symbols.append(s)
    return symbols


# ==================== HTTP 请求 ====================

def _request(base_url: str, method: str, path: str,
             payload: dict = None, timeout: int = 120) -> Tuple[bool, dict]:
    """发送 HTTP 请求并返回 (success, data)"""
    url = f"{base_url}{path}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=timeout)
        else:
            resp = requests.post(url, json=payload, timeout=timeout)

        data = resp.json()

        if resp.status_code >= 400:
            detail = data.get("detail", data.get("message", resp.text))
            return False, {"error": detail}

        return True, data
    except requests.ConnectionError:
        return False, {"error": f"无法连接到服务 {base_url}，请确认服务已启动"}
    except requests.Timeout:
        return False, {"error": f"请求超时 ({timeout}s)"}
    except Exception as e:
        return False, {"error": str(e)}


# ==================== 命令处理器 ====================

class ClientSession:
    """交互式客户端会话"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.running = True

    def print_banner(self):
        """打印欢迎信息"""
        print("=" * 60)
        print("  MACD 量化交易系统 - 交互式客户端")
        print("=" * 60)
        print(f"  服务地址: {self.base_url}")
        print(f"  输入 help 查看可用命令，exit 退出")
        print("=" * 60)
        print()

    def print_help(self):
        """打印帮助"""
        print("\n可用命令:")
        print("-" * 60)
        for cmd, desc in COMMANDS.items():
            print(f"  {cmd:<14} {desc}")
        print("-" * 60)
        print()

    def _print_result(self, ok: bool, data: dict):
        """格式化打印结果"""
        if not ok:
            print(f"  [错误] {data.get('error', '未知错误')}")
            return

        # 统一 ApiResponse 格式
        success = data.get("success", ok)
        message = data.get("message", "")
        payload = data.get("data")

        if message:
            print(f"  {message}")

        if payload is not None:
            if isinstance(payload, (dict, list)):
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"  {payload}")

    # ---------- 命令: health ----------
    def cmd_health(self, args: list):
        ok, data = _request(self.base_url, "GET", "/api/health")
        self._print_result(ok, data)

    # ---------- 命令: strategies ----------
    def cmd_strategies(self, args: list):
        ok, data = _request(self.base_url, "GET", "/api/strategies")
        if ok and data.get("data"):
            strategies = data["data"]
            print("\n可用策略:")
            print("-" * 60)
            for s in strategies:
                name = s.get("name", "")
                desc = s.get("description", "")
                params = s.get("default_params", {})
                print(f"  {name:<20} {desc}")
                if params:
                    print(f"  {'':20} 默认参数: {params}")
            print()
        else:
            self._print_result(ok, data)

    # ---------- 命令: analyze ----------
    def cmd_analyze(self, args: list):
        kv, positional = _parse_kv(args)
        symbols = _parse_symbols(positional)

        if not symbols:
            print("  用法: analyze <symbols> [--strategy macd] [--days 365] [--source baostock]")
            print("  示例: analyze 000001.SZ,002050.SZ --strategy macd --days 180")
            return

        payload = {"symbols": symbols}
        if "strategy" in kv:
            payload["strategy"] = kv["strategy"]
        if "days" in kv:
            payload["days"] = int(kv["days"])
        if "source" in kv:
            payload["source"] = kv["source"]
        if "config" in kv:
            payload["config_path"] = kv["config"]

        print(f"  分析标的: {symbols} ...")
        ok, data = _request(self.base_url, "POST", "/api/analyze", payload)
        if ok and data.get("data"):
            for item in data["data"]:
                print()
                if "error" in item:
                    print(f"  [{item.get('symbol', '?')}] 错误: {item['error']}")
                    continue
                print(f"  [{item.get('symbol', '')}]")
                print(f"    状态:   {item.get('status', '-')}")
                print(f"    建议:   {item.get('action', '-')}")
                print(f"    置信度: {item.get('confidence', 0):.0%}")
                reason = item.get("reason", "")
                if reason:
                    print(f"    理由:   {reason.splitlines()[0]}")
                indicators = item.get("indicators", {})
                if indicators:
                    print(f"    指标:")
                    for k, v in indicators.items():
                        print(f"      {k}: {v}")
            print()
        else:
            self._print_result(ok, data)

    # ---------- 命令: backtest ----------
    def cmd_backtest(self, args: list):
        kv, positional = _parse_kv(args)
        symbols = _parse_symbols(positional)

        if not symbols or "start" not in kv or "end" not in kv:
            print("  用法: backtest <symbols> --start YYYY-MM-DD --end YYYY-MM-DD [--strategy macd] [--capital 1000000]")
            print("  示例: backtest 002050.SZ --start 2024-01-01 --end 2025-01-01")
            return

        payload = {
            "symbols": symbols,
            "start_date": kv["start"],
            "end_date": kv["end"],
        }
        if "strategy" in kv:
            payload["strategy"] = kv["strategy"]
        if "capital" in kv:
            payload["initial_capital"] = float(kv["capital"])
        if "config" in kv:
            payload["config_path"] = kv["config"]

        print(f"  回测 {symbols}  {kv['start']} ~ {kv['end']} ...")
        ok, data = _request(self.base_url, "POST", "/api/backtest", payload, timeout=300)
        if ok and data.get("data"):
            d = data["data"]
            print()
            print("  回测结果:")
            print("  " + "-" * 40)
            fields = [
                ("总收益率", "total_return", True),
                ("年化收益", "annual_return", True),
                ("最大回撤", "max_drawdown", True),
                ("夏普比率", "sharpe_ratio", False),
                ("交易次数", "trade_count", False),
                ("胜率", "win_rate", True),
            ]
            for label, key, is_pct in fields:
                val = d.get(key)
                if val is not None:
                    if is_pct and isinstance(val, (int, float)):
                        print(f"    {label}: {val:.2%}")
                    elif isinstance(val, float):
                        print(f"    {label}: {val:.2f}")
                    else:
                        print(f"    {label}: {val}")
            print()
        else:
            self._print_result(ok, data)

    # ---------- 命令: monitor ----------
    def cmd_monitor(self, args: list):
        if not args:
            print("  用法: monitor <start|stop|status>")
            print("  示例: monitor start 000001.SZ,002050.SZ --interval 60")
            return

        sub = args[0].lower()
        rest = args[1:]

        if sub == "start":
            kv, positional = _parse_kv(rest)
            symbols = _parse_symbols(positional)
            if not symbols:
                print("  用法: monitor start <symbols> [--strategy macd] [--interval 60]")
                return

            payload = {"symbols": symbols}
            if "strategy" in kv:
                payload["strategy"] = kv["strategy"]
            if "interval" in kv:
                payload["interval"] = int(kv["interval"])
            if "source" in kv:
                payload["source"] = kv["source"]

            print(f"  启动监控: {symbols} ...")
            ok, data = _request(self.base_url, "POST", "/api/monitor/start", payload)
            self._print_result(ok, data)

        elif sub == "stop":
            ok, data = _request(self.base_url, "POST", "/api/monitor/stop")
            self._print_result(ok, data)

        elif sub == "status":
            self.cmd_status([])

        else:
            print(f"  未知子命令: {sub}，支持: start / stop / status")

    # ---------- 命令: status ----------
    def cmd_status(self, args: list):
        ok, data = _request(self.base_url, "GET", "/api/monitor/status")
        if ok and data.get("data"):
            d = data["data"]
            running = d.get("running", False)
            print(f"\n  监控状态: {'运行中' if running else '未运行'}")
            cfg = d.get("config")
            if cfg:
                print(f"    标的:     {cfg.get('symbols', [])}")
                print(f"    策略:     {cfg.get('strategy', '-')}")
                print(f"    间隔:     {cfg.get('interval', '-')}s")
                print(f"    启动时间: {cfg.get('started_at', '-')}")
            print()
        else:
            self._print_result(ok, data)

    # ---------- 命令: sync ----------
    def cmd_sync(self, args: list):
        kv, positional = _parse_kv(args)
        symbols = _parse_symbols(positional)

        if not symbols:
            print("  用法: sync <symbols> [--freq 5min] [--days 5] [--source baostock]")
            print("  频率: daily / 5min / 15min / 30min / 60min")
            print("  示例: sync 000001.SZ,002050.SZ --freq 5min --days 3")
            return

        payload = {"symbols": symbols}
        if "freq" in kv:
            payload["frequency"] = kv["freq"]
        if "days" in kv:
            payload["days"] = int(kv["days"])
        if "start" in kv:
            payload["start_date"] = kv["start"]
        if "end" in kv:
            payload["end_date"] = kv["end"]
        if "source" in kv:
            payload["source"] = kv["source"]

        freq_label = kv.get("freq", "daily")
        print(f"  同步 {symbols} [{freq_label}] ...")
        ok, data = _request(self.base_url, "POST", "/api/data/sync", payload, timeout=300)
        if ok and data.get("data"):
            d = data["data"]
            print(f"  同步完成: {d.get('count', 0)} 条数据")
            print(f"    频率: {d.get('frequency', '-')}")
            print(f"    日期: {d.get('start_date', '-')} ~ {d.get('end_date', '-')}")
        else:
            self._print_result(ok, data)

    # ---------- 命令: data (查看数据信息) ----------
    def cmd_data(self, args: list):
        kv, positional = _parse_kv(args)
        symbol = positional[0] if positional else None
        
        path = "/api/data/info"
        if symbol:
            path += f"?symbol={symbol}"
        
        ok, data = _request(self.base_url, "GET", path)
        if ok and data.get("data"):
            d = data["data"]
            daily = d.get("daily", [])
            minute = d.get("minute", [])

            if daily:
                print("\n  日线数据:")
                print("  " + "-" * 55)
                print(f"  {'股票':<14} {'条数':<8} {'开始日期':<12} {'结束日期':<12}")
                for item in daily:
                    print(f"  {item['symbol']:<14} {item['count']:<8} {item['start_date']:<12} {item['end_date']:<12}")

            if minute:
                print("\n  分时数据:")
                print("  " + "-" * 65)
                print(f"  {'股票':<12} {'频率':<7} {'条数':<8} {'开始时间':<20} {'结束时间':<20}")
                for item in minute:
                    print(f"  {item['symbol']:<12} {item['frequency']:<7} {item['count']:<8} {item['start_time']:<20} {item['end_time']:<20}")

            if not daily and not minute:
                print("  暂无数据")
            print()
        else:
            self._print_result(ok, data)

    # ---------- 命令分发 ----------
    def dispatch(self, line: str):
        """解析并分发一行命令"""
        line = line.strip()
        if not line:
            return

        try:
            parts = shlex.split(line)
        except ValueError:
            parts = line.split()

        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("exit", "quit", "q"):
            self.running = False
            return

        if cmd == "help":
            self.print_help()
        elif cmd == "clear":
            print("\033[2J\033[H", end="")
        elif cmd == "health":
            self.cmd_health(args)
        elif cmd == "strategies":
            self.cmd_strategies(args)
        elif cmd == "analyze":
            self.cmd_analyze(args)
        elif cmd == "backtest":
            self.cmd_backtest(args)
        elif cmd == "monitor":
            self.cmd_monitor(args)
        elif cmd == "status":
            self.cmd_status(args)
        elif cmd == "sync":
            self.cmd_sync(args)
        elif cmd == "data":
            self.cmd_data(args)
        else:
            print(f"  未知命令: {cmd}，输入 help 查看可用命令")

    # ---------- 主循环 ----------
    def run(self):
        """启动交互式 REPL"""
        self.print_banner()

        # 先检查连接
        ok, data = _request(self.base_url, "GET", "/api/health", timeout=5)
        if ok:
            print("  [连接成功] 服务运行正常\n")
        else:
            print(f"  [警告] 无法连接到 {self.base_url}，请确认服务已启动")
            print(f"  提示: python -m src.main serve\n")

        while self.running:
            try:
                line = input("macd> ")
                self.dispatch(line)
            except EOFError:
                # Ctrl+D
                print()
                self.running = False
            except KeyboardInterrupt:
                # Ctrl+C 不退出，只换行
                print()
                continue

        print("再见!")


def start_client(server: str):
    """启动客户端"""
    if requests is None:
        print("错误: 需要安装 requests 库")
        print("  pip install requests")
        sys.exit(1)

    if not server.startswith("http"):
        server = f"http://{server}"

    session = ClientSession(server)
    session.run()
