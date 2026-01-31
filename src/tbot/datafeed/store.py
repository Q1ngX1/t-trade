"""
数据存储模块

使用 SQLite 存储行情数据、指标快照和交易记录
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
from loguru import logger


class DataStore:
    """SQLite 数据存储"""

    def __init__(self, db_path: Path | str):
        """
        初始化数据存储

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_tables(self) -> None:
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1分钟K线数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bars_1m (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    vwap REAL,
                    bar_count INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, timestamp)
                )
            """)

            # 日线数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bars_daily (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    date DATE NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, date)
                )
            """)

            # 日内指标快照表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS indicator_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    vwap REAL,
                    or5_high REAL,
                    or5_low REAL,
                    or15_high REAL,
                    or15_low REAL,
                    ma20 REAL,
                    atr14 REAL,
                    regime TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 日类型分类记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS regime_daily (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    date DATE NOT NULL,
                    regime TEXT NOT NULL,
                    confidence REAL,
                    vwap_cross_count INTEGER,
                    pct_time_above_vwap REAL,
                    or_width REAL,
                    intraday_range REAL,
                    atr20 REAL,
                    early_volume_ratio REAL,
                    gap_pct REAL,
                    notes TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, date)
                )
            """)

            # 信号记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    signal_type TEXT NOT NULL,
                    direction TEXT,
                    entry_price REAL,
                    stop_loss REAL,
                    target_price REAL,
                    regime TEXT,
                    confidence REAL,
                    notes TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            logger.info(f"数据库初始化完成: {self.db_path}")

    def save_bars_1m(self, symbol: str, df: pd.DataFrame) -> int:
        """
        保存1分钟K线数据

        Args:
            symbol: 股票代码
            df: K线数据 DataFrame

        Returns:
            保存的记录数
        """
        if df.empty:
            return 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            count = 0

            for _, row in df.iterrows():
                try:
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO bars_1m 
                        (symbol, timestamp, open, high, low, close, volume, vwap, bar_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            symbol,
                            row.get("date") or row.get("timestamp"),
                            row["open"],
                            row["high"],
                            row["low"],
                            row["close"],
                            row["volume"],
                            row.get("average", row.get("vwap")),
                            row.get("barCount", row.get("bar_count")),
                        ),
                    )
                    count += 1
                except Exception as e:
                    logger.error(f"保存K线失败: {e}")

            conn.commit()
            logger.info(f"保存 {symbol} {count} 条1分钟K线")
            return count

    def save_bars_daily(self, symbol: str, df: pd.DataFrame) -> int:
        """保存日线数据"""
        if df.empty:
            return 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            count = 0

            for _, row in df.iterrows():
                try:
                    date_val = row.get("date")
                    if isinstance(date_val, datetime):
                        date_val = date_val.date()

                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO bars_daily 
                        (symbol, date, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            symbol,
                            str(date_val),
                            row["open"],
                            row["high"],
                            row["low"],
                            row["close"],
                            row["volume"],
                        ),
                    )
                    count += 1
                except Exception as e:
                    logger.error(f"保存日线失败: {e}")

            conn.commit()
            logger.info(f"保存 {symbol} {count} 条日线")
            return count

    def get_bars_1m(
        self,
        symbol: str,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
    ) -> pd.DataFrame:
        """
        获取1分钟K线数据

        Args:
            symbol: 股票代码
            start_date: 开始时间
            end_date: 结束时间

        Returns:
            K线 DataFrame
        """
        query = "SELECT * FROM bars_1m WHERE symbol = ?"
        params: list[Any] = [symbol]

        if start_date:
            query += " AND timestamp >= ?"
            params.append(str(start_date))
        if end_date:
            query += " AND timestamp <= ?"
            params.append(str(end_date))

        query += " ORDER BY timestamp"

        with self._get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params)

        return df

    def get_bars_daily(
        self,
        symbol: str,
        days: int = 60,
    ) -> pd.DataFrame:
        """
        获取最近N天的日线数据

        Args:
            symbol: 股票代码
            days: 天数

        Returns:
            日线 DataFrame
        """
        query = f"""
            SELECT * FROM bars_daily 
            WHERE symbol = ? 
            ORDER BY date DESC 
            LIMIT {days}
        """

        with self._get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=[symbol])

        return df.iloc[::-1].reset_index(drop=True)  # 按时间正序

    def save_regime(
        self,
        symbol: str,
        date: str,
        regime: str,
        metrics: dict[str, Any],
    ) -> None:
        """保存日类型分类"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO regime_daily 
                (symbol, date, regime, confidence, vwap_cross_count, 
                 pct_time_above_vwap, or_width, intraday_range, atr20,
                 early_volume_ratio, gap_pct, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    date,
                    regime,
                    metrics.get("confidence"),
                    metrics.get("vwap_cross_count"),
                    metrics.get("pct_time_above_vwap"),
                    metrics.get("or_width"),
                    metrics.get("intraday_range"),
                    metrics.get("atr20"),
                    metrics.get("early_volume_ratio"),
                    metrics.get("gap_pct"),
                    metrics.get("notes"),
                ),
            )
            conn.commit()
            logger.info(f"保存 {symbol} {date} 分类: {regime}")

    def save_signal(
        self,
        symbol: str,
        timestamp: datetime,
        signal_type: str,
        details: dict[str, Any],
    ) -> None:
        """保存信号记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO signals 
                (symbol, timestamp, signal_type, direction, entry_price, 
                 stop_loss, target_price, regime, confidence, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    str(timestamp),
                    signal_type,
                    details.get("direction"),
                    details.get("entry_price"),
                    details.get("stop_loss"),
                    details.get("target_price"),
                    details.get("regime"),
                    details.get("confidence"),
                    details.get("notes"),
                ),
            )
            conn.commit()

    def get_regime_history(
        self,
        symbol: str,
        days: int = 30,
    ) -> pd.DataFrame:
        """获取日类型分类历史"""
        query = f"""
            SELECT * FROM regime_daily 
            WHERE symbol = ? 
            ORDER BY date DESC 
            LIMIT {days}
        """

        with self._get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=[symbol])

        return df
