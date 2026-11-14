"""
Integration tests for Program B (BacktestEngine and PaperTradingExecutor) and SQLite environment isolation.
"""
from __future__ import annotations

import tempfile
import unittest

from adapters.testing.paper_executor import PaperTradingExecutor
from backtesting.backtest_engine import BacktestEngine
from backtesting.historical_data import HistoricalDatasetBuilder
from config.settings import SystemSettings
from database.database import DatabaseManager
from database.models import ExecutionEnvironment


class TestTestingProgram(unittest.TestCase):
    def test_backtest_and_paper_trading_never_contaminate_live_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/isolated.db"
            settings = SystemSettings(database_path=db_path, initial_simulated_capital_usdt=10.0)
            db = DatabaseManager(db_path)

            bt = BacktestEngine(settings=settings, db=db)
            bt_res = bt.run(HistoricalDatasetBuilder.build_multi_regime_dataset(num_steps=16))
            self.assertGreater(bt_res.signals_generated, 0)
            self.assertGreater(bt_res.scam_tokens_rejected, 0)

            paper = PaperTradingExecutor(settings=settings, db=db)
            for step_snaps in HistoricalDatasetBuilder.build_multi_regime_dataset(num_steps=6):
                paper.step_cycle(step_snaps)

            # Verify LIVE positions table in SQLite has 0 records
            live_positions = db.get_positions(ExecutionEnvironment.LIVE)
            self.assertEqual(len(live_positions), 0)


if __name__ == "__main__":
    unittest.main()
