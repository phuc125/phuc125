"""
AGENT 2: SMART MONEY AI
Analyzes wallet accumulation, distribution, large transactions, developer activity, and clusters.
"""
from __future__ import annotations

from database.models import MarketSnapshot
from shared_core.smart_money import SmartMoneyEngine, SmartMoneyReport


class SmartMoneyAgent:
    """Specialized Agent 2: Evaluates Smart Money flow and wallet concentration."""

    def analyze(self, snapshot: MarketSnapshot) -> SmartMoneyReport:
        return SmartMoneyEngine.evaluate(snapshot)
