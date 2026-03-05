#!/usr/bin/env python3
"""
调试多周期策略
"""
import sys
sys.path.insert(0, '.')

from datetime import datetime
from src.strategy.macd_multi_timeframe import MultiTimeframeMACDStrategy
from src.data.market import MarketDataService, DataSource

def main():
    # 初始化数据服务
    service = MarketDataService(source=DataSource.LOCAL)
    
    # 获取数据
    symbol = '002050.SZ'
    start = datetime(2020, 1, 1)
    end = datetime(2025, 12, 31)
    
    print(f"加载数据: {symbol}, {start.date()} ~ {end.date()}")
    data = service.get_history(symbol, start, end)
    print(f"数据条数: {len(data)}")
    
    if data.empty:
        print("无数据！")
        return
    
    # 初始化策略
    strategy = MultiTimeframeMACDStrategy({
        'fast_period': 12,
        'slow_period': 26,
        'signal_period': 9,
        'require_monthly_golden': True,
        'require_weekly_golden': True,
    })
    strategy.initialize()
    
    # 计算指标
    print("\n计算指标...")
    df = strategy.calculate_indicators(data)
    
    # 检查周线/月线指标
    print("\n=== 周线指标 ===")
    print(f"周线数据条数: {len(strategy._weekly_data) if strategy._weekly_data is not None else 0}")
    print(f"周线指标: {strategy._weekly_indicators}")
    
    print("\n=== 月线指标 ===")
    print(f"月线数据条数: {len(strategy._monthly_data) if strategy._monthly_data is not None else 0}")
    print(f"月线指标: {strategy._monthly_indicators}")
    
    # 检查多周期趋势
    is_uptrend, trend_desc = strategy.check_multi_timeframe_trend()
    print(f"\n多周期趋势: is_uptrend={is_uptrend}, {trend_desc}")
    
    # 统计日线金叉数量
    golden_cross_count = df['golden_cross'].sum()
    death_cross_count = df['death_cross'].sum()
    print(f"\n日线金叉次数: {golden_cross_count}")
    print(f"日线死叉次数: {death_cross_count}")
    
    # 找出所有日线金叉的日期
    golden_crosses = df[df['golden_cross'] == True]
    print(f"\n日线金叉日期:")
    for idx, row in golden_crosses.iterrows():
        date = row.get('date', idx)
        print(f"  {date}: MACD={row['macd']:.4f}")
    
    # 检查月线和周线在不同日期的状态
    print("\n=== 检查月线周线状态变化 ===")
    
    # 在几个关键日期检查状态
    key_dates = [
        datetime(2023, 3, 1),
        datetime(2023, 6, 1),
        datetime(2023, 9, 1),
        datetime(2024, 1, 1),
        datetime(2024, 6, 1),
        datetime(2025, 1, 1),
    ]
    
    for check_date in key_dates:
        mask = data['date'] <= check_date
        available_data = data[mask].copy()
        
        if len(available_data) < 60:
            continue
        
        # 重新计算指标
        _ = strategy.calculate_indicators(available_data)
        
        monthly_golden = strategy._monthly_indicators.get('is_golden', None)
        weekly_golden = strategy._weekly_indicators.get('is_golden', None)
        
        status = ""
        if monthly_golden is not None:
            status += "月线金叉✓ " if monthly_golden else "月线死叉✗ "
        if weekly_golden is not None:
            status += "周线金叉✓" if weekly_golden else "周线死叉✗"
        
        print(f"  {check_date.date()}: {status}")

if __name__ == "__main__":
    main()
