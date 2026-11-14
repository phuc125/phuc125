"""
Pool Discovery Module.
Aggregates pools across Raydium, Orca, Meteora, and DexScreener, deduplicating by
pool_address and filtering out illiquid or invalid pairs.
"""
from __future__ import annotations

from typing import Dict, List

from database.models import PoolState


class PoolDiscovery:
    """Deduplicates and filters liquidity pools across Solana DEX venues."""

    @staticmethod
    def deduplicate_pools(pools: List[PoolState]) -> List[PoolState]:
        """Deduplicate pools by pool_address, retaining the freshest record."""
        by_addr: Dict[str, PoolState] = {}
        for p in pools:
            if not p.pool_address or p.price_usd <= 0:
                continue
            existing = by_addr.get(p.pool_address)
            if existing is None or p.timestamp >= existing.timestamp:
                by_addr[p.pool_address] = p
        return list(by_addr.values())

    @staticmethod
    def group_pools_by_base_mint(pools: List[PoolState]) -> Dict[str, List[PoolState]]:
        """Group deduplicated pools by base token mint address."""
        grouped: Dict[str, List[PoolState]] = {}
        for pool in PoolDiscovery.deduplicate_pools(pools):
            grouped.setdefault(pool.base_mint, []).append(pool)
        return grouped
