"""
Agent 6 Backing Engine: Final Authority Risk Management Engine.
Enforces daily loss limits (2%), max open positions (2), slippage & price impact caps,
trade frequency limits, consecutive loss circuit breakers, correlation limits, and emergency stops.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from config.risk_config import RiskConfig
from database.models import MarketSnapshot
from dex.liquidity_analyzer import LiquidityAnalyzer
from shared_core.position_sizing import PositionSizeCalculation, PositionSizer
from shared_core.strategy_engine import StrategyDecision


@dataclass
class PortfolioRiskState:
    """Current portfolio risk telemetry passed into RiskEngine."""
    total_equity_usdt: float
    available_cash_usdt: float
    daily_realized_pnl_usdt: float
    daily_unrealized_pnl_usdt: float
    open_positions_count: int
    open_deployer_wallets: List[str] = field(default_factory=list)
    trades_last_hour: int = 0
    consecutive_losses: int = 0
    emergency_stop_active: bool = False


@dataclass
class RiskApprovalDecision:
    """Output of Agent 6 (Risk Management AI) — has final authority to reject any trade."""
    approved: bool
    recommended_position_usdt: float
    recommended_tokens: float
    estimated_price_impact_pct: float
    rejection_reasons: List[str] = field(default_factory=list)
    emergency_stop_triggered: bool = False


class RiskEngine:
    """Final authority risk gatekeeper for both Live Trading and Testing."""

    def __init__(self, config: Optional[RiskConfig] = None) -> None:
        self.config = config or RiskConfig.from_env()
        self.sizer = PositionSizer(self.config)

    def evaluate_trade_risk(
        self,
        snapshot: MarketSnapshot,
        strategy_decision: StrategyDecision,
        portfolio_state: PortfolioRiskState,
        volatility_score: float = 50.0,
    ) -> RiskApprovalDecision:
        reasons: List[str] = []
        estop = portfolio_state.emergency_stop_active

        # 1. Global Emergency Stop
        if estop:
            reasons.append("Global Emergency Stop is active.")

        # 2. Daily Loss Limit (2% of equity)
        daily_net_pnl = portfolio_state.daily_realized_pnl_usdt + portfolio_state.daily_unrealized_pnl_usdt
        max_daily_loss_usdt = portfolio_state.total_equity_usdt * self.config.max_daily_loss_pct
        if daily_net_pnl <= -max_daily_loss_usdt:
            reasons.append(
                f"Daily loss limit breached (daily PnL={daily_net_pnl:.4f} USDT <= -{max_daily_loss_usdt:.4f} USDT)."
            )
            estop = True

        # 3. Maximum Open Positions (2)
        if portfolio_state.open_positions_count >= self.config.max_open_positions:
            reasons.append(
                f"Maximum open positions reached ({portfolio_state.open_positions_count}/{self.config.max_open_positions})."
            )

        # 4. Trade Frequency Limit
        if portfolio_state.trades_last_hour >= self.config.max_trades_per_hour:
            reasons.append(
                f"Hourly trade frequency limit reached ({portfolio_state.trades_last_hour}/{self.config.max_trades_per_hour})."
            )

        # 5. Consecutive Losses Cooldown
        if portfolio_state.consecutive_losses >= self.config.max_consecutive_losses:
            reasons.append(
                f"Consecutive loss circuit breaker active ({portfolio_state.consecutive_losses} losses in a row)."
            )

        # 6. Correlated Deployer/Cluster Exposure
        deployer = snapshot.token.deployer_wallet
        if deployer and portfolio_state.open_deployer_wallets.count(deployer) >= self.config.max_correlated_positions:
            reasons.append(f"Correlated exposure limit: already holding token from deployer {deployer}.")

        # 7. Reward-to-Risk Ratio Check
        if strategy_decision.expected_reward_to_risk < self.config.min_reward_to_risk:
            reasons.append(
                f"Reward-to-risk ratio ({strategy_decision.expected_reward_to_risk:.2f}) below minimum ({self.config.min_reward_to_risk:.2f})."
            )

        # 8. Minimum Pool Liquidity Check
        pool = snapshot.primary_pool
        if pool.liquidity_usd < self.config.min_pool_liquidity_usd:
            reasons.append(
                f"Pool liquidity (${pool.liquidity_usd:,.0f}) below minimum (${self.config.min_pool_liquidity_usd:,.0f})."
            )

        # 9. Position Sizing Calculation
        sizing: PositionSizeCalculation = self.sizer.calculate_position_size(
            total_equity_usdt=portfolio_state.total_equity_usdt,
            available_cash_usdt=portfolio_state.available_cash_usdt,
            entry_price_usd=strategy_decision.entry_price_usd,
            stop_loss_usd=strategy_decision.stop_loss_usd,
            accessible_liquidity_usd=pool.accessible_liquidity_usd,
            volatility_score=volatility_score,
        )
        if sizing.recommended_notional_usdt <= 0:
            reasons.append(f"Position sizing returned 0 USDT ({sizing.capped_by}).")

        # 10. Price Impact Check
        impact_pct = LiquidityAnalyzer.estimate_price_impact_pct(sizing.recommended_notional_usdt, pool)
        if impact_pct > self.config.max_price_impact_pct:
            reasons.append(
                f"Estimated price impact ({impact_pct:.2f}%) exceeds maximum ({self.config.max_price_impact_pct:.2f}%)."
            )

        approved = len(reasons) == 0
        return RiskApprovalDecision(
            approved=approved,
            recommended_position_usdt=sizing.recommended_notional_usdt if approved else 0.0,
            recommended_tokens=sizing.recommended_tokens if approved else 0.0,
            estimated_price_impact_pct=impact_pct,
            rejection_reasons=reasons,
            emergency_stop_triggered=estop,
        )
