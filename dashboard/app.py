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
if __name__ == "__main__":
    render_streamlit_app()
