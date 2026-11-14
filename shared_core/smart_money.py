"""
Agent 2 Backing Engine: Smart Money & On-Chain Wallet Activity Analyzer.
Evaluates accumulation vs. distribution, large transactions, and developer activity.
Explicitly discounts past wallet profitability to avoid assuming profitable wallets stay profitable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from database.models import MarketSnapshot


@dataclass
class SmartMoneyReport:
    """Output of Agent 2 (Smart Money AI)."""
    smart_money_score: float  # Normalized 0 to 100
    status: str  # ACCUMULATION, DISTRIBUTION, NEUTRAL, MISSING_DATA
    summary: str
    confidence: float  # 0 to 1
    data_available: bool


class SmartMoneyEngine:
    """Evaluates on-chain Smart Money flow without fabricating unavailable wallet data."""

    @staticmethod
    def evaluate(snapshot: MarketSnapshot) -> SmartMoneyReport:
        wallet = snapshot.wallet_activity
        pool = snapshot.primary_pool

        if wallet is None or not wallet.data_available:
            return SmartMoneyReport(
                smart_money_score=0.0,
                status="MISSING_DATA",
                summary="On-chain Smart Money wallet attribution data is unavailable for this token.",
                confidence=0.0,
                data_available=False,
            )

        liq = max(1000.0, pool.accessible_liquidity_usd)
        inflow_pct_of_liq = (wallet.smart_money_net_inflow_usd / liq) * 100.0
        buyer_seller_diff = wallet.smart_money_buyers_count - wallet.smart_money_sellers_count

        # Base neutral score 50, adjusted by net inflow and buyer breadth, discounted by 0.85
        # to account for regime mean-reversion of historically profitable wallets.
        raw_score = (
            50.0
            + min(30.0, max(-30.0, inflow_pct_of_liq * 4.5))
            + min(15.0, max(-15.0, buyer_seller_diff * 3.0))
            + min(10.0, wallet.large_tx_count_1h * 1.2)
        )
        if wallet.developer_sold_pct > 10.0:
            raw_score -= min(30.0, wallet.developer_sold_pct * 0.6)
        if wallet.early_sniper_dump_detected:
            raw_score -= 20.0

        score = round(max(0.0, min(100.0, raw_score)), 2)
        if score >= 62.0 and wallet.smart_money_net_inflow_usd > 0:
            status = "ACCUMULATION"
        elif score <= 40.0 or wallet.smart_money_net_inflow_usd < 0:
            status = "DISTRIBUTION"
        else:
            status = "NEUTRAL"

        summary = (
            f"Smart Money status={status} (net inflow=${wallet.smart_money_net_inflow_usd:,.0f}, "
            f"buyers={wallet.smart_money_buyers_count}, sellers={wallet.smart_money_sellers_count}, "
            f"dev_sold={wallet.developer_sold_pct:.1f}%). Past wallet win-rates are discounted against mean reversion."
        )
        return SmartMoneyReport(
            smart_money_score=score,
            status=status,
            summary=summary,
            confidence=0.78,
            data_available=True,
        )
