"""
持仓管理器
提供持仓数据的持久化存储和查询
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from pathlib import Path
import sqlite3
import threading
import json
import logging

from src.core.models import Position, Trade, OrderSide

logger = logging.getLogger(__name__)


class PortfolioManager:
    """
    持仓管理器

    提供持仓和交易记录的持久化存储功能

    Usage:
        pm = PortfolioManager()

        # 保存持仓
        pm.save_position(position)

        # 获取持仓
        positions = pm.get_positions()

        # 保存交易
        pm.save_trade(trade)

        # 获取交易记录
        trades = pm.get_trades(limit=50)
    """

    def __init__(self, db_path: str = "data/portfolio.db"):
        """
        初始化持仓管理器

        Args:
            db_path: 数据库路径
        """
        self.db_path = db_path
        self._db_lock = threading.Lock()
        self._init_db()

        logger.info(f"初始化持仓管理器: {db_path}")

    def save_position(self, position: Position) -> None:
        """
        保存/更新持仓

        Args:
            position: 持仓对象
        """
        with self._db_lock:
            conn = sqlite3.connect(self.db_path)
            try:
                if position.quantity > 0:
                    conn.execute('''
                        INSERT OR REPLACE INTO positions
                        (symbol, quantity, avg_cost, current_price, unrealized_pnl, realized_pnl, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        position.symbol,
                        position.quantity,
                        position.avg_cost,
                        position.current_price,
                        position.unrealized_pnl,
                        position.realized_pnl,
                        datetime.now().isoformat()
                    ))
                else:
                    # 清仓时删除记录
                    conn.execute('DELETE FROM positions WHERE symbol = ?', (position.symbol,))
                conn.commit()
            finally:
                conn.close()

    def get_position(self, symbol: str) -> Optional[Position]:
        """
        获取指定持仓

        Args:
            symbol: 股票代码

        Returns:
            Optional[Position]: 持仓对象
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            'SELECT * FROM positions WHERE symbol = ?',
            (symbol,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return Position(
                symbol=row[0],
                quantity=row[1],
                avg_cost=row[2],
                current_price=row[3],
                # row[4] = unrealized_pnl（派生值，由 property 计算，不传入构造）
                realized_pnl=row[5]
            )

        return None

    def get_positions(self) -> List[Position]:
        """
        获取所有持仓

        Returns:
            List[Position]: 持仓列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM positions WHERE quantity > 0')
        rows = cursor.fetchall()
        conn.close()

        positions = []
        for row in rows:
            positions.append(Position(
                symbol=row[0],
                quantity=row[1],
                avg_cost=row[2],
                current_price=row[3],
                # row[4] = unrealized_pnl（派生值，由 property 计算，不传入构造）
                realized_pnl=row[5]
            ))

        return positions

    def save_trade(self, trade: Trade) -> None:
        """
        保存交易记录

        Args:
            trade: 交易记录
        """
        with self._db_lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute('''
                    INSERT OR REPLACE INTO trades 
                    (trade_id, order_id, symbol, side, quantity, price, commission, timestamp, strategy)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    trade.trade_id,
                    trade.order_id,
                    trade.symbol,
                    trade.side.value,
                    trade.quantity,
                    trade.price,
                    trade.commission,
                    trade.timestamp.isoformat(),
                    trade.strategy
                ))
                conn.commit()
            finally:
                conn.close()

    def get_trades(self, symbol: str = None,
                   start_date: datetime = None,
                   end_date: datetime = None,
                   limit: int = 100) -> List[Trade]:
        """
        获取交易记录

        Args:
            symbol: 股票代码过滤
            start_date: 开始日期
            end_date: 结束日期
            limit: 返回数量限制

        Returns:
            List[Trade]: 交易记录列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = 'SELECT * FROM trades WHERE 1=1'
        params = []

        if symbol:
            query += ' AND symbol = ?'
            params.append(symbol)

        if start_date:
            query += ' AND timestamp >= ?'
            params.append(start_date.isoformat())

        if end_date:
            query += ' AND timestamp <= ?'
            params.append(end_date.isoformat())

        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        trades = []
        for row in rows:
            trades.append(Trade(
                trade_id=row[0],
                order_id=row[1],
                symbol=row[2],
                side=OrderSide(row[3]),
                quantity=row[4],
                price=row[5],
                commission=row[6],
                timestamp=datetime.fromisoformat(row[7]),
                strategy=row[8]
            ))

        return trades

    def get_daily_summary(self, target_date: date = None) -> Dict[str, Any]:
        """
        获取每日汇总

        Args:
            target_date: 目标日期

        Returns:
            Dict: 汇总数据
        """
        target = target_date or date.today()
        start = datetime.combine(target, datetime.min.time())
        end = datetime.combine(target, datetime.max.time())

        trades = self.get_trades(start_date=start, end_date=end, limit=1000)

        buy_trades = [t for t in trades if t.side == OrderSide.BUY]
        sell_trades = [t for t in trades if t.side == OrderSide.SELL]

        def _trade_amount(t) -> float:
            """兼容 amount 未赋值的旧数据"""
            if t.amount and t.amount > 0:
                return t.amount
            return t.price * t.quantity

        return {
            'date': target.isoformat(),
            'trade_count': len(trades),
            'buy_count': len(buy_trades),
            'sell_count': len(sell_trades),
            'buy_amount': sum(_trade_amount(t) for t in buy_trades),
            'sell_amount': sum(_trade_amount(t) for t in sell_trades),
            'commission': sum(t.commission for t in trades),
        }

    def save_snapshot(self, portfolio_data: Dict[str, Any]) -> None:
        """
        保存组合快照

        Args:
            portfolio_data: 组合数据
        """
        with self._db_lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute('''
                    INSERT INTO snapshots (date, data)
                    VALUES (?, ?)
                ''', (
                    date.today().isoformat(),
                    json.dumps(portfolio_data)
                ))
                conn.commit()
            finally:
                conn.close()

    def get_snapshots(self, days: int = 30) -> List[Dict]:
        """
        获取历史快照

        Args:
            days: 回溯天数

        Returns:
            List[Dict]: 快照列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT date, data FROM snapshots
            ORDER BY date DESC
            LIMIT ?
        ''', (days,))

        rows = cursor.fetchall()
        conn.close()

        return [
            {'date': row[0], **json.loads(row[1])}
            for row in rows
        ]

    def clear(self) -> None:
        """清空所有数据"""
        with self._db_lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute('DELETE FROM positions')
                conn.execute('DELETE FROM trades')
                conn.execute('DELETE FROM snapshots')
                conn.commit()
            finally:
                conn.close()

        logger.info("持仓数据已清空")

    def _init_db(self) -> None:
        """初始化数据库"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)

        # 持仓表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                quantity REAL,
                avg_cost REAL,
                current_price REAL,
                unrealized_pnl REAL,
                realized_pnl REAL,
                updated_at TEXT
            )
        ''')

        # 交易记录表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                order_id TEXT,
                symbol TEXT,
                side TEXT,
                quantity REAL,
                price REAL,
                commission REAL,
                timestamp TEXT,
                strategy TEXT
            )
        ''')

        # 组合快照表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS snapshots (
                date TEXT PRIMARY KEY,
                data TEXT
            )
        ''')

        # 创建索引
        conn.execute('CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)')

        conn.commit()
        conn.close()
