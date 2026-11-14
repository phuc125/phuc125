"""
Shared Data Engine: Normalizes raw market, pool, OHLCV, wallet, and sentiment records
into canonical MarketSnapshot objects used identically by Live and Testing programs.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from database.models import (
    MarketSnapshot,
    OHLCVBar,
    PoolState,
    SentimentSnapshot,
    TokenMetadata,
    WalletActivitySnapshot,
)


class DataEngine:
    """Normalizes and validates multi-source DEX and on-chain data without fabricating missing fields."""

    @staticmethod
    def compute_accessible_liquidity(
        total_liquidity_usd: float,
        lp_locked_pct: Optional[float],
        fee_bps: int = 30,
    ) -> float:
        """
        Estimate accessible quote-side liquidity after accounting for single-side depth
        (approx 50% of constant-product pool TVL) and unlocked LP rug hair-cuts.
        """
        if total_liquidity_usd <= 0 or math.isnan(total_liquidity_usd):
            return 0.0
        quote_side_depth = total_liquidity_usd * 0.50
        lock_factor = 1.0
        if lp_locked_pct is not None:
            lock_factor = max(0.25, min(1.0, lp_locked_pct / 100.0))
        else:
            lock_factor = 0.70  # Conservative haircut when LP lock status is unknown
        fee_factor = max(0.90, 1.0 - (fee_bps / 10000.0) * 5.0)
        return round(quote_side_depth * lock_factor * fee_factor, 2)

    @classmethod
    def normalize_pool_record(cls, raw: Dict[str, Any], default_venue: str = "unknown") -> PoolState:
        """Convert raw provider dictionary into a validated PoolState object."""
        liq_usd = float(raw.get("liquidity_usd", 0.0) or 0.0)
        lp_locked = raw.get("lp_locked_pct")
        lp_locked_val = float(lp_locked) if lp_locked is not None else None
        fee_bps = int(raw.get("fee_bps", 30) or 30)
        accessible = raw.get("accessible_liquidity_usd")
        if accessible is None:
            accessible_val = cls.compute_accessible_liquidity(liq_usd, lp_locked_val, fee_bps)
        else:
            accessible_val = float(accessible)

        return PoolState(
            pool_address=str(raw.get("pool_address", "")),
            dex_venue=str(raw.get("dex_venue", default_venue)).lower(),
            base_mint=str(raw.get("base_mint", "")),
            quote_mint=str(raw.get("quote_mint", "")),
            base_symbol=str(raw.get("base_symbol", "UNKNOWN")),
            quote_symbol=str(raw.get("quote_symbol", "USDT")),
            price_usd=max(0.0, float(raw.get("price_usd", 0.0) or 0.0)),
            price_quote=max(0.0, float(raw.get("price_quote", raw.get("price_usd", 0.0)) or 0.0)),
            liquidity_usd=max(0.0, liq_usd),
            accessible_liquidity_usd=max(0.0, accessible_val),
            volume_5m_usd=max(0.0, float(raw.get("volume_5m_usd", 0.0) or 0.0)),
            volume_1h_usd=max(0.0, float(raw.get("volume_1h_usd", 0.0) or 0.0)),
            volume_24h_usd=max(0.0, float(raw.get("volume_24h_usd", 0.0) or 0.0)),
            buys_5m=max(0, int(raw.get("buys_5m", 0) or 0)),
            sells_5m=max(0, int(raw.get("sells_5m", 0) or 0)),
            buys_1h=max(0, int(raw.get("buys_1h", 0) or 0)),
            sells_1h=max(0, int(raw.get("sells_1h", 0) or 0)),
            price_change_5m_pct=float(raw.get("price_change_5m_pct", 0.0) or 0.0),
            price_change_1h_pct=float(raw.get("price_change_1h_pct", 0.0) or 0.0),
            price_change_24h_pct=float(raw.get("price_change_24h_pct", 0.0) or 0.0),
            fdv_usd=float(raw["fdv_usd"]) if raw.get("fdv_usd") is not None else None,
            market_cap_usd=float(raw["market_cap_usd"]) if raw.get("market_cap_usd") is not None else None,
            lp_locked_pct=lp_locked_val,
            liquidity_change_1h_pct=float(raw.get("liquidity_change_1h_pct", 0.0) or 0.0),
            fee_bps=fee_bps,
            created_at_ts=float(raw["created_at_ts"]) if raw.get("created_at_ts") is not None else None,
            timestamp=float(raw["timestamp"]) if raw.get("timestamp") is not None else PoolState(
                pool_address="", dex_venue="", base_mint="", quote_mint="",
                base_symbol="", quote_symbol="", price_usd=0, price_quote=0,
                liquidity_usd=0, accessible_liquidity_usd=0, volume_5m_usd=0,
                volume_1h_usd=0, volume_24h_usd=0, buys_5m=0, sells_5m=0,
                buys_1h=0, sells_1h=0, price_change_5m_pct=0, price_change_1h_pct=0,
                price_change_24h_pct=0
            ).timestamp,
        )

    @staticmethod
    def select_primary_pool(pools: List[PoolState]) -> Optional[PoolState]:
        """Select the canonical primary pool for a token based on accessible liquidity and 1h volume."""
        if not pools:
            return None
        return max(
            pools,
            key=lambda p: (p.accessible_liquidity_usd * 0.70 + p.volume_1h_usd * 0.30),
        )

    @staticmethod
    def deduplicate_snapshots_by_mint(snapshots: List[MarketSnapshot]) -> List[MarketSnapshot]:
        """Deduplicate candidate token snapshots by mint_address, merging pools."""
        by_mint: Dict[str, MarketSnapshot] = {}
        for snap in snapshots:
            mint = snap.token.mint_address
            if not mint:
                continue
            if mint not in by_mint:
                by_mint[mint] = snap
            else:
                existing = by_mint[mint]
                seen_addrs = {p.pool_address for p in existing.all_pools}
                for pool in snap.all_pools:
                    if pool.pool_address not in seen_addrs:
                        existing.all_pools.append(pool)
                        seen_addrs.add(pool.pool_address)
                primary = DataEngine.select_primary_pool(existing.all_pools)
                if primary is not None:
                    existing.primary_pool = primary
        return list(by_mint.values())
