"""
Realistic Execution Simulator for Backtesting and Paper Trading.
Models DEX trading fees, bid-ask spread, constant-product price impact, latency slippage,
partial fills on low liquidity, and deterministic transaction failure conditions.
Never assumes orders fill at the raw displayed mid-price.
"""
from __future__ import annotations

from dataclasses import dataclass

from config.risk_config import RiskConfig
from database.models import PoolState
from dex.liquidity_analyzer import LiquidityAnalyzer


@dataclass
class SimulatedFill:
    """Result of a realistic simulated swap execution."""
    executed: bool
    reason: str
    displayed_price_usd: float
    fill_price_usd: float
    filled_notional_usdt: float
    filled_tokens: float
    fee_paid_usdt: float
    slippage_bps_realized: float
    price_impact_pct: float
    is_partial_fill: bool = False


class ExecutionSimulator:
    """Simulates realistic Solana DEX order execution with friction, impact, and latency."""

    def __init__(self, risk_config: RiskConfig, latency_ms: int = 450) -> None:
        self.config = risk_config
        self.latency_ms = latency_ms

    def simulate_buy(
        self,
        pool: PoolState,
        requested_notional_usdt: float,
        max_slippage_bps: int,
    ) -> SimulatedFill:
        if pool.price_usd <= 0 or pool.accessible_liquidity_usd < 500.0:
            return SimulatedFill(
                executed=False,
                reason="Pool delisted, inactive, or insufficient accessible liquidity.",
                displayed_price_usd=pool.price_usd,
                fill_price_usd=0.0,
                filled_notional_usdt=0.0,
                filled_tokens=0.0,
                fee_paid_usdt=self.config.solana_base_tx_fee_usdt,
                slippage_bps_realized=0.0,
                price_impact_pct=0.0,
            )

        # Partial fill if order exceeds 2% of accessible liquidity
        max_fill_notional = pool.accessible_liquidity_usd * 0.02
        is_partial = requested_notional_usdt > max_fill_notional
        actual_notional = min(requested_notional_usdt, max_fill_notional)

        impact_pct = LiquidityAnalyzer.estimate_price_impact_pct(actual_notional, pool)
        half_spread_bps = 15.0  # 0.15% typical half-spread on meme coin AMM pools
        latency_drift_bps = min(40.0, abs(pool.price_change_5m_pct) * 2.5 * (self.latency_ms / 1000.0))
        total_slippage_bps = (impact_pct * 100.0) + half_spread_bps + latency_drift_bps

        if total_slippage_bps > max_slippage_bps:
            return SimulatedFill(
                executed=False,
                reason=f"Simulated slippage ({total_slippage_bps:.1f} bps) exceeded max_slippage_bps ({max_slippage_bps} bps).",
                displayed_price_usd=pool.price_usd,
                fill_price_usd=0.0,
                filled_notional_usdt=0.0,
                filled_tokens=0.0,
                fee_paid_usdt=self.config.solana_base_tx_fee_usdt,
                slippage_bps_realized=round(total_slippage_bps, 2),
                price_impact_pct=impact_pct,
            )

        fill_price = pool.price_usd * (1.0 + total_slippage_bps / 10000.0)
        dex_fee_usdt = actual_notional * (pool.fee_bps / 10000.0)
        total_fee_usdt = round(dex_fee_usdt + self.config.solana_base_tx_fee_usdt, 6)
        net_invested = max(0.0, actual_notional - total_fee_usdt)
        tokens_received = net_invested / fill_price if fill_price > 0 else 0.0

        return SimulatedFill(
            executed=True,
            reason="PARTIAL_FILL" if is_partial else "FILLED",
            displayed_price_usd=pool.price_usd,
            fill_price_usd=round(fill_price, 10),
            filled_notional_usdt=round(actual_notional, 6),
            filled_tokens=tokens_received,
            fee_paid_usdt=total_fee_usdt,
            slippage_bps_realized=round(total_slippage_bps, 2),
            price_impact_pct=impact_pct,
            is_partial_fill=is_partial,
        )

    def simulate_sell(
        self,
        pool: PoolState,
        quantity_tokens: float,
        trigger_price_usd: float,
    ) -> SimulatedFill:
        base_price = min(pool.price_usd, trigger_price_usd) if trigger_price_usd > 0 else pool.price_usd
        gross_notional = quantity_tokens * base_price
        impact_pct = LiquidityAnalyzer.estimate_price_impact_pct(gross_notional, pool)
        half_spread_bps = 15.0
        total_slippage_bps = (impact_pct * 100.0) + half_spread_bps
        fill_price = max(1e-10, base_price * (1.0 - total_slippage_bps / 10000.0))

        executed_gross = quantity_tokens * fill_price
        dex_fee_usdt = executed_gross * (pool.fee_bps / 10000.0)
        total_fee_usdt = round(dex_fee_usdt + self.config.solana_base_tx_fee_usdt, 6)

        return SimulatedFill(
            executed=True,
            reason="EXIT_FILLED",
            displayed_price_usd=base_price,
            fill_price_usd=round(fill_price, 10),
            filled_notional_usdt=round(executed_gross, 6),
            filled_tokens=quantity_tokens,
            fee_paid_usdt=total_fee_usdt,
            slippage_bps_realized=round(total_slippage_bps, 2),
            price_impact_pct=impact_pct,
        )
