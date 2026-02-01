"""
交易引擎主模块

整合所有组件，实现完整的交易逻辑：
- 日类型分类
- 风险门控
- 信号生成
- 交易执行
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Callable, Protocol

import yaml
from loguru import logger

from tbot.engine.state import TradingState, TradeRecord
from tbot.engine.risk_gate import RiskGate, RiskCheckResult, MarketData
from tbot.engine.signal_generator import (
    SignalGenerator, 
    TradingSignal, 
    SignalType,
    MarketSnapshot,
)
from tbot.regime.rules import Regime, RegimeClassifier, ClassificationResult
from tbot.regime.features import RegimeFeatures


class OrderExecutor(Protocol):
    """订单执行器协议"""
    
    def place_limit_buy(
        self, 
        symbol: str, 
        shares: int, 
        price: float,
        improve_pct: float = 0.0,
    ) -> str:
        """下限价买单，返回订单ID"""
        ...
    
    def place_limit_sell(
        self, 
        symbol: str, 
        shares: int, 
        price: float,
        improve_pct: float = 0.0,
    ) -> str:
        """下限价卖单，返回订单ID"""
        ...


class SimulatedExecutor:
    """模拟订单执行器"""
    
    _order_count: int = 0
    
    def place_limit_buy(
        self, 
        symbol: str, 
        shares: int, 
        price: float,
        improve_pct: float = 0.0,
    ) -> str:
        self._order_count += 1
        order_id = f"SIM-BUY-{self._order_count}"
        
        # 价格改善（限价单挂更低价买入）
        limit_price = price * (1 - improve_pct)
        
        logger.info(
            f"[模拟] 限价买单: {symbol} {shares}股 @ ${limit_price:.2f} "
            f"(市价 ${price:.2f}, 改善 {improve_pct:.2%})"
        )
        
        return order_id
    
    def place_limit_sell(
        self, 
        symbol: str, 
        shares: int, 
        price: float,
        improve_pct: float = 0.0,
    ) -> str:
        self._order_count += 1
        order_id = f"SIM-SELL-{self._order_count}"
        
        # 价格改善（限价单挂更高价卖出）
        limit_price = price * (1 + improve_pct)
        
        logger.info(
            f"[模拟] 限价卖单: {symbol} {shares}股 @ ${limit_price:.2f} "
            f"(市价 ${price:.2f}, 改善 {improve_pct:.2%})"
        )
        
        return order_id


@dataclass
class EngineConfig:
    """引擎配置"""
    
    # 仓位配置
    core_shares: int = 100
    t_max_shares: int = 50
    t_step_shares: int = 25
    
    # 价格改善
    price_improve_pct: float = 0.001  # 0.1%
    
    # 模式
    simulation_mode: bool = True
    
    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> EngineConfig:
        pos = config.get("position", {})
        return cls(
            core_shares=pos.get("core_shares", 100),
            t_max_shares=pos.get("t_max_shares", 50),
            t_step_shares=pos.get("t_step_shares", 25),
        )


@dataclass
class TradingEngine:
    """
    交易引擎
    
    整合日类型分类、风险门控、信号生成的完整交易系统
    
    使用流程：
    1. 创建引擎并添加股票
    2. 每次收到行情更新时调用 on_market_update()
    3. 引擎自动进行分类、检查风险、生成信号、执行交易
    """
    
    # 配置
    config: EngineConfig = field(default_factory=EngineConfig)
    
    # 组件
    classifier: RegimeClassifier = field(default_factory=RegimeClassifier)
    risk_gate: RiskGate = field(default_factory=RiskGate)
    signal_generator: SignalGenerator = field(default_factory=SignalGenerator)
    executor: OrderExecutor = field(default_factory=SimulatedExecutor)
    
    # 状态
    _states: dict[str, TradingState] = field(default_factory=dict)
    _regimes: dict[str, Regime] = field(default_factory=dict)
    _last_signals: dict[str, TradingSignal] = field(default_factory=dict)
    _current_date: date | None = None
    
    # 回调
    on_signal: Callable[[str, TradingSignal], None] | None = None
    on_trade: Callable[[str, TradeRecord], None] | None = None
    on_regime_change: Callable[[str, Regime, Regime], None] | None = None
    
    def add_symbol(self, symbol: str) -> TradingState:
        """
        添加股票
        
        Args:
            symbol: 股票代码
        
        Returns:
            TradingState
        """
        if symbol in self._states:
            return self._states[symbol]
        
        state = TradingState(
            symbol=symbol,
            core_shares=self.config.core_shares,
            t_max_shares=self.config.t_max_shares,
            t_step_shares=self.config.t_step_shares,
        )
        
        self._states[symbol] = state
        self._regimes[symbol] = Regime.UNKNOWN
        
        logger.info(f"[{symbol}] 已添加到交易引擎")
        
        return state
    
    def remove_symbol(self, symbol: str):
        """移除股票"""
        self._states.pop(symbol, None)
        self._regimes.pop(symbol, None)
        self._last_signals.pop(symbol, None)
        logger.info(f"[{symbol}] 已从交易引擎移除")
    
    def set_regime(self, symbol: str, regime: Regime):
        """
        手动设置日类型（用于外部分类结果）
        
        Args:
            symbol: 股票代码
            regime: 日类型
        """
        if symbol not in self._regimes:
            return
        
        old_regime = self._regimes[symbol]
        self._regimes[symbol] = regime
        
        if old_regime != regime:
            logger.info(f"[{symbol}] 日类型变更: {old_regime.value} -> {regime.value}")
            if self.on_regime_change:
                self.on_regime_change(symbol, old_regime, regime)
    
    def on_market_update(
        self,
        symbol: str,
        market: MarketSnapshot,
        current_time: datetime,
        market_data: MarketData | None = None,
        features: RegimeFeatures | None = None,
    ) -> TradingSignal:
        """
        处理行情更新
        
        这是主入口点，每次收到新行情时调用
        
        Args:
            symbol: 股票代码
            market: 市场快照
            current_time: 当前时间
            market_data: 市场数据（用于流动性检查）
            features: 分类特征（可选，用于自动分类）
        
        Returns:
            TradingSignal
        """
        # 检查日期变更
        self._check_date_change(current_time.date())
        
        # 确保股票已添加
        if symbol not in self._states:
            self.add_symbol(symbol)
        
        state = self._states[symbol]
        regime = self._regimes[symbol]
        
        # 如果提供了特征且日类型未知，进行分类
        if features and regime == Regime.UNKNOWN:
            result = self.classifier.classify(features)
            self.set_regime(symbol, result.regime)
            regime = result.regime
        
        # 风险检查
        risk_result = self.risk_gate.check_all(
            state=state,
            current_time=current_time,
            market_data=market_data,
            regime=regime,
        )
        
        if not risk_result.passed:
            signal = TradingSignal(
                signal_type=SignalType.HOLD,
                reason=f"风险门控: {risk_result.reason}",
            )
            self._last_signals[symbol] = signal
            return signal
        
        # 生成信号
        signal = self.signal_generator.generate(
            state=state,
            market=market,
            regime=regime,
        )
        
        self._last_signals[symbol] = signal
        
        # 触发回调
        if self.on_signal:
            self.on_signal(symbol, signal)
        
        # 执行交易
        if signal.signal_type != SignalType.HOLD and signal.shares > 0:
            self._execute_signal(symbol, signal, market.price)
        
        return signal
    
    def _execute_signal(self, symbol: str, signal: TradingSignal, price: float):
        """执行交易信号"""
        state = self._states[symbol]
        
        if signal.signal_type == SignalType.BUY:
            # 下买单
            order_id = self.executor.place_limit_buy(
                symbol=symbol,
                shares=signal.shares,
                price=price,
                improve_pct=self.config.price_improve_pct,
            )
            
            # 记录交易（假设成交）
            if self.config.simulation_mode:
                trade = state.record_buy(
                    shares=signal.shares,
                    price=price,
                    reason=signal.reason,
                )
                if self.on_trade:
                    self.on_trade(symbol, trade)
        
        elif signal.signal_type == SignalType.SELL:
            # 下卖单
            order_id = self.executor.place_limit_sell(
                symbol=symbol,
                shares=signal.shares,
                price=price,
                improve_pct=self.config.price_improve_pct,
            )
            
            # 记录交易（假设成交）
            if self.config.simulation_mode:
                trade = state.record_sell(
                    shares=signal.shares,
                    price=price,
                    reason=signal.reason,
                )
                if self.on_trade:
                    self.on_trade(symbol, trade)
    
    def _check_date_change(self, current_date: date):
        """检查日期变更，重置状态"""
        if self._current_date is None:
            self._current_date = current_date
            return
        
        if current_date != self._current_date:
            logger.info(f"日期变更: {self._current_date} -> {current_date}")
            
            # 重置所有状态
            for symbol, state in self._states.items():
                state.reset_daily()
                self._regimes[symbol] = Regime.UNKNOWN
            
            self.signal_generator.reset_daily()
            self._current_date = current_date
    
    def get_state(self, symbol: str) -> TradingState | None:
        """获取交易状态"""
        return self._states.get(symbol)
    
    def get_regime(self, symbol: str) -> Regime:
        """获取日类型"""
        return self._regimes.get(symbol, Regime.UNKNOWN)
    
    def get_last_signal(self, symbol: str) -> TradingSignal | None:
        """获取最后信号"""
        return self._last_signals.get(symbol)
    
    def get_summary(self) -> dict[str, Any]:
        """获取引擎摘要"""
        return {
            "symbols": list(self._states.keys()),
            "states": {
                symbol: state.to_dict() 
                for symbol, state in self._states.items()
            },
            "regimes": {
                symbol: regime.value 
                for symbol, regime in self._regimes.items()
            },
            "last_signals": {
                symbol: signal.to_dict() 
                for symbol, signal in self._last_signals.items()
            },
        }
    
    @classmethod
    def from_config_file(cls, config_path: str) -> TradingEngine:
        """从配置文件创建"""
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        return cls.from_config(config)
    
    @classmethod
    def from_config(cls, config: dict[str, Any]) -> TradingEngine:
        """从配置字典创建"""
        return cls(
            config=EngineConfig.from_dict(config),
            risk_gate=RiskGate.from_config(config),
            signal_generator=SignalGenerator.from_config(config),
        )
