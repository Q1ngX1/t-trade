"""
交易状态管理模块

管理日内交易状态：
- 机动仓持仓
- 已完成回合数
- 日内盈亏
- 交易记录
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Any

from loguru import logger


class TradeDirection(str, Enum):
    """交易方向"""
    BUY = "buy"
    SELL = "sell"


@dataclass
class TradeRecord:
    """交易记录"""
    symbol: str
    direction: TradeDirection
    shares: int
    price: float
    timestamp: datetime
    reason: str = ""
    
    @property
    def value(self) -> float:
        """交易金额"""
        return self.shares * self.price
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "shares": self.shares,
            "price": self.price,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "value": self.value,
        }


@dataclass
class PositionSnapshot:
    """持仓快照"""
    symbol: str
    core_shares: int  # 底仓
    t_inventory: int  # 机动仓 (正=加仓未减，负=减仓未回补)
    avg_cost: float = 0.0
    current_price: float = 0.0
    
    @property
    def total_shares(self) -> int:
        """总持仓"""
        return self.core_shares + self.t_inventory
    
    @property
    def unrealized_pnl(self) -> float:
        """未实现盈亏"""
        if self.avg_cost <= 0:
            return 0.0
        return (self.current_price - self.avg_cost) * self.total_shares
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "core_shares": self.core_shares,
            "t_inventory": self.t_inventory,
            "total_shares": self.total_shares,
            "avg_cost": self.avg_cost,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
        }


@dataclass
class TradingState:
    """
    交易状态
    
    管理单只股票的日内交易状态
    """
    symbol: str
    
    # 仓位配置
    core_shares: int = 100
    t_max_shares: int = 50
    t_step_shares: int = 25
    
    # 当前状态
    t_inventory: int = 0  # 机动仓持有（正=加了未减，负=减了未回补）
    round_trips_done: int = 0
    daily_pnl: float = 0.0
    last_trade_time: datetime | None = None
    
    # 回合追踪
    _pending_buy_shares: int = 0  # 待配对的买入
    _pending_sell_shares: int = 0  # 待配对的卖出
    _pending_buy_cost: float = 0.0
    _pending_sell_proceeds: float = 0.0
    
    # 交易记录
    trades: list[TradeRecord] = field(default_factory=list)
    
    def reset_daily(self):
        """每日重置"""
        self.t_inventory = 0
        self.round_trips_done = 0
        self.daily_pnl = 0.0
        self.last_trade_time = None
        self._pending_buy_shares = 0
        self._pending_sell_shares = 0
        self._pending_buy_cost = 0.0
        self._pending_sell_proceeds = 0.0
        self.trades = []
        logger.info(f"[{self.symbol}] 交易状态已重置")
    
    def record_buy(self, shares: int, price: float, reason: str = "") -> TradeRecord:
        """
        记录买入
        
        Args:
            shares: 买入股数
            price: 买入价格
            reason: 买入原因
        
        Returns:
            TradeRecord
        """
        now = datetime.now()
        
        record = TradeRecord(
            symbol=self.symbol,
            direction=TradeDirection.BUY,
            shares=shares,
            price=price,
            timestamp=now,
            reason=reason,
        )
        
        self.trades.append(record)
        self.t_inventory += shares
        self.last_trade_time = now
        
        # 回合追踪
        self._pending_buy_shares += shares
        self._pending_buy_cost += shares * price
        
        self._check_round_trip_completion()
        
        logger.info(
            f"[{self.symbol}] 买入 {shares} 股 @ ${price:.2f} | "
            f"机动仓: {self.t_inventory} | 原因: {reason}"
        )
        
        return record
    
    def record_sell(self, shares: int, price: float, reason: str = "") -> TradeRecord:
        """
        记录卖出
        
        Args:
            shares: 卖出股数
            price: 卖出价格
            reason: 卖出原因
        
        Returns:
            TradeRecord
        """
        now = datetime.now()
        
        record = TradeRecord(
            symbol=self.symbol,
            direction=TradeDirection.SELL,
            shares=shares,
            price=price,
            timestamp=now,
            reason=reason,
        )
        
        self.trades.append(record)
        self.t_inventory -= shares
        self.last_trade_time = now
        
        # 回合追踪
        self._pending_sell_shares += shares
        self._pending_sell_proceeds += shares * price
        
        self._check_round_trip_completion()
        
        logger.info(
            f"[{self.symbol}] 卖出 {shares} 股 @ ${price:.2f} | "
            f"机动仓: {self.t_inventory} | 原因: {reason}"
        )
        
        return record
    
    def _check_round_trip_completion(self):
        """检查回合是否完成"""
        # 一买一卖配对完成算一个回合
        matched = min(self._pending_buy_shares, self._pending_sell_shares)
        
        if matched > 0:
            # 计算该回合盈亏
            if self._pending_buy_shares > 0:
                avg_buy = self._pending_buy_cost / self._pending_buy_shares
            else:
                avg_buy = 0
                
            if self._pending_sell_shares > 0:
                avg_sell = self._pending_sell_proceeds / self._pending_sell_shares
            else:
                avg_sell = 0
            
            round_pnl = matched * (avg_sell - avg_buy)
            self.daily_pnl += round_pnl
            
            # 更新待配对数量
            self._pending_buy_shares -= matched
            self._pending_sell_shares -= matched
            
            if self._pending_buy_shares == 0:
                self._pending_buy_cost = 0.0
            else:
                # 按比例减少成本
                self._pending_buy_cost *= (1 - matched / (matched + self._pending_buy_shares))
                
            if self._pending_sell_shares == 0:
                self._pending_sell_proceeds = 0.0
            else:
                self._pending_sell_proceeds *= (1 - matched / (matched + self._pending_sell_shares))
            
            self.round_trips_done += 1
            
            logger.info(
                f"[{self.symbol}] 回合 #{self.round_trips_done} 完成 | "
                f"盈亏: ${round_pnl:+.2f} | 日内累计: ${self.daily_pnl:+.2f}"
            )
    
    def get_available_buy_shares(self) -> int:
        """可买入的股数（做T加仓）"""
        # 如果已有卖出未回补，可以回补
        if self.t_inventory < 0:
            return min(self.t_step_shares, -self.t_inventory)
        # 否则不能超过最大机动仓
        return min(self.t_step_shares, self.t_max_shares - self.t_inventory)
    
    def get_available_sell_shares(self) -> int:
        """可卖出的股数（做T减仓）"""
        # 如果已有买入未卖出，可以卖出
        if self.t_inventory > 0:
            return min(self.t_step_shares, self.t_inventory)
        # 否则不能超过最大机动仓
        return min(self.t_step_shares, self.t_max_shares + self.t_inventory)
    
    def can_buy(self) -> bool:
        """是否可以买入"""
        return self.get_available_buy_shares() > 0
    
    def can_sell(self) -> bool:
        """是否可以卖出"""
        return self.get_available_sell_shares() > 0
    
    def get_position_snapshot(self, current_price: float = 0.0) -> PositionSnapshot:
        """获取持仓快照"""
        return PositionSnapshot(
            symbol=self.symbol,
            core_shares=self.core_shares,
            t_inventory=self.t_inventory,
            current_price=current_price,
        )
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "core_shares": self.core_shares,
            "t_max_shares": self.t_max_shares,
            "t_step_shares": self.t_step_shares,
            "t_inventory": self.t_inventory,
            "round_trips_done": self.round_trips_done,
            "daily_pnl": self.daily_pnl,
            "last_trade_time": self.last_trade_time.isoformat() if self.last_trade_time else None,
            "trades_count": len(self.trades),
            "can_buy": self.can_buy(),
            "can_sell": self.can_sell(),
        }
