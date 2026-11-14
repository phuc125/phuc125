"""
Continuous Learning & Strategy Parameter Evaluator.
Analyzes historical winning/losing trades, identifies strategy weaknesses, and proposes
validated parameter adjustments without ever auto-deploying untested changes to Live Trading.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from database.models import PositionRecord
from shared_core.performance_analyzer import PerformanceAnalyzer, PerformanceReport


@dataclass
class ParameterRecommendation:
    """Proposed parameter adjustment requiring backtest validation and operator approval."""
    parameter_name: str
    current_value: float
    proposed_value: float
    rationale: str
    auto_deployed_to_live: bool = False  # Always False by safety policy


@dataclass
class LearningEvaluationSummary:
    """Summary of strategy evaluation and proposed adjustments."""
    performance: PerformanceReport
    weakest_strategy: str
    strongest_strategy: str
    recommendations: List[ParameterRecommendation] = field(default_factory=list)


class ContinuousLearningEvaluator:
    """Evaluates closed trade outcomes and generates safe parameter recommendations."""

    @staticmethod
    def evaluate_outcomes(
        closed_positions: List[PositionRecord],
        equity_curve: List[float],
        current_min_opportunity_score: float = 75.0,
    ) -> LearningEvaluationSummary:
        perf = PerformanceAnalyzer.analyze(closed_positions, equity_curve)
        by_strat: Dict[str, Dict[str, float]] = perf.performance_by_strategy

        weakest = "NONE"
        strongest = "NONE"
        if by_strat:
            weakest = min(by_strat.items(), key=lambda kv: kv[1].get("net_pnl_usdt", 0.0))[0]
            strongest = max(by_strat.items(), key=lambda kv: kv[1].get("net_pnl_usdt", 0.0))[0]

        recs: List[ParameterRecommendation] = []
        if perf.total_trades >= 4 and perf.win_rate_pct < 45.0:
            recs.append(
                ParameterRecommendation(
                    parameter_name="MIN_OPPORTUNITY_SCORE",
                    current_value=current_min_opportunity_score,
                    proposed_value=min(90.0, current_min_opportunity_score + 5.0),
                    rationale="Win rate below 45%; raising minimum opportunity score threshold to filter marginal setups.",
                    auto_deployed_to_live=False,
                )
            )
        if perf.fees_pct_of_gross_profit > 35.0:
            recs.append(
                ParameterRecommendation(
                    parameter_name="MIN_REWARD_TO_RISK",
                    current_value=1.8,
                    proposed_value=2.1,
                    rationale="Fee drag exceeds 35% of gross profit; require higher reward-to-risk ratio per trade.",
                    auto_deployed_to_live=False,
                )
            )

        return LearningEvaluationSummary(
            performance=perf,
            weakest_strategy=weakest,
            strongest_strategy=strongest,
            recommendations=recs,
        )
