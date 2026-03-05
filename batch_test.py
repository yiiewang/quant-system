#!/usr/bin/env python3.8
"""
批量回测股票 - 周线策略对比
"""
import sys
import subprocess
import re
from typing import List, Tuple, Dict

# 测试股票列表
STOCKS = [
    ("002050.SZ", "三花智控"),
    ("000651.SZ", "格力电器"),
    ("600588.SH", "用友网络"),
    ("002594.SZ", "比亚迪"),
    ("300750.SZ", "宁德时代"),
    ("601318.SH", "中国平安"),
    ("600036.SH", "招商银行"),
    ("300059.SZ", "东方财富"),
    ("688981.SH", "中芯国际"),
    ("601012.SH", "隆基绿能"),
]


def run_backtest(symbol: str, strategy: str) -> Dict:
    """运行回测并解析结果"""
    cmd = f"python3.8 -m src.main backtest --start 2020-01-01 --end 2025-12-31 --symbols {symbol} --strategy {strategy}"
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120
        )
        output = result.stdout + result.stderr
        
        # 解析结果
        metrics = {}
        
        # 总收益率
        match = re.search(r'总收益率:\s*([-\d.]+)%', output)
        if match:
            metrics['total_return'] = float(match.group(1))
        
        # 年化收益
        match = re.search(r'年化收益:\s*([-\d.]+)%', output)
        if match:
            metrics['annual_return'] = float(match.group(1))
        
        # 最大回撤
        match = re.search(r'最大回撤:\s*([-\d.]+)%', output)
        if match:
            metrics['max_drawdown'] = float(match.group(1))
        
        # 交易次数
        match = re.search(r'交易次数:\s*(\d+)', output)
        if match:
            metrics['trade_count'] = int(match.group(1))
        
        # 夏普比率
        match = re.search(r'夏普比率:\s*([-\d.]+)', output)
        if match:
            metrics['sharpe'] = float(match.group(1))
        
        # 胜率
        match = re.search(r'胜率:\s*([-\d.]+)%', output)
        if match:
            metrics['win_rate'] = float(match.group(1))
        
        return metrics
        
    except Exception as e:
        print(f"Error: {e}")
        return {}


def main():
    print("=" * 80)
    print("📊 周线策略 vs 日线策略 批量回测对比")
    print("=" * 80)
    print(f"回测期间: 2020-01-01 ~ 2025-12-31 (约5年)")
    print(f"MACD 参数: fast=5, slow=10, signal=9")
    print("=" * 80)
    print()
    
    results = []
    
    for symbol, name in STOCKS:
        print(f"\n🔄 测试: {name} ({symbol})")
        print("-" * 40)
        
        # 周线策略
        print(f"   运行周线策略...")
        weekly_metrics = run_backtest(symbol, "weekly")
        
        # 日线策略
        print(f"   运行日线策略...")
        daily_metrics = run_backtest(symbol, "macd")
        
        if weekly_metrics and daily_metrics:
            results.append({
                'symbol': symbol,
                'name': name,
                'weekly': weekly_metrics,
                'daily': daily_metrics
            })
            
            # 打印对比
            print(f"\n   {'指标':<12} {'周线策略':>12} {'日线策略':>12} {'差值':>12}")
            print(f"   {'-'*48}")
            
            w = weekly_metrics
            d = daily_metrics
            
            print(f"   {'总收益率':<10} {w.get('total_return', 0):>10.2f}% {d.get('total_return', 0):>10.2f}% {w.get('total_return', 0) - d.get('total_return', 0):>+10.2f}%")
            print(f"   {'年化收益':<10} {w.get('annual_return', 0):>10.2f}% {d.get('annual_return', 0):>10.2f}% {w.get('annual_return', 0) - d.get('annual_return', 0):>+10.2f}%")
            print(f"   {'最大回撤':<10} {w.get('max_drawdown', 0):>10.2f}% {d.get('max_drawdown', 0):>10.2f}% {w.get('max_drawdown', 0) - d.get('max_drawdown', 0):>+10.2f}%")
            print(f"   {'交易次数':<10} {w.get('trade_count', 0):>10d}  {d.get('trade_count', 0):>10d}  {w.get('trade_count', 0) - d.get('trade_count', 0):>+10d}")
            print(f"   {'夏普比率':<10} {w.get('sharpe', 0):>10.2f}  {d.get('sharpe', 0):>10.2f}  {w.get('sharpe', 0) - d.get('sharpe', 0):>+10.2f}")
            print(f"   {'胜率':<12} {w.get('win_rate', 0):>10.2f}% {d.get('win_rate', 0):>10.2f}% {w.get('win_rate', 0) - d.get('win_rate', 0):>+10.2f}%")
    
    # 汇总
    print("\n" + "=" * 80)
    print("📈 汇总对比")
    print("=" * 80)
    
    if results:
        # 表头
        print(f"\n{'股票':<12} {'周线收益':>10} {'日线收益':>10} {'周线回撤':>10} {'日线回撤':>10} {'周线胜率':>10} {'日线胜率':>10}")
        print("-" * 72)
        
        weekly_wins = 0
        total_weekly_return = 0
        total_daily_return = 0
        
        for r in results:
            name = r['name'][:6]
            w = r['weekly']
            d = r['daily']
            
            wr = w.get('total_return', 0)
            dr = d.get('total_return', 0)
            
            total_weekly_return += wr
            total_daily_return += dr
            
            if wr > dr:
                weekly_wins += 1
                marker = "✨"
            else:
                marker = ""
            
            print(f"{name:<10} {wr:>9.2f}% {dr:>9.2f}% {w.get('max_drawdown', 0):>9.2f}% {d.get('max_drawdown', 0):>9.2f}% {w.get('win_rate', 0):>9.2f}% {d.get('win_rate', 0):>9.2f}% {marker}")
        
        print("-" * 72)
        print(f"{'平均':<10} {total_weekly_return/len(results):>9.2f}% {total_daily_return/len(results):>9.2f}%")
        print()
        print(f"周线策略胜出: {weekly_wins}/{len(results)} 只股票 ({weekly_wins/len(results)*100:.0f}%)")
        print(f"周线平均收益: {total_weekly_return/len(results):.2f}%")
        print(f"日线平均收益: {total_daily_return/len(results):.2f}%")


if __name__ == "__main__":
    main()
