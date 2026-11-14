"""
Orca Whirlpool DEX Connector (https://www.orca.so/).
Monitors Orca concentrated liquidity Whirlpool pools and normalizes pool states.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

import requests

from config.dex_config import DexConfig
from database.models import PoolState
from shared_core.data_engine import DataEngine

logger = logging.getLogger("solana_ai_meme_trader.orca")


class OrcaConnector:
    """Connector for Orca Whirlpool pool monitoring on Solana."""

    def __init__(
        self,
        config: Optional[DexConfig] = None,
        http_get_fn: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.config = config or DexConfig.from_env()
        self._http_get = http_get_fn or requests.get

    def parse_orca_pool(self, item: Dict[str, Any]) -> Optional[PoolState]:
        """Normalize an Orca Whirlpool record into PoolState."""
        address = str(item.get("address") or item.get("pool_address") or "")
        tok_a = item.get("tokenA", {}) or {}
        tok_b = item.get("tokenB", {}) or {}
        base_mint = str(tok_a.get("mint") or item.get("base_mint") or "")
        quote_mint = str(tok_b.get("mint") or item.get("quote_mint") or "")
        if not address or not base_mint:
            return None

        tvl = float(item.get("tvl") or item.get("liquidity_usd") or 0.0)
        vol_day = float((item.get("volume", {}) or {}).get("day") or item.get("volume_24h_usd") or 0.0)
        lp_fee_rate = float(item.get("lpFeeRate") or 0.003)

        raw = {
            "pool_address": address,
            "dex_venue": "orca",
            "base_mint": base_mint,
            "quote_mint": quote_mint,
            "base_symbol": str(tok_a.get("symbol") or item.get("base_symbol") or "MEME"),
            "quote_symbol": str(tok_b.get("symbol") or item.get("quote_symbol") or "USDT"),
            "price_usd": float(item.get("price") or item.get("price_usd") or 0.0),
            "liquidity_usd": tvl,
            "volume_5m_usd": float(item.get("volume_5m_usd") or (vol_day / 240.0)),
            "volume_1h_usd": float(item.get("volume_1h_usd") or (vol_day / 20.0)),
            "volume_24h_usd": vol_day,
            "buys_5m": int(item.get("buys_5m", 10)),
            "sells_5m": int(item.get("sells_5m", 8)),
            "buys_1h": int(item.get("buys_1h", 90)),
            "sells_1h": int(item.get("sells_1h", 75)),
            "price_change_5m_pct": float(item.get("price_change_5m_pct", 0.0)),
            "price_change_1h_pct": float(item.get("price_change_1h_pct", 0.0)),
            "price_change_24h_pct": float(item.get("price_change_24h_pct", 0.0)),
            "fee_bps": max(1, int(round(lp_fee_rate * 10000))),
        }
        return DataEngine.normalize_pool_record(raw, default_venue="orca")

    def fetch_whirlpools(self, mint_address: Optional[str] = None) -> List[PoolState]:
        """Fetch Orca Whirlpool list and optionally filter by token mint."""
        url = f"{self.config.orca_api_url.rstrip('/')}/v1/whirlpool/list"
        try:
            resp = self._http_get(url, timeout=self.config.rpc_timeout_seconds)
            resp.raise_for_status()
            payload = resp.json()
            pools = payload.get("whirlpools", []) if isinstance(payload, dict) else []
            out: List[PoolState] = []
            for p in pools:
                parsed = self.parse_orca_pool(p)
                if parsed and (mint_address is None or mint_address in (parsed.base_mint, parsed.quote_mint)):
                    out.append(parsed)
            return out
        except Exception as exc:
            logger.debug("Orca fetch_whirlpools unavailable: %s", exc)
            return []
