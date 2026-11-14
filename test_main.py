#!/usr/bin/env python3
"""
PROGRAM B: TESTING ENTRY POINT (test_main.py)
Responsibilities:
- Historical Backtesting (`python test_main.py --mode backtest`)
- Real-time Paper Trading (`python test_main.py --mode paper`)
- Strategy testing, ML walk-forward evaluation, and simulated portfolio management.
Safety Guarantee: Uses simulated capital (10 USDT default) and never accesses real transaction signing.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from adapters.testing.paper_executor import PaperTradingExecutor
from adapters.testing.testing_market_data import TestingMarketDataAdapter
from backtesting.backtest_engine import BacktestEngine
from config.risk_config import OpportunityWeights, RiskConfig
from config.settings import OperatingMode, SystemSettings, configure_logging
from database.database import DatabaseManager
from learning.experiment_tracker import ExperimentTracker
from learning.model_evaluation import ContinuousLearningEvaluator


def run_backtest_mode(settings: SystemSettings, risk_config: RiskConfig, weights: OpportunityWeights) -> int:
    logger = configure_logging(settings.log_level)
    logger.info("Starting PROGRAM B (test_main.py) in HISTORICAL BACKTEST mode...")
    db = DatabaseManager(settings.database_path)
    engine = BacktestEngine(settings=settings, risk_config=risk_config, weights=weights, db=db)
    result = engine.run()

    eval_summary = ContinuousLearningEvaluator.evaluate_outcomes(
        closed_positions=result.closed_positions,
        equity_curve=result.equity_curve,
        current_min_opportunity_score=risk_config.min_opportunity_score,
    )
    tracker = ExperimentTracker(db)
    tracker.register_model_version(
        version_id="gbdt_ensemble_v1.0",
        model_type="Hybrid_GBDT_Ensemble",
        metrics=result.performance.to_dict(),
        is_active=True,
    )

    summary = {
        "program": "PROGRAM_B_TESTING",
        "mode": "BACKTEST",
        "initial_capital_usdt": result.initial_capital_usdt,
        "final_equity_usdt": result.final_equity_usdt,
        "signals_evaluated": result.signals_generated,
        "scam_tokens_rejected": result.scam_tokens_rejected,
        "performance": result.performance.to_dict(),
        "continuous_learning_recommendations": [
            {
                "parameter": r.parameter_name,
                "current": r.current_value,
                "proposed": r.proposed_value,
                "rationale": r.rationale,
            }
            for r in eval_summary.recommendations
        ],
    }
    print(json.dumps(summary, indent=2))
    return 0


def run_paper_mode(
    settings: SystemSettings,
    risk_config: RiskConfig,
    weights: OpportunityWeights,
    cycles: int = 8,
) -> int:
    logger = configure_logging(settings.log_level)
    logger.info("Starting PROGRAM B (test_main.py) in REAL-TIME PAPER TRADING mode (%d cycles)...", cycles)
    db = DatabaseManager(settings.database_path)
    executor = PaperTradingExecutor(settings=settings, risk_config=risk_config, weights=weights, db=db)
    market_feed = TestingMarketDataAdapter()

    for _ in range(max(1, cycles)):
        snapshots = market_feed.get_current_snapshots(prefer_live_feed=False)
        executor.step_cycle(snapshots)

    report = executor.build_session_report(cycles_completed=cycles)
    output = {
        "program": "PROGRAM_B_TESTING",
        "mode": "PAPER",
        "cycles_completed": report.cycles_completed,
        "initial_capital_usdt": report.initial_capital_usdt,
        "current_equity_usdt": report.current_equity_usdt,
        "available_cash_usdt": report.available_cash_usdt,
        "realized_pnl_usdt": report.realized_pnl_usdt,
        "unrealized_pnl_usdt": report.unrealized_pnl_usdt,
        "open_positions_count": report.open_positions_count,
        "sample_fill_comparisons": [
            {
                "symbol": c.symbol,
                "side": c.side,
                "expected_price_usd": c.expected_price_usd,
                "simulated_fill_price_usd": c.simulated_fill_price_usd,
                "slippage_bps": c.slippage_bps,
                "fee_usdt": c.fee_usdt,
            }
            for c in report.fill_comparisons[:5]
        ],
        "performance": report.performance.to_dict() if report.performance else {},
    }
    print(json.dumps(output, indent=2))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Solana AI Meme Coin Trading System - Testing Program (Program B)")
    parser.add_argument(
        "--mode",
        choices=["backtest", "paper"],
        default="backtest",
        help="Execution mode for Program B: 'backtest' or 'paper'",
    )
    parser.add_argument("--cycles", type=int, default=8, help="Number of cycles to run in paper mode")
    args = parser.parse_args(argv)

    base_settings = SystemSettings.from_env()
    mode_enum = OperatingMode.BACKTEST if args.mode == "backtest" else OperatingMode.PAPER
    settings = SystemSettings(
        operating_mode=mode_enum,
        live_trading_authorized=False,
        live_approval_token="",
        emergency_stop_active=base_settings.emergency_stop_active,
        primary_quote_asset=base_settings.primary_quote_asset,
        initial_simulated_capital_usdt=base_settings.initial_simulated_capital_usdt,
        database_path=base_settings.database_path,
        log_level=base_settings.log_level,
        audit_log_path=base_settings.audit_log_path,
    )
    risk_config = RiskConfig.from_env()
    weights = OpportunityWeights.from_env()

    if args.mode == "backtest":
        return run_backtest_mode(settings, risk_config, weights)
    return run_paper_mode(settings, risk_config, weights, cycles=args.cycles)


if __name__ == "__main__":
    sys.exit(main())
