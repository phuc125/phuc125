"""
Unit tests for Bitget Wallet Monitoring, Balance Normalization, and Signing Security Boundaries.
"""
from __future__ import annotations

import base64
import os
import unittest

from config.wallet_config import SecurityError, WalletConfig
from wallet.balance_tracker import BalanceTracker
from wallet.wallet_security import WalletSecurityGuard


class TestWalletSecurityAndAccounting(unittest.TestCase):
    def test_balance_tracker_normalizes_to_usdt_and_reserves_gas(self) -> None:
        tracker = BalanceTracker(reserve_sol_for_gas=0.02)
        sheet = tracker.build_balance_sheet(
            is_simulated=False,
            sol_balance=0.10,
            sol_price_usdt=180.0,
            usdt_balance=10.0,
            spl_balances={"MintA": 1000.0},
            spl_prices_usdt={"MintA": 0.0025},
            locked_in_orders_usdt=1.5,
            realized_pnl_usdt=0.45,
            unrealized_pnl_usdt=0.15,
        )
        self.assertFalse(sheet.is_simulated)
        self.assertEqual(sheet.available_trading_usdt, 8.5)
        # Total value = 0.10*180 (18.0) + 10.0 USDT + 2.5 SPL = 30.5 USDT
        self.assertEqual(sheet.total_portfolio_value_usdt, 30.5)

    def test_secret_variable_in_env_raises_security_error(self) -> None:
        os.environ["PRIVATE_KEY"] = " accidental_secret "
        try:
            with self.assertRaises(SecurityError):
                WalletConfig.from_env()
        finally:
            os.environ.pop("PRIVATE_KEY", None)

    def test_transaction_validator_blocks_unwhitelisted_program(self) -> None:
        guard = WalletSecurityGuard()
        dummy_tx = base64.b64encode(b"A" * 128).decode("utf-8")
        res = guard.validate_transaction_before_signing(
            serialized_tx_base64=dummy_tx,
            expected_program_ids=["MaliciousProgram111111111111111111111111111"],
            simulation_result={"success": True},
            notional_usdt=1.0,
            max_notional_usdt=2.5,
        )
        self.assertFalse(res.is_valid)
        self.assertIn("whitelist", res.reason)


if __name__ == "__main__":
    unittest.main()
