"""
信号生成模块

根据日类型和市场状态生成交易信号：
- CHOP (震荡日): 均值回归，VWAP/OR边界反转
- TREND (趋势日): 顺势回调加仓，延伸减仓
- EVENT (事件日): 更宽阈值，更小仓位
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from loguru import logger

from tbot.engine.state import TradingState
from tbot.regime.rules import Regime


class SignalType(str, Enum):
    """信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class TradingSignal:
    """交易信号"""
    signal_type: SignalType
    shares: int = 0
    reason: str = ""
    confidence: float = 0.0
    price_target: float | None = None
    stop_loss: float | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_type": self.signal_type.value,
            "shares": self.shares,
            "reason": self.reason,
            "confidence": self.confidence,
            "price_target": self.price_target,
            "stop_loss": self.stop_loss,
        }


@dataclass
class MarketSnapshot:
    """市场快照"""
    price: float
    vwap: float
    high: float
    low: float
    open: float
    volume: int
    
    # Opening Range
    or_high: float
    or_low: float
    or_complete: bool = False
    
    # 衍生指标
    intraday_vol: float = 0.0  # 日内波动率估计
    vwap_slope: float = 0.0  # VWAP 斜率
    
    @property
    def dev_from_vwap(self) -> float:
        """与 VWAP 的偏离"""
        return self.price - self.vwap
    
    @property
    def dev_from_vwap_pct(self) -> float:
        """与 VWAP 的偏离百分比"""
        if self.vwap <= 0:
            return 0.0
        return (self.price - self.vwap) / self.vwap
    
    @property
    def dev_normalized(self) -> float:
        """标准化偏离（用波动率归一化）"""
        if self.intraday_vol <= 0:
            return 0.0
        return self.dev_from_vwap / self.intraday_vol
    
    def is_near_or_high(self, band_pct: float = 0.002) -> bool:
        """是否接近 OR 高点"""
        return abs(self.price - self.or_high) / self.or_high <= band_pct
    
    def is_near_or_low(self, band_pct: float = 0.002) -> bool:
        """是否接近 OR 低点"""
        return abs(self.price - self.or_low) / self.or_low <= band_pct


@dataclass
class SignalGenerator:
    """
    信号生成器
    
    根据日类型和市场状态生成交易信号
    """
    
    # 震荡日 (CHOP) 阈值
    chop_buy_threshold: float = -1.0  # 低于 VWAP N 个标准差时买入
    chop_sell_threshold: float = 1.0  # 高于 VWAP N 个标准差时卖出
    or_band_pct: float = 0.002  # OR 边界判定带宽
    breakout_hold_bars: int = 5  # 突破持续确认 bar 数
    
    # 趋势日 (TREND) 阈值
    trend_pullback_threshold: float = -0.5  # 回调买入阈值
    trend_extension_threshold: float = 1.5  # 延伸卖出阈值
    support_buffer_pct: float = 0.003  # 关键支撑缓冲
    
    # 事件日 (EVENT) 阈值
    event_buy_threshold: float = -1.5  # 更大偏离才买
    event_sell_threshold: float = 1.5  # 更大偏离才卖
    event_size_multiplier: float = 0.5  # 仓位缩小到50%
    
    # 突破追踪
    _breakout_up_bars: int = 0
    _breakout_down_bars: int = 0
    
    def generate(
        self,
        state: TradingState,
        market: MarketSnapshot,
        regime: Regime,
    ) -> TradingSignal:
        """
        生成交易信号
        
        Args:
            state: 交易状态
            market: 市场快照
            regime: 日类型
        
        Returns:
            TradingSignal
        """
        if regime == Regime.RANGE:
            return self._generate_chop_signal(state, market)
        elif regime == Regime.TREND_UP:
            return self._generate_trend_up_signal(state, market)
        elif regime == Regime.TREND_DOWN:
            return self._generate_trend_down_signal(state, market)
        elif regime == Regime.EVENT:
            return self._generate_event_signal(state, market)
        else:
            # UNKNOWN - 不交易
            return TradingSignal(
                signal_type=SignalType.HOLD,
                reason="日类型未知，暂不交易",
            )
    
    def _generate_chop_signal(
        self, 
        state: TradingState, 
        market: MarketSnapshot
    ) -> TradingSignal:
        """
        震荡日信号：均值回归
        
        策略：
        - 低于 VWAP 或接近 OR 低点时买入
        - 高于 VWAP 或接近 OR 高点时卖出
        """
        dev_norm = market.dev_normalized
        near_or_high = market.is_near_or_high(self.or_band_pct)
        near_or_low = market.is_near_or_low(self.or_band_pct)
        
        # 检查是否突破后持续（可能转趋势）
        self._update_breakout_tracking(market)
        if self._is_breakout_confirmed():
            return TradingSignal(
                signal_type=SignalType.HOLD,
                reason="OR 突破确认中，暂停震荡日策略",
            )
        
        # 买入条件：下沿或显著低于 VWAP，且机动仓 <= 0
        if (dev_norm <= self.chop_buy_threshold or near_or_low) and state.t_inventory <= 0:
            shares = state.get_available_buy_shares()
            if shares > 0:
                reasons = []
                if dev_norm <= self.chop_buy_threshold:
                    reasons.append(f"VWAP 偏离 {dev_norm:.2f}σ")
                if near_or_low:
                    reasons.append("接近 OR 低点")
                
                return TradingSignal(
                    signal_type=SignalType.BUY,
                    shares=shares,
                    reason="震荡日低位买入: " + ", ".join(reasons),
                    confidence=min(0.7 + abs(dev_norm) * 0.1, 0.95),
                    price_target=market.vwap,  # 目标回到 VWAP
                    stop_loss=market.or_low * 0.995,  # 止损在 OR 低点下方
                )
        
        # 卖出条件：上沿或显著高于 VWAP，且机动仓 >= 0
        if (dev_norm >= self.chop_sell_threshold or near_or_high) and state.t_inventory >= 0:
            shares = state.get_available_sell_shares()
            if shares > 0:
                reasons = []
                if dev_norm >= self.chop_sell_threshold:
                    reasons.append(f"VWAP 偏离 +{dev_norm:.2f}σ")
                if near_or_high:
                    reasons.append("接近 OR 高点")
                
                return TradingSignal(
                    signal_type=SignalType.SELL,
                    shares=shares,
                    reason="震荡日高位卖出: " + ", ".join(reasons),
                    confidence=min(0.7 + dev_norm * 0.1, 0.95),
                    price_target=market.vwap,
                    stop_loss=market.or_high * 1.005,
                )
        
        return TradingSignal(
            signal_type=SignalType.HOLD,
            reason="震荡日：等待更好的入场点",
        )
    
    def _generate_trend_up_signal(
        self, 
        state: TradingState, 
        market: MarketSnapshot
    ) -> TradingSignal:
        """
        上涨趋势日信号：顺势交易
        
        策略：
        - 回调到 VWAP 附近买入
        - 延伸时减仓
        """
        dev_norm = market.dev_normalized
        
        # 回调买入条件
        if dev_norm <= self.trend_pullback_threshold and state.t_inventory <= 0:
            # 检查是否有支撑
            near_support = market.price >= market.vwap * (1 - self.support_buffer_pct)
            
            if near_support:
                shares = state.get_available_buy_shares()
                if shares > 0:
                    return TradingSignal(
                        signal_type=SignalType.BUY,
                        shares=shares,
                        reason=f"趋势日回调买入: VWAP 偏离 {dev_norm:.2f}σ",
                        confidence=0.75,
                        price_target=market.high,  # 目标新高
                        stop_loss=market.vwap * 0.995,
                    )
        
        # 延伸减仓条件
        if dev_norm >= self.trend_extension_threshold and state.t_inventory > 0:
            shares = state.get_available_sell_shares()
            if shares > 0:
                return TradingSignal(
                    signal_type=SignalType.SELL,
                    shares=shares,
                    reason=f"趋势日延伸减仓: VWAP 偏离 +{dev_norm:.2f}σ",
                    confidence=0.7,
                    price_target=None,  # 无明确目标
                )
        
        return TradingSignal(
            signal_type=SignalType.HOLD,
            reason="趋势日：等待回调或延伸",
        )
    
    def _generate_trend_down_signal(
        self, 
        state: TradingState, 
        market: MarketSnapshot
    ) -> TradingSignal:
        """
        下跌趋势日信号
        
        策略：
        - 反弹减仓（如果有持仓）
        - 回落回补（如果已减仓）
        
        注意：下跌趋势日策略更保守，主要是防守
        """
        dev_norm = market.dev_normalized
        
        # 反弹减仓
        if dev_norm >= -self.trend_pullback_threshold and state.t_inventory > 0:
            shares = state.get_available_sell_shares()
            if shares > 0:
                return TradingSignal(
                    signal_type=SignalType.SELL,
                    shares=shares,
                    reason=f"下跌趋势日反弹减仓: VWAP 偏离 {dev_norm:+.2f}σ",
                    confidence=0.7,
                )
        
        # 回落回补（仅当之前有减仓）
        if dev_norm <= -self.trend_extension_threshold and state.t_inventory < 0:
            shares = state.get_available_buy_shares()
            if shares > 0:
                return TradingSignal(
                    signal_type=SignalType.BUY,
                    shares=shares,
                    reason=f"下跌趋势日回落回补: VWAP 偏离 {dev_norm:.2f}σ",
                    confidence=0.65,
                )
        
        return TradingSignal(
            signal_type=SignalType.HOLD,
            reason="下跌趋势日：保守等待",
        )
    
    def _generate_event_signal(
        self, 
        state: TradingState, 
        market: MarketSnapshot
    ) -> TradingSignal:
        """
        事件日信号：更宽阈值，更小仓位
        
        策略：类似震荡日，但阈值更宽，仓位更小
        """
        dev_norm = market.dev_normalized
        
        # 买入条件（更严格）
        if dev_norm <= self.event_buy_threshold and state.t_inventory <= 0:
            shares = int(state.get_available_buy_shares() * self.event_size_multiplier)
            if shares > 0:
                return TradingSignal(
                    signal_type=SignalType.BUY,
                    shares=shares,
                    reason=f"事件日低位买入: VWAP 偏离 {dev_norm:.2f}σ (仓位缩小)",
                    confidence=0.6,
                    price_target=market.vwap,
                )
        
        # 卖出条件（更严格）
        if dev_norm >= self.event_sell_threshold and state.t_inventory >= 0:
            shares = int(state.get_available_sell_shares() * self.event_size_multiplier)
            if shares > 0:
                return TradingSignal(
                    signal_type=SignalType.SELL,
                    shares=shares,
                    reason=f"事件日高位卖出: VWAP 偏离 +{dev_norm:.2f}σ (仓位缩小)",
                    confidence=0.6,
                    price_target=market.vwap,
                )
        
        return TradingSignal(
            signal_type=SignalType.HOLD,
            reason="事件日：保守等待更大偏离",
        )
    
    def _update_breakout_tracking(self, market: MarketSnapshot):
        """更新突破追踪"""
        if market.price > market.or_high:
            self._breakout_up_bars += 1
            self._breakout_down_bars = 0
        elif market.price < market.or_low:
            self._breakout_down_bars += 1
            self._breakout_up_bars = 0
        else:
            # 回到区间内，重置
            self._breakout_up_bars = 0
            self._breakout_down_bars = 0
    
    def _is_breakout_confirmed(self) -> bool:
        """检查突破是否确认"""
        return (
            self._breakout_up_bars >= self.breakout_hold_bars or
            self._breakout_down_bars >= self.breakout_hold_bars
        )
    
    def reset_daily(self):
        """每日重置"""
        self._breakout_up_bars = 0
        self._breakout_down_bars = 0
    
    @classmethod
    def from_config(cls, config: dict[str, Any]) -> SignalGenerator:
        """从配置创建"""
        thresholds = config.get("thresholds", {})
        chop = thresholds.get("chop", {})
        trend = thresholds.get("trend", {})
        event = thresholds.get("event", {})
        
        return cls(
            chop_buy_threshold=chop.get("buy_threshold", -1.0),
            chop_sell_threshold=chop.get("sell_threshold", 1.0),
            or_band_pct=chop.get("or_band_pct", 0.002),
            breakout_hold_bars=chop.get("breakout_hold_bars", 5),
            trend_pullback_threshold=trend.get("pullback_threshold", -0.5),
            trend_extension_threshold=trend.get("extension_threshold", 1.5),
            support_buffer_pct=trend.get("support_buffer_pct", 0.003),
            event_buy_threshold=event.get("buy_threshold", -1.5),
            event_sell_threshold=event.get("sell_threshold", 1.5),
            event_size_multiplier=event.get("size_multiplier", 0.5),
        )
