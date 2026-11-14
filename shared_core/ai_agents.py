"""
Multi-Agent AI Orchestrator.
Coordinates all six specialized AI agents in a deterministic pipeline used identically
by both Live Trading and Testing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from agents.market_agent import MarketAnalysisAgent
from agents.risk_agent import RiskManagementAgent
from agents.scam_detection_agent import ScamDetectionAgent
from agents.sentiment_agent import SentimentAgent
from agents.smart_money_agent import SmartMoneyAgent
from agents.strategy_agent import StrategyAgent
from config.risk_config import OpportunityWeights, RiskConfig
from database.models import MarketSnapshot
from dex.liquidity_analyzer import LiquidityAnalyzer, LiquidityAssessment
from shared_core.feature_engineering import FeatureEngineer
from shared_core.market_regime import MarketRegimeReport
from shared_core.opportunity_scoring import OpportunityScorer, OpportunityScoreResult
from shared_core.prediction_engine import MLPredictionOutput, PredictionEngine
from shared_core.risk_engine import PortfolioRiskState, RiskApprovalDecision
from shared_core.scam_detection import ScamDetectionReport
from shared_core.sentiment_engine import SentimentReport
from shared_core.smart_money import SmartMoneyReport
from shared_core.strategy_engine import StrategyDecision


@dataclass
class MultiAgentCommitteeResult:
    """Complete analytical dossier from all 6 specialized AI agents."""
    features: Dict[str, float]
    market_report: MarketRegimeReport
    smart_money_report: SmartMoneyReport
    sentiment_report: SentimentReport
    scam_report: ScamDetectionReport
    liquidity_report: LiquidityAssessment
    opportunity: OpportunityScoreResult
    ml_prediction: MLPredictionOutput
    strategy_decision: StrategyDecision
    risk_decision: RiskApprovalDecision


class MultiAgentSystem:
    """Orchestrates Agents 1 through 6 plus the ML Prediction Engine and Opportunity Scorer."""

    def __init__(
        self,
        risk_config: Optional[RiskConfig] = None,
        weights: Optional[OpportunityWeights] = None,
        prediction_engine: Optional[PredictionEngine] = None,
    ) -> None:
        self.risk_config = risk_config or RiskConfig.from_env()
        self.weights = weights or OpportunityWeights.from_env()
        self.prediction_engine = prediction_engine or PredictionEngine()

        self.market_agent = MarketAnalysisAgent()
        self.smart_money_agent = SmartMoneyAgent()
        self.sentiment_agent = SentimentAgent()
        self.scam_agent = ScamDetectionAgent(min_pool_liquidity_usd=self.risk_config.min_pool_liquidity_usd)
        self.strategy_agent = StrategyAgent(
            min_opportunity_score=self.risk_config.min_opportunity_score,
            min_rr=self.risk_config.min_reward_to_risk,
        )
        self.risk_agent = RiskManagementAgent(self.risk_config)
        self.scorer = OpportunityScorer(self.weights)

    def evaluate_snapshot(
        self,
        snapshot: MarketSnapshot,
        portfolio_state: PortfolioRiskState,
        reference_now: Optional[float] = None,
    ) -> MultiAgentCommitteeResult:
        features = FeatureEngineer.extract_features(snapshot)
        market_rep = self.market_agent.analyze(snapshot, features)
        sm_rep = self.smart_money_agent.analyze(snapshot)
        sent_rep = self.sentiment_agent.analyze(snapshot)
        scam_rep = self.scam_agent.analyze(snapshot)
        liq_rep = LiquidityAnalyzer.evaluate_pool(snapshot.primary_pool)

        opp = self.scorer.score(
            market_report=market_rep,
            smart_money_report=sm_rep,
            sentiment_report=sent_rep,
            liquidity_report=liq_rep,
            scam_report=scam_rep,
            data_timestamp=snapshot.timestamp,
            reference_now=reference_now,
        )

        ml_pred = self.prediction_engine.predict_from_features(features)

        strat_dec = self.strategy_agent.recommend(
            current_price_usd=snapshot.primary_pool.price_usd,
            features=features,
            market_report=market_rep,
            smart_money_report=sm_rep,
            scam_report=scam_rep,
            opportunity=opp,
            ml_pred=ml_pred,
        )

        risk_dec = self.risk_agent.evaluate(
            snapshot=snapshot,
            strategy_decision=strat_dec,
            portfolio_state=portfolio_state,
            volatility_score=market_rep.volatility_score,
        )

        return MultiAgentCommitteeResult(
            features=features,
            market_report=market_rep,
            smart_money_report=sm_rep,
            sentiment_report=sent_rep,
            scam_report=scam_rep,
            liquidity_report=liq_rep,
            opportunity=opp,
            ml_prediction=ml_pred,
            strategy_decision=strat_dec,
            risk_decision=risk_dec,
        )
