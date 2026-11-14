"""
Shared Trade Lifecycle Manager.
Evaluates open positions against stop-loss, take-profit, and emergency liquidity-rug exits
identically across Live Trading, Paper Trading, and Historical Backtesting.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from database.models import PoolState, PositionRecord


@dataclass
class ExitEvaluation:
    """Result of checking whether an open position should be exited."""
    should_exit: bool
    exit_reason: str
    trigger_price_usd: float


class TradeManager:
    """Monitors open positions for stop-loss, take-profit, or emergency rug triggers."""

    @staticmethod
    def check_exit_conditions(
        position: PositionRecord,
        current_price_usd: float,
        bar_low_usd: Optional[float] = None,
        bar_high_usd: Optional[float] = None,
        pool_state: Optional[PoolState] = None,
    ) -> ExitEvaluation:
        low_p = bar_low_usd if bar_low_usd is not None else current_price_usd
        high_p = bar_high_usd if bar_high_usd is not None else current_price_usd

        # 1. Emergency liquidity removal trigger
        if pool_state is not None and pool_state.liquidity_change_1h_pct <= -35.0:
            return ExitEvaluation(
                should_exit=True,
                exit_reason="EMERGENCY_LP_REMOVAL",
                trigger_price_usd=current_price_usd,
            )

        # 2. Conservative intrabar check: Stop-Loss takes priority if both SL and TP touched in same bar
        if low_p <= position.stop_loss_usd:
            return ExitEvaluation(
                should_exit=True,
                exit_reason="STOP_LOSS",
                trigger_price_usd=position.stop_loss_usd,
            )

        # 3. Take-Profit trigger
        if high_p >= position.take_profit_usd:
            return ExitEvaluation(
                should_exit=True,
                exit_reason="TAKE_PROFIT",
                trigger_price_usd=position.take_profit_usd,
            )

        return ExitEvaluation(
            should_exit=False,
            exit_reason="HOLD",
            trigger_price_usd=current_price_usd,
        )
