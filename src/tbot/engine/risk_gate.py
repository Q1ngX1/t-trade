"""
风险门控模块

实现交易前的风险检查：
- 日内亏损限制
- 开盘禁做时间
- 交易冷却期
- 价差/深度检查
- 回合数限制
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from loguru import logger

from tbot.engine.state import TradingState
from tbot.regime.rules import Regime


@dataclass
class RiskCheckResult:
    """风险检查结果"""
    passed: bool
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "details": self.details,
        }


@dataclass
class MarketData:
    """市场数据"""
    price: float
    bid: float = 0.0
    ask: float = 0.0
    spread: float = 0.0
    spread_pct: float = 0.0
    bid_size: int = 0
    ask_size: int = 0
    volume: int = 0


@dataclass
class RiskGate:
    """
    风险门控
    
    在执行交易前检查所有风险条件
    """
    
    # 基础参数
    max_round_trips_per_day: int = 2
    daily_loss_limit: float = 100.0
    cooldown_minutes: int = 15
    open_buffer_minutes: int = 30
    event_open_buffer_minutes: int = 60
    
    # 流动性参数
    max_spread_pct: float = 0.005  # 0.5%
    min_depth: int = 100
    
    # 市场时间 (ET)
    market_open: time = field(default_factory=lambda: time(9, 30))
    market_close: time = field(default_factory=lambda: time(16, 0))
    close_only_start: time = field(default_factory=lambda: time(15, 45))
    
    def check_all(
        self,
        state: TradingState,
        current_time: datetime,
        market_data: MarketData | None = None,
        regime: Regime = Regime.UNKNOWN,
    ) -> RiskCheckResult:
        """
        执行所有风险检查
        
        Args:
            state: 交易状态
            current_time: 当前时间
            market_data: 市场数据
            regime: 日类型
        
        Returns:
            RiskCheckResult
        """
        checks = [
            self._check_daily_loss(state),
            self._check_time_buffer(current_time, regime),
            self._check_cooldown(state, current_time),
            self._check_round_trips(state),
            self._check_close_only(current_time),
        ]
        
        # 如果有市场数据，检查流动性
        if market_data:
            checks.append(self._check_spread(market_data))
            checks.append(self._check_depth(market_data))
        
        # 返回第一个失败的检查
        for check in checks:
            if not check.passed:
                return check
        
        return RiskCheckResult(passed=True, reason="所有风险检查通过")
    
    def _check_daily_loss(self, state: TradingState) -> RiskCheckResult:
        """检查日内亏损限制"""
        if state.daily_pnl <= -self.daily_loss_limit:
            return RiskCheckResult(
                passed=False,
                reason=f"触发日内亏损限制",
                details={
                    "daily_pnl": state.daily_pnl,
                    "limit": -self.daily_loss_limit,
                }
            )
        return RiskCheckResult(passed=True)
    
    def _check_time_buffer(
        self, 
        current_time: datetime, 
        regime: Regime
    ) -> RiskCheckResult:
        """检查开盘禁做时间"""
        current_t = current_time.time()
        
        # 确定缓冲时间
        if regime == Regime.EVENT:
            buffer_minutes = self.event_open_buffer_minutes
        else:
            buffer_minutes = self.open_buffer_minutes
        
        # 计算允许交易的最早时间
        open_dt = datetime.combine(current_time.date(), self.market_open)
        earliest_trade = open_dt + timedelta(minutes=buffer_minutes)
        
        if current_time < earliest_trade:
            return RiskCheckResult(
                passed=False,
                reason=f"开盘禁做期（{buffer_minutes}分钟）",
                details={
                    "current_time": current_t.strftime("%H:%M:%S"),
                    "earliest_trade": earliest_trade.time().strftime("%H:%M:%S"),
                    "regime": regime.value,
                }
            )
        return RiskCheckResult(passed=True)
    
    def _check_cooldown(
        self, 
        state: TradingState, 
        current_time: datetime
    ) -> RiskCheckResult:
        """检查交易冷却期"""
        if state.last_trade_time is None:
            return RiskCheckResult(passed=True)
        
        elapsed = (current_time - state.last_trade_time).total_seconds() / 60
        
        if elapsed < self.cooldown_minutes:
            remaining = self.cooldown_minutes - elapsed
            return RiskCheckResult(
                passed=False,
                reason=f"交易冷却期（还需 {remaining:.1f} 分钟）",
                details={
                    "last_trade": state.last_trade_time.strftime("%H:%M:%S"),
                    "elapsed_minutes": elapsed,
                    "cooldown_minutes": self.cooldown_minutes,
                }
            )
        return RiskCheckResult(passed=True)
    
    def _check_round_trips(self, state: TradingState) -> RiskCheckResult:
        """检查回合数限制"""
        if state.round_trips_done >= self.max_round_trips_per_day:
            return RiskCheckResult(
                passed=False,
                reason=f"已达到每日最大回合数",
                details={
                    "round_trips_done": state.round_trips_done,
                    "max_round_trips": self.max_round_trips_per_day,
                }
            )
        return RiskCheckResult(passed=True)
    
    def _check_close_only(self, current_time: datetime) -> RiskCheckResult:
        """检查是否进入收盘前禁止新开仓时段"""
        current_t = current_time.time()
        
        if current_t >= self.close_only_start:
            return RiskCheckResult(
                passed=False,
                reason="收盘前禁止新开仓",
                details={
                    "current_time": current_t.strftime("%H:%M:%S"),
                    "close_only_start": self.close_only_start.strftime("%H:%M"),
                }
            )
        return RiskCheckResult(passed=True)
    
    def _check_spread(self, market_data: MarketData) -> RiskCheckResult:
        """检查价差"""
        if market_data.spread_pct > self.max_spread_pct:
            return RiskCheckResult(
                passed=False,
                reason=f"价差过大",
                details={
                    "spread_pct": f"{market_data.spread_pct:.3%}",
                    "max_spread_pct": f"{self.max_spread_pct:.3%}",
                }
            )
        return RiskCheckResult(passed=True)
    
    def _check_depth(self, market_data: MarketData) -> RiskCheckResult:
        """检查订单簿深度"""
        min_size = min(market_data.bid_size, market_data.ask_size)
        
        if min_size < self.min_depth:
            return RiskCheckResult(
                passed=False,
                reason=f"订单簿深度不足",
                details={
                    "bid_size": market_data.bid_size,
                    "ask_size": market_data.ask_size,
                    "min_depth": self.min_depth,
                }
            )
        return RiskCheckResult(passed=True)
    
    def is_trading_hours(self, current_time: datetime) -> bool:
        """检查是否在交易时间内"""
        current_t = current_time.time()
        return self.market_open <= current_t <= self.market_close
    
    @classmethod
    def from_config(cls, config: dict[str, Any]) -> RiskGate:
        """从配置创建"""
        risk_config = config.get("risk", {})
        liquidity_config = config.get("liquidity", {})
        windows_config = config.get("trading_windows", {})
        
        return cls(
            max_round_trips_per_day=risk_config.get("max_round_trips_per_day", 2),
            daily_loss_limit=risk_config.get("daily_loss_limit", 100.0),
            cooldown_minutes=risk_config.get("cooldown_minutes", 15),
            open_buffer_minutes=risk_config.get("open_buffer_minutes", 30),
            event_open_buffer_minutes=risk_config.get("event_open_buffer_minutes", 60),
            max_spread_pct=liquidity_config.get("max_spread_pct", 0.005),
            min_depth=liquidity_config.get("min_depth", 100),
            market_open=_parse_time(windows_config.get("market_open", "09:30")),
            market_close=_parse_time(windows_config.get("market_close", "16:00")),
            close_only_start=_parse_time(windows_config.get("close_only_start", "15:45")),
        )


def _parse_time(time_str: str) -> time:
    """解析时间字符串"""
    parts = time_str.split(":")
    return time(int(parts[0]), int(parts[1]))
