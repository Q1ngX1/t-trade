"""
MA20 (20日移动平均线) 计算模块
"""

from __future__ import annotations

import pandas as pd


def calculate_ma20(prices: pd.Series, period: int = 20) -> pd.Series:
    """
    计算移动平均线

    Args:
        prices: 价格序列 (通常是 close)
        period: 周期

    Returns:
        MA Series
    """
    return prices.rolling(window=period).mean()


def get_ma20_from_daily(daily_df: pd.DataFrame, period: int = 20) -> float | None:
    """
    从日线数据获取最新的 MA20

    Args:
        daily_df: 日线数据 DataFrame
        period: MA 周期

    Returns:
        最新的 MA 值
    """
    if daily_df.empty or len(daily_df) < period:
        return None

    ma = calculate_ma20(daily_df["close"], period)
    return float(ma.iloc[-1]) if not pd.isna(ma.iloc[-1]) else None


def calculate_atr(
    daily_df: pd.DataFrame,
    period: int = 14,
) -> pd.Series:
    """
    计算 ATR (Average True Range)

    Args:
        daily_df: 日线数据 DataFrame
        period: ATR 周期

    Returns:
        ATR Series
    """
    high = daily_df["high"]
    low = daily_df["low"]
    close = daily_df["close"]

    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR = TR 的指数移动平均
    atr = tr.ewm(span=period, adjust=False).mean()

    return atr


def get_atr_from_daily(daily_df: pd.DataFrame, period: int = 14) -> float | None:
    """
    从日线数据获取最新的 ATR

    Args:
        daily_df: 日线数据 DataFrame
        period: ATR 周期

    Returns:
        最新的 ATR 值
    """
    if daily_df.empty or len(daily_df) < period + 1:
        return None

    atr = calculate_atr(daily_df, period)
    return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else None
