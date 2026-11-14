"""Testing Market Data Adapter normalizing snapshots for test_main.py."""
from __future__ import annotations

from typing import List, Optional

from adapters.testing.market_simulator import TestingMarketSimulator
from database.models import MarketSnapshot


class TestingMarketDataAdapter:
    """Normalized market data provider for Paper Trading and Strategy Evaluation."""

    def __init__(self, simulator: Optional[TestingMarketSimulator] = None) -> None:
        self.simulator = simulator or TestingMarketSimulator()

    def get_current_snapshots(self, prefer_live_feed: bool = False) -> List[MarketSnapshot]:
        return self.simulator.fetch_paper_market_batch(prefer_live_feed=prefer_live_feed)
