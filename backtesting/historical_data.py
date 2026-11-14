"""
Historical Market Data Generator & Loader for Backtesting (with Survivorship-Bias Controls).
Includes active breakout tokens, trend pullback tokens, liquidity sweep reversals,
smart money accumulation tokens, AND delisted/rugged/inactive tokens so backtests
never suffer from survivorship bias.
"""
from __future__ import annotations

import math
from typing import Dict, List

from database.models import (
    MarketSnapshot,
    OHLCVBar,
    PoolState,
    SentimentSnapshot,
    TokenMetadata,
    WalletActivitySnapshot,
)
from shared_core.data_engine import DataEngine


class HistoricalDatasetBuilder:
    """Builds multi-token historical time-series slices including rugged/delisted tokens."""

    @staticmethod
    def build_multi_regime_dataset(num_steps: int = 36) -> List[List[MarketSnapshot]]:
        """
        Return a chronological list of time steps (t = 0 .. num_steps-1).
        At each step t, returns MarketSnapshots containing ONLY bars up to index t
        (strictly causal, zero future information).
        Includes 5 tokens across distinct regimes (including 1 scam/honeypot and 1 slow rug/delisted token).
        """
        base_ts = 1760000000.0
        timeline: List[List[MarketSnapshot]] = []

        # Pre-generate full bar histories, then slice causally up to step t
        token_specs = [
            {
                "mint": "SoLMeMeBrkOut11111111111111111111111111111",
                "symbol": "BONKAI",
                "name": "Bonk AI Momentum",
                "venue": "raydium",
                "pool": "RayPoolBrkOut11111111111111111111111111111",
                "mint_auth": False,
                "freeze_auth": False,
                "top10_pct": 24.0,
                "base_liq": 85000.0,
                "lp_locked": 95.0,
                "regime_type": "BREAKOUT",
            },
            {
                "mint": "SoLMeMeSmAccum2222222222222222222222222222",
                "symbol": "WHALEDOG",
                "name": "Whale Dog Accumulation",
                "venue": "orca",
                "pool": "OrcaPoolWhale22222222222222222222222222222",
                "mint_auth": False,
                "freeze_auth": False,
                "top10_pct": 28.0,
                "base_liq": 62000.0,
                "lp_locked": 90.0,
                "regime_type": "ACCUMULATION",
            },
            {
                "mint": "SoLMeMePullback333333333333333333333333333",
                "symbol": "CATTREND",
                "name": "Cat Trend Pullback",
                "venue": "meteora",
                "pool": "MetPoolCat33333333333333333333333333333333",
                "mint_auth": False,
                "freeze_auth": False,
                "top10_pct": 31.0,
                "base_liq": 54000.0,
                "lp_locked": 88.0,
                "regime_type": "PULLBACK",
            },
            {
                "mint": "SoLScamHoneypot444444444444444444444444444",
                "symbol": "RUGTRAP",
                "name": "Malicious Honeypot Token",
                "venue": "raydium",
                "pool": "RayPoolScam4444444444444444444444444444444",
                "mint_auth": True,
                "freeze_auth": True,
                "top10_pct": 84.0,
                "base_liq": 40000.0,
                "lp_locked": 10.0,
                "regime_type": "SCAM_HONEYPOT",
            },
            {
                "mint": "SoLDelistedDead555555555555555555555555555",
                "symbol": "DEADCOIN",
                "name": "Survivorship Bias Control Token",
                "venue": "raydium",
                "pool": "RayPoolDead5555555555555555555555555555555",
                "mint_auth": False,
                "freeze_auth": False,
                "top10_pct": 48.0,
                "base_liq": 22000.0,
                "lp_locked": 60.0,
                "regime_type": "DELISTED_DECAY",
            },
        ]

        # Build bar series per token
        bars_by_mint: Dict[str, List[OHLCVBar]] = {spec["mint"]: [] for spec in token_specs}
        for spec in token_specs:
            price = 0.0010
            mint = spec["mint"]
            rtype = spec["regime_type"]
            for i in range(num_steps + 15):
                ts = base_ts + i * 300.0
                if rtype == "BREAKOUT":
                    drift = 0.028 if (12 <= i <= 26) else (0.004 if i < 12 else -0.008)
                    wave = math.sin(i * 0.5) * 0.008
                    vol = 18000.0 if (12 <= i <= 26) else 4500.0
                elif rtype == "ACCUMULATION":
                    drift = -0.055 if (20 <= i <= 21) else (0.024 if (15 <= i <= 32) else 0.003)
                    wave = math.cos(i * 0.4) * 0.006
                    vol = 12000.0 if (15 <= i <= 30) else 3800.0
                elif rtype == "PULLBACK":
                    drift = -0.045 if (19 <= i <= 22) else (0.024 if 10 <= i <= 32 else 0.002)
                    wave = math.sin(i * 0.3) * 0.005
                    vol = 9500.0
                elif rtype == "SCAM_HONEYPOT":
                    drift = 0.055 if i < 25 else -0.45
                    wave = 0.0
                    vol = 25000.0
                else:  # DELISTED_DECAY (survivorship-bias control)
                    drift = -0.035 if i >= 18 else 0.005
                    wave = -0.004
                    vol = 2500.0 if i < 25 else 150.0

                open_p = price
                close_p = max(1e-7, open_p * (1.0 + drift + wave))
                high_p = max(open_p, close_p) * 1.012
                low_p = min(open_p, close_p) * 0.988
                price = close_p
                bars_by_mint[mint].append(
                    OHLCVBar(
                        timestamp=ts,
                        open=round(open_p, 8),
                        high=round(high_p, 8),
                        low=round(low_p, 8),
                        close=round(close_p, 8),
                        volume_usd=vol,
                        buy_volume_usd=vol * (0.65 if drift > 0 else 0.35),
                        sell_volume_usd=vol * (0.35 if drift > 0 else 0.65),
                        liquidity_usd=spec["base_liq"],
                    )
                )

        # Construct causal snapshots step-by-step (window end = 15 + step)
        for step in range(num_steps):
            idx = 15 + step
            step_ts = base_ts + idx * 300.0
            step_snapshots: List[MarketSnapshot] = []

            for spec in token_specs:
                mint = spec["mint"]
                rtype = spec["regime_type"]
                causal_bars = bars_by_mint[mint][: idx + 1]
                cur_bar = causal_bars[-1]
                prev_bar = causal_bars[-2]
                bar_1h_ago = causal_bars[max(0, len(causal_bars) - 12)]

                pc_5m = ((cur_bar.close / prev_bar.close) - 1.0) * 100.0
                pc_1h = ((cur_bar.close / bar_1h_ago.close) - 1.0) * 100.0
                vol_1h = sum(b.volume_usd for b in causal_bars[-12:])

                liq_now = spec["base_liq"]
                liq_change_1h = 5.0
                if rtype == "DELISTED_DECAY" and step >= 12:
                    liq_now = max(2000.0, spec["base_liq"] * (0.65 ** (step - 11)))
                    liq_change_1h = -38.0

                buys_5m = 38 if pc_5m > 0 else 12
                sells_5m = 14 if pc_5m > 0 else 28
                if rtype == "SCAM_HONEYPOT":
                    buys_5m, sells_5m = 50, 0

                pool = DataEngine.normalize_pool_record(
                    {
                        "pool_address": spec["pool"],
                        "dex_venue": spec["venue"],
                        "base_mint": mint,
                        "quote_mint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
                        "base_symbol": spec["symbol"],
                        "quote_symbol": "USDT",
                        "price_usd": cur_bar.close,
                        "price_quote": cur_bar.close,
                        "liquidity_usd": liq_now,
                        "volume_5m_usd": cur_bar.volume_usd,
                        "volume_1h_usd": vol_1h,
                        "volume_24h_usd": vol_1h * 8.0,
                        "buys_5m": buys_5m,
                        "sells_5m": sells_5m,
                        "buys_1h": buys_5m * 8,
                        "sells_1h": 0 if rtype == "SCAM_HONEYPOT" else sells_5m * 8,
                        "price_change_5m_pct": pc_5m,
                        "price_change_1h_pct": pc_1h,
                        "price_change_24h_pct": pc_1h * 1.5,
                        "lp_locked_pct": spec["lp_locked"],
                        "liquidity_change_1h_pct": liq_change_1h,
                        "timestamp": step_ts,
                    }
                )

                token = TokenMetadata(
                    mint_address=mint,
                    symbol=spec["symbol"],
                    name=spec["name"],
                    decimals=6,
                    mint_authority_active=spec["mint_auth"],
                    freeze_authority_active=spec["freeze_auth"],
                    deployer_wallet=f"Deployer_{spec['symbol']}",
                    top_10_holder_pct=spec["top10_pct"],
                    holder_count=1850 + step * 25,
                    holder_growth_1h_pct=8.5 if pc_1h > 0 else -1.5,
                )

                sm_inflow = 4200.0 if rtype in ("BREAKOUT", "ACCUMULATION", "PULLBACK") else -3500.0
                wallet_act = WalletActivitySnapshot(
                    mint_address=mint,
                    smart_money_net_inflow_usd=sm_inflow,
                    smart_money_buyers_count=9 if sm_inflow > 0 else 1,
                    smart_money_sellers_count=2 if sm_inflow > 0 else 8,
                    large_tx_count_1h=6,
                    early_sniper_dump_detected=(rtype == "SCAM_HONEYPOT"),
                    developer_sold_pct=75.0 if rtype == "SCAM_HONEYPOT" else 0.0,
                    suspicious_cluster_pct=55.0 if rtype == "SCAM_HONEYPOT" else 8.0,
                    wash_trading_ratio=0.65 if rtype == "SCAM_HONEYPOT" else 0.05,
                    data_available=True,
                    timestamp=step_ts,
                )

                sentiment = SentimentSnapshot(
                    mint_address=mint,
                    mentions_1h=140 if sm_inflow > 0 else 35,
                    mentions_change_pct=68.0 if sm_inflow > 0 else -12.0,
                    positive_ratio=0.76 if sm_inflow > 0 else 0.35,
                    coordinated_promo_risk=0.80 if rtype == "SCAM_HONEYPOT" else 0.08,
                    organic_engagement_score=78.0 if sm_inflow > 0 else 30.0,
                    data_available=True,
                    timestamp=step_ts,
                )

                step_snapshots.append(
                    MarketSnapshot(
                        token=token,
                        primary_pool=pool,
                        all_pools=[pool],
                        ohlcv_bars=causal_bars,
                        wallet_activity=wallet_act,
                        sentiment=sentiment,
                        timestamp=step_ts,
                    )
                )

            timeline.append(step_snapshots)
        return timeline
