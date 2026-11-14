"""
AGENT 4: SCAM DETECTION AI
Mandatory safety gate detecting rug pulls, honeypots, active mint/freeze authority, and wash trading.
"""
from __future__ import annotations

from database.models import MarketSnapshot
from shared_core.scam_detection import ScamDetectionEngine, ScamDetectionReport


class ScamDetectionAgent:
    """Specialized Agent 4: Mandatory safety gate for token eligibility."""

    def __init__(self, min_pool_liquidity_usd: float = 15000.0) -> None:
        self.min_pool_liquidity_usd = min_pool_liquidity_usd

    def analyze(self, snapshot: MarketSnapshot) -> ScamDetectionReport:
        return ScamDetectionEngine.evaluate(
            snapshot=snapshot,
            min_pool_liquidity_usd=self.min_pool_liquidity_usd,
        )
