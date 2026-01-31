"""
VWAP (成交量加权平均价) 计算模块

Session-based VWAP，每个交易日重新计算
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class VWAP:
    """
    实时 VWAP 计算器

    VWAP = Σ(Price × Volume) / Σ(Volume)

    每个交易日开始时重置
    """

    symbol: str

    # 内部状态
    _cumulative_pv: float = field(default=0.0, init=False)  # 累计价格×成交量
    _cumulative_volume: float = field(default=0.0, init=False)  # 累计成交量
    _current_vwap: float = field(default=0.0, init=False)
    _session_date: str | None = field(default=None, init=False)
    _history: list[dict] = field(default_factory=list, init=False)

    def update(
        self,
        timestamp: datetime,
        typical_price: float,
        volume: float,
    ) -> float:
        """
        更新 VWAP

        Args:
            timestamp: 时间戳
            typical_price: 典型价格 (H+L+C)/3 或直接用 close
            volume: 成交量

        Returns:
            当前 VWAP 值
        """
        # 检查是否新的一天
        date_str = timestamp.strftime("%Y-%m-%d")
        if self._session_date != date_str:
            self.reset(date_str)

        if volume <= 0:
            return self._current_vwap

        # 累加
        self._cumulative_pv += typical_price * volume
        self._cumulative_volume += volume

        # 计算 VWAP
        if self._cumulative_volume > 0:
            self._current_vwap = self._cumulative_pv / self._cumulative_volume

        # 记录历史
        self._history.append({
            "timestamp": timestamp,
            "vwap": self._current_vwap,
            "cumulative_volume": self._cumulative_volume,
        })

        return self._current_vwap

    def update_from_bar(
        self,
        timestamp: datetime,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> float:
        """
        从K线更新 VWAP

        Args:
            timestamp: 时间戳
            high: 最高价
            low: 最低价
            close: 收盘价
            volume: 成交量

        Returns:
            当前 VWAP 值
        """
        typical_price = (high + low + close) / 3
        return self.update(timestamp, typical_price, volume)

    def reset(self, session_date: str | None = None) -> None:
        """重置 VWAP（新的交易日）"""
        self._cumulative_pv = 0.0
        self._cumulative_volume = 0.0
        self._current_vwap = 0.0
        self._session_date = session_date
        self._history.clear()
        if session_date:
            logger.debug(f"{self.symbol} VWAP 重置: {session_date}")

    @property
    def value(self) -> float:
        """当前 VWAP 值"""
        return self._current_vwap

    @property
    def cumulative_volume(self) -> float:
        """累计成交量"""
        return self._cumulative_volume

    def get_history_df(self) -> pd.DataFrame:
        """获取历史 VWAP DataFrame"""
        if not self._history:
            return pd.DataFrame()
        return pd.DataFrame(self._history)


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    批量计算 VWAP

    Args:
        df: 包含 high, low, close, volume 列的 DataFrame

    Returns:
        VWAP Series
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cumulative_pv = (typical_price * df["volume"]).cumsum()
    cumulative_volume = df["volume"].cumsum()

    vwap = cumulative_pv / cumulative_volume
    vwap = vwap.replace([np.inf, -np.inf], np.nan)

    return vwap


def calculate_vwap_bands(
    vwap: pd.Series,
    df: pd.DataFrame,
    band_pct: float = 0.002,
) -> tuple[pd.Series, pd.Series]:
    """
    计算 VWAP bands

    Args:
        vwap: VWAP Series
        df: 原始数据 DataFrame
        band_pct: band 宽度百分比 (默认 0.2%)

    Returns:
        (上轨, 下轨) tuple
    """
    upper = vwap * (1 + band_pct)
    lower = vwap * (1 - band_pct)
    return upper, lower


def count_vwap_crosses(prices: pd.Series, vwap: pd.Series) -> int:
    """
    计算价格穿越 VWAP 的次数

    Args:
        prices: 价格序列 (通常是 close)
        vwap: VWAP 序列

    Returns:
        穿越次数
    """
    if len(prices) < 2:
        return 0

    above = prices > vwap
    crosses = (above != above.shift(1)).sum()
    return int(crosses) - 1  # 第一个不算


def pct_time_above_vwap(prices: pd.Series, vwap: pd.Series) -> float:
    """
    计算价格在 VWAP 上方的时间百分比

    Args:
        prices: 价格序列
        vwap: VWAP 序列

    Returns:
        百分比 (0-1)
    """
    if len(prices) == 0:
        return 0.0

    valid = ~(prices.isna() | vwap.isna())
    if valid.sum() == 0:
        return 0.0

    above = (prices[valid] > vwap[valid]).sum()
    return float(above / valid.sum())
