"""
Opening Range 指标测试
"""

import pandas as pd
import pytest
from datetime import datetime, time

from tbot.indicators.opening_range import (
    OpeningRange,
    calculate_opening_range,
    count_or_breakouts,
)


class TestOpeningRange:
    """Opening Range 计算器测试"""

    def test_initialization(self):
        """测试初始化"""
        or_calc = OpeningRange("AAPL")
        assert or_calc.symbol == "AAPL"
        assert or_calc.or5_high is None
        assert or_calc.or15_complete is False

    def test_or5_calculation(self):
        """测试 OR5 计算"""
        or_calc = OpeningRange("AAPL", or5_minutes=5)

        # 9:30 - 9:34 的数据
        or_calc.update(datetime(2024, 1, 15, 9, 30), high=101, low=99)
        or_calc.update(datetime(2024, 1, 15, 9, 31), high=102, low=98)
        or_calc.update(datetime(2024, 1, 15, 9, 32), high=100, low=99)
        or_calc.update(datetime(2024, 1, 15, 9, 33), high=103, low=97)
        or_calc.update(datetime(2024, 1, 15, 9, 34), high=101, low=99)

        # OR5 还未完成
        assert or_calc.or5_complete is False

        # 9:35 完成 OR5
        or_calc.update(datetime(2024, 1, 15, 9, 35), high=100, low=100)
        assert or_calc.or5_complete is True
        assert or_calc.or5_high == 103
        assert or_calc.or5_low == 97

    def test_or15_calculation(self):
        """测试 OR15 计算"""
        or_calc = OpeningRange("AAPL", or15_minutes=15)

        # 模拟 15 分钟数据
        for i in range(15):
            or_calc.update(
                datetime(2024, 1, 15, 9, 30 + i),
                high=100 + i,
                low=90 - i,
            )

        assert or_calc.or15_complete is False

        # 第 16 分钟完成
        or_calc.update(datetime(2024, 1, 15, 9, 45), high=100, low=100)
        assert or_calc.or15_complete is True
        assert or_calc.or15_high == 114  # 100 + 14
        assert or_calc.or15_low == 76  # 90 - 14

    def test_breakout_check(self):
        """测试突破检查"""
        or_calc = OpeningRange("AAPL")

        # 设置 OR
        for i in range(16):
            or_calc.update(datetime(2024, 1, 15, 9, 30 + i), high=100, low=90)

        assert or_calc.or15_complete is True

        # 检查突破
        assert or_calc.check_breakout(101) == "up"
        assert or_calc.check_breakout(89) == "down"
        assert or_calc.check_breakout(95) is None

    def test_reset_on_new_day(self):
        """测试新的一天重置"""
        or_calc = OpeningRange("AAPL")

        or_calc.update(datetime(2024, 1, 15, 9, 30), high=100, low=90)
        assert or_calc.or5_high == 100

        # 新的一天
        or_calc.update(datetime(2024, 1, 16, 9, 30), high=110, low=105)
        assert or_calc.or5_high == 110
        assert or_calc.or5_low == 105


class TestCalculateOpeningRange:
    """批量计算 Opening Range 测试"""

    def test_calculate_from_df(self):
        """从 DataFrame 计算"""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15 09:30", periods=20, freq="min"),
            "high": [100 + i for i in range(20)],
            "low": [90 - i for i in range(20)],
            "close": [95 for _ in range(20)],
            "volume": [1000 for _ in range(20)],
        })

        # OR5
        or5_high, or5_low = calculate_opening_range(df, or_minutes=5)
        assert or5_high == 104  # 100 + 4
        assert or5_low == 86  # 90 - 4

        # OR15
        or15_high, or15_low = calculate_opening_range(df, or_minutes=15)
        assert or15_high == 114
        assert or15_low == 76


class TestORBreakouts:
    """OR 突破统计测试"""

    def test_count_breakouts(self):
        """测试突破计数"""
        df = pd.DataFrame({
            "close": [95, 101, 95, 89, 95],  # 中间 -> 上 -> 中 -> 下 -> 中
        })

        up, down = count_or_breakouts(df, or_high=100, or_low=90)
        assert up == 1
        assert down == 1

    def test_no_breakouts(self):
        """测试无突破"""
        df = pd.DataFrame({
            "close": [95, 96, 94, 95],
        })

        up, down = count_or_breakouts(df, or_high=100, or_low=90)
        assert up == 0
        assert down == 0
