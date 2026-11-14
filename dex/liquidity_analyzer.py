"""
Liquidity Quality & Manipulation Analyzer.
Evaluates accessible liquidity, price impact, wash-trading volume anomalies,
and potential LP removal risks across Solana pools.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from database.models import PoolState


@dataclass
class LiquidityAssessment:
    """Comprehensive liquidity quality and manipulation report for a candidate pool."""
    pool_address: str
    dex_venue: str
    total_liquidity_usd: float
    accessible_liquidity_usd: float
    estimated_price_impact_pct: float
    volume_to_liquidity_ratio_1h: float
    wash_trading_suspected: bool
    lp_removal_warning: bool
    quality_score: float  # Normalized 0 to 100
    warnings: List[str] = field(default_factory=list)


class LiquidityAnalyzer:
    """Analyzes pool depth, constant-product price impact, and wash-trading anomalies."""

    @staticmethod
    def estimate_price_impact_pct(order_size_usdt: float, pool: PoolState) -> float:
        """
        Estimate price impact (%) for a given order size in USDT using constant-product
        quote reserve depth and venue concentration characteristics.
        """
        if order_size_usdt <= 0:
            return 0.0
        effective_depth = max(1.0, pool.accessible_liquidity_usd)
        # Constant product xy = k impact approx: dx / (x + dx)
        raw_impact = (order_size_usdt / (effective_depth + order_size_usdt)) * 100.0
        # Concentrated liquidity pools (Orca Whirlpool, Meteora DLMM) have tighter active bin depth
        if pool.dex_venue in ("orca", "meteora"):
            raw_impact *= 0.85
        return round(min(100.0, raw_impact), 4)

    @classmethod
    def evaluate_pool(cls, pool: PoolState, order_size_usdt: float = 1.0) -> LiquidityAssessment:
        """Evaluate pool liquidity quality on a 0-100 scale and flag anomalies."""
        warnings: List[str] = []
        impact_pct = cls.estimate_price_impact_pct(order_size_usdt, pool)
        vol_liq_ratio = pool.volume_1h_usd / max(1.0, pool.liquidity_usd)

        # Detect suspicious wash trading (extreme 1h volume relative to tiny LP with near-zero net price change
        # or suspiciously symmetric buy/sell counts)
        total_tx = pool.buys_1h + pool.sells_1h
        wash_suspected = False
        if vol_liq_ratio > 12.0 and total_tx < 25:
            wash_suspected = True
            warnings.append("High volume-to-liquidity ratio with abnormally low transaction count (possible wash trading).")
        elif vol_liq_ratio > 25.0 and abs(pool.price_change_1h_pct) < 0.3:
            wash_suspected = True
            warnings.append("Extreme volume turnover with flat price action suggests wash volume.")

        lp_removal_warning = False
        if pool.liquidity_change_1h_pct <= -25.0:
            lp_removal_warning = True
            warnings.append(f"Rapid liquidity drop detected ({pool.liquidity_change_1h_pct:.1f}% in 1h).")
        if pool.lp_locked_pct is not None and pool.lp_locked_pct < 50.0:
            warnings.append(f"Low LP lock percentage ({pool.lp_locked_pct:.1f}%).")

        # Compute 0-100 liquidity quality score
        # 1. Depth score (up to 55 pts for $50k+ accessible liquidity)
        depth_score = min(55.0, (pool.accessible_liquidity_usd / 50000.0) * 55.0)
        # 2. LP lock score (up to 25 pts)
        if pool.lp_locked_pct is not None:
            lock_score = min(25.0, (pool.lp_locked_pct / 100.0) * 25.0)
        else:
            lock_score = 12.5  # Neutral-conservative when unknown
        # 3. Impact & stability score (up to 20 pts)
        impact_penalty = min(20.0, impact_pct * 5.0)
        stability_score = max(0.0, 20.0 - impact_penalty)

        total_score = depth_score + lock_score + stability_score
        if wash_suspected:
            total_score *= 0.55
        if lp_removal_warning:
            total_score *= 0.35

        return LiquidityAssessment(
            pool_address=pool.pool_address,
            dex_venue=pool.dex_venue,
            total_liquidity_usd=pool.liquidity_usd,
            accessible_liquidity_usd=pool.accessible_liquidity_usd,
            estimated_price_impact_pct=impact_pct,
            volume_to_liquidity_ratio_1h=round(vol_liq_ratio, 3),
            wash_trading_suspected=wash_suspected,
            lp_removal_warning=lp_removal_warning,
            quality_score=round(max(0.0, min(100.0, total_score)), 2),
            warnings=warnings,
        )
