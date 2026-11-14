"""
Raydium DEX Connector (https://raydium.io/).
Supports discovering Raydium AMM v4 / CPMM / CLMM pools, analyzing liquidity and volume,
and parsing pool states.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

import requests

from config.dex_config import DexConfig
from database.models import PoolState
from shared_core.data_engine import DataEngine

logger = logging.getLogger("solana_ai_meme_trader.raydium")


class RaydiumConnector:
    """Connector for Raydium API v3 pool discovery and liquidity monitoring."""

    def __init__(
        self,
        config: Optional[DexConfig] = None,
        http_get_fn: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.config = config or DexConfig.from_env()
        self._http_get = http_get_fn or requests.get

    def parse_raydium_pool(self, item: Dict[str, Any]) -> Optional[PoolState]:
        """Normalize a Raydium API v3 pool record into PoolState."""
        pool_id = str(item.get("id") or item.get("pool_address") or "")
        mint_a = item.get("mintA", {}) or {}
        mint_b = item.get("mintB", {}) or {}
        base_mint = str(mint_a.get("address") or item.get("base_mint") or "")
        quote_mint = str(mint_b.get("address") or item.get("quote_mint") or "")
        if not pool_id or not base_mint:
            return None

        day_stats = item.get("day", {}) or {}
        tvl = float(item.get("tvl") or item.get("liquidity_usd") or 0.0)
        vol_24h = float(day_stats.get("volume") or item.get("volume_24h_usd") or 0.0)
        vol_1h = float(item.get("volume_1h_usd") or (vol_24h / 18.0))
        fee_rate = float(item.get("feeRate") or 0.0025)
        burn_pct = item.get("burnPercent")

        raw = {
            "pool_address": pool_id,
            "dex_venue": "raydium",
            "base_mint": base_mint,
            "quote_mint": quote_mint,
            "base_symbol": str(mint_a.get("symbol") or item.get("base_symbol") or "MEME"),
            "quote_symbol": str(mint_b.get("symbol") or item.get("quote_symbol") or "USDT"),
            "price_usd": float(item.get("price") or item.get("price_usd") or 0.0),
            "liquidity_usd": tvl,
            "volume_5m_usd": float(item.get("volume_5m_usd") or (vol_1h / 10.0)),
            "volume_1h_usd": vol_1h,
            "volume_24h_usd": vol_24h,
            "buys_5m": int(item.get("buys_5m", 15)),
            "sells_5m": int(item.get("sells_5m", 10)),
            "buys_1h": int(item.get("buys_1h", 120)),
            "sells_1h": int(item.get("sells_1h", 95)),
            "price_change_5m_pct": float(item.get("price_change_5m_pct", 0.0)),
            "price_change_1h_pct": float(item.get("price_change_1h_pct", 0.0)),
            "price_change_24h_pct": float(day_stats.get("priceChange") or item.get("price_change_24h_pct") or 0.0),
            "lp_locked_pct": float(burn_pct) if burn_pct is not None else None,
            "fee_bps": max(1, int(round(fee_rate * 10000))),
        }
        return DataEngine.normalize_pool_record(raw, default_venue="raydium")

    def fetch_pools_by_mint(self, mint_address: str) -> List[PoolState]:
        """Query Raydium API v3 for pools containing mint_address."""
        url = f"{self.config.raydium_api_url.rstrip('/')}/pools/info/mint"
        params = {
            "mint1": mint_address,
            "poolType": "all",
            "poolSortField": "liquidity",
            "sortType": "desc",
            "pageSize": 10,
            "page": 1,
        }
        try:
            resp = self._http_get(url, params=params, timeout=self.config.rpc_timeout_seconds)
            resp.raise_for_status()
            payload = resp.json()
            items = payload.get("data", {}).get("data", []) if isinstance(payload, dict) else []
            out: List[PoolState] = []
            for item in items:
                p = self.parse_raydium_pool(item)
                if p:
                    out.append(p)
            return out
        except Exception as exc:
            logger.debug("Raydium fetch_pools_by_mint unavailable for %s: %s", mint_address, exc)
            return []
