"""
Solana JSON-RPC and WebSocket Connector.
Provides provider health checks, retry logic, rate-limit handling, SPL mint authority
inspection, holder distribution queries, and transaction simulation.
Official documentation: https://solana.com/docs/rpc
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

import requests

from config.dex_config import DexConfig

logger = logging.getLogger("solana_ai_meme_trader.solana_rpc")


class SolanaRPCConnector:
    """Resilient JSON-RPC client for Solana on-chain inspection and transaction verification."""

    def __init__(
        self,
        config: Optional[DexConfig] = None,
        http_post_fn: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.config = config or DexConfig.from_env()
        self._http_post = http_post_fn or requests.post
        self._request_id = 0
        self._last_health_ok: Optional[bool] = None
        self._cache: Dict[str, tuple[float, Any]] = {}

    def _call_rpc(self, method: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Execute a JSON-RPC request with exponential backoff and rate-limit handling."""
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or [],
        }
        last_err: Optional[Exception] = None
        for attempt in range(1, self.config.rpc_max_retries + 1):
            try:
                resp = self._http_post(
                    self.config.solana_rpc_url,
                    json=payload,
                    timeout=self.config.rpc_timeout_seconds,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 429:
                    backoff = min(4.0, 0.5 * (2 ** (attempt - 1)))
                    logger.warning("Solana RPC rate limited (429) on %s; sleeping %.2fs", method, backoff)
                    time.sleep(backoff)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise RuntimeError(f"RPC Error on {method}: {data['error']}")
                return data.get("result", {})
            except Exception as exc:
                last_err = exc
                if attempt < self.config.rpc_max_retries:
                    time.sleep(0.25 * attempt)
        logger.debug("Solana RPC call %s failed after %d attempts: %s", method, self.config.rpc_max_retries, last_err)
        raise ConnectionError(f"Solana RPC {method} unavailable: {last_err}")

    def check_health(self) -> bool:
        """Check whether the configured Solana RPC node is healthy."""
        try:
            res = self._call_rpc("getHealth")
            ok = res == "ok" or (isinstance(res, dict) and res.get("status") == "ok")
            self._last_health_ok = ok
            return ok
        except Exception:
            self._last_health_ok = False
            return False

    def get_sol_balance_lamports(self, pubkey: str) -> Optional[int]:
        """Return SOL balance in lamports for a given public key, or None if unreachable."""
        if not pubkey:
            return None
        try:
            res = self._call_rpc("getBalance", [pubkey, {"commitment": self.config.solana_commitment}])
            if isinstance(res, dict) and "value" in res:
                return int(res["value"])
            return None
        except Exception:
            return None

    def get_token_accounts_by_owner(self, owner_pubkey: str) -> List[Dict[str, Any]]:
        """Fetch SPL token balances owned by a wallet via getTokenAccountsByOwner."""
        if not owner_pubkey:
            return []
        token_program = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        try:
            res = self._call_rpc(
                "getTokenAccountsByOwner",
                [
                    owner_pubkey,
                    {"programId": token_program},
                    {"encoding": "jsonParsed", "commitment": self.config.solana_commitment},
                ],
            )
            accounts = res.get("value", []) if isinstance(res, dict) else []
            parsed_list: List[Dict[str, Any]] = []
            for item in accounts:
                info = (
                    item.get("account", {})
                    .get("data", {})
                    .get("parsed", {})
                    .get("info", {})
                )
                token_amount = info.get("tokenAmount", {})
                mint = info.get("mint", "")
                ui_amount = float(token_amount.get("uiAmount") or 0.0)
                decimals = int(token_amount.get("decimals") or 0)
                if mint and ui_amount > 0:
                    parsed_list.append(
                        {"mint": mint, "ui_amount": ui_amount, "decimals": decimals}
                    )
            return parsed_list
        except Exception:
            return []

    def inspect_mint_security(self, mint_address: str) -> Dict[str, Optional[Any]]:
        """
        Inspect SPL mint account via getAccountInfo (jsonParsed) to detect active
        mintAuthority or freezeAuthority (critical rug/honeypot indicators).
        """
        cache_key = f"mint_sec:{mint_address}"
        now = time.time()
        if cache_key in self._cache and now - self._cache[cache_key][0] < self.config.cache_ttl_seconds:
            return self._cache[cache_key][1]

        try:
            res = self._call_rpc(
                "getAccountInfo",
                [mint_address, {"encoding": "jsonParsed", "commitment": self.config.solana_commitment}],
            )
            info = (
                res.get("value", {})
                .get("data", {})
                .get("parsed", {})
                .get("info", {})
                if isinstance(res, dict) and res.get("value")
                else {}
            )
            if not info:
                return {"mint_authority_active": None, "freeze_authority_active": None, "decimals": None}
            out = {
                "mint_authority_active": info.get("mintAuthority") is not None,
                "freeze_authority_active": info.get("freezeAuthority") is not None,
                "decimals": int(info.get("decimals", 6)),
            }
            self._cache[cache_key] = (now, out)
            return out
        except Exception:
            return {"mint_authority_active": None, "freeze_authority_active": None, "decimals": None}

    def get_top_holder_concentration_pct(self, mint_address: str, total_supply_ui: float) -> Optional[float]:
        """Compute percentage of supply held by top 10 holders via getTokenLargestAccounts."""
        if total_supply_ui <= 0:
            return None
        try:
            res = self._call_rpc("getTokenLargestAccounts", [mint_address])
            accounts = res.get("value", []) if isinstance(res, dict) else []
            if not accounts:
                return None
            top_10_sum = sum(float(a.get("uiAmount") or 0.0) for a in accounts[:10])
            return round(min(100.0, (top_10_sum / total_supply_ui) * 100.0), 2)
        except Exception:
            return None

    def simulate_transaction(self, serialized_tx_base64: str) -> Dict[str, Any]:
        """Simulate a base64-encoded transaction on Solana RPC before signing/broadcast."""
        try:
            res = self._call_rpc(
                "simulateTransaction",
                [
                    serialized_tx_base64,
                    {"encoding": "base64", "commitment": self.config.solana_commitment, "sigVerify": False},
                ],
            )
            val = res.get("value", {}) if isinstance(res, dict) else {}
            err = val.get("err")
            logs = val.get("logs", [])
            units = val.get("unitsConsumed", 0)
            return {
                "success": err is None,
                "error": err,
                "logs": logs,
                "units_consumed": units,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "logs": [],
                "units_consumed": 0,
            }

    def get_signature_status(self, tx_signature: str) -> Dict[str, Any]:
        """Query confirmation status of a submitted transaction signature."""
        try:
            res = self._call_rpc("getSignatureStatuses", [[tx_signature], {"searchTransactionHistory": True}])
            vals = res.get("value", []) if isinstance(res, dict) else []
            status = vals[0] if vals else None
            if not status:
                return {"confirmed": False, "status": "NOT_FOUND", "error": None}
            conf_status = status.get("confirmationStatus", "processed")
            err = status.get("err")
            return {
                "confirmed": err is None and conf_status in ("confirmed", "finalized"),
                "status": conf_status.upper(),
                "error": err,
            }
        except Exception as exc:
            return {"confirmed": False, "status": "RPC_UNAVAILABLE", "error": str(exc)}
