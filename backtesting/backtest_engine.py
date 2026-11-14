"""
Complete Historical Backtesting Engine (Phase 10).
Stepped chronologically bar-by-bar with zero look-ahead bias, realistic slippage/fees,
survivorship-bias controls (delisted/rugged tokens included), and SQLite persistence.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backtesting.execution_simulator import ExecutionSimulator
from backtesting.historical_data import HistoricalDatasetBuilder
from config.risk_config import OpportunityWeights, RiskConfig
from config.settings import SystemSettings
from database.database import DatabaseManager
from database.models import (
    ExecutionEnvironment,
    MarketSnapshot,
    PositionRecord,
    TradeAction,
    TradingSignal,
)
from shared_core.performance_analyzer import PerformanceAnalyzer, PerformanceReport
from shared_core.portfolio_manager import PortfolioManager
from shared_core.signal_engine import SignalEngine
from shared_core.trade_manager import TradeManager


@dataclass
class BacktestRunResult:
    """Complete output of a historical backtest run."""
    initial_capital_usdt: float
    final_equity_usdt: float
    signals_generated: int
    scam_tokens_rejected: int
    performance: PerformanceReport
    equity_curve: List[float] = field(default_factory=list)
    closed_positions: List[PositionRecord] = field(default_factory=list)


class BacktestEngine:
    """Runs causal historical backtests using the shared SignalEngine and PortfolioManager."""

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
        self.signal_engine = SignalEngine(risk_config=self.risk_config, weights=self.weights)
        self.simulator = ExecutionSimulator(self.risk_config)

    def run(
        self,
        timeline: Optional[List[List[MarketSnapshot]]] = None,
    ) -> BacktestRunResult:
        steps = timeline or HistoricalDatasetBuilder.build_multi_regime_dataset(num_steps=36)
        portfolio = PortfolioManager(
            environment=ExecutionEnvironment.BACKTEST,
            initial_capital_usdt=self.settings.initial_simulated_capital_usdt,
        )

        signals_count = 0
        scam_rejected_count = 0

        for step_idx, step_snapshots in enumerate(steps):
            snap_by_mint: Dict[str, MarketSnapshot] = {s.token.mint_address: s for s in step_snapshots}

            # 1. Mark-to-market and check exits on existing open positions first
            for pos_id, pos in list(portfolio.open_positions.items()):
                snap = snap_by_mint.get(pos.mint_address)
                if snap is None:
                    continue
                cur_bar = snap.ohlcv_bars[-1] if snap.ohlcv_bars else None
                pos.update_mark_price(snap.primary_pool.price_usd)

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
                    closed = portfolio.close_position(
                        position_id=pos_id,
                        exit_price_usd=sell_fill.fill_price_usd,
                        exit_fee_usdt=sell_fill.fee_paid_usdt,
                        exit_reason=exit_eval.exit_reason,
                    )
                    if closed:
                        self.db.save_position(closed)

            # 2. Evaluate new candidate tokens at this causal step
            held_mints = {p.mint_address for p in portfolio.open_positions.values()}
            for snap in step_snapshots:
                if snap.token.mint_address in held_mints:
                    continue

                signal, committee = self.signal_engine.generate_signal(
                    snapshot=snap,
                    portfolio_state=portfolio.get_risk_state(),
                    environment=ExecutionEnvironment.BACKTEST,
                    reference_now=snap.timestamp,
                )
                signals_count += 1
                if committee.scam_report.eligibility.value == "REJECTED":
                    scam_rejected_count += 1
                self.db.save_signal(signal)

                if signal.action == TradeAction.BUY and signal.recommended_position_usdt > 0:
                    fill = self.simulator.simulate_buy(
                        pool=snap.primary_pool,
                        requested_notional_usdt=signal.recommended_position_usdt,
                        max_slippage_bps=self.risk_config.max_slippage_bps,
                    )
                    if fill.executed and fill.filled_tokens > 0:
                        pos = PositionRecord(
                            position_id=f"bt_pos_{uuid.uuid4().hex[:10]}",
                            environment=ExecutionEnvironment.BACKTEST,
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
                        portfolio.register_open_position(pos, total_cost_usdt=fill.filled_notional_usdt)
                        self.db.save_position(pos)
                        held_mints.add(snap.token.mint_address)

            # Reset hourly trade counter every 12 five-minute bars
            if (step_idx + 1) % 12 == 0:
                portfolio.trades_last_hour = 0

        # Close any remaining open positions at end of backtest window for clean accounting
        if steps:
            final_snaps = {s.token.mint_address: s for s in steps[-1]}
            for pos_id, pos in list(portfolio.open_positions.items()):
                snap = final_snaps.get(pos.mint_address)
                mark_p = snap.primary_pool.price_usd if snap else pos.current_price_usd
                sell_fill = self.simulator.simulate_sell(
                    pool=snap.primary_pool if snap else PoolState(
                        pool_address=pos.pool_address, dex_venue=pos.dex_venue,
                        base_mint=pos.mint_address, quote_mint="", base_symbol=pos.symbol,
                        quote_symbol="USDT", price_usd=mark_p, price_quote=mark_p,
                        liquidity_usd=25000.0, accessible_liquidity_usd=12000.0,
                        volume_5m_usd=1000.0, volume_1h_usd=5000.0, volume_24h_usd=20000.0,
                        buys_5m=5, sells_5m=5, buys_1h=20, sells_1h=20,
                        price_change_5m_pct=0.0, price_change_1h_pct=0.0, price_change_24h_pct=0.0,
                    ),
                    quantity_tokens=pos.quantity_tokens,
                    trigger_price_usd=mark_p,
                )
                closed = portfolio.close_position(
                    position_id=pos_id,
                    exit_price_usd=sell_fill.fill_price_usd,
                    exit_fee_usdt=sell_fill.fee_paid_usdt,
                    exit_reason="END_OF_BACKTEST_WINDOW",
                )
                if closed:
                    self.db.save_position(closed)

        perf = PerformanceAnalyzer.analyze(portfolio.closed_positions, portfolio.equity_curve)
        self.db.record_portfolio_snapshot(
            environment=ExecutionEnvironment.BACKTEST,
            total_equity_usdt=portfolio.total_equity_usdt,
            available_cash_usdt=portfolio.available_cash_usdt,
            reserved_funds_usdt=0.0,
            realized_pnl_usdt=portfolio.realized_pnl_usdt,
            unrealized_pnl_usdt=portfolio.unrealized_pnl_usdt,
            drawdown_pct=portfolio.current_drawdown_pct,
        )

        return BacktestRunResult(
            initial_capital_usdt=self.settings.initial_simulated_capital_usdt,
            final_equity_usdt=portfolio.total_equity_usdt,
            signals_generated=signals_count,
            scam_tokens_rejected=scam_rejected_count,
            performance=perf,
            equity_curve=portfolio.equity_curve,
            closed_positions=portfolio.closed_positions,
        )
