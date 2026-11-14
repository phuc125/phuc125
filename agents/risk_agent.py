"""
AGENT 6: RISK MANAGEMENT AI
Final authority gatekeeper enforcing position sizing, drawdown caps, and daily loss limits.
"""
from __future__ import annotations

from typing import Optional

from config.risk_config import RiskConfig
from database.models import MarketSnapshot
from shared_core.risk_engine import PortfolioRiskState, RiskApprovalDecision, RiskEngine
from shared_core.strategy_engine import StrategyDecision


class RiskManagementAgent:
    """Specialized Agent 6: Final authority risk approval and position sizing."""

    def __init__(self, config: Optional[RiskConfig] = None) -> None:
        self.engine = RiskEngine(config)

    def evaluate(
        self,
        snapshot: MarketSnapshot,
        strategy_decision: StrategyDecision,
        portfolio_state: PortfolioRiskState,
        volatility_score: float = 50.0,
    ) -> RiskApprovalDecision:
        return self.engine.evaluate_trade_risk(
            snapshot=snapshot,
            strategy_decision=strategy_decision,
            portfolio_state=portfolio_state,
            volatility_score=volatility_score,
        )
