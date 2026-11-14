"""
Agent 5 Backing Engine: Adaptive Trading Strategy Selector.
Implements the four required strategy families plus NO_TRADE:
- Strategy A: Momentum Breakout (MOMENTUM_BREAKOUT)
- Strategy B: Trend Following + Pullback (TREND_FOLLOWING_PULLBACK)
- Strategy C: Liquidity Sweep + Reversal (LIQUIDITY_SWEEP_REVERSAL)
- Strategy D: Smart Money Accumulation (SMART_MONEY_ACCUMULATION)
- NO_TRADE when conditions are unfavorable or safety gates veto.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from database.models import StrategyFamily, TradeAction, TradeEligibility
from shared_core.market_regime import MarketRegimeReport, MarketRegimeType
from shared_core.opportunity_scoring import OpportunityScoreResult
from shared_core.prediction_engine import MLPredictionOutput
from shared_core.scam_detection import ScamDetectionReport
from shared_core.smart_money import SmartMoneyReport


@dataclass
class StrategyDecision:
    """Output of Agent 5 (Strategy AI)."""
    strategy_family: StrategyFamily
    action: TradeAction
    entry_price_usd: float
    stop_loss_usd: float
    take_profit_usd: float
    expected_reward_to_risk: float
    reasoning: str


class AdaptiveStrategyEngine:
    """Selects the optimal strategy family or returns NO_TRADE with full explanation."""

    def __init__(self, min_opportunity_score: float = 75.0, min_rr: float = 1.8) -> None:
        self.min_opportunity_score = min_opportunity_score
        self.min_rr = min_rr

    def select_strategy(
        self,
        current_price_usd: float,
        features: Dict[str, float],
        market_report: MarketRegimeReport,
        smart_money_report: SmartMoneyReport,
        scam_report: ScamDetectionReport,
        opportunity: OpportunityScoreResult,
        ml_pred: MLPredictionOutput,
    ) -> StrategyDecision:
        if current_price_usd <= 0:
            return self._no_trade(0.0, "Invalid non-positive token price.")

        # 1. Mandatory Scam Detection Gate
        if scam_report.eligibility != TradeEligibility.ELIGIBLE:
            return self._no_trade(
                current_price_usd,
                f"Rejected by Scam Detection AI ({scam_report.classification.value}, "
                f"risk_score={scam_report.risk_score:.1f}): {'; '.join(scam_report.warning_signs[:2])}",
            )

        # 2. Minimum Opportunity Score Gate
        if opportunity.total_score < self.min_opportunity_score:
            return self._no_trade(
                current_price_usd,
                f"Opportunity score ({opportunity.total_score:.1f}/100) is below minimum threshold "
                f"({self.min_opportunity_score:.1f}/100).",
            )

        # 3. ML Probability Gate
        if ml_pred.prob_positive_return < 0.52 or ml_pred.expected_return_pct <= 0.5:
            return self._no_trade(
                current_price_usd,
                f"ML ensemble predicts insufficient edge (P(pos)={ml_pred.prob_positive_return:.2f}, "
                f"E[ret]={ml_pred.expected_return_pct:.2f}%).",
            )

        vol_pct = max(2.5, min(12.0, market_report.volatility_score * 0.12))
        stop_dist_pct = max(0.03, min(0.10, vol_pct / 100.0))

        # Strategy A: Momentum Breakout
        if (
            market_report.regime == MarketRegimeType.BULLISH_BREAKOUT
            or (features.get("volume_acceleration", 1.0) >= 1.4 and features.get("return_1", 0.0) > 2.0)
        ):
            sl = round(current_price_usd * (1.0 - stop_dist_pct), 10)
            tp = round(current_price_usd * (1.0 + stop_dist_pct * 2.4), 10)
            rr = round((tp - current_price_usd) / max(1e-12, current_price_usd - sl), 2)
            return StrategyDecision(
                strategy_family=StrategyFamily.MOMENTUM_BREAKOUT,
                action=TradeAction.BUY,
                entry_price_usd=current_price_usd,
                stop_loss_usd=sl,
                take_profit_usd=tp,
                expected_reward_to_risk=rr,
                reasoning=(
                    f"Strategy A (Momentum Breakout) selected: volume acceleration="
                    f"{features.get('volume_acceleration', 1.0):.2f}x, buy/sell imbalance="
                    f"{features.get('buy_sell_imbalance', 0.0):+.2f}, score={opportunity.total_score:.1f}/100, R:R={rr}."
                ),
            )

        # Strategy B: Trend Following + Pullback
        if market_report.regime == MarketRegimeType.UPTREND_PULLBACK or (
            market_report.trend_direction == "BULLISH" and 40.0 <= features.get("rsi_14", 50.0) <= 62.0
        ):
            sl = round(current_price_usd * (1.0 - stop_dist_pct * 0.9), 10)
            tp = round(current_price_usd * (1.0 + stop_dist_pct * 2.1), 10)
            rr = round((tp - current_price_usd) / max(1e-12, current_price_usd - sl), 2)
            return StrategyDecision(
                strategy_family=StrategyFamily.TREND_FOLLOWING_PULLBACK,
                action=TradeAction.BUY,
                entry_price_usd=current_price_usd,
                stop_loss_usd=sl,
                take_profit_usd=tp,
                expected_reward_to_risk=rr,
                reasoning=(
                    f"Strategy B (Trend Following + Pullback) selected: established bullish EMA structure "
                    f"with controlled RSI ({features.get('rsi_14', 50.0):.1f}) pullback near support, R:R={rr}."
                ),
            )

        # Strategy C: Liquidity Sweep + Reversal
        if market_report.regime == MarketRegimeType.CAPITULATION_REVERSAL:
            sl = round(current_price_usd * (1.0 - stop_dist_pct * 0.85), 10)
            tp = round(current_price_usd * (1.0 + stop_dist_pct * 2.2), 10)
            rr = round((tp - current_price_usd) / max(1e-12, current_price_usd - sl), 2)
            return StrategyDecision(
                strategy_family=StrategyFamily.LIQUIDITY_SWEEP_REVERSAL,
                action=TradeAction.BUY,
                entry_price_usd=current_price_usd,
                stop_loss_usd=sl,
                take_profit_usd=tp,
                expected_reward_to_risk=rr,
                reasoning=(
                    f"Strategy C (Liquidity Sweep + Reversal) selected: downside liquidity sweep absorbed "
                    f"with positive buy imbalance ({features.get('buy_sell_imbalance', 0.0):+.2f}), R:R={rr}."
                ),
            )

        # Strategy D: Smart Money Accumulation
        if (
            market_report.regime == MarketRegimeType.STEALTH_ACCUMULATION
            or smart_money_report.status == "ACCUMULATION"
        ):
            sl = round(current_price_usd * (1.0 - stop_dist_pct * 0.95), 10)
            tp = round(current_price_usd * (1.0 + stop_dist_pct * 2.3), 10)
            rr = round((tp - current_price_usd) / max(1e-12, current_price_usd - sl), 2)
            return StrategyDecision(
                strategy_family=StrategyFamily.SMART_MONEY_ACCUMULATION,
                action=TradeAction.BUY,
                entry_price_usd=current_price_usd,
                stop_loss_usd=sl,
                take_profit_usd=tp,
                expected_reward_to_risk=rr,
                reasoning=(
                    f"Strategy D (Smart Money Accumulation) selected: Smart Money score="
                    f"{smart_money_report.smart_money_score:.1f}/100 with improving liquidity, R:R={rr}."
                ),
            )

        return self._no_trade(
            current_price_usd,
            f"Market regime ({market_report.regime.value}) does not match high-conviction entry criteria.",
        )

    @staticmethod
    def _no_trade(price_usd: float, reason: str) -> StrategyDecision:
        return StrategyDecision(
            strategy_family=StrategyFamily.NO_TRADE,
            action=TradeAction.NO_TRADE,
            entry_price_usd=price_usd,
            stop_loss_usd=price_usd,
            take_profit_usd=price_usd,
            expected_reward_to_risk=0.0,
            reasoning=reason,
        )
