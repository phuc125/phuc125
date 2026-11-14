#!/usr/bin/env python3
"""
PROGRAM A: LIVE TRADING & MARKET MONITORING ENTRY POINT (live_main.py)
Responsibilities:
- Live Market Monitoring (`python live_main.py --mode monitor`)
- Controlled Live Trading (`python live_main.py --mode live`)
Safety Interlock:
Live Trading is DISABLED by default and strictly refuses to execute unless:
1. LIVE_TRADING_AUTHORIZED=true
2. Valid LIVE_APPROVAL_TOKEN (>= 12 chars) is provided
3. EMERGENCY_STOP_ACTIVE=false
4. Valid BITGET_WALLET_PUBLIC_KEY and active BITGET_SIGNING_MODE are configured and verified.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from adapters.live.live_executor import ControlledLiveExecutor
from adapters.live.live_market_data import LiveMarketDataAdapter
from adapters.live.live_portfolio import LivePortfolioAdapter
from backtesting.historical_data import HistoricalDatasetBuilder
from config.risk_config import OpportunityWeights, RiskConfig
from config.settings import OperatingMode, SystemSettings, configure_logging
from config.wallet_config import SigningMode, WalletConfig
from database.database import DatabaseManager
from database.models import ExecutionEnvironment
from shared_core.signal_engine import SignalEngine
from wallet.bitget_connector import BitgetWalletConnector


def run_monitor_mode(
    settings: SystemSettings,
    risk_config: RiskConfig,
    weights: OpportunityWeights,
    wallet_config: WalletConfig,
) -> int:
    logger = configure_logging(settings.log_level)
    logger.info("Starting PROGRAM A (live_main.py) in READ-ONLY LIVE MARKET MONITOR mode...")
    db = DatabaseManager(settings.database_path)
    bitget = BitgetWalletConnector(wallet_config)
    wallet_status = bitget.verify_status()

    portfolio = LivePortfolioAdapter(db=db, initial_capital_usdt=settings.initial_simulated_capital_usdt)
    sync_report = portfolio.sync_with_bitget_wallet()

    market_adapter = LiveMarketDataAdapter()
    snapshots = market_adapter.poll_live_snapshots()
    used_fallback_feed = False
    if not snapshots:
        # In offline/sandbox environments without outbound internet, inspect sample normalized snapshots
        snapshots = HistoricalDatasetBuilder.build_multi_regime_dataset(num_steps=1)[0]
        used_fallback_feed = True

    signal_engine = SignalEngine(risk_config=risk_config, weights=weights)
    evaluated_signals = []
    for snap in snapshots:
        sig, _ = signal_engine.generate_signal(
            snapshot=snap,
            portfolio_state=portfolio.get_risk_state(),
            environment=ExecutionEnvironment.LIVE,
            reference_now=snap.timestamp,
        )
        evaluated_signals.append(
            {
                "symbol": sig.symbol,
                "mint_address": sig.mint_address,
                "action": sig.action.value,
                "strategy": sig.strategy_family.value,
                "opportunity_score": sig.opportunity_score,
                "scam_classification": sig.scam_classification.value,
                "trade_eligibility": sig.trade_eligibility.value,
            }
        )

    output = {
        "program": "PROGRAM_A_LIVE",
        "mode": "MONITOR",
        "live_execution_locked": True,
        "offline_reference_feed_used": used_fallback_feed,
        "bitget_wallet_status": {
            "connected": wallet_status.connected,
            "public_key": wallet_status.public_key or "NOT_CONFIGURED",
            "signing_mode": wallet_status.signing_mode,
            "interactive_signing_ready": wallet_status.interactive_signing_ready,
        },
        "portfolio_sync": {
            "synced": sync_report.synced,
            "available_trading_usdt": sync_report.balance_sheet.available_trading_usdt,
            "total_portfolio_value_usdt": sync_report.balance_sheet.total_portfolio_value_usdt,
        },
        "monitored_signals": evaluated_signals,
    }
    print(json.dumps(output, indent=2))
    return 0


def run_live_mode(
    settings: SystemSettings,
    risk_config: RiskConfig,
    weights: OpportunityWeights,
    wallet_config: WalletConfig,
) -> int:
    logger = configure_logging(settings.log_level)
    logger.info("Verifying authorization and safety interlocks for PROGRAM A LIVE TRADING mode...")
    db = DatabaseManager(settings.database_path)

    # Mandatory Safety Gate 1: SystemSettings validation
    try:
        live_settings = SystemSettings(
            operating_mode=OperatingMode.LIVE,
            live_trading_authorized=settings.live_trading_authorized,
            live_approval_token=settings.live_approval_token,
            emergency_stop_active=settings.emergency_stop_active,
            primary_quote_asset=settings.primary_quote_asset,
            initial_simulated_capital_usdt=settings.initial_simulated_capital_usdt,
            database_path=settings.database_path,
            log_level=settings.log_level,
            audit_log_path=settings.audit_log_path,
        )
        live_settings.validate()
    except (PermissionError, ValueError) as exc:
        msg = f"LIVE TRADING REFUSED BY SAFETY INTERLOCK: {exc}"
        logger.error(msg)
        db.log_audit_event(
            environment=ExecutionEnvironment.LIVE,
            event_type="LIVE_STARTUP_REFUSED",
            severity="CRITICAL",
            details={"reason": str(exc)},
        )
        print(json.dumps({"program": "PROGRAM_A_LIVE", "mode": "LIVE", "status": "REFUSED", "reason": str(exc)}, indent=2))
        return 1

    # Mandatory Safety Gate 2: Bitget Wallet integration & signing bridge verification
    bitget = BitgetWalletConnector(wallet_config)
    status = bitget.verify_status()
    if (
        not status.connected
        or wallet_config.signing_mode == SigningMode.DISABLED
        or not status.interactive_signing_ready
    ):
        reason = (
            "Bitget Wallet integration is not fully authorized or signing bridge is unreachable "
            f"(connected={status.connected}, signing_mode={status.signing_mode}, "
            f"bridge_ready={status.interactive_signing_ready})."
        )
        logger.error("LIVE TRADING REFUSED: %s", reason)
        db.log_audit_event(
            environment=ExecutionEnvironment.LIVE,
            event_type="LIVE_WALLET_CHECK_FAILED",
            severity="CRITICAL",
            details={"reason": reason},
        )
        print(json.dumps({"program": "PROGRAM_A_LIVE", "mode": "LIVE", "status": "REFUSED", "reason": reason}, indent=2))
        return 1

    portfolio = LivePortfolioAdapter(db=db, initial_capital_usdt=live_settings.initial_simulated_capital_usdt)
    portfolio.sync_with_bitget_wallet()
    executor = ControlledLiveExecutor(
        settings=live_settings,
        risk_config=risk_config,
        wallet_config=wallet_config,
        db=db,
        portfolio=portfolio,
    )
    signal_engine = SignalEngine(risk_config=risk_config, weights=weights)
    market_adapter = LiveMarketDataAdapter()
    snapshots = market_adapter.poll_live_snapshots()

    results = []
    for snap in snapshots:
        sig, _ = signal_engine.generate_signal(
            snapshot=snap,
            portfolio_state=portfolio.get_risk_state(),
            environment=ExecutionEnvironment.LIVE,
        )
        if sig.action.value == "BUY":
            outcome = executor.execute_signal(snapshot=snap, signal=sig)
            results.append({"symbol": sig.symbol, "executed": outcome.executed, "reason": outcome.reason})

    print(json.dumps({"program": "PROGRAM_A_LIVE", "mode": "LIVE", "status": "ACTIVE", "executions": results}, indent=2))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Solana AI Meme Coin Trading System - Live Program (Program A)")
    parser.add_argument(
        "--mode",
        choices=["monitor", "live"],
        default="monitor",
        help="Execution mode for Program A: 'monitor' (read-only) or 'live' (requires explicit authorization)",
    )
    args = parser.parse_args(argv)

    settings = SystemSettings.from_env()
    risk_config = RiskConfig.from_env()
    weights = OpportunityWeights.from_env()
    wallet_config = WalletConfig.from_env()

    if args.mode == "live":
        return run_live_mode(settings, risk_config, weights, wallet_config)
    return run_monitor_mode(settings, risk_config, weights, wallet_config)


if __name__ == "__main__":
    sys.exit(main())
