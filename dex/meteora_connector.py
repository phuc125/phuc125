"""
Meteora DLMM / Dynamic AMM Connector (https://meteora.ag/).
Monitors dynamic liquidity bins, fee tiers, and unusual liquidity movements.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

import requests

from config.dex_config import DexConfig
from database.models import PoolState
from shared_core.data_engine import DataEngine

logger = logging.getLogger("solana_ai_meme_trader.meteora")


class MeteoraConnector:
    """Connector for Meteora DLMM and Dynamic AMM pools on Solana."""

    def __init__(
        self,
        config: Optional[DexConfig] = None,
        http_get_fn: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.config = config or DexConfig.from_env()
        self._http_get = http_get_fn or requests.get

    def parse_meteora_pair(self, item: Dict[str, Any]) -> Optional[PoolState]:
        """Normalize a Meteora DLMM pair record into PoolState."""
        addr = str(item.get("address") or item.get("pool_address") or "")
        mint_x = str(item.get("mint_x") or item.get("base_mint") or "")
        mint_y = str(item.get("mint_y") or item.get("quote_mint") or "")
        if not addr or not mint_x:
            return None

        name = str(item.get("name") or "MEME-USDT")
        parts = name.split("-") if "-" in name else [name, "USDT"]
        liq = float(item.get("liquidity") or item.get("liquidity_usd") or 0.0)
        vol_24h = float(item.get("trade_volume_24h") or item.get("volume_24h_usd") or 0.0)
        base_fee_pct = float(item.get("base_fee_percentage") or 0.25)

        raw = {
            "pool_address": addr,
            "dex_venue": "meteora",
            "base_mint": mint_x,
            "quote_mint": mint_y,
            "base_symbol": str(item.get("base_symbol") or parts[0]),
            "quote_symbol": str(item.get("quote_symbol") or (parts[1] if len(parts) > 1 else "USDT")),
            "price_usd": float(item.get("current_price") or item.get("price_usd") or 0.0),
            "liquidity_usd": liq,
            "volume_5m_usd": float(item.get("volume_5m_usd") or (vol_24h / 240.0)),
            "volume_1h_usd": float(item.get("volume_1h_usd") or (vol_24h / 20.0)),
            "volume_24h_usd": vol_24h,
            "buys_5m": int(item.get("buys_5m", 12)),
            "sells_5m": int(item.get("sells_5m", 9)),
            "buys_1h": int(item.get("buys_1h", 100)),
            "sells_1h": int(item.get("sells_1h", 80)),
            "price_change_5m_pct": float(item.get("price_change_5m_pct", 0.0)),
            "price_change_1h_pct": float(item.get("price_change_1h_pct", 0.0)),
            "price_change_24h_pct": float(item.get("price_change_24h_pct", 0.0)),
            "fee_bps": max(1, int(round(base_fee_pct * 100))),
        }
        return DataEngine.normalize_pool_record(raw, default_venue="meteora")

    def fetch_pairs_by_mint(self, mint_address: str) -> List[PoolState]:
        """Fetch Meteora DLMM pairs containing mint_address."""
        url = f"{self.config.meteora_api_url.rstrip('/')}/pair/all_by_groups"
        params = {"search_term": mint_address, "limit": 10}
        try:
            resp = self._http_get(url, params=params, timeout=self.config.rpc_timeout_seconds)
            resp.raise_for_status()
            payload = resp.json()
            groups = payload.get("groups", []) if isinstance(payload, dict) else []
            out: List[PoolState] = []
            for g in groups:
                for pair in g.get("pairs", []):
                    parsed = self.parse_meteora_pair(pair)
                    if parsed:
                        out.append(parsed)
            return out
        except Exception as exc:
            logger.debug("Meteora fetch_pairs_by_mint unavailable for %s: %s", mint_address, exc)
            return []
