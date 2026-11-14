"""
Unit tests for ExecutionSimulator, TransactionMonitor retry reconciliation, and ControlledLiveExecutor.
"""
from __future__ import annotations

import tempfile
import unittest

from adapters.live.live_executor import ControlledLiveExecutor
from adapters.live.live_portfolio import LivePortfolioAdapter
from backtesting.execution_simulator import ExecutionSimulator
from backtesting.historical_data import HistoricalDatasetBuilder
from config.risk_config import RiskConfig
from config.settings import OperatingMode, SystemSettings
from config.wallet_config import WalletConfig
from database.database import DatabaseManager
from database.models import ExecutionEnvironment
from shared_core.signal_engine import SignalEngine
from wallet.transaction_monitor import TransactionMonitor


class TestExecutionEngines(unittest.TestCase):
    def test_execution_simulator_applies_slippage_and_fees(self) -> None:
        sim = ExecutionSimulator(RiskConfig())
        snap = HistoricalDatasetBuilder.build_multi_regime_dataset(num_steps=2)[1][0]
        fill = sim.simulate_buy(snap.primary_pool, requested_notional_usdt=1.0, max_slippage_bps=150)
        self.assertTrue(fill.executed)
        self.assertGreater(fill.fill_price_usd, fill.displayed_price_usd)
        self.assertGreater(fill.fee_paid_usdt, 0.0)

    def test_transaction_monitor_prevents_blind_retry_on_uncertain_tx(self) -> None:
        mon = TransactionMonitor()
        mon.register_transaction("sig_test_123", "Mint123", "BUY", 1.0)
        # In offline environment RPC returns RPC_UNAVAILABLE -> status UNCERTAIN -> cannot retry blindly
        self.assertFalse(mon.can_safely_retry("sig_test_123"))

    def test_live_executor_blocks_when_unauthorized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(f"{tmpdir}/test.db")
            settings = SystemSettings(operating_mode=OperatingMode.PAPER, live_trading_authorized=False)
            risk_cfg = RiskConfig()
            wallet_cfg = WalletConfig()
            portfolio = LivePortfolioAdapter(db=db, initial_capital_usdt=10.0)
            executor = ControlledLiveExecutor(settings, risk_cfg, wallet_cfg, db, portfolio)

            snap = HistoricalDatasetBuilder.build_multi_regime_dataset(num_steps=2)[1][0]
            sig, _ = SignalEngine(risk_cfg).generate_signal(
                snap, portfolio.get_risk_state(), ExecutionEnvironment.LIVE, reference_now=snap.timestamp
            )
            outcome = executor.execute_signal(snap, sig)
            self.assertFalse(outcome.executed)
            self.assertEqual(outcome.stage_reached, "AUTHORIZATION_LOCK")


if __name__ == "__main__":
    unittest.main()
