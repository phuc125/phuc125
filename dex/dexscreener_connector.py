"""
DexScreener API Connector for Solana Token and Pair Discovery.
Official API Reference: https://docs.dexscreener.com/api/reference
Rate Limits: 60 req/min on token-profiles/boosts, 300 req/min on pairs/tokens.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

import requests

from config.dex_config import DexConfig
from database.models import PoolState
from shared_core.data_engine import DataEngine

logger = logging.getLogger("solana_ai_meme_trader.dexscreener")


class DexScreenerConnector:
    """Queries DexScreener REST endpoints and normalizes Solana pair metrics."""

    def __init__(
        self,
        config: Optional[DexConfig] = None,
        http_get_fn: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.config = config or DexConfig.from_env()
        self._http_get = http_get_fn or requests.get
        self._cache: Dict[str, tuple[float, Any]] = {}
        self._request_timestamps: List[float] = []

    def _throttle(self) -> None:
        now = time.time()
        self._request_timestamps = [t for t in self._request_timestamps if now - t < 60.0]
        if len(self._request_timestamps) >= self.config.dexscreener_rpm_limit:
            sleep_for = max(0.1, 60.0 - (now - self._request_timestamps[0]))
            time.sleep(min(2.0, sleep_for))
        self._request_timestamps.append(time.time())

    def _get_json(self, path: str) -> Any:
        now = time.time()
        if path in self._cache and now - self._cache[path][0] < self.config.cache_ttl_seconds:
            return self._cache[path][1]
        self._throttle()
        url = f"{self.config.dexscreener_base_url.rstrip('/')}/{path.lstrip('/')}"
        resp = self._http_get(url, timeout=self.config.rpc_timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
        self._cache[path] = (now, data)
        return data

    @staticmethod
    def parse_dexscreener_pair(pair: Dict[str, Any]) -> Optional[PoolState]:
        """Convert a raw DexScreener Solana pair JSON object into a normalized PoolState."""
        if pair.get("chainId") != "solana":
            return None
        base_token = pair.get("baseToken", {}) or {}
        quote_token = pair.get("quoteToken", {}) or {}
        liq = pair.get("liquidity", {}) or {}
        vol = pair.get("volume", {}) or {}
        txns = pair.get("txns", {}) or {}
        m5_tx = txns.get("m5", {}) or {}
        h1_tx = txns.get("h1", {}) or {}
        pc = pair.get("priceChange", {}) or {}

        raw = {
            "pool_address": pair.get("pairAddress", ""),
            "dex_venue": pair.get("dexId", "dexscreener"),
            "base_mint": base_token.get("address", ""),
            "quote_mint": quote_token.get("address", ""),
            "base_symbol": base_token.get("symbol", "UNKNOWN"),
            "quote_symbol": quote_token.get("symbol", "SOL"),
            "price_usd": float(pair.get("priceUsd") or 0.0),
            "price_quote": float(pair.get("priceNative") or 0.0),
            "liquidity_usd": float(liq.get("usd") or 0.0),
            "volume_5m_usd": float(vol.get("m5") or 0.0),
            "volume_1h_usd": float(vol.get("h1") or 0.0),
            "volume_24h_usd": float(vol.get("h24") or 0.0),
            "buys_5m": int(m5_tx.get("buys") or 0),
            "sells_5m": int(m5_tx.get("sells") or 0),
            "buys_1h": int(h1_tx.get("buys") or 0),
            "sells_1h": int(h1_tx.get("sells") or 0),
            "price_change_5m_pct": float(pc.get("m5") or 0.0),
            "price_change_1h_pct": float(pc.get("h1") or 0.0),
            "price_change_24h_pct": float(pc.get("h24") or 0.0),
            "fdv_usd": float(pair["fdv"]) if pair.get("fdv") is not None else None,
            "market_cap_usd": float(pair["marketCap"]) if pair.get("marketCap") is not None else None,
            "created_at_ts": float(pair["pairCreatedAt"]) / 1000.0 if pair.get("pairCreatedAt") else None,
        }
        if not raw["pool_address"] or not raw["base_mint"]:
            return None
        return DataEngine.normalize_pool_record(raw, default_venue="dexscreener")

    def fetch_token_pools(self, mint_address: str) -> List[PoolState]:
        """Fetch all active Solana pools for a given token mint from DexScreener."""
        try:
            data = self._get_json(f"token-pairs/v1/solana/{mint_address}")
            pairs = data if isinstance(data, list) else data.get("pairs", [])
            out: List[PoolState] = []
            for p in pairs or []:
                parsed = self.parse_dexscreener_pair(p)
                if parsed is not None:
                    out.append(parsed)
            return out
        except Exception as exc:
            logger.debug("DexScreener fetch_token_pools failed for %s: %s", mint_address, exc)
            return []

    def discover_latest_solana_profiles(self) -> List[str]:
        """Return newly profiled Solana token mint addresses from /token-profiles/latest/v1."""
        try:
            data = self._get_json("token-profiles/latest/v1")
            items = data if isinstance(data, list) else []
            return [
                str(item.get("tokenAddress"))
                for item in items
                if isinstance(item, dict)
                and item.get("chainId") == "solana"
                and item.get("tokenAddress")
            ]
        except Exception as exc:
            logger.debug("DexScreener discover_latest_solana_profiles unavailable: %s", exc)
            return []
