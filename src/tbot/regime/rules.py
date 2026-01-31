"""
日类型分类规则模块

分类：趋势日 / 震荡日 / 事件日
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger

from tbot.regime.features import RegimeFeatures


class Regime(str, Enum):
    """日类型枚举"""

    TREND_UP = "trend_up"  # 上涨趋势日
    TREND_DOWN = "trend_down"  # 下跌趋势日
    RANGE = "range"  # 震荡日
    EVENT = "event"  # 事件日
    UNKNOWN = "unknown"  # 未知


@dataclass
class ClassificationResult:
    """分类结果"""

    regime: Regime
    confidence: float  # 0-1
    reasons: list[str] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "features": self.features,
        }


@dataclass
class RegimeClassifier:
    """
    日类型分类器

    基于规则的分类，可解释性优先
    """

    # 趋势日阈值
    trend_vwap_same_side_pct: float = 0.70
    trend_or_breakout_hold_pct: float = 0.60
    trend_min_range_atr_ratio: float = 1.2

    # 震荡日阈值
    range_vwap_cross_min: int = 4
    range_or_false_breakout_count: int = 2
    range_max_range_atr_ratio: float = 0.8

    # 事件日阈值
    event_early_volume_ratio: float = 0.5  # 早盘成交量占比超过50%
    event_gap_pct: float = 0.015  # 缺口超过1.5%
    event_volume_ratio: float = 2.0  # 成交量是平时2倍以上

    def classify(self, features: RegimeFeatures) -> ClassificationResult:
        """
        根据特征进行日类型分类

        Args:
            features: 分类特征

        Returns:
            ClassificationResult
        """
        reasons: list[str] = []
        scores: dict[str, float] = {
            "trend_up": 0.0,
            "trend_down": 0.0,
            "range": 0.0,
            "event": 0.0,
        }

        # === 事件日判定（优先级最高）===
        event_score = self._score_event(features, reasons)
        scores["event"] = event_score

        if event_score >= 0.7:
            return ClassificationResult(
                regime=Regime.EVENT,
                confidence=event_score,
                reasons=reasons,
                features=features.to_dict(),
            )

        # === 趋势日判定 ===
        trend_up_score, trend_down_score = self._score_trend(features, reasons)
        scores["trend_up"] = trend_up_score
        scores["trend_down"] = trend_down_score

        # === 震荡日判定 ===
        range_score = self._score_range(features, reasons)
        scores["range"] = range_score

        # 选择最高得分
        max_regime = max(scores, key=lambda k: scores[k])
        max_score = scores[max_regime]

        if max_regime == "trend_up":
            regime = Regime.TREND_UP
        elif max_regime == "trend_down":
            regime = Regime.TREND_DOWN
        elif max_regime == "range":
            regime = Regime.RANGE
        else:
            regime = Regime.UNKNOWN

        # 如果所有得分都很低，标记为未知
        if max_score < 0.3:
            regime = Regime.UNKNOWN
            reasons.append("所有分类得分均较低，日类型不明确")

        logger.info(f"{features.symbol} {features.date} 分类: {regime.value} (置信度: {max_score:.2f})")

        return ClassificationResult(
            regime=regime,
            confidence=max_score,
            reasons=reasons,
            features=features.to_dict(),
        )

    def _score_event(self, features: RegimeFeatures, reasons: list[str]) -> float:
        """计算事件日得分"""
        score = 0.0
        evidence_count = 0

        # 大缺口
        if abs(features.gap_pct) >= self.event_gap_pct:
            score += 0.4
            evidence_count += 1
            reasons.append(f"缺口 {features.gap_pct:.2%} 超过阈值 {self.event_gap_pct:.2%}")

        # 早盘成交量异常
        if features.early_volume_ratio >= self.event_early_volume_ratio:
            score += 0.3
            evidence_count += 1
            reasons.append(f"早盘成交量占比 {features.early_volume_ratio:.2%} 异常高")

        # 成交量放大
        if features.volume_ratio is not None and features.volume_ratio >= self.event_volume_ratio:
            score += 0.3
            evidence_count += 1
            reasons.append(f"成交量是平均的 {features.volume_ratio:.1f} 倍")

        return min(score, 1.0)

    def _score_trend(
        self, features: RegimeFeatures, reasons: list[str]
    ) -> tuple[float, float]:
        """计算趋势日得分"""
        up_score = 0.0
        down_score = 0.0

        # VWAP 同侧时间
        if features.pct_time_above_vwap >= self.trend_vwap_same_side_pct:
            up_score += 0.4
            reasons.append(
                f"价格在 VWAP 上方 {features.pct_time_above_vwap:.1%} 时间"
            )
        elif features.pct_time_below_vwap >= self.trend_vwap_same_side_pct:
            down_score += 0.4
            reasons.append(
                f"价格在 VWAP 下方 {features.pct_time_below_vwap:.1%} 时间"
            )

        # VWAP 穿越次数少
        if features.vwap_cross_count <= 2:
            if features.pct_time_above_vwap > 0.5:
                up_score += 0.2
            else:
                down_score += 0.2
            reasons.append(f"VWAP 穿越仅 {features.vwap_cross_count} 次，趋势明显")

        # OR 突破后持续
        if features.or_up_breakout_count >= 1 and features.or_down_breakout_count == 0:
            up_score += 0.2
            reasons.append("OR 向上突破且未回落")
        elif features.or_down_breakout_count >= 1 and features.or_up_breakout_count == 0:
            down_score += 0.2
            reasons.append("OR 向下突破且未反弹")

        # 波动率相对 ATR
        if features.range_atr_ratio is not None:
            if features.range_atr_ratio >= self.trend_min_range_atr_ratio:
                base_score = 0.2
                if features.day_return > 0:
                    up_score += base_score
                else:
                    down_score += base_score
                reasons.append(
                    f"当日波动是 ATR 的 {features.range_atr_ratio:.2f} 倍"
                )

        return min(up_score, 1.0), min(down_score, 1.0)

    def _score_range(self, features: RegimeFeatures, reasons: list[str]) -> float:
        """计算震荡日得分"""
        score = 0.0

        # VWAP 频繁穿越
        if features.vwap_cross_count >= self.range_vwap_cross_min:
            score += 0.4
            reasons.append(f"VWAP 穿越 {features.vwap_cross_count} 次，震荡特征")

        # OR 假突破
        if features.or_false_breakout_count >= self.range_or_false_breakout_count:
            score += 0.3
            reasons.append(
                f"OR 假突破 {features.or_false_breakout_count} 次"
            )

        # 波动率小于 ATR
        if features.range_atr_ratio is not None:
            if features.range_atr_ratio <= self.range_max_range_atr_ratio:
                score += 0.3
                reasons.append(
                    f"当日波动仅为 ATR 的 {features.range_atr_ratio:.2f} 倍"
                )

        # VWAP 两侧时间接近
        vwap_balance = 1 - abs(features.pct_time_above_vwap - 0.5) * 2
        if vwap_balance >= 0.6:
            score += 0.2
            reasons.append("价格在 VWAP 两侧时间均衡")

        return min(score, 1.0)

    def classify_realtime(
        self,
        features: RegimeFeatures,
        time_progress: float = 1.0,
    ) -> ClassificationResult:
        """
        实时分类（盘中使用）

        Args:
            features: 当前特征
            time_progress: 交易时间进度 (0-1)

        Returns:
            ClassificationResult
        """
        result = self.classify(features)

        # 盘中分类置信度降低
        if time_progress < 0.5:
            result.confidence *= time_progress + 0.3
            result.reasons.append(f"注意: 交易日进度 {time_progress:.0%}，分类可能变化")

        return result
