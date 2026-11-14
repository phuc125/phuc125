"""
Unified Multi-DEX Scanner for Solana.
Coordinates Raydium, Orca, Meteora, DexScreener, Jupiter, and Solana RPC to satisfy
all 17 scanner requirements with provider health checks, caching, and fallback support.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from config.dex_config import DexConfig
from database.models import MarketSnapshot, PoolState, TokenMetadata
from dex.dexscreener_connector import DexScreenerConnector
from dex.execution_router import ExecutionRouter, SelectedRoute
from dex.jupiter_connector import JupiterAggregatorConnector
from dex.liquidity_analyzer import LiquidityAnalyzer, LiquidityAssessment
from dex.meteora_connector import MeteoraConnector
from dex.multi_dex_aggregator import MultiDexAggregator
from dex.orca_connector import OrcaConnector
from dex.raydium_connector import RaydiumConnector
from dex.solana_rpc_connector import SolanaRPCConnector
from dex.token_discovery import TokenDiscovery

logger = logging.getLogger("solana_ai_meme_trader.dex_scanner")


class MultiDexScanner:
    """
    Production-oriented Multi-DEX scanner covering Raydium, Orca, Meteora,
    Jupiter (swap aggregator), DexScreener, and Solana RPC.
    """

    def __init__(
        self,
        config: Optional[DexConfig] = None,
        rpc: Optional[SolanaRPCConnector] = None,
        dexscreener: Optional[DexScreenerConnector] = None,
        raydium: Optional[RaydiumConnector] = None,
        orca: Optional[OrcaConnector] = None,
        meteora: Optional[MeteoraConnector] = None,
        jupiter: Optional[JupiterAggregatorConnector] = None,
    ) -> None:
        self.config = config or DexConfig.from_env()
        self.rpc = rpc or SolanaRPCConnector(self.config)
        self.dexscreener = dexscreener or DexScreenerConnector(self.config)
        self.raydium = raydium or RaydiumConnector(self.config)
        self.orca = orca or OrcaConnector(self.config)
        self.meteora = meteora or MeteoraConnector(self.config)
        self.jupiter = jupiter or JupiterAggregatorConnector(self.config)
        self.router = ExecutionRouter(self.jupiter)
        self.token_discovery = TokenDiscovery(self.rpc)

    def scan_mints(
        self,
        mint_addresses: List[str],
        enrich_onchain: bool = False,
    ) -> List[MarketSnapshot]:
        """Scan all supported DEXs for a list of candidate Solana token mints."""
        all_pools: List[PoolState] = []
        for mint in dict.fromkeys(mint_addresses):
            if not mint:
                continue
            all_pools.extend(self.dexscreener.fetch_token_pools(mint))
            all_pools.extend(self.raydium.fetch_pools_by_mint(mint))
            all_pools.extend(self.orca.fetch_whirlpools(mint))
            all_pools.extend(self.meteora.fetch_pairs_by_mint(mint))

        tokens = self.token_discovery.build_token_metadata_from_pools(
            all_pools, enrich_onchain=enrich_onchain
        )
        return MultiDexAggregator.aggregate_to_snapshots(all_pools, known_tokens=tokens)

    def discover_and_scan_new_tokens(self, max_tokens: int = 10) -> List[MarketSnapshot]:
        """Discover newly profiled Solana tokens on DexScreener and scan across all DEXs."""
        mints = self.dexscreener.discover_latest_solana_profiles()[:max_tokens]
        if not mints:
            return []
        return self.scan_mints(mints, enrich_onchain=False)

    def analyze_snapshot_execution(
        self,
        snapshot: MarketSnapshot,
        order_size_usdt: float = 1.0,
        slippage_bps: int = 100,
    ) -> Dict[str, Optional[object]]:
        """Evaluate primary pool liquidity quality and select optimal execution route."""
        liq_report: LiquidityAssessment = LiquidityAnalyzer.evaluate_pool(
            snapshot.primary_pool, order_size_usdt=order_size_usdt
        )
        best_route: Optional[SelectedRoute] = self.router.select_best_route(
            snapshot.all_pools or [snapshot.primary_pool],
            order_size_usdt=order_size_usdt,
            slippage_bps=slippage_bps,
        )
        spread_pct = MultiDexAggregator.compute_cross_pool_spread_pct(snapshot.all_pools)
        return {
            "liquidity_assessment": liq_report,
            "selected_route": best_route,
            "cross_pool_spread_pct": spread_pct,
        }
