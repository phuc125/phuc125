"""
Global system settings and environment variable loader.
Validates operating modes, database paths, and global safety flags.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional


class OperatingMode(str, Enum):
    """Supported execution modes for the dual-program architecture."""
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    MONITOR = "MONITOR"
    LIVE = "LIVE"


def load_dotenv_file(env_path: Optional[Path] = None) -> Dict[str, str]:
    """Parse a .env file into environment variables without external dependencies."""
    loaded: Dict[str, str] = {}
    path = env_path or Path(".env")
    if not path.exists():
        return loaded
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val
            loaded[key] = val
    return loaded


@dataclass(frozen=True)
class SystemSettings:
    """Validated system-level configuration."""
    operating_mode: OperatingMode = OperatingMode.PAPER
    live_trading_authorized: bool = False
    live_approval_token: str = ""
    emergency_stop_active: bool = False
    primary_quote_asset: str = "USDT"
    initial_simulated_capital_usdt: float = 10.0
    database_path: str = "database/solana_meme_trader.db"
    log_level: str = "INFO"
    audit_log_path: str = "logs/audit_trail.jsonl"
    usdt_mint_address: str = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
    usdc_mint_address: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    wsol_mint_address: str = "So11111111111111111111111111111111111111112"

    def validate(self) -> None:
        """Validate system configuration invariants."""
        if self.initial_simulated_capital_usdt <= 0:
            raise ValueError("initial_simulated_capital_usdt must be strictly positive.")
        if self.primary_quote_asset not in ("USDT", "USDC", "SOL"):
            raise ValueError(f"Unsupported primary_quote_asset: {self.primary_quote_asset}")
        if self.operating_mode == OperatingMode.LIVE:
            if not self.live_trading_authorized:
                raise PermissionError(
                    "LIVE mode requested but LIVE_TRADING_AUTHORIZED is False. "
                    "Live trading is locked by default."
                )
            if len(self.live_approval_token.strip()) < 12:
                raise PermissionError(
                    "LIVE mode requires a non-trivial LIVE_APPROVAL_TOKEN (>=12 chars)."
                )
            if self.emergency_stop_active:
                raise PermissionError(
                    "Cannot start LIVE mode while EMERGENCY_STOP_ACTIVE is True."
                )

    @classmethod
    def from_env(cls, env_path: Optional[Path] = None) -> "SystemSettings":
        """Load SystemSettings from environment variables."""
        load_dotenv_file(env_path)
        mode_str = os.getenv("OPERATING_MODE", "PAPER").upper().strip()
        try:
            mode = OperatingMode(mode_str)
        except ValueError:
            mode = OperatingMode.PAPER

        auth_str = os.getenv("LIVE_TRADING_AUTHORIZED", "false").lower().strip()
        estop_str = os.getenv("EMERGENCY_STOP_ACTIVE", "false").lower().strip()

        return cls(
            operating_mode=mode,
            live_trading_authorized=(auth_str in ("true", "1", "yes")),
            live_approval_token=os.getenv("LIVE_APPROVAL_TOKEN", ""),
            emergency_stop_active=(estop_str in ("true", "1", "yes")),
            primary_quote_asset=os.getenv("PRIMARY_QUOTE_ASSET", "USDT").upper().strip(),
            initial_simulated_capital_usdt=float(os.getenv("INITIAL_SIMULATED_CAPITAL_USDT", "10.0")),
            database_path=os.getenv("DATABASE_PATH", "database/solana_meme_trader.db"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper().strip(),
            audit_log_path=os.getenv("AUDIT_LOG_PATH", "logs/audit_trail.jsonl"),
        )


def configure_logging(log_level: str = "INFO", log_file: Optional[str] = "logs/system.log") -> logging.Logger:
    """Configure structured console and file logging."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger = logging.getLogger("solana_ai_meme_trader")
    logger.setLevel(level)
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger
