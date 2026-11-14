"""
Real-Time Paper Trading Engine (Phase 11).
Uses the exact same SignalEngine as Live Trading, simulates fees, slippage, and price impact,
records expected price vs. simulated fill price, and NEVER accesses transaction signing.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from adapters.testing.execution_simulator import ExecutionSimulator
from adapters.testing.simulated_portfolio import SimulatedPortfolioAdapter
from config.risk_config import OpportunityWeights, RiskConfig
from config.settings import SystemSettings
from database.database import DatabaseManager
from database.models import (
    ExecutionEnvironment,
    MarketSnapshot,
    PositionRecord,
    TradeAction,
)
from shared_core.performance_analyzer import PerformanceAnalyzer, PerformanceReport
from shared_core.signal_engine import SignalEngine
from shared_core.trade_manager import TradeManager


@dataclass
class PaperFillComparison:
    """Audit record comparing expected signal price vs. simulated fill price."""
    symbol: str
    side: str
    expected_price_usd: float
    simulated_fill_price_usd: float
    slippage_bps: float
    fee_usdt: float


@dataclass
class PaperTradingSessionReport:
    """Summary of a Paper Trading session."""
    cycles_completed: int
    initial_capital_usdt: float
    current_equity_usdt: float
    available_cash_usdt: float
    realized_pnl_usdt: float
    unrealized_pnl_usdt: float
    open_positions_count: int
    fill_comparisons: List[PaperFillComparison] = field(default_factory=list)
    performance: Optional[PerformanceReport] = None


class PaperTradingExecutor:
    """Executes real-time Paper Trading with simulated balances and zero signing access."""

    def __init__(
        self,
        settings: Optional[SystemSettings] = None,
        risk_config: Optional[RiskConfig] = None,
        weights: Optional[OpportunityWeights] = None,
        db: Optional[DatabaseManager] = None,
    ) -> None:
        self.settings = settings or SystemSettings.from_env()
        self.risk_config = risk_config or RiskConfig.from_env()
        self.weights = weights or OpportunityWeights.from_env()
        self.db = db or DatabaseManager(self.settings.database_path)
        self.portfolio = SimulatedPortfolioAdapter(
            initial_capital_usdt=self.settings.initial_simulated_capital_usdt,
            environment=ExecutionEnvironment.PAPER,
        )
        self.signal_engine = SignalEngine(risk_config=self.risk_config, weights=self.weights)
        self.simulator = ExecutionSimulator(self.risk_config)
        self.fill_comparisons: List[PaperFillComparison] = []

    def step_cycle(self, snapshots: List[MarketSnapshot]) -> None:
        """Process one cycle of market snapshots in Paper Trading mode."""
        snap_by_mint: Dict[str, MarketSnapshot] = {s.token.mint_address: s for s in snapshots}

        # 1. Update open positions and evaluate SL/TP exits
        for pos_id, pos in list(self.portfolio.open_positions.items()):
            snap = snap_by_mint.get(pos.mint_address)
            if snap is None:
                continue
            pos.update_mark_price(snap.primary_pool.price_usd)
            cur_bar = snap.ohlcv_bars[-1] if snap.ohlcv_bars else None
            exit_eval = TradeManager.check_exit_conditions(
                position=pos,
                current_price_usd=snap.primary_pool.price_usd,
                bar_low_usd=cur_bar.low if cur_bar else None,
                bar_high_usd=cur_bar.high if cur_bar else None,
                pool_state=snap.primary_pool,
            )
            if exit_eval.should_exit:
                sell_fill = self.simulator.simulate_sell(
                    pool=snap.primary_pool,
                    quantity_tokens=pos.quantity_tokens,
                    trigger_price_usd=exit_eval.trigger_price_usd,
                )
                self.fill_comparisons.append(
                    PaperFillComparison(
                        symbol=pos.symbol,
                        side="SELL",
                        expected_price_usd=exit_eval.trigger_price_usd,
                        simulated_fill_price_usd=sell_fill.fill_price_usd,
                        slippage_bps=sell_fill.slippage_bps_realized,
                        fee_usdt=sell_fill.fee_paid_usdt,
                    )
                )
                closed = self.portfolio.close_position(
                    position_id=pos_id,
                    exit_price_usd=sell_fill.fill_price_usd,
                    exit_fee_usdt=sell_fill.fee_paid_usdt,
                    exit_reason=exit_eval.exit_reason,
                )
                if closed:
                    self.db.save_position(closed)

        # 2. Evaluate new entries
        held_mints = {p.mint_address for p in self.portfolio.open_positions.values()}
        for snap in snapshots:
            self.db.upsert_token(snap.token)
            self.db.upsert_pool(snap.primary_pool)
            if snap.token.mint_address in held_mints:
                continue

            signal, _ = self.signal_engine.generate_signal(
                snapshot=snap,
                portfolio_state=self.portfolio.get_risk_state(),
                environment=ExecutionEnvironment.PAPER,
                reference_now=snap.timestamp,
            )
            self.db.save_signal(signal)

            if signal.action == TradeAction.BUY and signal.recommended_position_usdt > 0:
                fill = self.simulator.simulate_buy(
                    pool=snap.primary_pool,
                    requested_notional_usdt=signal.recommended_position_usdt,
                    max_slippage_bps=self.risk_config.max_slippage_bps,
                )
                if fill.executed and fill.filled_tokens > 0:
                    self.fill_comparisons.append(
                        PaperFillComparison(
                            symbol=snap.token.symbol,
                            side="BUY",
                            expected_price_usd=signal.entry_price_usd,
                            simulated_fill_price_usd=fill.fill_price_usd,
                            slippage_bps=fill.slippage_bps_realized,
                            fee_usdt=fill.fee_paid_usdt,
                        )
                    )
                    pos = PositionRecord(
                        position_id=f"paper_pos_{uuid.uuid4().hex[:10]}",
                        environment=ExecutionEnvironment.PAPER,
                        mint_address=snap.token.mint_address,
                        symbol=snap.token.symbol,
                        pool_address=snap.primary_pool.pool_address,
                        dex_venue=snap.primary_pool.dex_venue,
                        strategy_family=signal.strategy_family.value,
                        entry_price_usd=fill.fill_price_usd,
                        current_price_usd=fill.fill_price_usd,
                        quantity_tokens=fill.filled_tokens,
                        notional_entry_usdt=fill.filled_notional_usdt,
                        stop_loss_usd=signal.stop_loss_usd,
                        take_profit_usd=signal.take_profit_usd,
                        fees_paid_usdt=fill.fee_paid_usdt,
                        slippage_bps=fill.slippage_bps_realized,
                        status="OPEN",
                    )
                    self.portfolio.register_open_position(pos, total_cost_usdt=fill.filled_notional_usdt)
                    self.db.save_position(pos)
                    held_mints.add(snap.token.mint_address)

        self.db.record_portfolio_snapshot(
            environment=ExecutionEnvironment.PAPER,
            total_equity_usdt=self.portfolio.total_equity_usdt,
            available_cash_usdt=self.portfolio.available_cash_usdt,
            reserved_funds_usdt=0.0,
            realized_pnl_usdt=self.portfolio.realized_pnl_usdt,
            unrealized_pnl_usdt=self.portfolio.unrealized_pnl_usdt,
            drawdown_pct=self.portfolio.current_drawdown_pct,
        )

    def build_session_report(self, cycles_completed: int) -> PaperTradingSessionReport:
        perf = PerformanceAnalyzer.analyze(
            self.portfolio.closed_positions,
            self.portfolio.equity_curve,
        )
        return PaperTradingSessionReport(
            cycles_completed=cycles_completed,
            initial_capital_usdt=self.portfolio.initial_capital_usdt,
            current_equity_usdt=self.portfolio.total_equity_usdt,
            available_cash_usdt=self.portfolio.available_cash_usdt,
            realized_pnl_usdt=self.portfolio.realized_pnl_usdt,
            unrealized_pnl_usdt=self.portfolio.unrealized_pnl_usdt,
            open_positions_count=len(self.portfolio.open_positions),
            fill_comparisons=self.fill_comparisons,
            performance=perf,
        )
