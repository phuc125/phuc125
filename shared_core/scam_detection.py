"""
Agent 4 Backing Engine: Mandatory Scam, Rug-Pull, and Honeypot Detection Gate.
Evaluates mint authority, freeze authority, holder concentration, liquidity removal,
developer dumping, and wash trading.
A high opportunity score can NEVER override a critical scam warning.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from database.models import (
    MarketSnapshot,
    RiskClassification,
    TradeEligibility,
)
from dex.liquidity_analyzer import LiquidityAnalyzer


@dataclass
class ScamDetectionReport:
    """Output of Agent 4 (Scam Detection AI)."""
    classification: RiskClassification
    risk_score: float  # 0 (safest) to 100 (critical scam)
    eligibility: TradeEligibility
    warning_signs: List[str] = field(default_factory=list)
    confidence: float = 0.85


class ScamDetectionEngine:
    """Mandatory safety gate that rejects or flags suspicious Solana meme coins."""

    @staticmethod
    def evaluate(
        snapshot: MarketSnapshot,
        min_pool_liquidity_usd: float = 15000.0,
    ) -> ScamDetectionReport:
        token = snapshot.token
        pool = snapshot.primary_pool
        wallet = snapshot.wallet_activity

        warnings: List[str] = []
        risk_points = 0.0
        critical_veto = False
        manual_review_needed = False

        # 1. Mint & Freeze Authority checks
        if token.mint_authority_active is True:
            warnings.append("CRITICAL: Mint authority is still active (unlimited token minting risk).")
            risk_points += 45.0
            critical_veto = True
        elif token.mint_authority_active is None:
            warnings.append("Mint authority status unverified on-chain; requires caution.")
            risk_points += 12.0
            manual_review_needed = True

        if token.freeze_authority_active is True:
            warnings.append("CRITICAL: Freeze authority is active (honeypot / account freeze risk).")
            risk_points += 45.0
            critical_veto = True
        elif token.freeze_authority_active is None:
            warnings.append("Freeze authority status unverified on-chain.")
            risk_points += 10.0

        # 2. Liquidity depth & rapid removal checks
        if pool.liquidity_usd < min_pool_liquidity_usd:
            warnings.append(
                f"Pool liquidity (${pool.liquidity_usd:,.0f}) is below minimum threshold (${min_pool_liquidity_usd:,.0f})."
            )
            risk_points += 35.0
            critical_veto = True

        if pool.liquidity_change_1h_pct <= -30.0:
            warnings.append(f"CRITICAL: Rapid LP removal detected ({pool.liquidity_change_1h_pct:.1f}% in 1h).")
            risk_points += 50.0
            critical_veto = True

        # 3. Holder & Insider Concentration
        if token.top_10_holder_pct is not None:
            if token.top_10_holder_pct >= 70.0:
                warnings.append(f"CRITICAL: Extreme top-10 holder concentration ({token.top_10_holder_pct:.1f}%).")
                risk_points += 40.0
                critical_veto = True
            elif token.top_10_holder_pct >= 50.0:
                warnings.append(f"Elevated top-10 holder concentration ({token.top_10_holder_pct:.1f}%).")
                risk_points += 20.0

        # 4. Developer dumping, sniper clusters, and wash trading
        if wallet is not None and wallet.data_available:
            if wallet.developer_sold_pct >= 50.0:
                warnings.append(f"CRITICAL: Developer wallet dumped {wallet.developer_sold_pct:.1f}% of holdings.")
                risk_points += 45.0
                critical_veto = True
            if wallet.early_sniper_dump_detected:
                warnings.append("Early sniper cluster dumping detected.")
                risk_points += 25.0
            if wallet.suspicious_cluster_pct >= 40.0:
                warnings.append(f"Suspicious coordinated wallet cluster holds {wallet.suspicious_cluster_pct:.1f}%.")
                risk_points += 30.0
                critical_veto = True
            if wallet.wash_trading_ratio >= 0.50:
                warnings.append(f"Manipulated wash trading ratio ({wallet.wash_trading_ratio:.2f}).")
                risk_points += 30.0
                critical_veto = True

        # 5. Honeypot sell-block heuristic (many buys, zero sells over 1h)
        if pool.buys_1h >= 30 and pool.sells_1h == 0:
            warnings.append("CRITICAL: 30+ buys with 0 sells in 1h indicates likely Honeypot token.")
            risk_points += 65.0
            critical_veto = True

        liq_eval = LiquidityAnalyzer.evaluate_pool(pool)
        if liq_eval.wash_trading_suspected:
            warnings.extend(liq_eval.warnings)
            risk_points += 25.0

        risk_score = round(min(100.0, risk_points), 2)

        if critical_veto or risk_score >= 65.0:
            classification = RiskClassification.CRITICAL_SCAM
            eligibility = TradeEligibility.REJECTED
        elif risk_score >= 40.0:
            classification = RiskClassification.HIGH_RISK
            eligibility = TradeEligibility.REJECTED
        elif manual_review_needed or risk_score >= 22.0:
            classification = RiskClassification.MODERATE_RISK
            eligibility = (
                TradeEligibility.MANUAL_REVIEW_REQUIRED
                if manual_review_needed and risk_score >= 30.0
                else TradeEligibility.ELIGIBLE
            )
        else:
            classification = RiskClassification.SAFE
            eligibility = TradeEligibility.ELIGIBLE

        return ScamDetectionReport(
            classification=classification,
            risk_score=risk_score,
            eligibility=eligibility,
            warning_signs=warnings,
            confidence=0.90 if token.mint_authority_active is not None else 0.65,
        )
