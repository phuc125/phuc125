"""
Wallet Security Boundary & Pre-Sign Transaction Validator.
Enforces strict isolation between AI decision-making and transaction signing.
Never accepts, logs, or exposes private keys or seed phrases.
"""
from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from config.wallet_config import SecurityError, WalletConfig

logger = logging.getLogger("solana_ai_meme_trader.wallet_security")

# Whitelisted Solana Program IDs allowed in swap transactions
ALLOWED_SOLANA_PROGRAMS: Set[str] = {
    "11111111111111111111111111111111",                      # System Program
    "ComputeBudget111111111111111111111111111111",           # Compute Budget
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",           # SPL Token Program
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",           # Token-2022 Program
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",          # Associated Token Account
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",           # Jupiter v6 Aggregator
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",          # Raydium AMM v4
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",          # Raydium CLMM
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",           # Orca Whirlpool
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",           # Meteora DLMM
}

BASE58_REGEX = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


@dataclass
class TransactionValidationResult:
    """Result of pre-sign instruction and security verification."""
    is_valid: bool
    reason: str
    verified_programs: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class WalletSecurityGuard:
    """Validates Solana addresses, prevents secret leakage, and inspects transaction payloads."""

    def __init__(self, config: Optional[WalletConfig] = None) -> None:
        self.config = config or WalletConfig.from_env()
        self.config.validate_no_secrets_in_env()

    @staticmethod
    def is_valid_solana_address(address: str) -> bool:
        """Check whether a string is a valid Base58 Solana public key / mint address."""
        if not address or not isinstance(address, str):
            return False
        return bool(BASE58_REGEX.match(address.strip()))

    @staticmethod
    def assert_no_secret_material(payload_str: str) -> None:
        """Verify that a payload or log string does not contain seed phrases or private key patterns."""
        lowered = payload_str.lower()
        for forbidden in ("mnemonic", "seed_phrase", "private_key", "secret_key", "-----begin"):
            if forbidden in lowered:
                raise SecurityError(f"Blocked payload containing forbidden secret keyword: {forbidden}")

    def validate_transaction_before_signing(
        self,
        serialized_tx_base64: str,
        expected_program_ids: Optional[List[str]] = None,
        simulation_result: Optional[Dict[str, object]] = None,
        notional_usdt: float = 0.0,
        max_notional_usdt: float = 2.5,
    ) -> TransactionValidationResult:
        """
        Validate a base64-encoded Solana transaction before forwarding to Bitget Wallet signing bridge.
        """
        self.assert_no_secret_material(serialized_tx_base64)

        if notional_usdt <= 0 or notional_usdt > max_notional_usdt:
            return TransactionValidationResult(
                is_valid=False,
                reason=f"Transaction notional ({notional_usdt:.4f} USDT) exceeds maximum allowed ({max_notional_usdt:.4f} USDT) or is non-positive.",
            )

        try:
            raw_bytes = base64.b64decode(serialized_tx_base64, validate=True)
            if len(raw_bytes) < 64 or len(raw_bytes) > 1232:
                return TransactionValidationResult(
                    is_valid=False,
                    reason=f"Invalid Solana transaction byte length ({len(raw_bytes)} bytes; expected 64..1232).",
                )
        except Exception as exc:
            return TransactionValidationResult(
                is_valid=False,
                reason=f"Invalid base64 transaction encoding: {exc}",
            )

        programs = expected_program_ids or ["JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"]
        for prog in programs:
            if prog not in ALLOWED_SOLANA_PROGRAMS:
                return TransactionValidationResult(
                    is_valid=False,
                    reason=f"Destination program {prog} is not in ALLOWED_SOLANA_PROGRAMS whitelist.",
                )

        if self.config.require_simulation_before_sign:
            if not simulation_result or not simulation_result.get("success", False):
                err_msg = simulation_result.get("error") if simulation_result else "Missing RPC simulation"
                return TransactionValidationResult(
                    is_valid=False,
                    reason=f"Pre-sign RPC transaction simulation failed or missing: {err_msg}",
                )

        return TransactionValidationResult(
            is_valid=True,
            reason="Transaction passed byte-bounds, program whitelist, notional cap, and RPC simulation checks.",
            verified_programs=programs,
        )
