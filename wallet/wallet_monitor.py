"""
Bitget Wallet Read-Only On-Chain Monitor.
Queries SOL, USDT, and SPL token balances from Solana RPC for the configured Bitget Wallet public key.
"""
from __future__ import annotations

from typing import Dict, Optional

from config.settings import SystemSettings
from config.wallet_config import WalletConfig
from dex.solana_rpc_connector import SolanaRPCConnector
from wallet.balance_tracker import BalanceTracker, NormalizedBalanceSheet


class BitgetWalletMonitor:
    """Monitors actual on-chain balances for a Bitget Wallet address without private keys."""

    def __init__(
        self,
        settings: Optional[SystemSettings] = None,
        wallet_config: Optional[WalletConfig] = None,
        rpc: Optional[SolanaRPCConnector] = None,
    ) -> None:
        self.settings = settings or SystemSettings.from_env()
        self.wallet_config = wallet_config or WalletConfig.from_env()
        self.rpc = rpc or SolanaRPCConnector()
        self.tracker = BalanceTracker(reserve_sol_for_gas=self.wallet_config.reserve_sol_for_gas)

    def fetch_live_balance_sheet(
        self,
        sol_price_usdt: float = 180.0,
        token_prices_usdt: Optional[Dict[str, float]] = None,
        realized_pnl_usdt: float = 0.0,
        unrealized_pnl_usdt: float = 0.0,
    ) -> NormalizedBalanceSheet:
        """Query Solana RPC for the wallet's SOL, USDT, and SPL balances and normalize to USDT."""
        pubkey = self.wallet_config.public_key.strip()
        prices = token_prices_usdt or {}
        if not pubkey:
            return self.tracker.build_balance_sheet(
                is_simulated=False,
                sol_balance=0.0,
                sol_price_usdt=sol_price_usdt,
                usdt_balance=0.0,
                spl_balances={},
                spl_prices_usdt=prices,
            )

        lamports = self.rpc.get_sol_balance_lamports(pubkey)
        sol_balance = (lamports / 1e9) if lamports is not None else 0.0

        token_accounts = self.rpc.get_token_accounts_by_owner(pubkey)
        usdt_balance = 0.0
        spl_balances: Dict[str, float] = {}

        for acc in token_accounts:
            mint = str(acc.get("mint", ""))
            qty = float(acc.get("ui_amount", 0.0))
            if mint == self.settings.usdt_mint_address:
                usdt_balance += qty
            elif mint:
                spl_balances[mint] = spl_balances.get(mint, 0.0) + qty

        return self.tracker.build_balance_sheet(
            is_simulated=False,
            sol_balance=sol_balance,
            sol_price_usdt=sol_price_usdt,
            usdt_balance=usdt_balance,
            spl_balances=spl_balances,
            spl_prices_usdt=prices,
            realized_pnl_usdt=realized_pnl_usdt,
            unrealized_pnl_usdt=unrealized_pnl_usdt,
        )
