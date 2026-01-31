"""
日类型分类规则测试
"""

import pytest

from tbot.regime.features import RegimeFeatures
from tbot.regime.rules import Regime, RegimeClassifier


class TestRegimeClassifier:
    """分类器测试"""

    @pytest.fixture
    def classifier(self):
        """创建分类器"""
        return RegimeClassifier()

    def test_trend_up_classification(self, classifier):
        """测试上涨趋势日分类"""
        features = RegimeFeatures(
            symbol="AAPL",
            date="2024-01-15",
            vwap_cross_count=1,
            pct_time_above_vwap=0.85,
            pct_time_below_vwap=0.15,
            or_up_breakout_count=1,
            or_down_breakout_count=0,
            range_atr_ratio=1.5,
            day_return=0.02,
        )

        result = classifier.classify(features)
        assert result.regime == Regime.TREND_UP
        assert result.confidence >= 0.5

    def test_trend_down_classification(self, classifier):
        """测试下跌趋势日分类"""
        features = RegimeFeatures(
            symbol="AAPL",
            date="2024-01-15",
            vwap_cross_count=2,
            pct_time_above_vwap=0.15,
            pct_time_below_vwap=0.85,
            or_up_breakout_count=0,
            or_down_breakout_count=1,
            range_atr_ratio=1.3,
            day_return=-0.02,
        )

        result = classifier.classify(features)
        assert result.regime == Regime.TREND_DOWN
        assert result.confidence >= 0.5

    def test_range_day_classification(self, classifier):
        """测试震荡日分类"""
        features = RegimeFeatures(
            symbol="AAPL",
            date="2024-01-15",
            vwap_cross_count=6,
            pct_time_above_vwap=0.52,
            pct_time_below_vwap=0.48,
            or_false_breakout_count=3,
            range_atr_ratio=0.6,
            day_return=0.001,
        )

        result = classifier.classify(features)
        assert result.regime == Regime.RANGE
        assert result.confidence >= 0.4

    def test_event_day_classification(self, classifier):
        """测试事件日分类"""
        features = RegimeFeatures(
            symbol="AAPL",
            date="2024-01-15",
            gap_pct=0.025,  # 2.5% 缺口
            early_volume_ratio=0.6,  # 60% 早盘成交量
            volume_ratio=2.5,  # 2.5倍平均成交量
        )

        result = classifier.classify(features)
        assert result.regime == Regime.EVENT
        assert result.confidence >= 0.7

    def test_unknown_classification(self, classifier):
        """测试未知类型"""
        features = RegimeFeatures(
            symbol="AAPL",
            date="2024-01-15",
            vwap_cross_count=3,
            pct_time_above_vwap=0.5,
            pct_time_below_vwap=0.5,
            range_atr_ratio=1.0,
        )

        result = classifier.classify(features)
        # 所有特征都很中性，可能是 UNKNOWN 或低置信度
        assert result.confidence <= 0.5 or result.regime == Regime.UNKNOWN

    def test_realtime_classification(self, classifier):
        """测试实时分类（盘中）"""
        features = RegimeFeatures(
            symbol="AAPL",
            date="2024-01-15",
            pct_time_above_vwap=0.8,
            vwap_cross_count=1,
        )

        # 早盘（进度 30%）
        result = classifier.classify_realtime(features, time_progress=0.3)
        assert "交易日进度" in result.reasons[-1]

        # 收盘后（进度 100%）
        result_full = classifier.classify_realtime(features, time_progress=1.0)
        # 置信度应该更高
        assert result_full.confidence >= result.confidence

    def test_classification_reasons(self, classifier):
        """测试分类原因输出"""
        features = RegimeFeatures(
            symbol="AAPL",
            date="2024-01-15",
            vwap_cross_count=7,
            pct_time_above_vwap=0.45,
            or_false_breakout_count=3,
            range_atr_ratio=0.5,
        )

        result = classifier.classify(features)
        assert len(result.reasons) > 0
        # 应该包含具体的判断依据
        any_vwap_reason = any("VWAP" in r for r in result.reasons)
        any_or_reason = any("OR" in r or "突破" in r for r in result.reasons)
        assert any_vwap_reason or any_or_reason
