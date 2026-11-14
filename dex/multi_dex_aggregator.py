"""
Multi-DEX Aggregator.
Combines pool states from Raydium, Orca, Meteora, and DexScreener into unified
MarketSnapshot objects with cross-pool arbitrage/spread detection and primary pool selection.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from database.models import MarketSnapshot, PoolState, TokenMetadata
from dex.pool_discovery import PoolDiscovery
from shared_core.data_engine import DataEngine


class MultiDexAggregator:
    """Normalizes and merges multi-DEX pool data by token mint address."""

    @staticmethod
    def compute_cross_pool_spread_pct(pools: List[PoolState]) -> float:
        """Calculate percentage price spread across different pools for the same token."""
        valid_prices = [p.price_usd for p in pools if p.price_usd > 0 and p.liquidity_usd >= 1000.0]
        if len(valid_prices) < 2:
            return 0.0
        min_p = min(valid_prices)
        max_p = max(valid_prices)
        if min_p <= 0:
            return 0.0
        return round(((max_p - min_p) / min_p) * 100.0, 3)

    @classmethod
    def aggregate_to_snapshots(
        cls,
        pools: List[PoolState],
        known_tokens: Optional[Dict[str, TokenMetadata]] = None,
    ) -> List[MarketSnapshot]:
        """Group multi-DEX pools by mint address and build canonical MarketSnapshots."""
        grouped = PoolDiscovery.group_pools_by_base_mint(pools)
        snapshots: List[MarketSnapshot] = []
        for mint, mint_pools in grouped.items():
            primary = DataEngine.select_primary_pool(mint_pools)
            if primary is None:
                continue
            token = (
                known_tokens[mint]
                if known_tokens and mint in known_tokens
                else TokenMetadata(
                    mint_address=mint,
                    symbol=primary.base_symbol,
                    name=f"{primary.base_symbol} Meme Coin",
                    created_at_ts=primary.created_at_ts,
                )
            )
            snapshots.append(
                MarketSnapshot(
                    token=token,
                    primary_pool=primary,
                    all_pools=mint_pools,
                )
            )
        return DataEngine.deduplicate_snapshots_by_mint(snapshots)
