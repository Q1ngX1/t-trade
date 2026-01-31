"""
日类型特征提取模块

提取用于分类的特征
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any

import pandas as pd

from tbot.indicators.ma20 import get_atr_from_daily
from tbot.indicators.opening_range import calculate_opening_range, count_or_breakouts
from tbot.indicators.vwap import calculate_vwap, count_vwap_crosses, pct_time_above_vwap


@dataclass
class RegimeFeatures:
    """日类型分类特征"""

    # 基础信息
    symbol: str
    date: str

    # VWAP 相关
    vwap_cross_count: int = 0
    pct_time_above_vwap: float = 0.0
    pct_time_below_vwap: float = 0.0

    # Opening Range 相关
    or5_width: float | None = None
    or15_width: float | None = None
    or_up_breakout_count: int = 0
    or_down_breakout_count: int = 0
    or_false_breakout_count: int = 0

    # 波动性
    intraday_range: float = 0.0  # 当日高-低
    intraday_range_pct: float = 0.0  # (高-低)/开盘价
    atr20: float | None = None  # 20日 ATR
    range_atr_ratio: float | None = None  # 当日波动 / ATR

    # 成交量
    total_volume: float = 0.0
    early_volume: float = 0.0  # 开盘30分钟成交量
    early_volume_ratio: float = 0.0  # 早盘成交量占比
    avg_daily_volume: float | None = None  # 平均日成交量
    volume_ratio: float | None = None  # 当日成交量 / 平均

    # 缺口
    gap_pct: float = 0.0  # 开盘缺口百分比

    # 方向性
    open_price: float = 0.0
    close_price: float = 0.0
    day_return: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "symbol": self.symbol,
            "date": self.date,
            "vwap_cross_count": self.vwap_cross_count,
            "pct_time_above_vwap": self.pct_time_above_vwap,
            "pct_time_below_vwap": self.pct_time_below_vwap,
            "or5_width": self.or5_width,
            "or15_width": self.or15_width,
            "or_up_breakout_count": self.or_up_breakout_count,
            "or_down_breakout_count": self.or_down_breakout_count,
            "or_false_breakout_count": self.or_false_breakout_count,
            "intraday_range": self.intraday_range,
            "intraday_range_pct": self.intraday_range_pct,
            "atr20": self.atr20,
            "range_atr_ratio": self.range_atr_ratio,
            "total_volume": self.total_volume,
            "early_volume": self.early_volume,
            "early_volume_ratio": self.early_volume_ratio,
            "gap_pct": self.gap_pct,
            "open_price": self.open_price,
            "close_price": self.close_price,
            "day_return": self.day_return,
        }


def extract_features(
    intraday_df: pd.DataFrame,
    daily_df: pd.DataFrame | None = None,
    symbol: str = "",
    date: str = "",
    prev_close: float | None = None,
) -> RegimeFeatures:
    """
    从日内数据提取分类特征

    Args:
        intraday_df: 日内1分钟数据
        daily_df: 日线数据（用于计算 ATR 等）
        symbol: 股票代码
        date: 日期
        prev_close: 前日收盘价

    Returns:
        RegimeFeatures
    """
    features = RegimeFeatures(symbol=symbol, date=date)

    if intraday_df.empty:
        return features

    # 基础价格
    features.open_price = float(intraday_df["open"].iloc[0])
    features.close_price = float(intraday_df["close"].iloc[-1])
    features.intraday_range = float(intraday_df["high"].max() - intraday_df["low"].min())

    if features.open_price > 0:
        features.intraday_range_pct = features.intraday_range / features.open_price
        features.day_return = (features.close_price - features.open_price) / features.open_price

    # 缺口计算
    if prev_close is not None and prev_close > 0:
        features.gap_pct = (features.open_price - prev_close) / prev_close

    # VWAP 特征
    vwap = calculate_vwap(intraday_df)
    features.vwap_cross_count = count_vwap_crosses(intraday_df["close"], vwap)
    features.pct_time_above_vwap = pct_time_above_vwap(intraday_df["close"], vwap)
    features.pct_time_below_vwap = 1 - features.pct_time_above_vwap

    # Opening Range 特征
    or5_high, or5_low = calculate_opening_range(intraday_df, or_minutes=5)
    or15_high, or15_low = calculate_opening_range(intraday_df, or_minutes=15)

    if or5_high is not None and or5_low is not None:
        features.or5_width = or5_high - or5_low

    if or15_high is not None and or15_low is not None:
        features.or15_width = or15_high - or15_low

        # OR 突破统计
        # 排除 OR 窗口内的数据
        if "timestamp" in intraday_df.columns:
            times = pd.to_datetime(intraday_df["timestamp"])
        elif "date" in intraday_df.columns:
            times = pd.to_datetime(intraday_df["date"])
        else:
            times = None

        if times is not None:
            after_or = times.dt.time >= time(9, 45)
            after_or_df = intraday_df[after_or]

            if not after_or_df.empty:
                up_breaks, down_breaks = count_or_breakouts(after_or_df, or15_high, or15_low)
                features.or_up_breakout_count = up_breaks
                features.or_down_breakout_count = down_breaks
                # 假突破 = 两个方向都有突破
                features.or_false_breakout_count = min(up_breaks, down_breaks)

    # 成交量特征
    features.total_volume = float(intraday_df["volume"].sum())

    # 早盘成交量（前30分钟）
    if "timestamp" in intraday_df.columns:
        times = pd.to_datetime(intraday_df["timestamp"])
    elif "date" in intraday_df.columns:
        times = pd.to_datetime(intraday_df["date"])
    else:
        times = None

    if times is not None:
        early_mask = times.dt.time < time(10, 0)
        features.early_volume = float(intraday_df[early_mask]["volume"].sum())
        if features.total_volume > 0:
            features.early_volume_ratio = features.early_volume / features.total_volume

    # 从日线数据提取 ATR
    if daily_df is not None and not daily_df.empty:
        features.atr20 = get_atr_from_daily(daily_df, period=20)
        if features.atr20 and features.atr20 > 0:
            features.range_atr_ratio = features.intraday_range / features.atr20

        # 平均成交量
        if "volume" in daily_df.columns and len(daily_df) >= 20:
            features.avg_daily_volume = float(daily_df["volume"].tail(20).mean())
            if features.avg_daily_volume > 0:
                features.volume_ratio = features.total_volume / features.avg_daily_volume

    return features
