"""
Risk-Adjusted Position Sizing Engine.
Calculates position size in USDT based on 0.5% risk per trade, stop-loss distance,
pool liquidity constraints, and maximum exposure caps. Never increases risk after losses.
"""
from __future__ import annotations

from dataclasses import dataclass

from config.risk_config import RiskConfig


@dataclass
class PositionSizeCalculation:
    """Detailed position sizing output in USDT and token units."""
    recommended_notional_usdt: float
    recommended_tokens: float
    risk_budget_usdt: float
    stop_loss_pct: float
    capped_by: str


class PositionSizer:
    """Computes conservative position sizes for 10 USDT initial capital."""

    def __init__(self, risk_config: RiskConfig) -> None:
        self.config = risk_config

    def calculate_position_size(
        self,
        total_equity_usdt: float,
        available_cash_usdt: float,
        entry_price_usd: float,
        stop_loss_usd: float,
        accessible_liquidity_usd: float,
        volatility_score: float = 50.0,
    ) -> PositionSizeCalculation:
        if entry_price_usd <= 0 or stop_loss_usd <= 0 or stop_loss_usd >= entry_price_usd:
            return PositionSizeCalculation(0.0, 0.0, 0.0, 0.0, "INVALID_PRICE_OR_STOP")

        # 1. Risk budget in USDT (e.g., 0.5% of 10 USDT = 0.05 USDT max loss at stop)
        risk_budget_usdt = max(0.0, total_equity_usdt * self.config.risk_per_trade_pct)
        stop_loss_pct = (entry_price_usd - stop_loss_usd) / entry_price_usd

        # Account for round-trip DEX fee + slippage buffer in effective stop loss
        round_trip_friction_pct = (self.config.default_dex_fee_bps * 2 + 50) / 10000.0
        effective_stop_pct = max(0.015, stop_loss_pct + round_trip_friction_pct)

        raw_notional = risk_budget_usdt / effective_stop_pct

        # Volatility dampener for high-volatility regimes (never increases risk)
        if volatility_score > 70.0:
            raw_notional *= 0.75

        capped_by = "RISK_BUDGET"
        notional = raw_notional

        # Cap by configured max_position_size_usdt
        if notional > self.config.max_position_size_usdt:
            notional = self.config.max_position_size_usdt
            capped_by = "MAX_POSITION_CAP"

        # Cap by 1% of pool accessible liquidity to prevent price impact
        liq_cap = accessible_liquidity_usd * 0.01
        if notional > liq_cap:
            notional = liq_cap
            capped_by = "POOL_LIQUIDITY_CAP"

        # Cap by available cash minus base fee buffer
        max_cash = max(0.0, available_cash_usdt - self.config.solana_base_tx_fee_usdt * 2)
        if notional > max_cash:
            notional = max_cash
            capped_by = "AVAILABLE_CASH"

        if notional < self.config.min_position_size_usdt:
            return PositionSizeCalculation(
                0.0, 0.0, round(risk_budget_usdt, 4), round(stop_loss_pct * 100.0, 2), "BELOW_MIN_VIABLE_SIZE"
            )

        tokens = notional / entry_price_usd
        return PositionSizeCalculation(
            recommended_notional_usdt=round(notional, 4),
            recommended_tokens=tokens,
            risk_budget_usdt=round(risk_budget_usdt, 4),
            stop_loss_pct=round(stop_loss_pct * 100.0, 2),
            capped_by=capped_by,
        )
