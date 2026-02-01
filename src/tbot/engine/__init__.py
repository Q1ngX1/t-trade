"""
T-Trade 交易引擎模块

实现日内 T+0 交易逻辑：
- TradingState: 交易状态管理
- RiskGate: 风险门控
- TradingEngine: 交易引擎
- SignalGenerator: 信号生成
"""

from tbot.engine.state import TradingState, TradeRecord, PositionSnapshot
from tbot.engine.risk_gate import RiskGate, RiskCheckResult
from tbot.engine.signal_generator import SignalGenerator, TradingSignal, SignalType
from tbot.engine.engine import TradingEngine

__all__ = [
    "TradingState",
    "TradeRecord",
    "PositionSnapshot",
    "RiskGate",
    "RiskCheckResult",
    "SignalGenerator",
    "TradingSignal",
    "SignalType",
    "TradingEngine",
]
