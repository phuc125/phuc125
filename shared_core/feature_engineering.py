"""
Causal Feature Engineering Engine.
Computes technical, liquidity, order-flow, holder, and risk features strictly from
historical bars up to index t (zero look-ahead bias).
"""
from __future__ import annotations

import math
from typing import Dict, List

import numpy as np

from database.models import MarketSnapshot, OHLCVBar


FEATURE_COLUMNS: List[str] = [
    "return_1",
    "return_3",
    "return_6",
    "volatility_12",
    "rsi_14",
    "macd_hist",
    "ema_fast_slow_ratio",
    "vwap_deviation_pct",
    "volume_acceleration",
    "buy_sell_imbalance",
    "liquidity_log_usd",
    "liquidity_change_1h_pct",
    "holder_growth_1h_pct",
    "smart_money_inflow_norm",
    "top10_holder_concentration",
    "scam_flag_count",
]


class FeatureEngineer:
    """Computes leak-free technical and on-chain features for AI agents and ML models."""

    @staticmethod
    def compute_rsi(closes: np.ndarray, period: int = 14) -> float:
        """Compute Wilder/EMA RSI using only past bars."""
        if len(closes) < 3:
            return 50.0
        deltas = np.diff(closes)
        window = deltas[-period:] if len(deltas) >= period else deltas
        gains = np.where(window > 0, window, 0.0)
        losses = np.where(window < 0, -window, 0.0)
        avg_gain = float(np.mean(gains))
        avg_loss = float(np.mean(losses))
        if avg_loss <= 1e-12:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return float(100.0 - (100.0 / (1.0 + rs)))

    @staticmethod
    def compute_ema(values: np.ndarray, span: int) -> float:
        """Compute causal Exponential Moving Average at the final element."""
        if len(values) == 0:
            return 0.0
        alpha = 2.0 / (span + 1.0)
        ema_val = float(values[0])
        for price in values[1:]:
            ema_val = alpha * float(price) + (1.0 - alpha) * ema_val
        return ema_val

    @classmethod
    def compute_macd_histogram(cls, closes: np.ndarray) -> float:
        """Compute normalized MACD histogram (% of current price)."""
        if len(closes) < 6 or closes[-1] <= 0:
            return 0.0
        ema_fast = cls.compute_ema(closes, span=12)
        ema_slow = cls.compute_ema(closes, span=26)
        macd_line = ema_fast - ema_slow
        # Approximate signal line using recent MACD values
        if len(closes) >= 9:
            sub_macds = []
            start_idx = max(4, len(closes) - 9)
            for idx in range(start_idx, len(closes) + 1):
                sub = closes[:idx]
                sub_macds.append(cls.compute_ema(sub, 12) - cls.compute_ema(sub, 26))
            signal_line = cls.compute_ema(np.array(sub_macds), span=9)
        else:
            signal_line = macd_line * 0.8
        hist = macd_line - signal_line
        return float((hist / closes[-1]) * 100.0)

    @staticmethod
    def compute_vwap_deviation(bars: List[OHLCVBar]) -> float:
        """Compute percentage deviation of current close from rolling VWAP."""
        if not bars:
            return 0.0
        recent = bars[-20:]
        vols = np.array([max(0.0, b.volume_usd) for b in recent], dtype=float)
        typical_prices = np.array([(b.high + b.low + b.close) / 3.0 for b in recent], dtype=float)
        total_vol = float(np.sum(vols))
        if total_vol <= 1e-9 or typical_prices[-1] <= 0:
            return 0.0
        vwap = float(np.sum(typical_prices * vols) / total_vol)
        if vwap <= 1e-12:
            return 0.0
        return float(((recent[-1].close - vwap) / vwap) * 100.0)

    @classmethod
    def extract_features(cls, snapshot: MarketSnapshot) -> Dict[str, float]:
        """
        Extract normalized feature dictionary from a MarketSnapshot.
        Strictly causal: only uses snapshot.ohlcv_bars up to the end of the provided slice.
        """
        bars = snapshot.ohlcv_bars
        pool = snapshot.primary_pool
        token = snapshot.token
        wallet = snapshot.wallet_activity

        if bars and len(bars) >= 2:
            closes = np.array([max(1e-12, b.close) for b in bars], dtype=float)
            vols = np.array([max(0.0, b.volume_usd) for b in bars], dtype=float)
            ret_1 = float((closes[-1] / closes[-2] - 1.0) * 100.0)
            ret_3 = float((closes[-1] / closes[max(0, len(closes) - 4)] - 1.0) * 100.0)
            ret_6 = float((closes[-1] / closes[max(0, len(closes) - 7)] - 1.0) * 100.0)

            log_rets = np.diff(np.log(closes[-min(13, len(closes)):]))
            vol_12 = float(np.std(log_rets) * 100.0) if len(log_rets) > 1 else 1.5

            rsi_14 = cls.compute_rsi(closes, period=14)
            macd_hist = cls.compute_macd_histogram(closes)
            ema_fast = cls.compute_ema(closes, span=9)
            ema_slow = cls.compute_ema(closes, span=21)
            ema_ratio = float(((ema_fast / max(1e-12, ema_slow)) - 1.0) * 100.0)
            vwap_dev = cls.compute_vwap_deviation(bars)

            recent_vol = float(np.mean(vols[-3:])) if len(vols) >= 3 else float(vols[-1])
            prior_vol = float(np.mean(vols[:-3])) if len(vols) > 3 else max(1.0, recent_vol)
            vol_accel = float(recent_vol / max(1.0, prior_vol))
        else:
            ret_1 = pool.price_change_5m_pct
            ret_3 = pool.price_change_5m_pct * 1.5
            ret_6 = pool.price_change_1h_pct
            vol_12 = max(1.0, abs(pool.price_change_5m_pct) * 0.6)
            rsi_14 = 50.0 + max(-40.0, min(40.0, pool.price_change_1h_pct * 0.8))
            macd_hist = pool.price_change_5m_pct * 0.15
            ema_ratio = pool.price_change_1h_pct * 0.25
            vwap_dev = pool.price_change_5m_pct * 0.4
            avg_5m_from_1h = max(1.0, pool.volume_1h_usd / 12.0)
            vol_accel = float(pool.volume_5m_usd / avg_5m_from_1h)

        total_tx_5m = pool.buys_5m + pool.sells_5m
        if total_tx_5m > 0:
            buy_sell_imb = float((pool.buys_5m - pool.sells_5m) / total_tx_5m)
        else:
            total_tx_1h = pool.buys_1h + pool.sells_1h
            buy_sell_imb = float((pool.buys_1h - pool.sells_1h) / total_tx_1h) if total_tx_1h > 0 else 0.0

        liq_log = math.log10(max(1.0, pool.accessible_liquidity_usd))
        holder_growth = float(token.holder_growth_1h_pct or 0.0)
        top10_conc = float(token.top_10_holder_pct if token.top_10_holder_pct is not None else 35.0)

        sm_inflow = 0.0
        if wallet and wallet.data_available and pool.accessible_liquidity_usd > 0:
            sm_inflow = float(wallet.smart_money_net_inflow_usd / max(1000.0, pool.accessible_liquidity_usd))

        scam_flags = 0.0
        if token.mint_authority_active is True:
            scam_flags += 1.0
        if token.freeze_authority_active is True:
            scam_flags += 1.0
        if top10_conc > 60.0:
            scam_flags += 1.0
        if wallet and wallet.early_sniper_dump_detected:
            scam_flags += 1.0

        return {
            "return_1": round(ret_1, 4),
            "return_3": round(ret_3, 4),
            "return_6": round(ret_6, 4),
            "volatility_12": round(vol_12, 4),
            "rsi_14": round(rsi_14, 4),
            "macd_hist": round(macd_hist, 4),
            "ema_fast_slow_ratio": round(ema_ratio, 4),
            "vwap_deviation_pct": round(vwap_dev, 4),
            "volume_acceleration": round(vol_accel, 4),
            "buy_sell_imbalance": round(buy_sell_imb, 4),
            "liquidity_log_usd": round(liq_log, 4),
            "liquidity_change_1h_pct": round(pool.liquidity_change_1h_pct, 4),
            "holder_growth_1h_pct": round(holder_growth, 4),
            "smart_money_inflow_norm": round(sm_inflow, 4),
            "top10_holder_concentration": round(top10_conc, 4),
            "scam_flag_count": scam_flags,
        }

    @classmethod
    def to_vector(cls, features: Dict[str, float]) -> np.ndarray:
        """Convert feature dictionary into an ordered numpy vector matching FEATURE_COLUMNS."""
        return np.array([float(features.get(col, 0.0)) for col in FEATURE_COLUMNS], dtype=float)
