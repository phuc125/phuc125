"""
Live Market Data Adapter.
Scans Raydium, Orca, Meteora, DexScreener, and Solana RPC for live market snapshots.
"""
from __future__ import annotations

from typing import List, Optional

from database.models import MarketSnapshot
from dex.dex_scanner import MultiDexScanner


class LiveMarketDataAdapter:
    """Provides normalized live market snapshots for live_main.py."""

    def __init__(self, scanner: Optional[MultiDexScanner] = None) -> None:
        self.scanner = scanner or MultiDexScanner()

    def poll_live_snapshots(self, custom_mints: Optional[List[str]] = None) -> List[MarketSnapshot]:
        if custom_mints:
            return self.scanner.scan_mints(custom_mints, enrich_onchain=True)
        return self.scanner.discover_and_scan_new_tokens(max_tokens=10)
