"""
On-Chain Transaction Monitor & State Reconciler.
Tracks pending transaction signatures, verifies confirmation status, and prevents
blind retries when transaction state is uncertain.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from dex.solana_rpc_connector import SolanaRPCConnector


@dataclass
class TrackedTransaction:
    """State record for a submitted Solana transaction."""
    tx_signature: str
    mint_address: str
    side: str
    notional_usdt: float
    status: str = "SUBMITTED"  # SUBMITTED, CONFIRMED, FAILED, UNCERTAIN
    submitted_at: float = field(default_factory=time.time)
    confirmed_at: Optional[float] = None
    error: Optional[str] = None


class TransactionMonitor:
    """Monitors transaction confirmations and enforces reconciliation before retry."""

    def __init__(self, rpc: Optional[SolanaRPCConnector] = None) -> None:
        self.rpc = rpc or SolanaRPCConnector()
        self._transactions: Dict[str, TrackedTransaction] = {}

    def register_transaction(
        self,
        tx_signature: str,
        mint_address: str,
        side: str,
        notional_usdt: float,
    ) -> TrackedTransaction:
        rec = TrackedTransaction(
            tx_signature=tx_signature,
            mint_address=mint_address,
            side=side,
            notional_usdt=notional_usdt,
        )
        self._transactions[tx_signature] = rec
        return rec

    def reconcile_signature(self, tx_signature: str) -> TrackedTransaction:
        """Query Solana RPC to reconcile the confirmation status of tx_signature."""
        rec = self._transactions.get(
            tx_signature,
            TrackedTransaction(tx_signature=tx_signature, mint_address="", side="UNKNOWN", notional_usdt=0.0),
        )
        res = self.rpc.get_signature_status(tx_signature)
        if res.get("confirmed"):
            rec.status = "CONFIRMED"
            rec.confirmed_at = time.time()
        elif res.get("error") is not None and res.get("status") != "RPC_UNAVAILABLE":
            rec.status = "FAILED"
            rec.error = str(res.get("error"))
        elif res.get("status") == "RPC_UNAVAILABLE":
            rec.status = "UNCERTAIN"
            rec.error = str(res.get("error"))
        self._transactions[tx_signature] = rec
        return rec

    def can_safely_retry(self, tx_signature: str) -> bool:
        """
        Never retry a transaction blindly if its previous status is SUBMITTED or UNCERTAIN.
        Only explicitly FAILED transactions may be retried.
        """
        rec = self.reconcile_signature(tx_signature)
        return rec.status == "FAILED"
