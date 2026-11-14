"""
SQLite persistence layer for the Solana AI Meme Coin Trading System.
Strictly separates LIVE trading records from PAPER and BACKTEST simulation records.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from database.models import (
    ExecutionEnvironment,
    PoolState,
    PositionRecord,
    TokenMetadata,
    TradingSignal,
    utc_now_iso,
)


class DatabaseManager:
    """Thread-safe SQLite database manager with strict Live vs. Testing separation."""

    def __init__(self, db_path: str = "database/solana_meme_trader.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize_schema(self) -> None:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS discovered_tokens (
                    mint_address TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    name TEXT NOT NULL,
                    decimals INTEGER NOT NULL,
                    mint_authority_active INTEGER,
                    freeze_authority_active INTEGER,
                    deployer_wallet TEXT,
                    top_10_holder_pct REAL,
                    holder_count INTEGER,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS discovered_pools (
                    pool_address TEXT PRIMARY KEY,
                    dex_venue TEXT NOT NULL,
                    base_mint TEXT NOT NULL,
                    quote_mint TEXT NOT NULL,
                    base_symbol TEXT NOT NULL,
                    quote_symbol TEXT NOT NULL,
                    price_usd REAL NOT NULL,
                    liquidity_usd REAL NOT NULL,
                    accessible_liquidity_usd REAL NOT NULL,
                    volume_1h_usd REAL NOT NULL,
                    volume_24h_usd REAL NOT NULL,
                    price_change_1h_pct REAL NOT NULL,
                    lp_locked_pct REAL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trading_signals (
                    signal_id TEXT PRIMARY KEY,
                    environment TEXT NOT NULL,
                    mint_address TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    pool_address TEXT NOT NULL,
                    dex_venue TEXT NOT NULL,
                    action TEXT NOT NULL,
                    strategy_family TEXT NOT NULL,
                    opportunity_score REAL NOT NULL,
                    opportunity_confidence REAL NOT NULL,
                    scam_risk_score REAL NOT NULL,
                    scam_classification TEXT NOT NULL,
                    trade_eligibility TEXT NOT NULL,
                    entry_price_usd REAL NOT NULL,
                    stop_loss_usd REAL NOT NULL,
                    take_profit_usd REAL NOT NULL,
                    expected_rr REAL NOT NULL,
                    recommended_position_usdt REAL NOT NULL,
                    ml_prob_positive REAL NOT NULL,
                    market_regime TEXT NOT NULL,
                    reasoning TEXT NOT NULL,
                    warnings_json TEXT NOT NULL,
                    component_scores_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS positions (
                    position_id TEXT PRIMARY KEY,
                    environment TEXT NOT NULL,
                    mint_address TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    pool_address TEXT NOT NULL,
                    dex_venue TEXT NOT NULL,
                    strategy_family TEXT NOT NULL,
                    entry_price_usd REAL NOT NULL,
                    current_price_usd REAL NOT NULL,
                    quantity_tokens REAL NOT NULL,
                    notional_entry_usdt REAL NOT NULL,
                    stop_loss_usd REAL NOT NULL,
                    take_profit_usd REAL NOT NULL,
                    fees_paid_usdt REAL NOT NULL,
                    slippage_bps REAL NOT NULL,
                    status TEXT NOT NULL,
                    exit_price_usd REAL,
                    realized_pnl_usdt REAL NOT NULL,
                    unrealized_pnl_usdt REAL NOT NULL,
                    exit_reason TEXT,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    tx_signature_entry TEXT,
                    tx_signature_exit TEXT
                );

                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    environment TEXT NOT NULL,
                    total_equity_usdt REAL NOT NULL,
                    available_cash_usdt REAL NOT NULL,
                    reserved_funds_usdt REAL NOT NULL,
                    realized_pnl_usdt REAL NOT NULL,
                    unrealized_pnl_usdt REAL NOT NULL,
                    drawdown_pct REAL NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS model_registry (
                    version_id TEXT PRIMARY KEY,
                    model_type TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    feature_names_json TEXT NOT NULL,
                    is_active INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    environment TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                """
            )

    def upsert_token(self, token: TokenMetadata) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO discovered_tokens (
                    mint_address, symbol, name, decimals,
                    mint_authority_active, freeze_authority_active,
                    deployer_wallet, top_10_holder_pct, holder_count, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mint_address) DO UPDATE SET
                    symbol=excluded.symbol,
                    name=excluded.name,
                    mint_authority_active=excluded.mint_authority_active,
                    freeze_authority_active=excluded.freeze_authority_active,
                    top_10_holder_pct=excluded.top_10_holder_pct,
                    holder_count=excluded.holder_count,
                    updated_at=excluded.updated_at
                """,
                (
                    token.mint_address,
                    token.symbol,
                    token.name,
                    token.decimals,
                    int(token.mint_authority_active) if token.mint_authority_active is not None else None,
                    int(token.freeze_authority_active) if token.freeze_authority_active is not None else None,
                    token.deployer_wallet,
                    token.top_10_holder_pct,
                    token.holder_count,
                    utc_now_iso(),
                ),
            )

    def upsert_pool(self, pool: PoolState) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO discovered_pools (
                    pool_address, dex_venue, base_mint, quote_mint,
                    base_symbol, quote_symbol, price_usd, liquidity_usd,
                    accessible_liquidity_usd, volume_1h_usd, volume_24h_usd,
                    price_change_1h_pct, lp_locked_pct, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pool_address) DO UPDATE SET
                    price_usd=excluded.price_usd,
                    liquidity_usd=excluded.liquidity_usd,
                    accessible_liquidity_usd=excluded.accessible_liquidity_usd,
                    volume_1h_usd=excluded.volume_1h_usd,
                    volume_24h_usd=excluded.volume_24h_usd,
                    price_change_1h_pct=excluded.price_change_1h_pct,
                    lp_locked_pct=excluded.lp_locked_pct,
                    updated_at=excluded.updated_at
                """,
                (
                    pool.pool_address,
                    pool.dex_venue,
                    pool.base_mint,
                    pool.quote_mint,
                    pool.base_symbol,
                    pool.quote_symbol,
                    pool.price_usd,
                    pool.liquidity_usd,
                    pool.accessible_liquidity_usd,
                    pool.volume_1h_usd,
                    pool.volume_24h_usd,
                    pool.price_change_1h_pct,
                    pool.lp_locked_pct,
                    utc_now_iso(),
                ),
            )

    def save_signal(self, signal: TradingSignal) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trading_signals (
                    signal_id, environment, mint_address, symbol, pool_address,
                    dex_venue, action, strategy_family, opportunity_score,
                    opportunity_confidence, scam_risk_score, scam_classification,
                    trade_eligibility, entry_price_usd, stop_loss_usd, take_profit_usd,
                    expected_rr, recommended_position_usdt, ml_prob_positive,
                    market_regime, reasoning, warnings_json, component_scores_json, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.signal_id,
                    signal.environment.value,
                    signal.mint_address,
                    signal.symbol,
                    signal.pool_address,
                    signal.dex_venue,
                    signal.action.value,
                    signal.strategy_family.value,
                    signal.opportunity_score,
                    signal.opportunity_confidence,
                    signal.scam_risk_score,
                    signal.scam_classification.value,
                    signal.trade_eligibility.value,
                    signal.entry_price_usd,
                    signal.stop_loss_usd,
                    signal.take_profit_usd,
                    signal.expected_rr,
                    signal.recommended_position_usdt,
                    signal.ml_prob_positive,
                    signal.market_regime,
                    signal.reasoning,
                    json.dumps(signal.warnings),
                    json.dumps(signal.component_scores),
                    signal.timestamp,
                ),
            )

    def save_position(self, pos: PositionRecord) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO positions (
                    position_id, environment, mint_address, symbol, pool_address,
                    dex_venue, strategy_family, entry_price_usd, current_price_usd,
                    quantity_tokens, notional_entry_usdt, stop_loss_usd, take_profit_usd,
                    fees_paid_usdt, slippage_bps, status, exit_price_usd,
                    realized_pnl_usdt, unrealized_pnl_usdt, exit_reason,
                    opened_at, closed_at, tx_signature_entry, tx_signature_exit
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pos.position_id,
                    pos.environment.value,
                    pos.mint_address,
                    pos.symbol,
                    pos.pool_address,
                    pos.dex_venue,
                    pos.strategy_family,
                    pos.entry_price_usd,
                    pos.current_price_usd,
                    pos.quantity_tokens,
                    pos.notional_entry_usdt,
                    pos.stop_loss_usd,
                    pos.take_profit_usd,
                    pos.fees_paid_usdt,
                    pos.slippage_bps,
                    pos.status,
                    pos.exit_price_usd,
                    pos.realized_pnl_usdt,
                    pos.unrealized_pnl_usdt,
                    pos.exit_reason,
                    pos.opened_at,
                    pos.closed_at,
                    pos.tx_signature_entry,
                    pos.tx_signature_exit,
                ),
            )

    def get_positions(
        self,
        environment: ExecutionEnvironment,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve positions strictly filtered by ExecutionEnvironment (never mixes LIVE and PAPER)."""
        query = "SELECT * FROM positions WHERE environment = ?"
        params: List[Any] = [environment.value]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY opened_at DESC"
        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_signals(
        self,
        environment: ExecutionEnvironment,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_signals WHERE environment = ? ORDER BY timestamp DESC LIMIT ?",
                (environment.value, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_discovered_pools(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM discovered_pools ORDER BY liquidity_usd DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def record_portfolio_snapshot(
        self,
        environment: ExecutionEnvironment,
        total_equity_usdt: float,
        available_cash_usdt: float,
        reserved_funds_usdt: float,
        realized_pnl_usdt: float,
        unrealized_pnl_usdt: float,
        drawdown_pct: float,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO portfolio_snapshots (
                    environment, total_equity_usdt, available_cash_usdt,
                    reserved_funds_usdt, realized_pnl_usdt, unrealized_pnl_usdt,
                    drawdown_pct, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    environment.value,
                    total_equity_usdt,
                    available_cash_usdt,
                    reserved_funds_usdt,
                    realized_pnl_usdt,
                    unrealized_pnl_usdt,
                    drawdown_pct,
                    utc_now_iso(),
                ),
            )

    def log_audit_event(
        self,
        environment: ExecutionEnvironment,
        event_type: str,
        severity: str,
        details: Dict[str, Any],
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_events (environment, event_type, severity, details_json, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (environment.value, event_type, severity, json.dumps(details), utc_now_iso()),
            )
