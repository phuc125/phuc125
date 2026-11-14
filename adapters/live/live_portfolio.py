"""
Live Portfolio Adapter.
Tracks actual Bitget Wallet balances and live positions strictly tagged with ExecutionEnvironment.LIVE.
"""
from __future__ import annotations

from typing import Optional

from database.database import DatabaseManager
from database.models import ExecutionEnvironment
from shared_core.portfolio_manager import PortfolioManager
from wallet.portfolio_sync import PortfolioSynchronizer, PortfolioSyncReport
from wallet.wallet_monitor import BitgetWalletMonitor


class LivePortfolioAdapter(PortfolioManager):
    """Live trading portfolio manager synchronized with Bitget Wallet."""

    def __init__(
        self,
        db: DatabaseManager,
        monitor: Optional[BitgetWalletMonitor] = None,
        initial_capital_usdt: float = 10.0,
    ) -> None:
        super().__init__(environment=ExecutionEnvironment.LIVE, initial_capital_usdt=initial_capital_usdt)
        self.db = db
        self.synchronizer = PortfolioSynchronizer(db=db, monitor=monitor)

    def sync_with_bitget_wallet(self, sol_price_usdt: float = 180.0) -> PortfolioSyncReport:
        report = self.synchronizer.sync_live_portfolio(sol_price_usdt=sol_price_usdt)
        if report.balance_sheet.available_trading_usdt > 0:
            self.available_cash_usdt = report.balance_sheet.available_trading_usdt
        return report
