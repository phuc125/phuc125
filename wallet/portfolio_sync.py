"""
Portfolio Synchronization Service.
Reconciles on-chain Bitget Wallet balances with recorded LIVE positions in SQLite,
without ever mixing PAPER or BACKTEST simulation records.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from database.database import DatabaseManager
from database.models import ExecutionEnvironment
from wallet.balance_tracker import NormalizedBalanceSheet
from wallet.wallet_monitor import BitgetWalletMonitor


@dataclass
class PortfolioSyncReport:
    """Result of synchronizing Bitget Wallet balances against the local LIVE ledger."""
    synced: bool
    balance_sheet: NormalizedBalanceSheet
    open_live_positions_count: int
    untracked_spl_mints: List[str]
    discrepancies: List[str]


class PortfolioSynchronizer:
    """Synchronizes on-chain Bitget Wallet holdings with the LIVE database ledger."""

    def __init__(
        self,
        db: DatabaseManager,
        monitor: Optional[BitgetWalletMonitor] = None,
    ) -> None:
        self.db = db
        self.monitor = monitor or BitgetWalletMonitor()

    def sync_live_portfolio(
        self,
        sol_price_usdt: float = 180.0,
        token_prices_usdt: Optional[Dict[str, float]] = None,
    ) -> PortfolioSyncReport:
        """Fetch live wallet balances, compare with OPEN LIVE positions, and record a snapshot."""
        open_positions = self.db.get_positions(ExecutionEnvironment.LIVE, status="OPEN")
        closed_positions = self.db.get_positions(ExecutionEnvironment.LIVE, status="CLOSED")

        realized_pnl = sum(float(p.get("realized_pnl_usdt", 0.0)) for p in closed_positions)
        unrealized_pnl = sum(float(p.get("unrealized_pnl_usdt", 0.0)) for p in open_positions)

        sheet = self.monitor.fetch_live_balance_sheet(
            sol_price_usdt=sol_price_usdt,
            token_prices_usdt=token_prices_usdt,
            realized_pnl_usdt=realized_pnl,
            unrealized_pnl_usdt=unrealized_pnl,
        )

        tracked_mints = {str(p["mint_address"]) for p in open_positions}
        untracked = [m for m in sheet.spl_token_balances if m not in tracked_mints]
        discrepancies: List[str] = []

        for pos in open_positions:
            mint = str(pos["mint_address"])
            expected_qty = float(pos["quantity_tokens"])
            actual_qty = float(sheet.spl_token_balances.get(mint, 0.0))
            if self.monitor.wallet_config.public_key and abs(expected_qty - actual_qty) > max(1e-4, expected_qty * 0.02):
                discrepancies.append(
                    f"Mint {mint}: Ledger expects {expected_qty:.4f} tokens, on-chain wallet holds {actual_qty:.4f}."
                )

        self.db.record_portfolio_snapshot(
            environment=ExecutionEnvironment.LIVE,
            total_equity_usdt=sheet.total_portfolio_value_usdt,
            available_cash_usdt=sheet.available_trading_usdt,
            reserved_funds_usdt=sheet.reserved_funds_usdt,
            realized_pnl_usdt=sheet.realized_pnl_usdt,
            unrealized_pnl_usdt=sheet.unrealized_pnl_usdt,
            drawdown_pct=0.0,
        )

        return PortfolioSyncReport(
            synced=len(discrepancies) == 0,
            balance_sheet=sheet,
            open_live_positions_count=len(open_positions),
            untracked_spl_mints=untracked,
            discrepancies=discrepancies,
        )
