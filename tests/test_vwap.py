"""
VWAP 指标测试
"""

import pandas as pd
import pytest
from datetime import datetime

from tbot.indicators.vwap import (
    VWAP,
    calculate_vwap,
    count_vwap_crosses,
    pct_time_above_vwap,
)


class TestVWAP:
    """VWAP 计算器测试"""

    def test_vwap_initialization(self):
        """测试初始化"""
        vwap = VWAP("AAPL")
        assert vwap.symbol == "AAPL"
        assert vwap.value == 0.0
        assert vwap.cumulative_volume == 0.0

    def test_vwap_update(self):
        """测试更新"""
        vwap = VWAP("AAPL")

        # 第一个数据点
        result = vwap.update(
            datetime(2024, 1, 15, 9, 30),
            typical_price=100.0,
            volume=1000,
        )
        assert result == 100.0
        assert vwap.cumulative_volume == 1000

        # 第二个数据点
        result = vwap.update(
            datetime(2024, 1, 15, 9, 31),
            typical_price=102.0,
            volume=1000,
        )
        # VWAP = (100*1000 + 102*1000) / 2000 = 101
        assert result == 101.0

    def test_vwap_reset_on_new_day(self):
        """测试新的一天自动重置"""
        vwap = VWAP("AAPL")

        vwap.update(datetime(2024, 1, 15, 9, 30), 100.0, 1000)
        assert vwap.value == 100.0

        # 新的一天
        vwap.update(datetime(2024, 1, 16, 9, 30), 110.0, 1000)
        assert vwap.value == 110.0  # 应该重置

    def test_update_from_bar(self):
        """测试从K线更新"""
        vwap = VWAP("AAPL")

        result = vwap.update_from_bar(
            datetime(2024, 1, 15, 9, 30),
            high=102.0,
            low=98.0,
            close=100.0,
            volume=1000,
        )
        # typical_price = (102 + 98 + 100) / 3 = 100
        assert result == 100.0


class TestCalculateVWAP:
    """批量计算 VWAP 测试"""

    def test_calculate_vwap_basic(self):
        """基础测试"""
        df = pd.DataFrame({
            "high": [102, 104, 103],
            "low": [98, 100, 99],
            "close": [100, 102, 101],
            "volume": [1000, 1000, 1000],
        })

        vwap = calculate_vwap(df)
        assert len(vwap) == 3
        assert vwap.iloc[0] == 100.0  # (102+98+100)/3 = 100

    def test_calculate_vwap_empty(self):
        """空数据测试"""
        df = pd.DataFrame(columns=["high", "low", "close", "volume"])
        vwap = calculate_vwap(df)
        assert len(vwap) == 0


class TestVWAPCrosses:
    """VWAP 穿越测试"""

    def test_count_crosses(self):
        """测试穿越计数"""
        prices = pd.Series([99, 101, 99, 101, 99])
        vwap = pd.Series([100, 100, 100, 100, 100])

        crosses = count_vwap_crosses(prices, vwap)
        assert crosses == 4  # 从下到上，上到下，下到上，上到下

    def test_no_crosses(self):
        """测试无穿越"""
        prices = pd.Series([101, 102, 103])
        vwap = pd.Series([100, 100, 100])

        crosses = count_vwap_crosses(prices, vwap)
        assert crosses == 0

    def test_pct_time_above(self):
        """测试在VWAP上方时间百分比"""
        prices = pd.Series([101, 101, 99, 101])
        vwap = pd.Series([100, 100, 100, 100])

        pct = pct_time_above_vwap(prices, vwap)
        assert pct == 0.75  # 3/4 在上方
