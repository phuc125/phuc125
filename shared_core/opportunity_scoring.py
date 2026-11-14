"""
Opportunity Scoring Engine (0 to 100).
Initial configurable weights:
- Smart Money: 25%
- Volume and Momentum: 25%
- Market Structure: 20%
- Liquidity Quality: 15%
- Sentiment: 15%
Explicitly penalizes missing or stale data and enforces Scam Detection as an independent mandatory gate.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config.risk_config import OpportunityWeights
from database.models import TradeEligibility
from dex.liquidity_analyzer import LiquidityAssessment
from shared_core.market_regime import MarketRegimeReport
from shared_core.scam_detection import ScamDetectionReport
from shared_core.sentiment_engine import SentimentReport
from shared_core.smart_money import SmartMoneyReport


@dataclass
class OpportunityScoreResult:
    """Detailed breakdown of the 0-100 Opportunity Score."""
    total_score: float
    raw_weighted_score: float
    confidence: float
    is_eligible: bool
    component_scores: Dict[str, float] = field(default_factory=dict)
    penalties_applied: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)


class OpportunityScorer:
    """Computes normalized 0-100 opportunity scores with explicit missing/stale data penalties."""

    def __init__(self, weights: Optional[OpportunityWeights] = None) -> None:
        self.weights = weights or OpportunityWeights.from_env()
        self.weights.validate()

    def score(
        self,
        market_report: MarketRegimeReport,
        smart_money_report: SmartMoneyReport,
        sentiment_report: SentimentReport,
        liquidity_report: LiquidityAssessment,
        scam_report: ScamDetectionReport,
        data_timestamp: Optional[float] = None,
        reference_now: Optional[float] = None,
    ) -> OpportunityScoreResult:
        penalties: List[str] = []
        reasons: List[str] = []

        # 1. Smart Money component (0-100)
        if smart_money_report.data_available:
            sm_score = smart_money_report.smart_money_score
            sm_conf = smart_money_report.confidence
            reasons.append(f"Smart Money ({sm_score:.1f}/100): {smart_money_report.status}")
        else:
            # Do NOT silently assign high scores to missing data; assign conservative 35.0 with penalty
            sm_score = 35.0
            sm_conf = 0.25
            penalties.append("Missing Smart Money attribution data (-15pt conservative cap on component).")

        # 2. Volume & Momentum component (0-100)
        vm_score = market_report.momentum_score
        reasons.append(f"Volume & Momentum ({vm_score:.1f}/100): trend={market_report.trend_direction}")

        # 3. Market Structure component (0-100)
        ms_score = market_report.structure_score
        reasons.append(f"Market Structure ({ms_score:.1f}/100): regime={market_report.regime.value}")

        # 4. Liquidity Quality component (0-100)
        lq_score = liquidity_report.quality_score
        reasons.append(
            f"Liquidity Quality ({lq_score:.1f}/100): accessible=${liquidity_report.accessible_liquidity_usd:,.0f}"
        )

        # 5. Sentiment component (0-100)
        if sentiment_report.data_available:
            sent_score = sentiment_report.sentiment_score
            sent_conf = sentiment_report.confidence
            reasons.append(f"Sentiment ({sent_score:.1f}/100): {sentiment_report.social_momentum}")
        else:
            sent_score = 35.0
            sent_conf = 0.25
            penalties.append("Missing social sentiment data (conservative 35/100 component score).")

        raw_weighted = (
            self.weights.smart_money * sm_score
            + self.weights.volume_momentum * vm_score
            + self.weights.market_structure * ms_score
            + self.weights.liquidity_quality * lq_score
            + self.weights.sentiment * sent_score
        )

        # Penalize stale market data if older than 120 seconds
        stale_penalty = 0.0
        if data_timestamp is not None:
            now_val = reference_now if reference_now is not None else time.time()
            age_sec = max(0.0, now_val - data_timestamp)
            if age_sec > 120.0:
                stale_penalty = min(25.0, (age_sec - 120.0) / 30.0)
                penalties.append(f"Stale market data ({age_sec:.0f}s old): -{stale_penalty:.1f} pts.")

        final_score = max(0.0, min(100.0, raw_weighted - stale_penalty))

        # Mandatory independent Scam Detection gate
        is_eligible = scam_report.eligibility == TradeEligibility.ELIGIBLE
        if not is_eligible:
            penalties.append(
                f"MANDATORY SAFETY GATE VETO: Scam classification={scam_report.classification.value} "
                f"(risk_score={scam_report.risk_score:.1f}). High opportunity score cannot override safety gate."
            )

        confidence = round(
            0.25 * sm_conf
            + 0.45 * market_report.confidence
            + 0.15 * sent_conf
            + 0.15 * scam_report.confidence,
            3,
        )

        return OpportunityScoreResult(
            total_score=round(final_score, 2),
            raw_weighted_score=round(raw_weighted, 2),
            confidence=confidence,
            is_eligible=is_eligible,
            component_scores={
                "smart_money": round(sm_score, 2),
                "volume_momentum": round(vm_score, 2),
                "market_structure": round(ms_score, 2),
                "liquidity_quality": round(lq_score, 2),
                "sentiment": round(sent_score, 2),
            },
            penalties_applied=penalties,
            reasons=reasons,
        )
