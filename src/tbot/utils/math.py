"""
数学工具模块

常用计算函数
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def zscore(series: pd.Series, window: int = 20) -> pd.Series:
    """
    计算滚动 Z-score

    Args:
        series: 数据序列
        window: 窗口大小

    Returns:
        Z-score 序列
    """
    mean = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    return (series - mean) / std


def calculate_r(entry: float, stop_loss: float, target: float) -> float:
    """
    计算风险收益比 (R)

    Args:
        entry: 入场价
        stop_loss: 止损价
        target: 目标价

    Returns:
        R 值
    """
    risk = abs(entry - stop_loss)
    if risk == 0:
        return 0.0
    reward = abs(target - entry)
    return reward / risk


def calculate_position_size(
    account_value: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
) -> int:
    """
    计算仓位大小（基于风险金额）

    Args:
        account_value: 账户总值
        risk_pct: 风险百分比 (如 0.02 = 2%)
        entry_price: 入场价
        stop_loss: 止损价

    Returns:
        股数
    """
    risk_amount = account_value * risk_pct
    risk_per_share = abs(entry_price - stop_loss)

    if risk_per_share == 0:
        return 0

    shares = int(risk_amount / risk_per_share)
    return max(0, shares)


def round_to_tick(price: float, tick_size: float = 0.01) -> float:
    """
    价格取整到 tick

    Args:
        price: 原始价格
        tick_size: tick 大小

    Returns:
        取整后的价格
    """
    return round(price / tick_size) * tick_size


def pct_change(current: float, previous: float) -> float:
    """
    计算百分比变化

    Args:
        current: 当前值
        previous: 前值

    Returns:
        百分比变化
    """
    if previous == 0:
        return 0.0
    return (current - previous) / previous


def calculate_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """
    计算夏普比率

    Args:
        returns: 收益率序列
        risk_free_rate: 无风险利率
        periods_per_year: 年化周期数

    Returns:
        夏普比率
    """
    excess_returns = returns - risk_free_rate / periods_per_year
    if excess_returns.std() == 0:
        return 0.0
    return float(np.sqrt(periods_per_year) * excess_returns.mean() / excess_returns.std())


def calculate_max_drawdown(equity_curve: pd.Series) -> tuple[float, int, int]:
    """
    计算最大回撤

    Args:
        equity_curve: 权益曲线

    Returns:
        (最大回撤百分比, 开始索引, 结束索引)
    """
    rolling_max = equity_curve.expanding().max()
    drawdown = (equity_curve - rolling_max) / rolling_max

    max_dd = float(drawdown.min())
    end_idx = int(drawdown.idxmin()) if not pd.isna(drawdown.idxmin()) else 0

    # 找到回撤开始点
    peak = equity_curve[:end_idx + 1].idxmax() if end_idx > 0 else 0
    start_idx = int(peak) if not pd.isna(peak) else 0

    return max_dd, start_idx, end_idx
