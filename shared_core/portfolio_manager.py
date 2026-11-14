"""
Shared Portfolio State Manager.
Tracks cash, open positions, realized/unrealized PnL, peak equity, and drawdown
strictly isolated by ExecutionEnvironment (LIVE vs. PAPER vs. BACKTEST).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from database.models import ExecutionEnvironment, PositionRecord
from shared_core.risk_engine import PortfolioRiskState


class PortfolioManager:
    """Maintains portfolio state, mark-to-market equity, and drawdown telemetry."""

    def __init__(
        self,
        environment: ExecutionEnvironment,
        initial_capital_usdt: float = 10.0,
    ) -> None:
        self.environment = environment
        self.initial_capital_usdt = initial_capital_usdt
        self.available_cash_usdt = initial_capital_usdt
        self.open_positions: Dict[str, PositionRecord] = {}
        self.closed_positions: List[PositionRecord] = []
        self.realized_pnl_usdt: float = 0.0
        self.peak_equity_usdt: float = initial_capital_usdt
        self.trades_last_hour: int = 0
        self.consecutive_losses: int = 0
        self.emergency_stop_active: bool = False
        self.equity_curve: List[float] = [initial_capital_usdt]

    @property
    def unrealized_pnl_usdt(self) -> float:
        return round(sum(p.unrealized_pnl_usdt for p in self.open_positions.values()), 6)

    @property
    def open_notional_usdt(self) -> float:
        return round(
            sum(p.quantity_tokens * p.current_price_usd for p in self.open_positions.values()),
            6,
        )

    @property
    def total_equity_usdt(self) -> float:
        eq = self.available_cash_usdt + self.open_notional_usdt
        if eq > self.peak_equity_usdt:
            self.peak_equity_usdt = eq
        return round(eq, 6)

    @property
    def current_drawdown_pct(self) -> float:
        eq = self.total_equity_usdt
        if self.peak_equity_usdt <= 0:
            return 0.0
        dd = ((self.peak_equity_usdt - eq) / self.peak_equity_usdt) * 100.0
        return round(max(0.0, dd), 3)

    def register_open_position(self, position: PositionRecord, total_cost_usdt: float) -> None:
        if position.environment != self.environment:
            raise ValueError(
                f"Environment mismatch: cannot add {position.environment} position to {self.environment} portfolio."
            )
        self.available_cash_usdt = round(max(0.0, self.available_cash_usdt - total_cost_usdt), 6)
        self.open_positions[position.position_id] = position
        self.trades_last_hour += 1
        self.equity_curve.append(self.total_equity_usdt)

    def close_position(
        self,
        position_id: str,
        exit_price_usd: float,
        exit_fee_usdt: float,
        exit_reason: str,
        closed_at_iso: Optional[str] = None,
        tx_signature_exit: Optional[str] = None,
    ) -> Optional[PositionRecord]:
        pos = self.open_positions.pop(position_id, None)
        if pos is None:
            return None

        gross_proceeds = pos.quantity_tokens * exit_price_usd
        net_proceeds = max(0.0, gross_proceeds - exit_fee_usdt)
        total_fees = pos.fees_paid_usdt + exit_fee_usdt
        net_pnl = net_proceeds - pos.notional_entry_usdt

        pos.status = "CLOSED"
        pos.current_price_usd = exit_price_usd
        pos.exit_price_usd = exit_price_usd
        pos.fees_paid_usdt = round(total_fees, 6)
        pos.realized_pnl_usdt = round(net_pnl, 6)
        pos.unrealized_pnl_usdt = 0.0
        pos.exit_reason = exit_reason
        if closed_at_iso:
            pos.closed_at = closed_at_iso
        if tx_signature_exit:
            pos.tx_signature_exit = tx_signature_exit

        self.available_cash_usdt = round(self.available_cash_usdt + net_proceeds, 6)
        self.realized_pnl_usdt = round(self.realized_pnl_usdt + net_pnl, 6)
        if net_pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        self.closed_positions.append(pos)
        self.equity_curve.append(self.total_equity_usdt)
        return pos

    def get_risk_state(self) -> PortfolioRiskState:
        return PortfolioRiskState(
            total_equity_usdt=self.total_equity_usdt,
            available_cash_usdt=self.available_cash_usdt,
            daily_realized_pnl_usdt=self.realized_pnl_usdt,
            daily_unrealized_pnl_usdt=self.unrealized_pnl_usdt,
            open_positions_count=len(self.open_positions),
            open_deployer_wallets=[],
            trades_last_hour=self.trades_last_hour,
            consecutive_losses=self.consecutive_losses,
            emergency_stop_active=self.emergency_stop_active,
        )
