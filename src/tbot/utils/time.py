"""
时间工具模块

处理交易时段、时区、session 边界
"""

from __future__ import annotations

from datetime import datetime, time
from enum import Enum
from typing import NamedTuple

import pendulum
from pendulum import DateTime


class MarketSession(str, Enum):
    """市场时段"""

    PREMARKET = "premarket"  # 盘前
    OPENING = "opening"  # 开盘（9:30-9:45 不交易期）
    MORNING = "morning"  # 上午交易时段
    MIDDAY = "midday"  # 午间
    AFTERNOON = "afternoon"  # 下午交易时段
    CLOSE_ONLY = "close_only"  # 收盘前（只平仓）
    AFTERHOURS = "afterhours"  # 盘后
    CLOSED = "closed"  # 休市


class TradingWindow(NamedTuple):
    """交易窗口"""

    start: time
    end: time
    priority: str = "medium"


# 默认交易时间设置 (美东时间)
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
NO_TRADE_END = time(9, 45)  # 开盘后不交易期结束
CLOSE_ONLY_START = time(15, 45)  # 收盘前只平仓

# 允许交易的窗口
TRADING_WINDOWS = [
    TradingWindow(time(9, 45), time(11, 0), "high"),
    TradingWindow(time(13, 30), time(15, 30), "medium"),
]

# 时区
ET_TIMEZONE = "America/New_York"


def get_et_now() -> DateTime:
    """获取当前美东时间"""
    return pendulum.now(ET_TIMEZONE)


def to_et(dt: datetime) -> DateTime:
    """转换为美东时间"""
    if isinstance(dt, DateTime):
        return dt.in_timezone(ET_TIMEZONE)
    return pendulum.instance(dt).in_timezone(ET_TIMEZONE)


def get_market_session(dt: datetime | None = None) -> MarketSession:
    """
    获取当前市场时段

    Args:
        dt: 时间，默认当前时间

    Returns:
        MarketSession
    """
    if dt is None:
        now = get_et_now()
    else:
        now = to_et(dt)

    current_time = now.time()

    # 盘前
    if current_time < MARKET_OPEN:
        return MarketSession.PREMARKET

    # 开盘不交易期
    if current_time < NO_TRADE_END:
        return MarketSession.OPENING

    # 上午交易
    if current_time < time(11, 30):
        return MarketSession.MORNING

    # 午间
    if current_time < time(13, 30):
        return MarketSession.MIDDAY

    # 下午交易
    if current_time < CLOSE_ONLY_START:
        return MarketSession.AFTERNOON

    # 收盘前
    if current_time < MARKET_CLOSE:
        return MarketSession.CLOSE_ONLY

    # 盘后
    return MarketSession.AFTERHOURS


def is_market_open(dt: datetime | None = None) -> bool:
    """
    判断市场是否开盘

    Args:
        dt: 时间

    Returns:
        是否开盘
    """
    if dt is None:
        now = get_et_now()
    else:
        now = to_et(dt)

    current_time = now.time()
    return MARKET_OPEN <= current_time < MARKET_CLOSE


def is_trading_allowed(dt: datetime | None = None) -> tuple[bool, str]:
    """
    判断当前是否允许交易

    Args:
        dt: 时间

    Returns:
        (是否允许, 原因)
    """
    if dt is None:
        now = get_et_now()
    else:
        now = to_et(dt)

    current_time = now.time()
    session = get_market_session(now)

    # 检查是否在允许的窗口内
    for window in TRADING_WINDOWS:
        if window.start <= current_time < window.end:
            return True, f"在交易窗口 {window.start}-{window.end}"

    # 不在窗口内
    if session == MarketSession.OPENING:
        return False, "开盘观察期 (9:30-9:45)"
    elif session == MarketSession.MIDDAY:
        return False, "午间休息 (11:30-13:30)"
    elif session == MarketSession.CLOSE_ONLY:
        return False, "收盘前只允许平仓"
    elif session in [MarketSession.PREMARKET, MarketSession.AFTERHOURS]:
        return False, "非交易时段"
    else:
        return False, "不在允许的交易窗口"


def get_trading_progress(dt: datetime | None = None) -> float:
    """
    获取交易日进度 (0-1)

    Args:
        dt: 时间

    Returns:
        进度百分比
    """
    if dt is None:
        now = get_et_now()
    else:
        now = to_et(dt)

    current_time = now.time()

    if current_time < MARKET_OPEN:
        return 0.0
    if current_time >= MARKET_CLOSE:
        return 1.0

    # 计算分钟数
    open_minutes = MARKET_OPEN.hour * 60 + MARKET_OPEN.minute
    close_minutes = MARKET_CLOSE.hour * 60 + MARKET_CLOSE.minute
    current_minutes = current_time.hour * 60 + current_time.minute

    total_minutes = close_minutes - open_minutes
    elapsed_minutes = current_minutes - open_minutes

    return elapsed_minutes / total_minutes


def get_session_start_end(date: datetime | None = None) -> tuple[DateTime, DateTime]:
    """
    获取交易日开始和结束时间

    Args:
        date: 日期

    Returns:
        (开始时间, 结束时间)
    """
    if date is None:
        today = get_et_now().date()
    else:
        today = to_et(date).date()

    start = pendulum.datetime(
        today.year, today.month, today.day,
        MARKET_OPEN.hour, MARKET_OPEN.minute,
        tz=ET_TIMEZONE,
    )
    end = pendulum.datetime(
        today.year, today.month, today.day,
        MARKET_CLOSE.hour, MARKET_CLOSE.minute,
        tz=ET_TIMEZONE,
    )

    return start, end


def format_time_et(dt: datetime) -> str:
    """格式化为美东时间字符串"""
    et_time = to_et(dt)
    return et_time.strftime("%Y-%m-%d %H:%M:%S ET")
