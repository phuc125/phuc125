"""
Isolated Transaction Signer Module.
Coordinates pre-sign RPC simulation, security validation, and Bitget Wallet interactive approval.
Strict boundary: AI agents never hold a reference to WalletSigner.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config.settings import OperatingMode, SystemSettings
from config.wallet_config import WalletConfig
from dex.solana_rpc_connector import SolanaRPCConnector
from wallet.bitget_connector import BitgetWalletConnector
from wallet.wallet_security import WalletSecurityGuard


@dataclass
class SigningOutcome:
    """Result of the isolated signing workflow."""
    approved_and_signed: bool
    signed_tx_base64: Optional[str]
    tx_signature: Optional[str]
    reason: str
    simulation_logs: List[str]


class IsolatedWalletSigner:
    """
    Isolated transaction-signing gate.
    Refuses to operate unless SystemSettings is in LIVE mode with explicit authorization.
    """

    def __init__(
        self,
        settings: Optional[SystemSettings] = None,
        wallet_config: Optional[WalletConfig] = None,
        rpc: Optional[SolanaRPCConnector] = None,
        bitget: Optional[BitgetWalletConnector] = None,
    ) -> None:
        self.settings = settings or SystemSettings.from_env()
        self.wallet_config = wallet_config or WalletConfig.from_env()
        self.rpc = rpc or SolanaRPCConnector()
        self.security = WalletSecurityGuard(self.wallet_config)
        self.bitget = bitget or BitgetWalletConnector(self.wallet_config, self.rpc)

    def sign_authorized_transaction(
        self,
        unsigned_tx_base64: str,
        notional_usdt: float,
        max_notional_usdt: float,
        expected_programs: Optional[List[str]] = None,
        metadata_summary: Optional[Dict[str, Any]] = None,
    ) -> SigningOutcome:
        """
        Execute the full isolated pre-sign verification and approval flow:
        1. Verify LIVE mode authorization and emergency stop state.
        2. Simulate transaction via Solana RPC.
        3. Validate instruction program IDs and notional bounds.
        4. Forward to Bitget Wallet approval bridge.
        """
        if self.settings.operating_mode != OperatingMode.LIVE or not self.settings.live_trading_authorized:
            return SigningOutcome(
                approved_and_signed=False,
                signed_tx_base64=None,
                tx_signature=None,
                reason="Live signing locked: system is not in authorized LIVE mode.",
                simulation_logs=[],
            )
        if self.settings.emergency_stop_active:
            return SigningOutcome(
                approved_and_signed=False,
                signed_tx_base64=None,
                tx_signature=None,
                reason="Emergency stop is active; signing aborted.",
                simulation_logs=[],
            )

        sim = self.rpc.simulate_transaction(unsigned_tx_base64)
        validation = self.security.validate_transaction_before_signing(
            serialized_tx_base64=unsigned_tx_base64,
            expected_program_ids=expected_programs,
            simulation_result=sim,
            notional_usdt=notional_usdt,
            max_notional_usdt=max_notional_usdt,
        )
        if not validation.is_valid:
            return SigningOutcome(
                approved_and_signed=False,
                signed_tx_base64=None,
                tx_signature=None,
                reason=validation.reason,
                simulation_logs=sim.get("logs", []),
            )

        bridge_res = self.bitget.request_Interactive_signature(
            serialized_tx_base64=unsigned_tx_base64,
            metadata_summary=metadata_summary or {"notional_usdt": notional_usdt},
        )
        return SigningOutcome(
            approved_and_signed=bool(bridge_res.get("signed", False)),
            signed_tx_base64=bridge_res.get("signed_tx_base64"),
            tx_signature=bridge_res.get("tx_signature"),
            reason=str(bridge_res.get("reason", "")),
            simulation_logs=sim.get("logs", []),
        )
