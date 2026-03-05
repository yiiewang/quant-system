"""
MACD 指标计算与绘图测试
使用三花智控 (002050.SZ) 股票数据绘制 MACD 图

数据来源: 本地 SQLite 数据库 (data/market.db)
"""
import unittest
import sys
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'src'))

from src.strategy.macd import MACDStrategy


# 本地数据库文件路径
LOCAL_DB_FILE = project_root / 'data' / 'market.db'


class TestMACDPlot(unittest.TestCase):
    """MACD 指标绘图测试"""
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化 - 从本地 SQLite 数据库加载三花智控数据"""
        cls.symbol = "002050.SZ"  # 三花智控
        cls.symbol_name = "三花智控"
        
        # 检查本地数据库文件是否存在
        if not LOCAL_DB_FILE.exists():
            raise unittest.SkipTest(f"本地数据库文件不存在: {LOCAL_DB_FILE}")
        
        # 从本地数据库读取数据
        print(f"\n正在从本地数据库加载 {cls.symbol_name} ({cls.symbol}) 数据...")
        print(f"数据库文件: {LOCAL_DB_FILE}")
        
        conn = sqlite3.connect(str(LOCAL_DB_FILE))
        query = f"SELECT * FROM ohlcv WHERE symbol = '{cls.symbol}' ORDER BY date"
        cls.data = pd.read_sql_query(query, conn)
        conn.close()
        
        # 转换日期列类型
        cls.data['date'] = pd.to_datetime(cls.data['date'])
        
        if cls.data.empty:
            raise unittest.SkipTest(f"数据库中没有 {cls.symbol} 的数据")
        
        print(f"加载到 {len(cls.data)} 条数据")
        print(f"时间范围: {cls.data['date'].min().strftime('%Y-%m-%d')} ~ {cls.data['date'].max().strftime('%Y-%m-%d')}")
    
    def setUp(self):
        """每个测试方法前初始化"""
        # 创建 MACD 策略实例
        self.strategy = MACDStrategy()
    
    def test_calculate_indicators(self):
        """测试 MACD 指标计算"""
        # 计算指标
        df = self.strategy.calculate_indicators(self.data.copy())
        
        # 验证新增列存在
        expected_columns = ['ema_fast', 'ema_slow', 'macd', 'signal', 'histogram', 
                          'volume_ma', 'volume_ratio', 'macd_cross']
        for col in expected_columns:
            self.assertIn(col, df.columns, f"缺少列: {col}")
        
        # 验证数据非空
        self.assertFalse(df['macd'].isna().all(), "MACD 全为空")
        self.assertFalse(df['signal'].isna().all(), "Signal 全为空")
        
        print(f"\n最新指标值:")
        print(f"  MACD (DIF): {df['macd'].iloc[-1]:.4f}")
        print(f"  Signal (DEA): {df['signal'].iloc[-1]:.4f}")
        print(f"  Histogram: {df['histogram'].iloc[-1]:.4f}")
    
    def test_plot_macd(self):
        """测试绘制三花智控 MACD 图"""
        # 计算指标
        df = self.strategy.calculate_indicators(self.data.copy())
        
        # 创建图形
        fig = plt.figure(figsize=(14, 10))
        gs = GridSpec(4, 1, height_ratios=[3, 1, 1, 1], hspace=0.05)
        
        # 设置字体 (使用英文避免中文字体问题)
        plt.rcParams['axes.unicode_minus'] = False
        
        # 子图1: K线图 + EMA
        ax1 = fig.add_subplot(gs[0])
        ax1.set_title(f'{self.symbol_name} ({self.symbol}) MACD Technical Analysis', fontsize=14, fontweight='bold')
        
        # 绘制收盘价
        ax1.plot(df['date'], df['close'], label='Close', color='black', linewidth=1)
        ax1.plot(df['date'], df['ema_fast'], label=f'EMA{self.strategy.params["fast_period"]}', 
                color='blue', linewidth=0.8, alpha=0.7)
        ax1.plot(df['date'], df['ema_slow'], label=f'EMA{self.strategy.params["slow_period"]}', 
                color='orange', linewidth=0.8, alpha=0.7)
        
        # 标记金叉死叉
        golden_cross = df[df['macd_cross'] == 1]
        death_cross = df[df['macd_cross'] == -1]
        
        ax1.scatter(golden_cross['date'], golden_cross['close'], 
                   marker='^', color='red', s=100, label='Golden Cross', zorder=5)
        ax1.scatter(death_cross['date'], death_cross['close'], 
                   marker='v', color='green', s=100, label='Death Cross', zorder=5)
        
        ax1.set_ylabel('Price (CNY)')
        ax1.legend(loc='upper left', fontsize=8)
        ax1.grid(True, alpha=0.3)
        ax1.set_xlim(df['date'].min(), df['date'].max())
        
        # 子图2: MACD 柱状图
        ax2 = fig.add_subplot(gs[1], sharex=ax1)
        
        # 分离正负柱
        positive = df['histogram'] >= 0
        negative = df['histogram'] < 0
        
        ax2.bar(df.loc[positive, 'date'], df.loc[positive, 'histogram'], 
               color='red', alpha=0.7, width=0.8, label='Bullish')
        ax2.bar(df.loc[negative, 'date'], df.loc[negative, 'histogram'], 
               color='green', alpha=0.7, width=0.8, label='Bearish')
        
        ax2.axhline(y=0, color='black', linewidth=0.5)
        ax2.set_ylabel('MACD Bar')
        ax2.legend(loc='upper left', fontsize=8)
        ax2.grid(True, alpha=0.3)
        
        # 子图3: MACD 线
        ax3 = fig.add_subplot(gs[2], sharex=ax1)
        ax3.plot(df['date'], df['macd'], label='DIF (MACD)', color='blue', linewidth=1)
        ax3.plot(df['date'], df['signal'], label='DEA (Signal)', color='orange', linewidth=1)
        ax3.axhline(y=0, color='black', linewidth=0.5, linestyle='--')
        ax3.fill_between(df['date'], df['macd'], df['signal'], 
                        where=(df['macd'] >= df['signal']), 
                        color='red', alpha=0.2)
        ax3.fill_between(df['date'], df['macd'], df['signal'], 
                        where=(df['macd'] < df['signal']), 
                        color='green', alpha=0.2)
        ax3.set_ylabel('MACD')
        ax3.legend(loc='upper left', fontsize=8)
        ax3.grid(True, alpha=0.3)
        
        # 子图4: 成交量
        ax4 = fig.add_subplot(gs[3], sharex=ax1)
        
        # 根据涨跌着色
        colors = ['red' if df['close'].iloc[i] >= df['open'].iloc[i] else 'green' 
                 for i in range(len(df))]
        ax4.bar(df['date'], df['volume'] / 10000, color=colors, alpha=0.7, width=0.8)
        ax4.plot(df['date'], df['volume_ma'] / 10000, color='blue', linewidth=1, 
                label='20-Day MA')
        ax4.set_ylabel('Volume (10K)')
        ax4.set_xlabel('Date')
        ax4.legend(loc='upper left', fontsize=8)
        ax4.grid(True, alpha=0.3)
        
        # 格式化 x 轴日期
        ax4.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax4.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax1.get_xticklabels(), visible=False)
        plt.setp(ax2.get_xticklabels(), visible=False)
        plt.setp(ax3.get_xticklabels(), visible=False)
        
        # 添加统计信息
        last_row = df.iloc[-1]
        stats_text = (
            f"Latest ({last_row['date'].strftime('%Y-%m-%d')}):\n"
            f"Close: {last_row['close']:.2f}\n"
            f"DIF: {last_row['macd']:.4f}\n"
            f"DEA: {last_row['signal']:.4f}\n"
            f"MACD Bar: {last_row['histogram']:.4f}\n"
            f"Vol Ratio: {last_row['volume_ratio']:.2f}"
        )
        
        # 在右上角添加文本框
        props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
        ax1.text(0.98, 0.98, stats_text, transform=ax1.transAxes, fontsize=9,
                verticalalignment='top', horizontalalignment='right', bbox=props)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图片
        output_dir = Path(__file__).parent.parent / 'output'
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / f'{self.symbol}_macd.png'
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"\n图表已保存至: {output_path}")
        
        # 显示图片（在非交互式环境中会跳过）
        try:
            plt.show()
        except Exception:
            pass
        
        plt.close()
        
        # 验证图片已生成
        self.assertTrue(output_path.exists(), "图片未生成")
    
    def test_golden_death_cross_stats(self):
        """测试金叉死叉统计"""
        df = self.strategy.calculate_indicators(self.data.copy())
        
        golden_crosses = df[df['macd_cross'] == 1]
        death_crosses = df[df['macd_cross'] == -1]
        
        print(f"\n=== {self.symbol_name} 金叉死叉统计 ===")
        print(f"金叉次数: {len(golden_crosses)}")
        print(f"死叉次数: {len(death_crosses)}")
        
        if not golden_crosses.empty:
            print(f"\n最近金叉日期:")
            for _, row in golden_crosses.tail(3).iterrows():
                print(f"  {row['date'].strftime('%Y-%m-%d')} - 收盘价: ¥{row['close']:.2f}")
        
        if not death_crosses.empty:
            print(f"\n最近死叉日期:")
            for _, row in death_crosses.tail(3).iterrows():
                print(f"  {row['date'].strftime('%Y-%m-%d')} - 收盘价: ¥{row['close']:.2f}")


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
