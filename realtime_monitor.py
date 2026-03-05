#!/usr/bin/env python3
"""
实时行情监控与邮件通知系统

功能:
1. 实时获取行情数据
2. 计算 MACD 指标和交易信号
3. 通过邮件发送交易信号通知
4. 支持交易时间和非交易时间不同的刷新间隔

使用方法:
    # 基本用法
    python realtime_monitor.py --symbols 002050.SZ --email your@email.com
    
    # 完整参数
    python realtime_monitor.py \\
        --symbols 002050.SZ,000001.SZ \\
        --email your@email.com \\
        --smtp-server smtp.qq.com \\
        --smtp-port 465 \\
        --smtp-user your@qq.com \\
        --smtp-pass your_auth_code \\
        --strategy weekly \\
        --interval 60 \\
        --skip-trading-time-check
"""

import os
import sys
import argparse
import logging
import time as time_module
from datetime import datetime, time, timedelta
from typing import List, Dict, Any, Optional
import signal

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/realtime_monitor.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class RealtimeMonitor:
    """
    实时行情监控器
    
    监控指定股票的行情，计算技术指标，发送交易信号通知
    """
    
    def __init__(
        self,
        symbols: List[str],
        strategy_type: str = 'weekly',
        email_config: Optional[Dict] = None,
        poll_interval: int = 60,
        skip_trading_time_check: bool = False
    ):
        """
        初始化监控器
        
        Args:
            symbols: 股票代码列表
            strategy_type: 策略类型 (macd/weekly/multi_timeframe)
            email_config: 邮件配置
            poll_interval: 轮询间隔（秒）
            skip_trading_time_check: 是否跳过交易时间检查
        """
        self.symbols = symbols
        self.strategy_type = strategy_type
        self.poll_interval = poll_interval
        self.skip_trading_time_check = skip_trading_time_check
        
        # 状态
        self._running = False
        self._last_signals: Dict[str, str] = {}  # 上次信号缓存，避免重复通知
        self._today_signals: List[Dict] = []      # 今日信号记录
        
        # 初始化组件
        self._init_strategy()
        self._init_data_service()
        self._init_notifier(email_config)
        
        # 信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _init_strategy(self):
        """初始化策略"""
        logger.info(f"加载策略: {self.strategy_type}")
        
        if self.strategy_type == 'weekly':
            from src.strategy.macd_weekly import WeeklyMACDStrategy
            self.strategy = WeeklyMACDStrategy()
        elif self.strategy_type == 'multi_timeframe':
            from src.strategy.macd_multi_timeframe import MultiTimeframeMACDStrategy
            self.strategy = MultiTimeframeMACDStrategy()
        else:
            from src.strategy.macd import MACDStrategy
            self.strategy = MACDStrategy()
        
        self.strategy.initialize()
        logger.info(f"策略已加载: {self.strategy.name}")
    
    def _init_data_service(self):
        """初始化数据服务"""
        from src.data.market import MarketDataService, DataSource
        
        self.data_service = MarketDataService(source=DataSource.BAOSTOCK)
        logger.info("数据服务已初始化 (BaoStock)")
    
    def _init_notifier(self, email_config: Optional[Dict]):
        """初始化邮件通知器"""
        self.notifier = None
        
        if email_config and email_config.get('recipients'):
            from src.notification.email_notifier import EmailNotifier, EmailConfig
            
            config = EmailConfig(
                smtp_server=email_config.get('smtp_server', 'smtp.qq.com'),
                smtp_port=email_config.get('smtp_port', 465),
                username=email_config.get('username', ''),
                password=email_config.get('password', ''),
                recipients=email_config.get('recipients', []),
                use_ssl=email_config.get('use_ssl', True)
            )
            
            self.notifier = EmailNotifier(config)
            
            # 测试连接
            if self.notifier.test_connection():
                logger.info(f"邮件通知已启用，收件人: {config.recipients}")
            else:
                logger.warning("邮件连接测试失败，请检查配置")
        else:
            logger.info("未配置邮件通知，仅输出到控制台")
    
    def _signal_handler(self, signum, frame):
        """处理系统信号"""
        logger.info(f"收到信号 {signum}，正在停止...")
        self.stop()
    
    def start(self):
        """启动监控"""
        self._running = True
        
        logger.info("=" * 60)
        logger.info("🚀 实时行情监控系统启动")
        logger.info("=" * 60)
        logger.info(f"监控标的: {self.symbols}")
        logger.info(f"策略类型: {self.strategy_type}")
        logger.info(f"刷新间隔: {self.poll_interval}秒")
        logger.info(f"交易时间检查: {'跳过' if self.skip_trading_time_check else '启用'}")
        logger.info("=" * 60)
        
        # 发送启动通知
        if self.notifier:
            self.notifier.send_alert(
                "监控系统启动",
                f"开始监控: {', '.join(self.symbols)}，策略: {self.strategy_type}"
            )
        
        # 主循环
        self._run_loop()
    
    def stop(self):
        """停止监控"""
        self._running = False
        logger.info("监控系统已停止")
        
        # 发送停止通知和每日汇总
        if self.notifier and self._today_signals:
            self.notifier.send_daily_summary(
                portfolio_value=0,
                daily_pnl=0,
                positions=[],
                signals=self._today_signals
            )
    
    def _run_loop(self):
        """主循环"""
        while self._running:
            try:
                # 检查交易时间
                if not self.skip_trading_time_check and not self._is_trading_time():
                    wait_time = self._get_wait_time_to_trading()
                    if wait_time > 300:  # 超过5分钟才打印
                        logger.info(f"非交易时间，等待 {wait_time // 60} 分钟后开盘...")
                        time_module.sleep(min(wait_time, 300))  # 最多等5分钟再检查
                    else:
                        time_module.sleep(60)
                    continue
                
                # 处理每个标的
                for symbol in self.symbols:
                    try:
                        self._process_symbol(symbol)
                    except Exception as e:
                        logger.error(f"处理 {symbol} 时出错: {e}")
                
                # 等待下次轮询
                time_module.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"循环异常: {e}")
                time_module.sleep(10)
    
    def _process_symbol(self, symbol: str):
        """
        处理单个标的
        
        Args:
            symbol: 股票代码
        """
        logger.debug(f"处理 {symbol}...")
        
        # 获取行情数据
        data = self._get_market_data(symbol)
        
        if data is None or data.empty:
            logger.warning(f"无法获取 {symbol} 行情数据")
            return
        
        # 计算指标
        data = self.strategy.calculate_indicators(data)
        
        # 获取当前价格和指标值
        current_price = data['close'].iloc[-1]
        
        # 获取 MACD 指标（根据策略类型）
        macd_info = self._get_macd_info(data)
        
        # 生成信号
        signal_result = self._generate_signal(symbol, data)
        
        # 输出信息
        self._print_status(symbol, current_price, macd_info, signal_result)
        
        # 处理信号
        if signal_result and signal_result['type'] != 'HOLD':
            self._handle_signal(symbol, current_price, signal_result, macd_info)
    
    def _get_market_data(self, symbol: str):
        """获取行情数据"""
        import pandas as pd
        
        # 根据策略类型确定需要的数据量
        if self.strategy_type == 'weekly':
            # 周线策略需要更多历史数据
            lookback_days = 730  # 约2年
        else:
            lookback_days = 365
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)
        
        try:
            # 使用数据服务获取数据
            data = self.data_service.get_history(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date
            )
            
            if data is None or data.empty:
                logger.warning(f"{symbol} 无数据")
                return None
            
            return data
            
        except Exception as e:
            logger.error(f"获取 {symbol} 数据失败: {e}")
            return None
    
    def _get_macd_info(self, data) -> Dict[str, Any]:
        """提取 MACD 指标信息"""
        info = {}
        
        # 根据策略类型获取指标
        if self.strategy_type == 'weekly':
            # 周线策略的指标在 _weekly_data 中
            if hasattr(self.strategy, '_weekly_data') and self.strategy._weekly_data is not None:
                weekly = self.strategy._weekly_data
                if 'macd' in weekly.columns:
                    info['MACD'] = weekly['macd'].iloc[-1]
                if 'signal' in weekly.columns:
                    info['Signal'] = weekly['signal'].iloc[-1]
                if 'histogram' in weekly.columns:
                    info['Histogram'] = weekly['histogram'].iloc[-1]
                
                # 判断金叉/死叉
                if 'golden_cross' in weekly.columns and weekly['golden_cross'].iloc[-1]:
                    info['Cross'] = '金叉 ✨'
                elif 'death_cross' in weekly.columns and weekly['death_cross'].iloc[-1]:
                    info['Cross'] = '死叉 ⚠️'
                elif 'is_golden' in weekly.columns:
                    info['Cross'] = '多头' if weekly['is_golden'].iloc[-1] else '空头'
        else:
            # 日线策略的指标在 data 中
            if 'macd' in data.columns:
                info['MACD'] = data['macd'].iloc[-1]
            if 'signal' in data.columns:
                info['Signal'] = data['signal'].iloc[-1]
            if 'histogram' in data.columns:
                info['Histogram'] = data['histogram'].iloc[-1]
            
            # 判断金叉/死叉
            if 'macd' in data.columns and 'signal' in data.columns:
                if len(data) >= 2:
                    prev_diff = data['macd'].iloc[-2] - data['signal'].iloc[-2]
                    curr_diff = data['macd'].iloc[-1] - data['signal'].iloc[-1]
                    
                    if prev_diff < 0 and curr_diff > 0:
                        info['Cross'] = '金叉 ✨'
                    elif prev_diff > 0 and curr_diff < 0:
                        info['Cross'] = '死叉 ⚠️'
                    elif curr_diff > 0:
                        info['Cross'] = '多头'
                    else:
                        info['Cross'] = '空头'
        
        return info
    
    def _generate_signal(self, symbol: str, data) -> Optional[Dict]:
        """生成交易信号"""
        try:
            # 构建策略上下文
            from src.strategy.base import StrategyContext
            from src.core.models import Position, Portfolio
            
            # 模拟空持仓
            initial_capital = 1000000
            portfolio = Portfolio(
                cash=initial_capital,
                total_value=initial_capital,
                positions={},
                initial_capital=initial_capital
            )
            position = None
            
            context = StrategyContext(
                symbol=symbol,
                portfolio=portfolio,
                position=position,
                params=self.strategy.params
            )
            
            # 生成信号
            signal = self.strategy.generate_signal(data, context)
            
            return {
                'type': signal.signal_type.name,
                'price': signal.price,
                'reason': signal.reason,
                'strength': signal.strength
            }
            
        except Exception as e:
            logger.error(f"生成信号失败: {e}")
            return None
    
    def _print_status(
        self,
        symbol: str,
        price: float,
        macd_info: Dict,
        signal: Optional[Dict]
    ):
        """打印状态信息"""
        now = datetime.now().strftime('%H:%M:%S')
        
        # 信号颜色
        if signal:
            if signal['type'] == 'BUY':
                signal_str = f"\033[92m🟢 买入\033[0m"
            elif signal['type'] == 'SELL':
                signal_str = f"\033[91m🔴 卖出\033[0m"
            else:
                signal_str = "⚪ 观望"
        else:
            signal_str = "⚪ 无信号"
        
        # MACD 信息
        macd_str = ""
        if macd_info:
            cross = macd_info.get('Cross', '')
            hist = macd_info.get('Histogram', 0)
            macd_str = f"[{cross}] Hist={hist:.4f}"
        
        print(f"[{now}] {symbol:<12} ¥{price:>8.2f} | {signal_str:<15} | {macd_str}")
    
    def _handle_signal(
        self,
        symbol: str,
        price: float,
        signal: Dict,
        macd_info: Dict
    ):
        """处理交易信号"""
        signal_type = signal['type']
        reason = signal['reason']
        
        # 检查是否与上次信号相同（避免重复通知）
        last_signal = self._last_signals.get(symbol)
        
        if last_signal == signal_type:
            logger.debug(f"{symbol} 信号未变化，跳过通知")
            return
        
        # 更新信号缓存
        self._last_signals[symbol] = signal_type
        
        # 记录今日信号
        self._today_signals.append({
            'time': datetime.now().strftime('%H:%M:%S'),
            'symbol': symbol,
            'type': signal_type,
            'price': price,
            'reason': reason
        })
        
        # 打印醒目提示
        logger.info("=" * 60)
        logger.info(f"🚨 新信号: {symbol} {signal_type} @ ¥{price:.2f}")
        logger.info(f"原因: {reason}")
        logger.info("=" * 60)
        
        # 发送邮件通知
        if self.notifier:
            self.notifier.send_signal(
                symbol=symbol,
                signal_type=signal_type,
                price=price,
                reason=reason,
                additional_info=macd_info
            )
    
    def _is_trading_time(self) -> bool:
        """检查是否在交易时间内"""
        now = datetime.now()
        current_time = now.time()
        
        # A股交易时间: 9:30-11:30, 13:00-15:00
        morning_start = time(9, 30)
        morning_end = time(11, 30)
        afternoon_start = time(13, 0)
        afternoon_end = time(15, 0)
        
        is_morning = morning_start <= current_time <= morning_end
        is_afternoon = afternoon_start <= current_time <= afternoon_end
        
        # 检查是否工作日
        is_weekday = now.weekday() < 5
        
        return is_weekday and (is_morning or is_afternoon)
    
    def _get_wait_time_to_trading(self) -> int:
        """计算距离下次交易时间的秒数"""
        now = datetime.now()
        current_time = now.time()
        
        # 今天的交易时间点
        morning_start = datetime.combine(now.date(), time(9, 30))
        afternoon_start = datetime.combine(now.date(), time(13, 0))
        
        # 如果是工作日
        if now.weekday() < 5:
            if current_time < time(9, 30):
                # 早盘前
                return int((morning_start - now).total_seconds())
            elif time(11, 30) < current_time < time(13, 0):
                # 午休
                return int((afternoon_start - now).total_seconds())
            elif current_time > time(15, 0):
                # 收盘后，等明天
                pass
        
        # 计算下一个交易日开盘时间
        next_trading_day = now
        while True:
            next_trading_day += timedelta(days=1)
            if next_trading_day.weekday() < 5:
                break
        
        next_open = datetime.combine(next_trading_day.date(), time(9, 30))
        return int((next_open - now).total_seconds())


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='MACD 实时行情监控与邮件通知系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基本用法（仅控制台输出）
  python realtime_monitor.py --symbols 002050.SZ

  # 启用邮件通知（QQ邮箱）
  python realtime_monitor.py \\
      --symbols 002050.SZ,000001.SZ \\
      --email your@email.com \\
      --smtp-user your@qq.com \\
      --smtp-pass your_auth_code

  # 跳过交易时间检查（测试用）
  python realtime_monitor.py --symbols 002050.SZ --skip-trading-time-check

邮箱配置说明:
  - QQ邮箱: smtp.qq.com:465, 需要使用授权码（非登录密码）
  - 163邮箱: smtp.163.com:465
  - Gmail: smtp.gmail.com:587
        """
    )
    
    # 基本参数
    parser.add_argument(
        '--symbols', '-s',
        required=True,
        help='股票代码，多个用逗号分隔 (如: 002050.SZ,000001.SZ)'
    )
    parser.add_argument(
        '--strategy',
        default='weekly',
        choices=['macd', 'weekly', 'multi_timeframe'],
        help='策略类型 (默认: weekly)'
    )
    parser.add_argument(
        '--interval', '-i',
        type=int,
        default=60,
        help='刷新间隔秒数 (默认: 60)'
    )
    parser.add_argument(
        '--skip-trading-time-check',
        action='store_true',
        help='跳过交易时间检查（测试用）'
    )
    
    # 邮件参数
    parser.add_argument(
        '--email', '-e',
        help='接收通知的邮箱地址'
    )
    parser.add_argument(
        '--smtp-server',
        default='smtp.qq.com',
        help='SMTP服务器 (默认: smtp.qq.com)'
    )
    parser.add_argument(
        '--smtp-port',
        type=int,
        default=465,
        help='SMTP端口 (默认: 465)'
    )
    parser.add_argument(
        '--smtp-user',
        help='SMTP用户名（发件邮箱）'
    )
    parser.add_argument(
        '--smtp-pass',
        help='SMTP密码/授权码'
    )
    
    # 其他参数
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='详细输出'
    )
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # 创建日志目录
    os.makedirs('logs', exist_ok=True)
    
    # 解析股票代码
    symbols = [s.strip() for s in args.symbols.split(',')]
    
    # 构建邮件配置
    email_config = None
    if args.email:
        email_config = {
            'smtp_server': args.smtp_server,
            'smtp_port': args.smtp_port,
            'username': args.smtp_user or '',
            'password': args.smtp_pass or '',
            'recipients': [args.email],
            'use_ssl': True
        }
    
    # 创建并启动监控器
    monitor = RealtimeMonitor(
        symbols=symbols,
        strategy_type=args.strategy,
        email_config=email_config,
        poll_interval=args.interval,
        skip_trading_time_check=args.skip_trading_time_check
    )
    
    monitor.start()


if __name__ == '__main__':
    main()
