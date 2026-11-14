"""
Token Discovery Module.
Deduplicates newly created Solana SPL tokens by mint address and enriches them with
on-chain authority and holder concentration metadata when RPC is available.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from database.models import PoolState, TokenMetadata
from dex.solana_rpc_connector import SolanaRPCConnector


class TokenDiscovery:
    """Discovers and deduplicates candidate meme coin tokens by canonical mint address."""

    def __init__(self, rpc_connector: Optional[SolanaRPCConnector] = None) -> None:
        self.rpc = rpc_connector

    def build_token_metadata_from_pools(
        self,
        pools: List[PoolState],
        enrich_onchain: bool = False,
    ) -> Dict[str, TokenMetadata]:
        """Deduplicate tokens across multiple pools by base_mint."""
        tokens: Dict[str, TokenMetadata] = {}
        for pool in pools:
            mint = pool.base_mint.strip()
            if not mint:
                continue
            if mint not in tokens:
                tok = TokenMetadata(
                    mint_address=mint,
                    symbol=pool.base_symbol,
                    name=f"{pool.base_symbol} Token",
                    created_at_ts=pool.created_at_ts,
                )
                if enrich_onchain and self.rpc is not None:
                    sec = self.rpc.inspect_mint_security(mint)
                    tok.mint_authority_active = sec.get("mint_authority_active")
                    tok.freeze_authority_active = sec.get("freeze_authority_active")
                    if sec.get("decimals") is not None:
                        tok.decimals = int(sec["decimals"])
                tokens[mint] = tok
        return tokens
