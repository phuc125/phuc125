"""
Agent 3 Backing Engine: Social & Community Sentiment Analyzer.
Reports missing data transparently rather than inventing sentiment when social feeds are absent.
Detects coordinated promotion and artificial hype spikes.
"""
from __future__ import annotations

from dataclasses import dataclass

from database.models import MarketSnapshot


@dataclass
class SentimentReport:
    """Output of Agent 3 (Sentiment AI)."""
    sentiment_score: float  # Normalized 0 to 100
    social_momentum: str  # SURGING, POSITIVE, NEUTRAL, NEGATIVE, MISSING_DATA
    hype_risk_score: float  # 0 to 100
    summary: str
    confidence: float
    data_available: bool


class SentimentEngine:
    """Evaluates community mentions and coordinated promotion risk."""

    @staticmethod
    def evaluate(snapshot: MarketSnapshot) -> SentimentReport:
        sent = snapshot.sentiment
        if sent is None or not sent.data_available:
            return SentimentReport(
                sentiment_score=0.0,
                social_momentum="MISSING_DATA",
                hype_risk_score=50.0,
                summary="Social sentiment data unavailable; missing-data penalty applied (no fabricated sentiment).",
                confidence=0.0,
                data_available=False,
            )

        # Penalize coordinated bot promotion
        promo_penalty = sent.coordinated_promo_risk * 45.0
        pos_component = (sent.positive_ratio - 0.5) * 50.0
        growth_component = min(25.0, max(-15.0, sent.mentions_change_pct * 0.15))
        organic_component = (sent.organic_engagement_score - 50.0) * 0.4

        raw_score = 50.0 + pos_component + growth_component + organic_component - promo_penalty
        score = round(max(0.0, min(100.0, raw_score)), 2)
        hype_risk = round(max(0.0, min(100.0, sent.coordinated_promo_risk * 100.0)), 2)

        if score >= 70.0 and sent.mentions_change_pct > 50.0:
            momentum = "SURGING"
        elif score >= 55.0:
            momentum = "POSITIVE"
        elif score <= 40.0:
            momentum = "NEGATIVE"
        else:
            momentum = "NEUTRAL"

        summary = (
            f"Mentions(1h)={sent.mentions_1h} ({sent.mentions_change_pct:+.1f}%), "
            f"organic={sent.organic_engagement_score:.1f}/100, promo_risk={hype_risk:.1f}%."
        )
        return SentimentReport(
            sentiment_score=score,
            social_momentum=momentum,
            hype_risk_score=hype_risk,
            summary=summary,
            confidence=0.72,
            data_available=True,
        )
