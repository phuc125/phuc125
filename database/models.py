"""
Normalized domain models and data structures shared across Live Trading and Testing.
Guarantees strict schema parity between live execution and backtest/paper simulation.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DexVenue(str, Enum):
    RAYDIUM = "raydium"
    ORCA = "orca"
    METEORA = "meteora"
    JUPITER = "jupiter"
    DEXSCREENER = "dexscreener"
    UNKNOWN = "unknown"


class RiskClassification(str, Enum):
    SAFE = "SAFE"
    MODERATE_RISK = "MODERATE_RISK"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL_SCAM = "CRITICAL_SCAM"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class TradeEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    REJECTED = "REJECTED"


class StrategyFamily(str, Enum):
    MOMENTUM_BREAKOUT = "MOMENTUM_BREAKOUT"
    TREND_FOLLOWING_PULLBACK = "TREND_FOLLOWING_PULLBACK"
    LIQUIDITY_SWEEP_REVERSAL = "LIQUIDITY_SWEEP_REVERSAL"
    SMART_MONEY_ACCUMULATION = "SMART_MONEY_ACCUMULATION"
    NO_TRADE = "NO_TRADE"


class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"


class ExecutionEnvironment(str, Enum):
    LIVE = "LIVE"
    PAPER = "PAPER"
    BACKTEST = "BACKTEST"


@dataclass
class TokenMetadata:
    """Normalized representation of a Solana SPL token."""
    mint_address: str
    symbol: str
    name: str
    decimals: int = 6
    created_at_ts: Optional[float] = None
    mint_authority_active: Optional[bool] = None
    freeze_authority_active: Optional[bool] = None
    deployer_wallet: Optional[str] = None
    top_10_holder_pct: Optional[float] = None
    holder_count: Optional[int] = None
    holder_growth_1h_pct: Optional[float] = None
    is_verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PoolState:
    """Normalized liquidity pool state across Raydium, Orca, Meteora, and DexScreener."""
    pool_address: str
    dex_venue: str
    base_mint: str
    quote_mint: str
    base_symbol: str
    quote_symbol: str
    price_usd: float
    price_quote: float
    liquidity_usd: float
    accessible_liquidity_usd: float
    volume_5m_usd: float
    volume_1h_usd: float
    volume_24h_usd: float
    buys_5m: int
    sells_5m: int
    buys_1h: int
    sells_1h: int
    price_change_5m_pct: float
    price_change_1h_pct: float
    price_change_24h_pct: float
    fdv_usd: Optional[float] = None
    market_cap_usd: Optional[float] = None
    lp_locked_pct: Optional[float] = None
    liquidity_change_1h_pct: float = 0.0
    fee_bps: int = 30
    created_at_ts: Optional[float] = None
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OHLCVBar:
    """Single historical or live candlestick bar."""
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume_usd: float
    buy_volume_usd: float = 0.0
    sell_volume_usd: float = 0.0
    liquidity_usd: float = 0.0


@dataclass
class WalletActivitySnapshot:
    """On-chain Smart Money and developer wallet activity for a token."""
    mint_address: str
    smart_money_net_inflow_usd: float = 0.0
    smart_money_buyers_count: int = 0
    smart_money_sellers_count: int = 0
    large_tx_count_1h: int = 0
    early_sniper_dump_detected: bool = False
    developer_sold_pct: float = 0.0
    suspicious_cluster_pct: float = 0.0
    wash_trading_ratio: float = 0.0
    data_available: bool = True
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


@dataclass
class SentimentSnapshot:
    """Social and community mention snapshot for a token."""
    mint_address: str
    mentions_1h: int = 0
    mentions_change_pct: float = 0.0
    positive_ratio: float = 0.5
    coordinated_promo_risk: float = 0.0
    organic_engagement_score: float = 50.0
    data_available: bool = False
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


@dataclass
class MarketSnapshot:
    """Complete normalized market state for a candidate token at a point in time."""
    token: TokenMetadata
    primary_pool: PoolState
    all_pools: List[PoolState] = field(default_factory=list)
    ohlcv_bars: List[OHLCVBar] = field(default_factory=list)
    wallet_activity: Optional[WalletActivitySnapshot] = None
    sentiment: Optional[SentimentSnapshot] = None
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


@dataclass
class TradingSignal:
    """Unified trading signal produced by shared_core/signal_engine.py."""
    signal_id: str
    mint_address: str
    symbol: str
    pool_address: str
    dex_venue: str
    environment: ExecutionEnvironment
    action: TradeAction
    strategy_family: StrategyFamily
    opportunity_score: float
    opportunity_confidence: float
    scam_risk_score: float
    scam_classification: RiskClassification
    trade_eligibility: TradeEligibility
    entry_price_usd: float
    stop_loss_usd: float
    take_profit_usd: float
    expected_rr: float
    recommended_position_usdt: float
    ml_prob_positive: float
    ml_expected_return_pct: float
    market_regime: str
    reasoning: str
    warnings: List[str] = field(default_factory=list)
    component_scores: Dict[str, float] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["environment"] = self.environment.value
        d["action"] = self.action.value
        d["strategy_family"] = self.strategy_family.value
        d["scam_classification"] = self.scam_classification.value
        d["trade_eligibility"] = self.trade_eligibility.value
        return d


@dataclass
class PositionRecord:
    """Open or closed trading position strictly tagged with its ExecutionEnvironment."""
    position_id: str
    environment: ExecutionEnvironment
    mint_address: str
    symbol: str
    pool_address: str
    dex_venue: str
    strategy_family: str
    entry_price_usd: float
    current_price_usd: float
    quantity_tokens: float
    notional_entry_usdt: float
    stop_loss_usd: float
    take_profit_usd: float
    fees_paid_usdt: float
    slippage_bps: float
    status: str = "OPEN"  # OPEN or CLOSED
    exit_price_usd: Optional[float] = None
    realized_pnl_usdt: float = 0.0
    unrealized_pnl_usdt: float = 0.0
    exit_reason: Optional[str] = None
    opened_at: str = field(default_factory=utc_now_iso)
    closed_at: Optional[str] = None
    tx_signature_entry: Optional[str] = None
    tx_signature_exit: Optional[str] = None

    def update_mark_price(self, mark_price_usd: float) -> None:
        self.current_price_usd = mark_price_usd
        if self.status == "OPEN":
            gross_val = self.quantity_tokens * mark_price_usd
            self.unrealized_pnl_usdt = gross_val - self.notional_entry_usdt - self.fees_paid_usdt

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["environment"] = self.environment.value
        return d
