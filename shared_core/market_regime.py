"""
Market Regime Detection Engine.
Classifies price action, volatility, and order flow into actionable regimes
for Agent 1 (Market Analysis AI) and Adaptive Strategy Selection.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict


class MarketRegimeType(str, Enum):
    BULLISH_BREAKOUT = "BULLISH_BREAKOUT"
    UPTREND_PULLBACK = "UPTREND_PULLBACK"
    CAPITULATION_REVERSAL = "CAPITULATION_REVERSAL"
    STEALTH_ACCUMULATION = "STEALTH_ACCUMULATION"
    CHOPPY_LOW_LIQUIDITY = "CHOPPY_LOW_LIQUIDITY"
    BEARISH_DISTRIBUTION = "BEARISH_DISTRIBUTION"
    EXTREME_VOLATILITY_PUMP_DUMP = "EXTREME_VOLATILITY_PUMP_DUMP"


@dataclass
class MarketRegimeReport:
    """Output of market regime and structure evaluation."""
    regime: MarketRegimeType
    trend_direction: str  # BULLISH, BEARISH, NEUTRAL
    momentum_score: float  # 0 to 100
    volatility_score: float  # 0 to 100 (higher = more volatile)
    structure_score: float  # 0 to 100 (higher = cleaner tradable structure)
    support_price_usd: float
    resistance_price_usd: float
    confidence: float  # 0 to 1


class MarketRegimeClassifier:
    """Classifies token market conditions using causal features and OHLCV structure."""

    @staticmethod
    def classify(features: Dict[str, float], current_price_usd: float) -> MarketRegimeReport:
        ret_1 = features.get("return_1", 0.0)
        ret_3 = features.get("return_3", 0.0)
        ret_6 = features.get("return_6", 0.0)
        vol_12 = features.get("volatility_12", 2.0)
        rsi = features.get("rsi_14", 50.0)
        ema_ratio = features.get("ema_fast_slow_ratio", 0.0)
        vol_accel = features.get("volume_acceleration", 1.0)
        imbalance = features.get("buy_sell_imbalance", 0.0)
        sm_inflow = features.get("smart_money_inflow_norm", 0.0)

        # Determine trend direction
        if ema_ratio > 0.8 and ret_6 > 2.0:
            trend = "BULLISH"
        elif ema_ratio < -0.8 and ret_6 < -2.0:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"

        # Momentum score (0-100)
        raw_mom = (
            50.0
            + min(25.0, max(-25.0, ret_3 * 2.2))
            + min(15.0, max(-15.0, (vol_accel - 1.0) * 10.0))
            + min(10.0, max(-10.0, imbalance * 20.0))
        )
        momentum_score = round(max(0.0, min(100.0, raw_mom)), 2)

        # Volatility score (0-100)
        volatility_score = round(max(0.0, min(100.0, vol_12 * 8.5)), 2)

        # Classify regime
        if vol_12 > 11.0 and abs(ret_1) > 25.0:
            regime = MarketRegimeType.EXTREME_VOLATILITY_PUMP_DUMP
            structure_score = 25.0
        elif ret_1 > 2.5 and vol_accel >= 1.35 and imbalance > 0.12 and 52.0 <= rsi <= 82.0:
            regime = MarketRegimeType.BULLISH_BREAKOUT
            structure_score = 84.0
        elif trend == "BULLISH" and -6.0 <= ret_1 <= 1.2 and 40.0 <= rsi <= 60.0 and imbalance >= -0.05:
            regime = MarketRegimeType.UPTREND_PULLBACK
            structure_score = 80.0
        elif ret_6 < -8.0 and ret_1 > 1.0 and rsi < 42.0 and imbalance > 0.15 and vol_accel >= 1.2:
            regime = MarketRegimeType.CAPITULATION_REVERSAL
            structure_score = 76.0
        elif abs(ret_3) < 6.0 and sm_inflow > 0.015 and imbalance > 0.08:
            regime = MarketRegimeType.STEALTH_ACCUMULATION
            structure_score = 82.0
        elif trend == "BEARISH" and imbalance < -0.10:
            regime = MarketRegimeType.BEARISH_DISTRIBUTION
            structure_score = 30.0
        else:
            regime = MarketRegimeType.CHOPPY_LOW_LIQUIDITY
            structure_score = 45.0

        band_pct = max(0.03, min(0.18, (vol_12 / 100.0) * 2.2))
        support = round(current_price_usd * (1.0 - band_pct), 10)
        resistance = round(current_price_usd * (1.0 + band_pct * 1.4), 10)

        return MarketRegimeReport(
            regime=regime,
            trend_direction=trend,
            momentum_score=momentum_score,
            volatility_score=volatility_score,
            structure_score=round(structure_score, 2),
            support_price_usd=support,
            resistance_price_usd=resistance,
            confidence=0.82 if vol_accel >= 1.0 else 0.65,
        )
