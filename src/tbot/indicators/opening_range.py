"""
Opening Range (OR) 计算模块

OR5: 开盘后5分钟的高低点
OR15: 开盘后15分钟的高低点
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time

import pandas as pd
from loguru import logger


@dataclass
class OpeningRange:
    """
    Opening Range 计算器

    实时跟踪并计算 OR5/OR15
    """

    symbol: str
    or5_minutes: int = 5
    or15_minutes: int = 15
    market_open: time = field(default_factory=lambda: time(9, 30))

    # OR5 状态
    _or5_high: float | None = field(default=None, init=False)
    _or5_low: float | None = field(default=None, init=False)
    _or5_complete: bool = field(default=False, init=False)

    # OR15 状态
    _or15_high: float | None = field(default=None, init=False)
    _or15_low: float | None = field(default=None, init=False)
    _or15_complete: bool = field(default=False, init=False)

    # 当前日期
    _session_date: str | None = field(default=None, init=False)

    def update(
        self,
        timestamp: datetime,
        high: float,
        low: float,
    ) -> None:
        """
        更新 Opening Range

        Args:
            timestamp: 时间戳
            high: 最高价
            low: 最低价
        """
        # 检查是否新的一天
        date_str = timestamp.strftime("%Y-%m-%d")
        if self._session_date != date_str:
            self.reset(date_str)

        bar_time = timestamp.time()
        minutes_since_open = self._minutes_since_open(bar_time)

        if minutes_since_open < 0:
            # 盘前数据，忽略
            return

        # OR5 更新
        if not self._or5_complete:
            if minutes_since_open < self.or5_minutes:
                if self._or5_high is None or high > self._or5_high:
                    self._or5_high = high
                if self._or5_low is None or low < self._or5_low:
                    self._or5_low = low
            else:
                self._or5_complete = True
                logger.info(
                    f"{self.symbol} OR5 完成: High={self._or5_high:.2f}, Low={self._or5_low:.2f}"
                )

        # OR15 更新
        if not self._or15_complete:
            if minutes_since_open < self.or15_minutes:
                if self._or15_high is None or high > self._or15_high:
                    self._or15_high = high
                if self._or15_low is None or low < self._or15_low:
                    self._or15_low = low
            else:
                self._or15_complete = True
                logger.info(
                    f"{self.symbol} OR15 完成: High={self._or15_high:.2f}, Low={self._or15_low:.2f}"
                )

    def _minutes_since_open(self, t: time) -> int:
        """计算距离开盘的分钟数"""
        return (t.hour * 60 + t.minute) - (self.market_open.hour * 60 + self.market_open.minute)

    def reset(self, session_date: str | None = None) -> None:
        """重置 OR（新的交易日）"""
        self._or5_high = None
        self._or5_low = None
        self._or5_complete = False
        self._or15_high = None
        self._or15_low = None
        self._or15_complete = False
        self._session_date = session_date
        if session_date:
            logger.debug(f"{self.symbol} OR 重置: {session_date}")

    @property
    def or5_high(self) -> float | None:
        return self._or5_high

    @property
    def or5_low(self) -> float | None:
        return self._or5_low

    @property
    def or5_width(self) -> float | None:
        """OR5 宽度"""
        if self._or5_high is not None and self._or5_low is not None:
            return self._or5_high - self._or5_low
        return None

    @property
    def or5_complete(self) -> bool:
        return self._or5_complete

    @property
    def or15_high(self) -> float | None:
        return self._or15_high

    @property
    def or15_low(self) -> float | None:
        return self._or15_low

    @property
    def or15_width(self) -> float | None:
        """OR15 宽度"""
        if self._or15_high is not None and self._or15_low is not None:
            return self._or15_high - self._or15_low
        return None

    @property
    def or15_complete(self) -> bool:
        return self._or15_complete

    def check_breakout(self, price: float) -> str | None:
        """
        检查是否突破 OR

        Args:
            price: 当前价格

        Returns:
            "up" / "down" / None
        """
        if not self._or15_complete:
            return None

        if self._or15_high is not None and price > self._or15_high:
            return "up"
        if self._or15_low is not None and price < self._or15_low:
            return "down"

        return None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "symbol": self.symbol,
            "session_date": self._session_date,
            "or5_high": self._or5_high,
            "or5_low": self._or5_low,
            "or5_width": self.or5_width,
            "or5_complete": self._or5_complete,
            "or15_high": self._or15_high,
            "or15_low": self._or15_low,
            "or15_width": self.or15_width,
            "or15_complete": self._or15_complete,
        }


def calculate_opening_range(
    df: pd.DataFrame,
    or_minutes: int = 15,
    market_open: time | None = None,
) -> tuple[float | None, float | None]:
    """
    从 DataFrame 计算 Opening Range

    Args:
        df: 1分钟K线数据
        or_minutes: OR 窗口（分钟）
        market_open: 开盘时间

    Returns:
        (OR High, OR Low)
    """
    if market_open is None:
        market_open = time(9, 30)

    if df.empty:
        return None, None

    # 获取时间列
    if "timestamp" in df.columns:
        times = pd.to_datetime(df["timestamp"])
    elif "date" in df.columns:
        times = pd.to_datetime(df["date"])
    else:
        return None, None

    # 筛选 OR 窗口内的数据
    or_mask = times.dt.time < time(
        market_open.hour,
        market_open.minute + or_minutes,
    )
    or_data = df[or_mask]

    if or_data.empty:
        return None, None

    return float(or_data["high"].max()), float(or_data["low"].min())


def count_or_breakouts(
    df: pd.DataFrame,
    or_high: float,
    or_low: float,
) -> tuple[int, int]:
    """
    计算 OR 突破次数

    Args:
        df: K线数据
        or_high: OR 高点
        or_low: OR 低点

    Returns:
        (向上突破次数, 向下突破次数)
    """
    up_breaks = 0
    down_breaks = 0

    last_state = "inside"

    for _, row in df.iterrows():
        close = row["close"]

        if close > or_high:
            if last_state != "above":
                up_breaks += 1
            last_state = "above"
        elif close < or_low:
            if last_state != "below":
                down_breaks += 1
            last_state = "below"
        else:
            last_state = "inside"

    return up_breaks, down_breaks
