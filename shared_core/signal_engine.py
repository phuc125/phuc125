"""
Shared Signal Engine.
Transforms MultiAgentCommitteeResult into a standardized TradingSignal object.
Used identically by Live Trading and Testing programs to guarantee mode parity.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from config.risk_config import OpportunityWeights, RiskConfig
from database.models import (
    ExecutionEnvironment,
    MarketSnapshot,
    StrategyFamily,
    TradeAction,
    TradingSignal,
)
from shared_core.ai_agents import MultiAgentCommitteeResult, MultiAgentSystem
from shared_core.prediction_engine import PredictionEngine
from shared_core.risk_engine import PortfolioRiskState


class SignalEngine:
    """
    Canonical signal generator shared by live_main.py and test_main.py.
    Given identical MarketSnapshot, PortfolioRiskState, and configuration, produces
    identical signal parameters across LIVE, PAPER, and BACKTEST environments.
    """

    def __init__(
        self,
        risk_config: Optional[RiskConfig] = None,
        weights: Optional[OpportunityWeights] = None,
        prediction_engine: Optional[PredictionEngine] = None,
    ) -> None:
        self.multi_agent = MultiAgentSystem(
            risk_config=risk_config,
            weights=weights,
            prediction_engine=prediction_engine,
        )

    def generate_signal(
        self,
        snapshot: MarketSnapshot,
        portfolio_state: PortfolioRiskState,
        environment: ExecutionEnvironment,
        reference_now: Optional[float] = None,
    ) -> tuple[TradingSignal, MultiAgentCommitteeResult]:
        committee = self.multi_agent.evaluate_snapshot(
            snapshot=snapshot,
            portfolio_state=portfolio_state,
            reference_now=reference_now,
        )

        strat = committee.strategy_decision
        risk = committee.risk_decision

        # Final authority check: if Risk Management AI rejects the trade, force NO_TRADE
        if strat.action == TradeAction.BUY and not risk.approved:
            final_action = TradeAction.NO_TRADE
            final_strategy = StrategyFamily.NO_TRADE
            final_reasoning = (
                f"{strat.reasoning} | VETOED BY RISK AI: {'; '.join(risk.rejection_reasons)}"
            )
            pos_usdt = 0.0
        else:
            final_action = strat.action
            final_strategy = strat.strategy_family
            final_reasoning = strat.reasoning
            pos_usdt = risk.recommended_position_usdt

        warnings = list(committee.scam_report.warning_signs) + list(committee.opportunity.penalties_applied)
        if not risk.approved:
            warnings.extend(risk.rejection_reasons)

        # Deterministic signal ID from mint + snapshot timestamp + environment
        digest_input = f"{environment.value}:{snapshot.token.mint_address}:{snapshot.timestamp:.3f}"
        sig_hash = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:16]

        signal = TradingSignal(
            signal_id=f"sig_{sig_hash}",
            mint_address=snapshot.token.mint_address,
            symbol=snapshot.token.symbol,
            pool_address=snapshot.primary_pool.pool_address,
            dex_venue=snapshot.primary_pool.dex_venue,
            environment=environment,
            action=final_action,
            strategy_family=final_strategy,
            opportunity_score=committee.opportunity.total_score,
            opportunity_confidence=committee.opportunity.confidence,
            scam_risk_score=committee.scam_report.risk_score,
            scam_classification=committee.scam_report.classification,
            trade_eligibility=committee.scam_report.eligibility,
            entry_price_usd=strat.entry_price_usd,
            stop_loss_usd=strat.stop_loss_usd,
            take_profit_usd=strat.take_profit_usd,
            expected_rr=strat.expected_reward_to_risk,
            recommended_position_usdt=pos_usdt,
            ml_prob_positive=committee.ml_prediction.prob_positive_return,
            ml_expected_return_pct=committee.ml_prediction.expected_return_pct,
            market_regime=committee.market_report.regime.value,
            reasoning=final_reasoning,
            warnings=warnings,
            component_scores=committee.opportunity.component_scores,
        )
        return signal, committee
