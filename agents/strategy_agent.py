"""
AGENT 5: STRATEGY AI
Synthesizes outputs from Agents 1-4, Opportunity Scorer, and ML Engine to select an adaptive strategy.
"""
from __future__ import annotations

from typing import Dict

from shared_core.market_regime import MarketRegimeReport
from shared_core.opportunity_scoring import OpportunityScoreResult
from shared_core.prediction_engine import MLPredictionOutput
from shared_core.scam_detection import ScamDetectionReport
from shared_core.smart_money import SmartMoneyReport
from shared_core.strategy_engine import AdaptiveStrategyEngine, StrategyDecision


class StrategyAgent:
    """Specialized Agent 5: Adaptive strategy selector and entry/exit planner."""

    def __init__(self, min_opportunity_score: float = 75.0, min_rr: float = 1.8) -> None:
        self.engine = AdaptiveStrategyEngine(
            min_opportunity_score=min_opportunity_score,
            min_rr=min_rr,
        )

    def recommend(
        self,
        current_price_usd: float,
        features: Dict[str, float],
        market_report: MarketRegimeReport,
        smart_money_report: SmartMoneyReport,
        scam_report: ScamDetectionReport,
        opportunity: OpportunityScoreResult,
        ml_pred: MLPredictionOutput,
    ) -> StrategyDecision:
        return self.engine.select_strategy(
            current_price_usd=current_price_usd,
            features=features,
            market_report=market_report,
            smart_money_report=smart_money_report,
            scam_report=scam_report,
            opportunity=opportunity,
            ml_pred=ml_pred,
        )
