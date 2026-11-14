"""
Simulated Portfolio Adapter for Paper Trading and Backtesting.
Strictly enforces ExecutionEnvironment.PAPER / BACKTEST and never touches real wallets.
"""
from __future__ import annotations

from database.models import ExecutionEnvironment
from shared_core.portfolio_manager import PortfolioManager


class SimulatedPortfolioAdapter(PortfolioManager):
    """Paper & Backtest portfolio manager initialized with 10 USDT simulated capital."""

    def __init__(
        self,
        initial_capital_usdt: float = 10.0,
        environment: ExecutionEnvironment = ExecutionEnvironment.PAPER,
    ) -> None:
        if environment == ExecutionEnvironment.LIVE:
            raise ValueError("SimulatedPortfolioAdapter cannot be initialized in LIVE mode.")
        super().__init__(environment=environment, initial_capital_usdt=initial_capital_usdt)
