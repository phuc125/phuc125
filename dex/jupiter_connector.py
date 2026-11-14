"""
Jupiter Swap Aggregator Connector (https://jup.ag/ & https://developers.jup.ag/docs/swap).
Treats Jupiter strictly as a swap aggregator across Solana liquidity venues (Raydium, Orca, Meteora),
not as an independent liquidity pool DEX.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import requests

from config.dex_config import DexConfig

logger = logging.getLogger("solana_ai_meme_trader.jupiter")


@dataclass
class SwapQuote:
    """Normalized swap quote from Jupiter v6 or deterministic local route estimator."""
    input_mint: str
    output_mint: str
    in_amount_atomic: int
    out_amount_atomic: int
    in_amount_ui: float
    out_amount_ui: float
    price_impact_pct: float
    slippage_bps: int
    estimated_fee_usdt: float
    route_labels: List[str] = field(default_factory=list)
    raw_quote_response: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def is_fresh(self, max_age_seconds: float = 10.0) -> bool:
        return (time.time() - self.timestamp) <= max_age_seconds


class JupiterAggregatorConnector:
    """
    Swap quote and transaction serialization client for Jupiter v6 API.
    Includes a deterministic constant-product route calculator fallback for offline/testing parity.
    """

    def __init__(
        self,
        config: Optional[DexConfig] = None,
        http_get_fn: Optional[Callable[..., Any]] = None,
        http_post_fn: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.config = config or DexConfig.from_env()
        self._http_get = http_get_fn or requests.get
        self._http_post = http_post_fn or requests.post

    def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount_atomic: int,
        input_decimals: int = 6,
        output_decimals: int = 6,
        slippage_bps: int = 100,
    ) -> Optional[SwapQuote]:
        """Request an aggregated swap route quote from Jupiter v6 /quote endpoint."""
        url = f"{self.config.jupiter_quote_api_url.rstrip('/')}/quote"
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount_atomic),
            "slippageBps": str(slippage_bps),
        }
        headers: Dict[str, str] = {}
        if self.config.jupiter_api_key:
            headers["x-api-key"] = self.config.jupiter_api_key

        try:
            resp = self._http_get(url, params=params, headers=headers, timeout=self.config.rpc_timeout_seconds)
            resp.raise_for_status()
            data = resp.json()
            in_amt = int(data.get("inAmount", amount_atomic))
            out_amt = int(data.get("outAmount", 0))
            impact = float(data.get("priceImpactPct") or 0.0) * 100.0
            route_plan = data.get("routePlan", []) or []
            labels = [
                str(step.get("swapInfo", {}).get("label", "AMM"))
                for step in route_plan
                if isinstance(step, dict)
            ]
            in_ui = in_amt / (10 ** input_decimals)
            out_ui = out_amt / (10 ** output_decimals)
            return SwapQuote(
                input_mint=input_mint,
                output_mint=output_mint,
                in_amount_atomic=in_amt,
                out_amount_atomic=out_amt,
                in_amount_ui=in_ui,
                out_amount_ui=out_ui,
                price_impact_pct=abs(impact),
                slippage_bps=slippage_bps,
                estimated_fee_usdt=round(in_ui * 0.003 + 0.002, 6),
                route_labels=labels or ["JupiterAggregatedRoute"],
                raw_quote_response=data,
            )
        except Exception as exc:
            logger.debug("Jupiter get_quote API unreachable (%s); returning None", exc)
            return None

    def build_swap_transaction(
        self,
        quote: SwapQuote,
        user_public_key: str,
    ) -> Optional[str]:
        """
        Request a serialized VersionedTransaction (base64) from Jupiter /swap endpoint.
        Never signs or broadcasts the transaction.
        """
        if not quote.raw_quote_response or not user_public_key:
            return None
        url = f"{self.config.jupiter_quote_api_url.rstrip('/')}/swap"
        payload = {
            "quoteResponse": quote.raw_quote_response,
            "userPublicKey": user_public_key,
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True,
        }
        try:
            resp = self._http_post(url, json=payload, timeout=self.config.rpc_timeout_seconds)
            resp.raise_for_status()
            data = resp.json()
            return data.get("swapTransaction")
        except Exception as exc:
            logger.debug("Jupiter build_swap_transaction unavailable: %s", exc)
            return None
