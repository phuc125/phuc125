"""
Bitget Wallet Connector (https://web3.bitget.com/en/docs/connect/mainnet/solana).
ARCHITECTURAL DISCLOSURE ON BITGET WALLET CAPABILITIES:
1. Official Bitget Wallet browser/mobile extension exposes `window.bitkeep.solana` (Wallet Standard)
   for user-approved interactive signing (`connect()`, `signTransaction()`, `signAndSendTransaction()`).
2. Official Bitget Wallet Order Mode / Instruction Mode APIs return unsigned calldata/serialized transactions
   that the user or local bridge must sign; Bitget Wallet does NOT provide an unattended cloud private-key
   signing API.
3. Accordingly, this connector provides:
   - Read-only public key monitoring via Solana RPC (`SOL`, `USDT`, and SPL tokens).
   - Local Approval Bridge client (`EXTERNAL_APPROVAL_BRIDGE`) where unsigned VersionedTransactions are queued
     for explicit operator approval in a local Bitget Wallet DApp browser session.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import requests

from config.wallet_config import SigningMode, WalletConfig
from dex.solana_rpc_connector import SolanaRPCConnector
from wallet.wallet_security import WalletSecurityGuard

logger = logging.getLogger("solana_ai_meme_trader.bitget_connector")


@dataclass
class BitgetConnectionStatus:
    """Connection and capability status for Bitget Wallet."""
    connected: bool
    public_key: str
    signing_mode: str
    read_only_monitoring_ready: bool
    interactive_signing_ready: bool
    capability_note: str


class BitgetWalletConnector:
    """Manages connection state and capability verification for Bitget Wallet on Solana."""

    def __init__(
        self,
        wallet_config: Optional[WalletConfig] = None,
        rpc: Optional[SolanaRPCConnector] = None,
        http_post_fn: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.config = wallet_config or WalletConfig.from_env()
        self.rpc = rpc or SolanaRPCConnector()
        self.security = WalletSecurityGuard(self.config)
        self._http_post = http_post_fn or requests.post

    def verify_status(self) -> BitgetConnectionStatus:
        """Verify Bitget Wallet configuration, public key validity, and signing bridge reachability."""
        pubkey = self.config.public_key.strip()
        valid_pubkey = self.security.is_valid_solana_address(pubkey)

        bridge_ready = False
        if self.config.signing_mode == SigningMode.EXTERNAL_APPROVAL_BRIDGE and valid_pubkey:
            bridge_ready = self._ping_local_approval_bridge()

        note = (
            "Bitget Wallet Solana integration uses public-key RPC monitoring for balances/portfolio sync "
            "and requires explicit user approval via the local Bitget Wallet extension bridge "
            "(window.bitkeep.solana) for transaction signing. Unattended headless signing is disabled by design."
        )
        return BitgetConnectionStatus(
            connected=valid_pubkey,
            public_key=pubkey if valid_pubkey else "",
            signing_mode=self.config.signing_mode.value,
            read_only_monitoring_ready=valid_pubkey,
            interactive_signing_ready=bridge_ready,
            capability_note=note,
        )

    def _ping_local_approval_bridge(self) -> bool:
        """Check whether the local operator approval bridge for Bitget Wallet is listening."""
        url = f"http://{self.config.bridge_host}:{self.config.bridge_port}/health"
        try:
            resp = requests.get(url, timeout=1.5)
            return resp.status_code == 200
        except Exception:
            return False

    def request_Interactive_signature(
        self,
        serialized_tx_base64: str,
        metadata_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Submit a validated unsigned base64 VersionedTransaction to the local Bitget Wallet
        approval bridge for explicit operator signature.
        """
        if self.config.signing_mode == SigningMode.DISABLED:
            return {
                "signed": False,
                "signed_tx_base64": None,
                "tx_signature": None,
                "reason": "BITGET_SIGNING_MODE is DISABLED.",
            }

        self.security.assert_no_secret_material(serialized_tx_base64)
        url = f"http://{self.config.bridge_host}:{self.config.bridge_port}/v1/bitget/sign"
        payload = {
            "publicKey": self.config.public_key,
            "unsignedTransactionBase64": serialized_tx_base64,
            "requireUserApproval": self.config.require_manual_user_approval,
            "metadata": metadata_summary,
        }
        try:
            resp = self._http_post(url, json=payload, timeout=self.config.approval_timeout_seconds)
            resp.raise_for_status()
            data = resp.json()
            return {
                "signed": bool(data.get("signed", False)),
                "signed_tx_base64": data.get("signedTransactionBase64"),
                "tx_signature": data.get("signature"),
                "reason": data.get("reason", "Approved by operator via Bitget Wallet bridge"),
            }
        except Exception as exc:
            return {
                "signed": False,
                "signed_tx_base64": None,
                "tx_signature": None,
                "reason": f"Bitget Wallet approval bridge unreachable or rejected request: {exc}",
            }
