"""
Bitget Wallet configuration and security boundary settings.
Never stores or accepts raw private keys or seed phrases.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class SigningMode(str, Enum):
    """Supported transaction signing modes for Bitget Wallet integration."""
    DISABLED = "DISABLED"
    EXTERNAL_APPROVAL_BRIDGE = "EXTERNAL_APPROVAL_BRIDGE"
    ORDER_MODE_API = "ORDER_MODE_API"


@dataclass(frozen=True)
class WalletConfig:
    """Validated Bitget Wallet monitoring and signing configuration."""
    public_key: str = ""
    signing_mode: SigningMode = SigningMode.DISABLED
    bridge_host: str = "127.0.0.1"
    bridge_port: int = 8788
    bitget_api_key: str = ""
    reserve_sol_for_gas: float = 0.02
    require_simulation_before_sign: bool = True
    require_manual_user_approval: bool = True
    approval_timeout_seconds: int = 60

    def validate_no_secrets_in_env(self) -> None:
        """Guardrail ensuring user did not accidentally configure raw private keys in env."""
        forbidden_vars = ("PRIVATE_KEY", "SEED_PHRASE", "MNEMONIC", "SECRET_KEY", "WALLET_SECRET")
        for var in forbidden_vars:
            if os.getenv(var):
                raise SecurityError(
                    f"CRITICAL SECURITY VIOLATION: Environment variable '{var}' detected. "
                    "Never pass raw private keys or seed phrases into the trading system."
                )

    @classmethod
    def from_env(cls) -> "WalletConfig":
        mode_raw = os.getenv("BITGET_SIGNING_MODE", "DISABLED").upper().strip()
        try:
            mode = SigningMode(mode_raw)
        except ValueError:
            mode = SigningMode.DISABLED

        cfg = cls(
            public_key=os.getenv("BITGET_WALLET_PUBLIC_KEY", "").strip(),
            signing_mode=mode,
            bridge_host=os.getenv("BITGET_BRIDGE_HOST", "127.0.0.1").strip(),
            bridge_port=int(os.getenv("BITGET_BRIDGE_PORT", "8788")),
            bitget_api_key=os.getenv("BITGET_API_KEY", "").strip(),
        )
        cfg.validate_no_secrets_in_env()
        return cfg


class SecurityError(Exception):
    """Raised when a wallet or signing security boundary is violated."""
