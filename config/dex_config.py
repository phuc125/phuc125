"""
DEX, Aggregator, and Solana RPC endpoint configuration.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DexConfig:
    """Endpoints, timeouts, and rate limits for Solana DEX and RPC connectors."""
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"
    solana_ws_url: str = "wss://api.mainnet-beta.solana.com"
    solana_commitment: str = "confirmed"
    rpc_timeout_seconds: float = 10.0
    rpc_max_retries: int = 3

    dexscreener_base_url: str = "https://api.dexscreener.com"
    dexscreener_rpm_limit: int = 60

    jupiter_quote_api_url: str = "https://quote-api.jup.ag/v6"
    jupiter_api_key: str = ""
    jupiter_rpm_limit: int = 60

    raydium_api_url: str = "https://api-v3.raydium.io"
    orca_api_url: str = "https://api.mainnet.orca.so"
    meteora_api_url: str = "https://dlmm-api.meteora.ag"

    cache_ttl_seconds: float = 15.0
    quote_max_age_seconds: float = 10.0

    # Canonical Solana Program IDs
    raydium_v4_program_id: str = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    raydium_clmm_program_id: str = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
    orca_whirlpool_program_id: str = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
    meteora_dlmm_program_id: str = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
    jupiter_v6_program_id: str = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"

    @classmethod
    def from_env(cls) -> "DexConfig":
        return cls(
            solana_rpc_url=os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
            solana_ws_url=os.getenv("SOLANA_WS_URL", "wss://api.mainnet-beta.solana.com"),
            solana_commitment=os.getenv("SOLANA_COMMITMENT", "confirmed"),
            rpc_timeout_seconds=float(os.getenv("RPC_TIMEOUT_SECONDS", "10.0")),
            rpc_max_retries=int(os.getenv("RPC_MAX_RETRIES", "3")),
            dexscreener_base_url=os.getenv("DEXSCREENER_BASE_URL", "https://api.dexscreener.com"),
            jupiter_quote_api_url=os.getenv("JUPITER_QUOTE_API_URL", "https://quote-api.jup.ag/v6"),
            jupiter_api_key=os.getenv("JUPITER_API_KEY", ""),
            raydium_api_url=os.getenv("RAYDIUM_API_URL", "https://api-v3.raydium.io"),
            orca_api_url=os.getenv("ORCA_API_URL", "https://api.mainnet.orca.so"),
            meteora_api_url=os.getenv("METEORA_API_URL", "https://dlmm-api.meteora.ag"),
        )
