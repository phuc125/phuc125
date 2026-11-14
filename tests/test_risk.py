"""
Unit tests for RiskEngine and PositionSizer (10 USDT initial capital, 0.5% risk per trade,
2% max daily loss, max 2 open positions, emergency stop).
"""
from __future__ import annotations

import unittest

from backtesting.historical_data import HistoricalDatasetBuilder
from config.risk_config import RiskConfig
from database.models import StrategyFamily, TradeAction
from shared_core.position_sizing import PositionSizer
from shared_core.risk_engine import PortfolioRiskState, RiskEngine
from shared_core.strategy_engine import StrategyDecision


class TestRiskManagement(unittest.TestCase):
    def setUp(self) -> None:
        self.config = RiskConfig()
        self.sizer = PositionSizer(self.config)
        self.engine = RiskEngine(self.config)
        self.snap = HistoricalDatasetBuilder.build_multi_regime_dataset(num_steps=3)[2][0]

    def test_position_sizing_respects_half_percent_risk_budget(self) -> None:
        # 10 USDT equity -> 0.5% risk budget = 0.05 USDT
        res = self.sizer.calculate_position_size(
            total_equity_usdt=10.0,
            available_cash_usdt=10.0,
            entry_price_usd=0.0010,
            stop_loss_usd=0.00095,  # 5% stop distance
            accessible_liquidity_usd=50000.0,
            volatility_score=40.0,
        )
        self.assertEqual(res.risk_budget_usdt, 0.05)
        self.assertGreater(res.recommended_notional_usdt, 0.20)
        self.assertLessEqual(res.recommended_notional_usdt, self.config.max_position_size_usdt)

    def test_daily_loss_limit_triggers_emergency_stop_and_rejects(self) -> None:
        strat = StrategyDecision(
            strategy_family=StrategyFamily.MOMENTUM_BREAKOUT,
            action=TradeAction.BUY,
            entry_price_usd=self.snap.primary_pool.price_usd,
            stop_loss_usd=self.snap.primary_pool.price_usd * 0.95,
            take_profit_usd=self.snap.primary_pool.price_usd * 1.12,
            expected_reward_to_risk=2.4,
            reasoning="Test entry",
        )
        # Daily loss of -0.25 USDT on 10 USDT equity exceeds 2% (-0.20 USDT)
        bad_state = PortfolioRiskState(
            total_equity_usdt=10.0,
            available_cash_usdt=9.75,
            daily_realized_pnl_usdt=-0.25,
            daily_unrealized_pnl_usdt=0.0,
            open_positions_count=0,
        )
        decision = self.engine.evaluate_trade_risk(self.snap, strat, bad_state)
        self.assertFalse(decision.approved)
        self.assertTrue(decision.emergency_stop_triggered)


if __name__ == "__main__":
    unittest.main()
