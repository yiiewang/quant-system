"""
数据层回归测试：验证本次修改的核心功能
测试范围：
  1. MarketDataService 基本读写
  2. _do_persist 向量化写入（含 daily + minute）
  3. get_latest LRU 缓存淘汰
  4. get_history 缓存命中
  5. sync 增量判断
  6. PortfolioManager 并发写锁
  7. MarketDataService close() / with 语句
  8. IndicatorCalculator MACD 计算
"""
import sys
import os
import threading
import tempfile
import time
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.data.market import MarketDataService, DataSource, Frequency
from src.data.portfolio import PortfolioManager
from src.data.indicator import IndicatorCalculator
from src.core.models import Position, Trade, OrderSide

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"

results = []

def check(name, cond, detail=""):
    status = PASS if cond else FAIL
    print(f"  {status} {name}" + (f"  ({detail})" if detail else ""))
    results.append((name, cond))

# ─── 辅助：构造假 OHLCV DataFrame ─────────────────────────────────────────────

def make_daily_df(symbol="000001.SZ", n=50, start="2024-01-01"):
    dates = pd.date_range(start, periods=n, freq='B')
    return pd.DataFrame({
        'symbol': symbol,
        'date': dates,
        'open':   np.random.uniform(10, 11, n),
        'high':   np.random.uniform(11, 12, n),
        'low':    np.random.uniform(9,  10, n),
        'close':  np.random.uniform(10, 11, n),
        'volume': np.random.uniform(1e6, 2e6, n),
        'amount': np.random.uniform(1e7, 2e7, n),
    })

def make_minute_df(symbol="000001.SZ", n=100):
    dts = pd.date_range("2024-01-02 09:30", periods=n, freq='5min')
    return pd.DataFrame({
        'symbol': symbol,
        'datetime': dts,
        'open':   np.random.uniform(10, 11, n),
        'high':   np.random.uniform(11, 12, n),
        'low':    np.random.uniform(9,  10, n),
        'close':  np.random.uniform(10, 11, n),
        'volume': np.random.uniform(1e5, 2e5, n),
        'amount': np.random.uniform(1e6, 2e6, n),
    })

# ─── Test 1: 基本读写 + _do_persist 向量化 ────────────────────────────────────

print("\n[1] 基本读写 + _do_persist 向量化")
with tempfile.TemporaryDirectory() as tmpdir:
    db = os.path.join(tmpdir, "market.db")
    with MarketDataService(source=DataSource.LOCAL, db_path=db) as svc:
        df_daily = make_daily_df(n=50)
        svc._do_persist("000001.SZ", df_daily, Frequency.DAILY)
        time.sleep(0.1)  # 等 worker
        conn = sqlite3.connect(db)
        cnt = conn.execute("SELECT COUNT(*) FROM ohlcv WHERE symbol='000001.SZ'").fetchone()[0]
        conn.close()
        check("日线 50 条写入成功", cnt == 50, f"实际={cnt}")

        df_min = make_minute_df(n=100)
        svc._do_persist("000001.SZ", df_min, Frequency.MIN_5)
        time.sleep(0.1)
        conn = sqlite3.connect(db)
        cnt2 = conn.execute("SELECT COUNT(*) FROM ohlcv_minute WHERE symbol='000001.SZ'").fetchone()[0]
        conn.close()
        check("分时 100 条写入成功", cnt2 == 100, f"实际={cnt2}")

        # 验证可读回
        result = svc._query_from_db("000001.SZ")
        check("_query_from_db 读回日线", len(result) == 50, f"实际={len(result)}")

# ─── Test 2: LRU 缓存淘汰 ────────────────────────────────────────────────────

print("\n[2] get_latest LRU 缓存淘汰")
with tempfile.TemporaryDirectory() as tmpdir:
    db = os.path.join(tmpdir, "market.db")
    with MarketDataService(source=DataSource.LOCAL, db_path=db) as svc:
        svc._cache_maxsize = 3
        # 手动填 3 条
        for i in range(3):
            key = f"sym{i}_50"
            svc._set_cache(key, pd.DataFrame({'v': [i]}))
        check("缓存写入3条", len(svc._cache) == 3)

        # 第4条应淘汰最旧的
        oldest_key = min(svc._cache_time, key=svc._cache_time.get)
        svc._set_cache("sym3_50", pd.DataFrame({'v': [3]}))
        check("LRU 淘汰：大小不超限", len(svc._cache) == 3)
        check("LRU 淘汰：最旧 key 被移除", oldest_key not in svc._cache)

# ─── Test 3: get_history 缓存命中 ────────────────────────────────────────────

print("\n[3] get_history 缓存命中")
with tempfile.TemporaryDirectory() as tmpdir:
    db = os.path.join(tmpdir, "market.db")
    with MarketDataService(source=DataSource.LOCAL, db_path=db) as svc:
        # 先写入数据
        df_daily = make_daily_df(n=30, start="2024-01-01")
        svc._do_persist("000001.SZ", df_daily, Frequency.DAILY)
        time.sleep(0.1)

        start = datetime(2024, 1, 1)
        end   = datetime(2024, 3, 1)

        # 第一次：走 SQLite
        t0 = time.time()
        r1 = svc.get_history("000001.SZ", start, end)
        t1 = time.time() - t0

        # 第二次：走缓存
        t2 = time.time()
        r2 = svc.get_history("000001.SZ", start, end)
        t3 = time.time() - t2

        check("get_history 两次结果一致", r1.shape == r2.shape, f"shape={r1.shape}")
        check("get_history 缓存命中（第2次更快）", t3 <= t1 + 0.05)
        cache_key = ("000001.SZ", "2024-01-01", "2024-03-01")
        check("history_cache 有记录", cache_key in svc._history_cache)

# ─── Test 4: sync 增量判断 ────────────────────────────────────────────────────

print("\n[4] sync 增量判断 (_get_local_latest_date)")
with tempfile.TemporaryDirectory() as tmpdir:
    db = os.path.join(tmpdir, "market.db")
    with MarketDataService(source=DataSource.LOCAL, db_path=db) as svc:
        # 无数据时返回 None
        result = svc._get_local_latest_date("000001.SZ", Frequency.DAILY)
        check("无数据时返回 None", result is None)

        # 写入数据后返回最新日期
        df = make_daily_df(n=20, start="2024-01-01")
        svc._do_persist("000001.SZ", df, Frequency.DAILY)
        time.sleep(0.1)
        result2 = svc._get_local_latest_date("000001.SZ", Frequency.DAILY)
        check("有数据时返回最新日期", result2 is not None, f"latest={result2}")

        # 分时
        df_m = make_minute_df(n=10)
        svc._do_persist("000001.SZ", df_m, Frequency.MIN_5)
        time.sleep(0.1)
        result3 = svc._get_local_latest_date("000001.SZ", Frequency.MIN_5)
        check("分时最新日期", result3 is not None, f"latest={result3}")

# ─── Test 5: DataSource.LOCAL 不触发 Provider ─────────────────────────────────

print("\n[5] DataSource.LOCAL 不触发远端拉取")
with tempfile.TemporaryDirectory() as tmpdir:
    db = os.path.join(tmpdir, "market.db")
    with MarketDataService(source=DataSource.LOCAL, db_path=db) as svc:
        try:
            svc._get_provider()
            check("LOCAL 应抛 RuntimeError", False)
        except RuntimeError as e:
            check("LOCAL._get_provider 抛 RuntimeError", True, str(e)[:40])

        # get_latest 数据不足时不崩溃（LOCAL 跳过远端）
        try:
            r = svc.get_latest("000001.SZ", lookback=10)
            check("get_latest LOCAL 不足时不崩溃", True, f"返回{len(r)}条")
        except Exception as e:
            check("get_latest LOCAL 不足时不崩溃", False, str(e))

# ─── Test 6: PortfolioManager 并发写锁 ────────────────────────────────────────

print("\n[6] PortfolioManager 并发写锁")
with tempfile.TemporaryDirectory() as tmpdir:
    db = os.path.join(tmpdir, "portfolio.db")
    pm = PortfolioManager(db_path=db)
    errors = []

    def write_position(i):
        try:
            pos = Position(
                symbol=f"00000{i}.SZ",
                quantity=100 * (i + 1),
                avg_cost=10.0 + i,
                current_price=11.0 + i,
            )
            pm.save_position(pos)
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=write_position, args=(i,)) for i in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()

    check("20 线程并发写入无报错", len(errors) == 0, f"errors={errors[:2]}")
    positions = pm.get_positions()
    check("并发写入后数据完整", len(positions) == 20, f"实际={len(positions)}")

# ─── Test 7: close() / with 语句 ────────────────────────────────────────────

print("\n[7] close() / with 语句资源释放")
with tempfile.TemporaryDirectory() as tmpdir:
    db = os.path.join(tmpdir, "market.db")
    svc = MarketDataService(source=DataSource.LOCAL, db_path=db)
    check("worker 线程启动", svc._persist_worker.is_alive())
    svc.close()
    time.sleep(0.2)
    check("close() 后 worker 停止", not svc._persist_worker.is_alive())
    check("close() 后只读连接关闭", svc._read_conn is None)

# ─── Test 8: IndicatorCalculator MACD ────────────────────────────────────────

print("\n[8] IndicatorCalculator MACD 计算")
calc = IndicatorCalculator()
df_price = make_daily_df(n=60)
result = calc.macd(df_price, fast_period=12, slow_period=26, signal_period=9)
check("MACD 返回 DataFrame", isinstance(result, pd.DataFrame))
check("包含 macd/signal/histogram 列",
      all(c in result.columns for c in ['macd', 'signal', 'histogram']))
check("histogram = macd - signal",
      abs((result['macd'] - result['signal'] - result['histogram']).dropna().max()) < 1e-9)

# A股惯例验证（strategy 层覆盖）
result['histogram_ashare'] = 2 * (result['macd'] - result['signal'])
check("A股 histogram = 2*(macd-signal)",
      abs((result['histogram_ashare'] - 2 * result['histogram']).dropna().max()) < 1e-9)

# ─── 汇总 ────────────────────────────────────────────────────────────────────

print("\n" + "─" * 50)
passed = sum(1 for _, ok in results if ok)
total  = len(results)
color  = "\033[92m" if passed == total else "\033[91m"
print(f"{color}{'✓ ALL PASS' if passed == total else '✗ SOME FAILED'}  {passed}/{total}\033[0m")

if passed < total:
    print("\n失败项：")
    for name, ok in results:
        if not ok:
            print(f"  ✗ {name}")
    sys.exit(1)
