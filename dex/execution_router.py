"""
Multi-Venue Execution Router.
Compares direct DEX pools (Raydium, Orca, Meteora) and Jupiter Aggregator quotes
to select the lowest-cost, lowest-impact execution route.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from database.models import PoolState
from dex.jupiter_connector import JupiterAggregatorConnector, SwapQuote
from dex.liquidity_analyzer import LiquidityAnalyzer


@dataclass
class SelectedRoute:
    """Optimal execution route selected across available Solana pools and Jupiter."""
    venue: str
    pool_address: str
    expected_price_usd: float
    expected_output_tokens: float
    estimated_price_impact_pct: float
    estimated_fee_usdt: float
    slippage_bps: int
    via_jupiter_aggregator: bool
    jupiter_quote: Optional[SwapQuote] = None


class ExecutionRouter:
    """Evaluates candidate pools and Jupiter quotes to find the best execution path."""

    def __init__(self, jupiter: Optional[JupiterAggregatorConnector] = None) -> None:
        self.jupiter = jupiter or JupiterAggregatorConnector()

    def select_best_route(
        self,
        pools: List[PoolState],
        order_size_usdt: float,
        slippage_bps: int = 100,
        prefer_jupiter_quote: Optional[SwapQuote] = None,
    ) -> Optional[SelectedRoute]:
        """
        Compare all discovered pools for the token and optional Jupiter quote.
        Returns the route that maximizes net output tokens after price impact and fees.
        """
        if not pools or order_size_usdt <= 0:
            return None

        best_route: Optional[SelectedRoute] = None
        best_net_tokens = -1.0

        for pool in pools:
            if pool.price_usd <= 0 or pool.accessible_liquidity_usd <= 0:
                continue
            impact_pct = LiquidityAnalyzer.estimate_price_impact_pct(order_size_usdt, pool)
            dex_fee_usdt = order_size_usdt * (pool.fee_bps / 10000.0)
            total_fee_usdt = dex_fee_usdt + 0.002  # Add Solana base + priority fee
            net_usdt = max(0.0, order_size_usdt - total_fee_usdt)
            effective_price = pool.price_usd * (1.0 + impact_pct / 100.0)
            expected_tokens = net_usdt / effective_price if effective_price > 0 else 0.0

            if expected_tokens > best_net_tokens:
                best_net_tokens = expected_tokens
                best_route = SelectedRoute(
                    venue=pool.dex_venue,
                    pool_address=pool.pool_address,
                    expected_price_usd=round(effective_price, 10),
                    expected_output_tokens=expected_tokens,
                    estimated_price_impact_pct=impact_pct,
                    estimated_fee_usdt=round(total_fee_usdt, 6),
                    slippage_bps=slippage_bps,
                    via_jupiter_aggregator=False,
                )

        if prefer_jupiter_quote is not None and prefer_jupiter_quote.out_amount_ui > best_net_tokens:
            primary_pool = pools[0]
            eff_price = (
                order_size_usdt / prefer_jupiter_quote.out_amount_ui
                if prefer_jupiter_quote.out_amount_ui > 0
                else primary_pool.price_usd
            )
            best_route = SelectedRoute(
                venue="jupiter:" + "+".join(prefer_jupiter_quote.route_labels),
                pool_address=primary_pool.pool_address,
                expected_price_usd=round(eff_price, 10),
                expected_output_tokens=prefer_jupiter_quote.out_amount_ui,
                estimated_price_impact_pct=prefer_jupiter_quote.price_impact_pct,
                estimated_fee_usdt=prefer_jupiter_quote.estimated_fee_usdt,
                slippage_bps=slippage_bps,
                via_jupiter_aggregator=True,
                jupiter_quote=prefer_jupiter_quote,
            )

        return best_route
