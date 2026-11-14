"""
Unit tests for Multi-DEX Scanner, Deduplication, Liquidity Analyzer, and Execution Router.
"""
from __future__ import annotations

import unittest

from database.models import PoolState
from dex.dexscreener_connector import DexScreenerConnector
from dex.execution_router import ExecutionRouter
from dex.jupiter_connector import SwapQuote
from dex.liquidity_analyzer import LiquidityAnalyzer
from dex.multi_dex_aggregator import MultiDexAggregator
from shared_core.data_engine import DataEngine


class TestDexScanner(unittest.TestCase):
    def test_token_deduplication_and_primary_pool_selection(self) -> None:
        mint = "SoLMintTest11111111111111111111111111111111"
        p_raydium = DataEngine.normalize_pool_record(
            {
                "pool_address": "RayPool111",
                "dex_venue": "raydium",
                "base_mint": mint,
                "quote_mint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
                "base_symbol": "MEMEX",
                "quote_symbol": "USDT",
                "price_usd": 0.0020,
                "liquidity_usd": 90000.0,
                "volume_1h_usd": 45000.0,
                "lp_locked_pct": 95.0,
            }
        )
        p_orca = DataEngine.normalize_pool_record(
            {
                "pool_address": "OrcaPool222",
                "dex_venue": "orca",
                "base_mint": mint,
                "quote_mint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
                "base_symbol": "MEMEX",
                "quote_symbol": "USDT",
                "price_usd": 0.00202,
                "liquidity_usd": 25000.0,
                "volume_1h_usd": 8000.0,
                "lp_locked_pct": 90.0,
            }
        )
        snaps = MultiDexAggregator.aggregate_to_snapshots([p_raydium, p_orca])
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0].primary_pool.pool_address, "RayPool111")
        self.assertEqual(len(snaps[0].all_pools), 2)

        spread = MultiDexAggregator.compute_cross_pool_spread_pct(snaps[0].all_pools)
        self.assertAlmostEqual(spread, 1.0, places=2)

    def test_wash_trading_detection(self) -> None:
        wash_pool = DataEngine.normalize_pool_record(
            {
                "pool_address": "WashPool999",
                "dex_venue": "meteora",
                "base_mint": "SoLWashMint99999999999999999999999999999999",
                "quote_mint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
                "base_symbol": "WASH",
                "quote_symbol": "USDT",
                "price_usd": 0.005,
                "liquidity_usd": 10000.0,
                "volume_1h_usd": 350000.0,
                "buys_1h": 5,
                "sells_1h": 5,
                "price_change_1h_pct": 0.05,
            }
        )
        eval_res = LiquidityAnalyzer.evaluate_pool(wash_pool)
        self.assertTrue(eval_res.wash_trading_suspected)

    def test_execution_router_prefers_better_jupiter_quote(self) -> None:
        pool = DataEngine.normalize_pool_record(
            {
                "pool_address": "RayPoolRoute1",
                "dex_venue": "raydium",
                "base_mint": "SoLRouteMint1111111111111111111111111111111",
                "quote_mint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
                "base_symbol": "ROUTEX",
                "quote_symbol": "USDT",
                "price_usd": 0.01,
                "liquidity_usd": 50000.0,
                "volume_1h_usd": 10000.0,
            }
        )
        router = ExecutionRouter()
        direct = router.select_best_route([pool], order_size_usdt=1.0, slippage_bps=100)
        self.assertIsNotNone(direct)
        assert direct is not None
        self.assertFalse(direct.via_jupiter_aggregator)

        jup_quote = SwapQuote(
            input_mint="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
            output_mint=pool.base_mint,
            in_amount_atomic=1_000_000,
            out_amount_atomic=105_000_000,
            in_amount_ui=1.0,
            out_amount_ui=105.0,
            price_impact_pct=0.05,
            slippage_bps=100,
            estimated_fee_usdt=0.003,
            route_labels=["Raydium", "Meteora"],
        )
        agg = router.select_best_route([pool], order_size_usdt=1.0, slippage_bps=100, prefer_jupiter_quote=jup_quote)
        assert agg is not None
        self.assertTrue(agg.via_jupiter_aggregator)
        self.assertEqual(agg.expected_output_tokens, 105.0)

    def test_dexscreener_pair_parser(self) -> None:
        raw_pair = {
            "chainId": "solana",
            "dexId": "raydium",
            "pairAddress": "PairAddrSol123",
            "baseToken": {"address": "MintSolBase123", "symbol": "SOLCAT"},
            "quoteToken": {"address": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", "symbol": "USDT"},
            "priceUsd": "0.0042",
            "priceNative": "0.000025",
            "liquidity": {"usd": 64000},
            "volume": {"m5": 3200, "h1": 21000, "h24": 150000},
            "txns": {"m5": {"buys": 24, "sells": 11}, "h1": {"buys": 180, "sells": 110}},
            "priceChange": {"m5": 4.2, "h1": 14.5, "h24": 42.0},
        }
        parsed = DexScreenerConnector.parse_dexscreener_pair(raw_pair)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.base_symbol, "SOLCAT")
        self.assertEqual(parsed.liquidity_usd, 64000.0)


if __name__ == "__main__":
    unittest.main()
