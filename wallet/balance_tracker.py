"""
Wallet Balance Tracker.
Normalizes SOL, USDT, and SPL token balances into USDT (primary accounting currency)
and clearly separates Actual Wallet Balance, Available Trading Balance, Reserved Funds,
and Simulated Balance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class NormalizedBalanceSheet:
    """Normalized USDT accounting breakdown for either Live Wallet or Simulated Portfolio."""
    is_simulated: bool
    sol_balance: float
    sol_price_usdt: float
    usdt_balance: float
    spl_token_balances: Dict[str, float] = field(default_factory=dict)
    spl_token_values_usdt: Dict[str, float] = field(default_factory=dict)
    reserved_gas_sol: float = 0.02
    reserved_funds_usdt: float = 0.0
    available_trading_usdt: float = 0.0
    total_portfolio_value_usdt: float = 0.0
    realized_pnl_usdt: float = 0.0
    unrealized_pnl_usdt: float = 0.0


class BalanceTracker:
    """Computes normalized USDT portfolio values and enforces gas/margin reserve boundaries."""

    def __init__(self, reserve_sol_for_gas: float = 0.02) -> None:
        self.reserve_sol_for_gas = max(0.0, reserve_sol_for_gas)

    def build_balance_sheet(
        self,
        is_simulated: bool,
        sol_balance: float,
        sol_price_usdt: float,
        usdt_balance: float,
        spl_balances: Dict[str, float],
        spl_prices_usdt: Dict[str, float],
        locked_in_orders_usdt: float = 0.0,
        realized_pnl_usdt: float = 0.0,
        unrealized_pnl_usdt: float = 0.0,
    ) -> NormalizedBalanceSheet:
        """Normalize all holdings into USDT and compute available trading capital."""
        sol_val_usdt = max(0.0, sol_balance) * max(0.0, sol_price_usdt)
        reserved_sol_usdt = min(sol_val_usdt, self.reserve_sol_for_gas * max(0.0, sol_price_usdt))

        spl_values: Dict[str, float] = {}
        total_spl_usdt = 0.0
        for mint, qty in spl_balances.items():
            price = max(0.0, float(spl_prices_usdt.get(mint, 0.0)))
            val = max(0.0, qty) * price
            spl_values[mint] = round(val, 4)
            total_spl_usdt += val

        reserved_total_usdt = round(reserved_sol_usdt + max(0.0, locked_in_orders_usdt), 4)
        available_usdt = round(max(0.0, usdt_balance - max(0.0, locked_in_orders_usdt)), 4)
        total_value = round(sol_val_usdt + max(0.0, usdt_balance) + total_spl_usdt, 4)

        return NormalizedBalanceSheet(
            is_simulated=is_simulated,
            sol_balance=round(sol_balance, 6),
            sol_price_usdt=round(sol_price_usdt, 4),
            usdt_balance=round(usdt_balance, 4),
            spl_token_balances=dict(spl_balances),
            spl_token_values_usdt=spl_values,
            reserved_gas_sol=self.reserve_sol_for_gas,
            reserved_funds_usdt=reserved_total_usdt,
            available_trading_usdt=available_usdt,
            total_portfolio_value_usdt=total_value,
            realized_pnl_usdt=round(realized_pnl_usdt, 4),
            unrealized_pnl_usdt=round(unrealized_pnl_usdt, 4),
        )
