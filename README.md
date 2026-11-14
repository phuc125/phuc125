# Solana AI Meme Coin Trading System (`solana_ai_meme_trader`)

A modular, safety-first, dual-program AI trading and research system for Solana meme coins using a shared multi-agent core (`shared_core/`), multi-DEX scanning ([Raydium](https://raydium.io/), [Orca](https://www.orca.so/), [Meteora](https://meteora.ag/), [Jupiter Swap API](https://developers.jup.ag/docs/swap), [DexScreener API](https://docs.dexscreener.com/api/reference), and [Solana RPC](https://solana.com/docs)), [Bitget Wallet integration](https://web3.bitget.com/en/docs/connect/mainnet/solana), leak-free machine learning, realistic historical backtesting, real-time paper trading, and controlled live execution.

## 1. Architecture & Dual-Program Synchronization

Both executable entry points share 100% of their analytical, scoring, strategy, feature-engineering, and risk-management logic via `shared_core/`:

- **Program A (`live_main.py`)**: Live Market Monitoring (`--mode monitor`) and Controlled Live Trading (`--mode live`). Live Trading is **locked by default** and refuses to start unless `LIVE_TRADING_AUTHORIZED=true`, a valid `LIVE_APPROVAL_TOKEN` is supplied, `EMERGENCY_STOP_ACTIVE=false`, and the Bitget Wallet approval bridge is active.
- **Program B (`test_main.py`)**: Historical Backtesting (`--mode backtest`) and Real-Time Paper Trading (`--mode paper`) with `10.0 USDT` initial simulated capital. Program B has zero access to transaction-signing modules.

## 2. Installation & Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 3. Startup & Testing Commands

```bash
# Historical Backtesting (Program B)
python3 test_main.py --mode backtest

# Real-Time Paper Trading (Program B)
python3 test_main.py --mode paper --cycles 8

# Live Read-Only Market & Wallet Monitoring (Program A)
python3 live_main.py --mode monitor

# Live Trading (Program A - refuses execution until explicitly authorized in .env)
python3 live_main.py --mode live

# Streamlit Control Center Dashboard
streamlit run dashboard/app.py

# Run Full Regression & Mode-Parity Test Suite
python3 -m unittest discover -s tests -v
```

## 4. Bitget Wallet Security & Honest Limitations

- **No Unattended Private Keys**: Official [Bitget Wallet Solana documentation](https://web3.bitget.com/en/docs/connect/mainnet/solana) exposes interactive DApp signing (`window.bitkeep.solana`) and unsigned calldata APIs (`Order Mode` / `Instruction Mode`). It does not provide a headless cloud private-key signing API.
- **Isolated Signing Bridge**: `wallet/wallet_signer.py` validates program whitelists, notional caps, and Solana RPC `simulateTransaction` results before forwarding unsigned `VersionedTransaction` payloads to the local operator approval bridge. Private keys and seed phrases are strictly forbidden in `.env`, code, or logs (`WalletConfig.validate_no_secrets_in_env()`).
