"""
AGENT 1: MARKET ANALYSIS AI
Analyzes price action, OHLCV, volume, momentum, volatility, support/resistance, and market regime.
"""
from __future__ import annotations

from typing import Dict

from database.models import MarketSnapshot
from shared_core.market_regime import MarketRegimeClassifier, MarketRegimeReport


class MarketAnalysisAgent:
    """Specialized Agent 1: Evaluates technical structure and market regime."""

    def analyze(self, snapshot: MarketSnapshot, features: Dict[str, float]) -> MarketRegimeReport:
        return MarketRegimeClassifier.classify(
            features=features,
            current_price_usd=snapshot.primary_pool.price_usd,
        )
