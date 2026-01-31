"""
K线数据聚合器

将 tick 或 5s bars 聚合为 1s/1m bars
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd
from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class Bar:
    """K线数据结构"""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float = 0.0
    bar_count: int = 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "vwap": self.vwap,
            "bar_count": self.bar_count,
        }


@dataclass
class BarAggregator:
    """
    K线聚合器

    将 5s bars 聚合为 1m bars，并实时更新
    """

    symbol: str
    interval_seconds: int = 60  # 聚合周期（秒）

    # 内部状态
    _current_bar: Bar | None = field(default=None, init=False)
    _completed_bars: list[Bar] = field(default_factory=list, init=False)
    _callbacks: list[Callable[[str, Bar], None]] = field(default_factory=list, init=False)

    def add_callback(self, callback: Callable[[str, Bar], None]) -> None:
        """添加新K线完成回调"""
        self._callbacks.append(callback)

    def on_bar(self, timestamp: datetime, open_: float, high: float, low: float, 
               close: float, volume: float, vwap: float = 0.0) -> Bar | None:
        """
        处理新的 bar 数据

        Args:
            timestamp: K线时间戳
            open_: 开盘价
            high: 最高价
            low: 最低价
            close: 收盘价
            volume: 成交量
            vwap: VWAP

        Returns:
            如果完成一根新K线，返回该K线
        """
        # 计算当前 bar 所属的时间窗口
        bar_start = self._get_bar_start(timestamp)

        completed_bar = None

        if self._current_bar is None:
            # 第一根 bar
            self._current_bar = Bar(
                timestamp=bar_start,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                vwap=vwap,
                bar_count=1,
            )
        elif self._current_bar.timestamp != bar_start:
            # 新的时间窗口，完成上一根 bar
            completed_bar = self._current_bar
            self._completed_bars.append(completed_bar)

            # 触发回调
            for callback in self._callbacks:
                try:
                    callback(self.symbol, completed_bar)
                except Exception as e:
                    logger.error(f"Bar 回调执行失败: {e}")

            # 开始新 bar
            self._current_bar = Bar(
                timestamp=bar_start,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                vwap=vwap,
                bar_count=1,
            )
        else:
            # 同一时间窗口，更新当前 bar
            self._current_bar.high = max(self._current_bar.high, high)
            self._current_bar.low = min(self._current_bar.low, low)
            self._current_bar.close = close
            self._current_bar.volume += volume
            self._current_bar.bar_count += 1
            # VWAP 用最新值
            if vwap > 0:
                self._current_bar.vwap = vwap

        return completed_bar

    def _get_bar_start(self, timestamp: datetime) -> datetime:
        """计算 bar 开始时间"""
        seconds = timestamp.second + timestamp.minute * 60 + timestamp.hour * 3600
        bar_seconds = (seconds // self.interval_seconds) * self.interval_seconds

        hours = bar_seconds // 3600
        minutes = (bar_seconds % 3600) // 60
        secs = bar_seconds % 60

        return timestamp.replace(hour=hours, minute=minutes, second=secs, microsecond=0)

    @property
    def current_bar(self) -> Bar | None:
        """当前未完成的 bar"""
        return self._current_bar

    @property
    def completed_bars(self) -> list[Bar]:
        """已完成的 bars"""
        return self._completed_bars.copy()

    def to_dataframe(self, include_current: bool = False) -> pd.DataFrame:
        """
        转换为 DataFrame

        Args:
            include_current: 是否包含当前未完成的 bar

        Returns:
            DataFrame
        """
        bars = self._completed_bars.copy()
        if include_current and self._current_bar:
            bars.append(self._current_bar)

        if not bars:
            return pd.DataFrame()

        return pd.DataFrame([bar.to_dict() for bar in bars])

    def reset(self) -> None:
        """重置聚合器"""
        self._current_bar = None
        self._completed_bars.clear()
        logger.info(f"已重置 {self.symbol} 聚合器")
