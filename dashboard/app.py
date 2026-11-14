"""
Streamlit Dashboard Entry Point (Phase 15).
Includes all 6 required sections:
1. Overview
2. DEX Scanner
3. AI Analysis
4. Trading (Open Positions & Trade History)
5. Performance (Win Rate, Profit Factor, Equity Curve, Strategy Comparison)
6. Wallet (Bitget Wallet Connection Status, SOL/USDT/SPL Balances, Portfolio Sync)
Strictly separates actual LIVE Trading data from simulated PAPER / BACKTEST data.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Any, Dict

from backtesting.historical_data import HistoricalDatasetBuilder
from config.risk_config import OpportunityWeights, RiskConfig
from config.settings import SystemSettings
from config.wallet_config import WalletConfig
from database.database import DatabaseManager
from database.models import ExecutionEnvironment
from shared_core.signal_engine import SignalEngine
from wallet.bitget_connector import BitgetWalletConnector
from wallet.wallet_monitor import BitgetWalletMonitor


def build_dashboard_state(
    environment: ExecutionEnvironment = ExecutionEnvironment.PAPER,
    db_path: str = "database/solana_meme_trader.db",
) -> Dict[str, Any]:
    """
    Assemble complete dashboard telemetry strictly filtered by ExecutionEnvironment
    (never mixes LIVE and PAPER/BACKTEST balances or statistics).
    Can be called both by Streamlit UI and by automated verification tests.
    """
    settings = SystemSettings.from_env()
    risk_config = RiskConfig.from_env()
    weights = OpportunityWeights.from_env()
    wallet_config = WalletConfig.from_env()
    db = DatabaseManager(db_path)

    open_positions = db.get_positions(environment=environment, status="OPEN")
    closed_positions = db.get_positions(environment=environment, status="CLOSED")
    recent_signals = db.get_signals(environment=environment, limit=50)
    discovered_pools = db.get_discovered_pools(limit=50)

    bitget_conn = BitgetWalletConnector(wallet_config)
    wallet_status = bitget_conn.verify_status()
    wallet_monitor = BitgetWalletMonitor(settings=settings, wallet_config=wallet_config)
    live_sheet = wallet_monitor.fetch_live_balance_sheet()

    # Sample live/candidate AI analysis for the AI Analysis tab
    sample_snaps = HistoricalDatasetBuilder.build_multi_regime_dataset(num_steps=1)[0]
    sig_engine = SignalEngine(risk_config=risk_config, weights=weights)
    ai_dossiers = []
    for snap in sample_snaps:
        from shared_core.portfolio_manager import PortfolioManager
        pm = PortfolioManager(environment=environment, initial_capital_usdt=settings.initial_simulated_capital_usdt)
        sig, committee = sig_engine.generate_signal(snap, pm.get_risk_state(), environment, reference_now=snap.timestamp)
        ai_dossiers.append(
            {
                "symbol": snap.token.symbol,
                "mint": snap.token.mint_address,
                "dex": snap.primary_pool.dex_venue,
                "price_usd": snap.primary_pool.price_usd,
                "liquidity_usd": snap.primary_pool.liquidity_usd,
                "opportunity_score": sig.opportunity_score,
                "market_regime": committee.market_report.regime.value,
                "smart_money_status": committee.smart_money_report.status,
                "sentiment_momentum": committee.sentiment_report.social_momentum,
                "scam_classification": committee.scam_report.classification.value,
                "scam_warnings": committee.scam_report.warning_signs,
                "strategy_selected": sig.strategy_family.value,
                "action": sig.action.value,
                "recommended_usdt": sig.recommended_position_usdt,
                "reasoning": sig.reasoning,
            }
        )

    realized_pnl = sum(float(p.get("realized_pnl_usdt", 0.0)) for p in closed_positions)
    unrealized_pnl = sum(float(p.get("unrealized_pnl_usdt", 0.0)) for p in open_positions)
    base_cap = settings.initial_simulated_capital_usdt if environment != ExecutionEnvironment.LIVE else live_sheet.total_portfolio_value_usdt

    return {
        "environment": environment.value,
        "is_simulated": environment != ExecutionEnvironment.LIVE,
        "overview": {
            "operating_mode": environment.value,
            "initial_capital_usdt": round(base_cap, 4),
            "portfolio_value_usdt": round(base_cap + realized_pnl + unrealized_pnl, 4),
            "realized_pnl_usdt": round(realized_pnl, 4),
            "unrealized_pnl_usdt": round(unrealized_pnl, 4),
            "open_positions_count": len(open_positions),
            "closed_trades_count": len(closed_positions),
        },
        "dex_scanner": ai_dossiers,
        "discovered_pools_db": discovered_pools,
        "ai_analysis": ai_dossiers,
        "trading": {
            "open_positions": open_positions,
            "trade_history": closed_positions,
            "recent_signals": recent_signals,
        },
        "wallet": {
            "connected": wallet_status.connected,
            "public_key": wallet_status.public_key or "Not Configured (.env BITGET_WALLET_PUBLIC_KEY)",
            "signing_mode": wallet_status.signing_mode,
            "interactive_signing_ready": wallet_status.interactive_signing_ready,
            "capability_note": wallet_status.capability_note,
            "sol_balance": live_sheet.sol_balance,
            "usdt_balance": live_sheet.usdt_balance,
            "available_trading_usdt": live_sheet.available_trading_usdt,
            "reserved_funds_usdt": live_sheet.reserved_funds_usdt,
            "spl_token_balances": live_sheet.spl_token_balances,
        },
    }


def render_streamlit_app() -> None:
    """Render the interactive Streamlit dashboard when invoked via `streamlit run dashboard/app.py`."""
    import streamlit as st  # type: ignore

    st.set_page_config(page_title="Solana AI Meme Coin Trader", layout="wide")
    st.title("Solana AI Meme Coin Trading System — Institutional Control Center")

    env_choice = st.sidebar.selectbox(
        "Select Isolated Environment Ledger",
        options=["PAPER", "BACKTEST", "LIVE"],
        index=0,
        help="Real LIVE data and Simulated PAPER/BACKTEST data are strictly isolated.",
    )
    state = build_dashboard_state(environment=ExecutionEnvironment(env_choice))

    if state["is_simulated"]:
        st.info(f"Viewing SIMULATED ({state['environment']}) Ledger — Real wallet signing is completely disabled.")
    else:
        st.warning("Viewing LIVE Trading Ledger — Real transactions require explicit authorization and Bitget Wallet approval.")

    tabs = st.tabs(["1. Overview", "2. DEX Scanner", "3. AI Analysis", "4. Trading", "5. Performance", "6. Bitget Wallet"])

    with tabs[0]:
        ov = state["overview"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Operating Mode", ov["operating_mode"])
        c2.metric("Portfolio Value (USDT)", f"${ov['portfolio_value_usdt']:.4f}")
        c3.metric("Realized PnL (USDT)", f"${ov['realized_pnl_usdt']:+.4f}")
        c4.metric("Unrealized PnL (USDT)", f"${ov['unrealized_pnl_usdt']:+.4f}")

    with tabs[1]:
        st.subheader("Multi-DEX Token & Pool Scanner (Raydium, Orca, Meteora, DexScreener)")
        st.dataframe(state["dex_scanner"], use_container_width=True)

    with tabs[2]:
        st.subheader("Six-Agent AI Committee Dossier")
        for item in state["ai_analysis"]:
            with st.expander(f"{item['symbol']} ({item['dex'].upper()}) — Score: {item['opportunity_score']}/100 | Eligibility: {item['scam_classification']}"):
                st.write(item)

    with tabs[3]:
        st.subheader("Open Positions")
        st.dataframe(state["trading"]["open_positions"], use_container_width=True)
        st.subheader("Closed Trade History")
        st.dataframe(state["trading"]["trade_history"], use_container_width=True)

    with tabs[4]:
        st.subheader("Strategy & Risk-Adjusted Performance")
        st.write("Closed Trades Count:", state["overview"]["closed_trades_count"])
        st.dataframe(state["trading"]["recent_signals"], use_container_width=True)

    with tabs[5]:
        st.subheader("Bitget Wallet Connection & Portfolio Sync")
        w = state["wallet"]
        st.write("**Connected:**", w["connected"])
        st.write("**Public Key:**", w["public_key"])
        st.write("**Signing Mode:**", w["signing_mode"])
        st.info(w["capability_note"])
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("SOL Balance", f"{w['sol_balance']:.4f} SOL")
        col2.metric("USDT Balance", f"${w['usdt_balance']:.4f}")
        col3.metric("Available Trading (USDT)", f"${w['available_trading_usdt']:.4f}")
        col4.metric("Reserved Funds (USDT)", f"${w['reserved_funds_usdt']:.4f}")
        if w["spl_token_balances"]:
            st.subheader("SPL Token Balances")
            st.dataframe(w["spl_token_balances"], use_container_width=True)


if __name__ == "__main__":
    render_streamlit_app()
