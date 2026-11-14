"""
Risk management configuration and opportunity scoring weights.
Enforces conservative defaults for initial 10 USDT capital.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class OpportunityWeights:
    """Configurable weights for the 0-100 Opportunity Scoring Engine."""
    smart_money: float = 0.25
    volume_momentum: float = 0.25
    market_structure: float = 0.20
    liquidity_quality: float = 0.15
    sentiment: float = 0.15

    def validate(self) -> None:
        total = (
            self.smart_money
            + self.volume_momentum
            + self.market_structure
            + self.liquidity_quality
            + self.sentiment
        )
        if abs(total - 1.0) > 1e-4:
            raise ValueError(f"OpportunityWeights must sum to 1.0, got {total:.4f}")
        for name, val in self.to_dict().items():
            if val < 0.0 or val > 1.0:
                raise ValueError(f"Weight {name} out of range [0, 1]: {val}")

    def to_dict(self) -> Dict[str, float]:
        return {
            "smart_money": self.smart_money,
            "volume_momentum": self.volume_momentum,
            "market_structure": self.market_structure,
            "liquidity_quality": self.liquidity_quality,
            "sentiment": self.sentiment,
        }

    @classmethod
    def from_env(cls) -> "OpportunityWeights":
        w = cls(
            smart_money=float(os.getenv("WEIGHT_SMART_MONEY", "0.25")),
            volume_momentum=float(os.getenv("WEIGHT_VOLUME_MOMENTUM", "0.25")),
            market_structure=float(os.getenv("WEIGHT_MARKET_STRUCTURE", "0.20")),
            liquidity_quality=float(os.getenv("WEIGHT_LIQUIDITY_QUALITY", "0.15")),
            sentiment=float(os.getenv("WEIGHT_SENTIMENT", "0.15")),
        )
        w.validate()
        return w


@dataclass(frozen=True)
class RiskConfig:
    """Conservative risk parameters for capital preservation."""
    risk_per_trade_pct: float = 0.005          # 0.5% risk per trade
    max_daily_loss_pct: float = 0.02           # 2.0% maximum daily loss
    max_open_positions: int = 2                # Max 2 open positions concurrently
    min_opportunity_score: float = 75.0        # 75/100 minimum score
    max_slippage_bps: int = 150                # 1.5% max slippage
    max_price_impact_pct: float = 2.0          # 2.0% max price impact
    min_pool_liquidity_usd: float = 15000.0    # Minimum $15k pool liquidity
    max_position_size_usdt: float = 2.5        # Max 25% of 10 USDT in a single position
    min_position_size_usdt: float = 0.20       # Min viable position size on Solana
    max_trades_per_hour: int = 6               # Anti-overtrading limit
    max_consecutive_losses: int = 3            # Cooldown trigger after consecutive losses
    max_correlated_positions: int = 1          # Max positions sharing deployer/cluster
    min_reward_to_risk: float = 1.8            # Minimum expected R:R ratio
    default_dex_fee_bps: int = 30              # 0.30% typical AMM fee
    solana_base_tx_fee_usdt: float = 0.002     # Estimated base + priority fee in USDT
    emergency_stop_enabled: bool = True

    def validate(self) -> None:
        if not (0.0005 <= self.risk_per_trade_pct <= 0.05):
            raise ValueError("risk_per_trade_pct must be between 0.05% and 5%.")
        if not (0.005 <= self.max_daily_loss_pct <= 0.20):
            raise ValueError("max_daily_loss_pct must be between 0.5% and 20%.")
        if self.max_open_positions < 1 or self.max_open_positions > 20:
            raise ValueError("max_open_positions must be between 1 and 20.")
        if not (0.0 <= self.min_opportunity_score <= 100.0):
            raise ValueError("min_opportunity_score must be in [0, 100].")
        if self.max_slippage_bps < 1 or self.max_slippage_bps > 2000:
            raise ValueError("max_slippage_bps must be in [1, 2000].")
        if self.max_price_impact_pct <= 0.0 or self.max_price_impact_pct > 15.0:
            raise ValueError("max_price_impact_pct must be in (0, 15].")
        if self.min_pool_liquidity_usd < 1000.0:
            raise ValueError("min_pool_liquidity_usd must be at least $1,000.")

    @classmethod
    def from_env(cls) -> "RiskConfig":
        cfg = cls(
            risk_per_trade_pct=float(os.getenv("RISK_PER_TRADE_PCT", "0.005")),
            max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", "0.02")),
            max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "2")),
            min_opportunity_score=float(os.getenv("MIN_OPPORTUNITY_SCORE", "75.0")),
            max_slippage_bps=int(os.getenv("MAX_SLIPPAGE_BPS", "150")),
            max_price_impact_pct=float(os.getenv("MAX_PRICE_IMPACT_PCT", "2.0")),
            min_pool_liquidity_usd=float(os.getenv("MIN_POOL_LIQUIDITY_USD", "15000.0")),
            max_position_size_usdt=float(os.getenv("MAX_POSITION_SIZE_USDT", "2.5")),
            max_trades_per_hour=int(os.getenv("MAX_TRADES_PER_HOUR", "6")),
            max_correlated_positions=int(os.getenv("CORRELATION_MAX_CLUSTER_EXPOSURE", "1")),
            emergency_stop_enabled=os.getenv("EMERGENCY_STOP_ENABLED", "true").lower() in ("true", "1", "yes"),
        )
        cfg.validate()
        return cfg
