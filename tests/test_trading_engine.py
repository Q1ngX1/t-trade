"""
交易引擎测试
"""

import pytest
from datetime import datetime, time

from tbot.engine.state import TradingState, TradeDirection
from tbot.engine.risk_gate import RiskGate, MarketData
from tbot.engine.signal_generator import SignalGenerator, MarketSnapshot
from tbot.engine.engine import TradingEngine, EngineConfig
from tbot.regime.rules import Regime


class TestTradingState:
    """交易状态测试"""
    
    def test_initial_state(self):
        """测试初始状态"""
        state = TradingState(
            symbol="AAPL",
            core_shares=100,
            t_max_shares=50,
            t_step_shares=25,
        )
        
        assert state.t_inventory == 0
        assert state.round_trips_done == 0
        assert state.daily_pnl == 0.0
        assert state.can_buy()
        assert state.can_sell()
    
    def test_record_buy(self):
        """测试记录买入"""
        state = TradingState(symbol="AAPL", t_step_shares=25)
        
        trade = state.record_buy(25, 150.0, "测试买入")
        
        assert trade.direction == TradeDirection.BUY
        assert trade.shares == 25
        assert trade.price == 150.0
        assert state.t_inventory == 25
        assert len(state.trades) == 1
    
    def test_record_sell(self):
        """测试记录卖出"""
        state = TradingState(symbol="AAPL", t_step_shares=25)
        
        # 先买入
        state.record_buy(25, 150.0)
        # 再卖出
        trade = state.record_sell(25, 152.0, "测试卖出")
        
        assert trade.direction == TradeDirection.SELL
        assert state.t_inventory == 0
        assert state.round_trips_done == 1
        assert state.daily_pnl == 25 * (152.0 - 150.0)  # $50 盈利
    
    def test_round_trip_completion(self):
        """测试回合完成"""
        state = TradingState(symbol="AAPL", t_step_shares=25)
        
        # 第一个回合
        state.record_buy(25, 100.0)
        state.record_sell(25, 102.0)
        assert state.round_trips_done == 1
        assert state.daily_pnl == 50.0  # 25 * $2
        
        # 第二个回合
        state.record_sell(25, 103.0)  # 先卖
        state.record_buy(25, 101.0)   # 再买回
        assert state.round_trips_done == 2
        assert state.daily_pnl == 100.0  # 50 + 25 * $2
    
    def test_available_shares(self):
        """测试可用股数计算"""
        state = TradingState(
            symbol="AAPL",
            t_max_shares=50,
            t_step_shares=25,
        )
        
        # 初始状态
        assert state.get_available_buy_shares() == 25
        assert state.get_available_sell_shares() == 25
        
        # 买入后
        state.t_inventory = 25
        assert state.get_available_buy_shares() == 25  # 还能买25
        assert state.get_available_sell_shares() == 25
        
        # 买满后
        state.t_inventory = 50
        assert state.get_available_buy_shares() == 0
        assert state.get_available_sell_shares() == 25


class TestRiskGate:
    """风险门控测试"""
    
    def test_daily_loss_limit(self):
        """测试日内亏损限制"""
        gate = RiskGate(daily_loss_limit=100.0)
        state = TradingState(symbol="AAPL")
        state.daily_pnl = -50.0
        
        result = gate._check_daily_loss(state)
        assert result.passed
        
        state.daily_pnl = -100.0
        result = gate._check_daily_loss(state)
        assert not result.passed
    
    def test_time_buffer(self):
        """测试开盘禁做时间"""
        gate = RiskGate(
            open_buffer_minutes=30,
            event_open_buffer_minutes=60,
        )
        
        # 普通日 9:45 前不能交易
        early_time = datetime(2025, 1, 6, 9, 29)
        result = gate._check_time_buffer(early_time, Regime.RANGE)
        assert not result.passed
        
        # 普通日 9:45 后可以交易
        later_time = datetime(2025, 1, 6, 10, 0)
        result = gate._check_time_buffer(later_time, Regime.RANGE)
        assert result.passed
        
        # 事件日需要等到 10:30
        event_early = datetime(2025, 1, 6, 10, 0)
        result = gate._check_time_buffer(event_early, Regime.EVENT)
        assert not result.passed
        
        event_later = datetime(2025, 1, 6, 10, 30)
        result = gate._check_time_buffer(event_later, Regime.EVENT)
        assert result.passed
    
    def test_cooldown(self):
        """测试交易冷却期"""
        gate = RiskGate(cooldown_minutes=15)
        state = TradingState(symbol="AAPL")
        
        # 没有上次交易
        result = gate._check_cooldown(state, datetime.now())
        assert result.passed
        
        # 刚交易完
        state.last_trade_time = datetime(2025, 1, 6, 10, 0)
        current = datetime(2025, 1, 6, 10, 10)
        result = gate._check_cooldown(state, current)
        assert not result.passed
        
        # 冷却期过后
        current = datetime(2025, 1, 6, 10, 20)
        result = gate._check_cooldown(state, current)
        assert result.passed
    
    def test_round_trips_limit(self):
        """测试回合数限制"""
        gate = RiskGate(max_round_trips_per_day=2)
        state = TradingState(symbol="AAPL")
        
        state.round_trips_done = 1
        result = gate._check_round_trips(state)
        assert result.passed
        
        state.round_trips_done = 2
        result = gate._check_round_trips(state)
        assert not result.passed
    
    def test_spread_check(self):
        """测试价差检查"""
        gate = RiskGate(max_spread_pct=0.005)
        
        # 正常价差
        market = MarketData(price=100.0, spread_pct=0.003)
        result = gate._check_spread(market)
        assert result.passed
        
        # 价差过大
        market = MarketData(price=100.0, spread_pct=0.01)
        result = gate._check_spread(market)
        assert not result.passed


class TestSignalGenerator:
    """信号生成器测试"""
    
    def test_chop_buy_signal(self):
        """测试震荡日买入信号"""
        gen = SignalGenerator(chop_buy_threshold=-1.0)
        state = TradingState(symbol="AAPL", t_step_shares=25)
        
        # 低于 VWAP 1个标准差
        market = MarketSnapshot(
            price=99.0,
            vwap=100.0,
            high=101.0,
            low=98.0,
            open=100.0,
            volume=10000,
            or_high=101.0,
            or_low=99.0,
            intraday_vol=1.0,  # dev_norm = -1.0
        )
        
        signal = gen._generate_chop_signal(state, market)
        assert signal.signal_type.value == "buy"
        assert signal.shares == 25
    
    def test_chop_sell_signal(self):
        """测试震荡日卖出信号"""
        gen = SignalGenerator(chop_sell_threshold=1.0)
        state = TradingState(symbol="AAPL", t_step_shares=25)
        
        # 高于 VWAP 1个标准差
        market = MarketSnapshot(
            price=101.0,
            vwap=100.0,
            high=102.0,
            low=99.0,
            open=100.0,
            volume=10000,
            or_high=101.5,
            or_low=99.0,
            intraday_vol=1.0,
        )
        
        signal = gen._generate_chop_signal(state, market)
        assert signal.signal_type.value == "sell"
    
    def test_trend_up_pullback_buy(self):
        """测试趋势日回调买入"""
        gen = SignalGenerator(
            trend_pullback_threshold=-0.5,
            support_buffer_pct=0.01,  # 1% 缓冲
        )
        state = TradingState(symbol="AAPL", t_step_shares=25)
        
        # 回调到 VWAP 附近但仍在支撑上方
        # price=99.5, vwap=100, dev=-0.5, support=99.0
        market = MarketSnapshot(
            price=99.5,
            vwap=100.0,
            high=102.0,
            low=99.0,
            open=100.0,
            volume=10000,
            or_high=101.0,
            or_low=99.0,
            intraday_vol=1.0,  # dev_norm = -0.5
        )
        
        signal = gen._generate_trend_up_signal(state, market)
        assert signal.signal_type.value == "buy"
    
    def test_event_wider_threshold(self):
        """测试事件日更宽阈值"""
        gen = SignalGenerator(
            event_buy_threshold=-1.5,
            event_sell_threshold=1.5,
        )
        state = TradingState(symbol="AAPL", t_step_shares=25)
        
        # -1.0 偏离在事件日不会触发买入
        market = MarketSnapshot(
            price=99.0,
            vwap=100.0,
            high=101.0,
            low=98.0,
            open=100.0,
            volume=10000,
            or_high=101.0,
            or_low=99.0,
            intraday_vol=1.0,
        )
        
        signal = gen._generate_event_signal(state, market)
        assert signal.signal_type.value == "hold"
        
        # -1.5 偏离才会触发
        market.price = 98.5
        signal = gen._generate_event_signal(state, market)
        assert signal.signal_type.value == "buy"


class TestTradingEngine:
    """交易引擎测试"""
    
    def test_add_symbol(self):
        """测试添加股票"""
        engine = TradingEngine()
        
        state = engine.add_symbol("AAPL")
        
        assert "AAPL" in engine._states
        assert engine.get_regime("AAPL") == Regime.UNKNOWN
    
    def test_set_regime(self):
        """测试设置日类型"""
        engine = TradingEngine()
        engine.add_symbol("AAPL")
        
        engine.set_regime("AAPL", Regime.RANGE)
        
        assert engine.get_regime("AAPL") == Regime.RANGE
    
    def test_market_update_with_risk_gate(self):
        """测试带风险门控的行情更新"""
        engine = TradingEngine()
        engine.add_symbol("AAPL")
        engine.set_regime("AAPL", Regime.RANGE)
        
        market = MarketSnapshot(
            price=99.0,
            vwap=100.0,
            high=101.0,
            low=98.0,
            open=100.0,
            volume=10000,
            or_high=101.0,
            or_low=99.0,
            intraday_vol=1.0,
        )
        
        # 开盘禁做期
        early_time = datetime(2025, 1, 6, 9, 35)
        signal = engine.on_market_update("AAPL", market, early_time)
        
        assert signal.signal_type.value == "hold"
        assert "风险门控" in signal.reason
    
    def test_full_trading_flow(self):
        """测试完整交易流程"""
        engine = TradingEngine(
            config=EngineConfig(
                core_shares=100,
                t_max_shares=50,
                t_step_shares=25,
                simulation_mode=True,
            )
        )
        engine.add_symbol("AAPL")
        engine.set_regime("AAPL", Regime.RANGE)
        
        # 可以交易的时间
        trade_time = datetime(2025, 1, 6, 10, 30)
        
        # 低位买入
        low_market = MarketSnapshot(
            price=99.0,
            vwap=100.0,
            high=101.0,
            low=98.0,
            open=100.0,
            volume=10000,
            or_high=101.0,
            or_low=99.0,
            intraday_vol=1.0,
        )
        
        signal = engine.on_market_update("AAPL", low_market, trade_time)
        
        # 应该生成买入信号并执行
        state = engine.get_state("AAPL")
        assert state.t_inventory == 25
        assert len(state.trades) == 1
    
    def test_daily_reset(self):
        """测试日期变更重置"""
        engine = TradingEngine()
        engine.add_symbol("AAPL")
        
        state = engine.get_state("AAPL")
        state.t_inventory = 25
        state.round_trips_done = 1
        engine.set_regime("AAPL", Regime.RANGE)
        
        # 模拟日期变更
        engine._current_date = datetime(2025, 1, 5).date()
        engine._check_date_change(datetime(2025, 1, 6).date())
        
        assert state.t_inventory == 0
        assert state.round_trips_done == 0
        assert engine.get_regime("AAPL") == Regime.UNKNOWN
