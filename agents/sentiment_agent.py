"""
AGENT 3: SENTIMENT AI
Analyzes community mentions, social momentum, and coordinated promotion risk without fabricating data.
"""
from __future__ import annotations

from database.models import MarketSnapshot
from shared_core.sentiment_engine import SentimentEngine, SentimentReport


class SentimentAgent:
    """Specialized Agent 3: Evaluates social momentum and hype risk."""

    def analyze(self, snapshot: MarketSnapshot) -> SentimentReport:
        return SentimentEngine.evaluate(snapshot)
