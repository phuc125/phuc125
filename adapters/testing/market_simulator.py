"""
Testing Market Simulator Adapter.
Streams live DexScreener/DEX snapshots when available or falls back cleanly to realistic
multi-DEX candidate feeds for Paper Trading without ever submitting real transactions.
"""
from __future__ import annotations

from typing import List, Optional

from backtesting.historical_data import HistoricalDatasetBuilder
from database.models import MarketSnapshot
from dex.dex_scanner import MultiDexScanner


class TestingMarketSimulator:
    """Provides candidate MarketSnapshots for Paper Trading."""

    def __init__(self, scanner: Optional[MultiDexScanner] = None) -> None:
        self.scanner = scanner or MultiDexScanner()
        self._fallback_timeline = HistoricalDatasetBuilder.build_multi_regime_dataset(num_steps=20)
        self._cursor = 0

    def fetch_paper_market_batch(self, prefer_live_feed: bool = True) -> List[MarketSnapshot]:
        if prefer_live_feed:
            live_snaps = self.scanner.discover_and_scan_new_tokens(max_tokens=6)
            if live_snaps:
                return live_snaps
        batch = self._fallback_timeline[self._cursor % len(self._fallback_timeline)]
        self._cursor += 1
        return batch
