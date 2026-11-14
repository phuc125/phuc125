"""
MANDATORY REGRESSION TEST: LIVE vs. TESTING SIGNAL PARITY (test_mode_parity.py)
Verifies that Program A (LIVE) and Program B (PAPER / BACKTEST) produce identical
TradingSignal decisions, opportunity scores, strategy selections, stop-losses, take-profits,
and position sizes when given identical MarketSnapshot data and RiskConfig.
"""
from __future__ import annotations

import unittest

from backtesting.historical_data import HistoricalDatasetBuilder
from config.risk_config import OpportunityWeights, RiskConfig
from database.models import ExecutionEnvironment
from shared_core.portfolio_manager import PortfolioManager
from shared_core.signal_engine import SignalEngine


class TestLiveAndTestingModeParity(unittest.TestCase):
    def test_identical_inputs_produce_equivalent_signals_across_live_paper_and_backtest(self) -> None:
        risk_cfg = RiskConfig()
        weights = OpportunityWeights()
        engine = SignalEngine(risk_config=risk_cfg, weights=weights)

        timeline = HistoricalDatasetBuilder.build_multi_regime_dataset(num_steps=8)
        for step_snaps in timeline:
            for snap in step_snaps:
                pm_live = PortfolioManager(ExecutionEnvironment.LIVE, initial_capital_usdt=10.0)
                pm_paper = PortfolioManager(ExecutionEnvironment.PAPER, initial_capital_usdt=10.0)
                pm_bt = PortfolioManager(ExecutionEnvironment.BACKTEST, initial_capital_usdt=10.0)

                sig_live, _ = engine.generate_signal(
                    snap, pm_live.get_risk_state(), ExecutionEnvironment.LIVE, reference_now=snap.timestamp
                )
                sig_paper, _ = engine.generate_signal(
                    snap, pm_paper.get_risk_state(), ExecutionEnvironment.PAPER, reference_now=snap.timestamp
                )
                sig_bt, _ = engine.generate_signal(
                    snap, pm_bt.get_risk_state(), ExecutionEnvironment.BACKTEST, reference_now=snap.timestamp
                )

                self.assertEqual(sig_live.action, sig_paper.action)
                self.assertEqual(sig_live.action, sig_bt.action)
                self.assertEqual(sig_live.strategy_family, sig_paper.strategy_family)
                self.assertEqual(sig_live.opportunity_score, sig_paper.opportunity_score)
                self.assertEqual(sig_live.scam_risk_score, sig_paper.scam_risk_score)
                self.assertEqual(sig_live.trade_eligibility, sig_paper.trade_eligibility)
                self.assertEqual(sig_live.entry_price_usd, sig_paper.entry_price_usd)
                self.assertEqual(sig_live.stop_loss_usd, sig_paper.stop_loss_usd)
                self.assertEqual(sig_live.take_profit_usd, sig_paper.take_profit_usd)
                self.assertEqual(sig_live.recommended_position_usdt, sig_paper.recommended_position_usdt)
                self.assertEqual(sig_live.ml_prob_positive, sig_paper.ml_prob_positive)


if __name__ == "__main__":
    unittest.main()
