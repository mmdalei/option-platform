"""
config.py - application settings.

Everything is read from environment variables (or from a `.env` file placed next to
this file), so nothing machine-specific lives in the code. The defaults suit a
single-user local setup: SQLite, in-process cache, live TSETMC data.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else default


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


def _str(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in os.getenv(name, default).split(",") if p.strip())


@dataclass(frozen=True)
class Settings:
    # -- Data source ------------------------------------------------------
    source: str = _str("OPTIONS_SOURCE", "live").lower()          # "live" | "demo"
    tsetmc_base_url: str = _str("TSETMC_BASE_URL", "https://cdn.tsetmc.com").rstrip("/")
    tsetmc_market: int = _int("TSETMC_MARKET", 0)                 # 0 = Bourse + FaraBourse, 1 = Bourse, 2 = FaraBourse
    poll_interval: float = _float("POLL_INTERVAL_SECONDS", 5.0)
    request_timeout: float = _float("REQUEST_TIMEOUT_SECONDS", 10.0)

    # -- Storage ----------------------------------------------------------
    # PostgreSQL example: postgresql+psycopg://user:pass@localhost:5432/options
    # (then: pip install "psycopg[binary]")
    database_url: str = _str("DATABASE_URL", "sqlite:///./options.db")
    redis_url: str = _str("REDIS_URL", "")                        # empty -> in-process cache
    cache_ttl: int = _int("CACHE_TTL_SECONDS", 120)
    history_interval: float = _float("HISTORY_INTERVAL_SECONDS", 60.0)

    # -- Pricing model ----------------------------------------------------
    # These are assumptions, not market facts: set them to what you consider appropriate.
    risk_free_rate: float = _float("RISK_FREE_RATE", 0.30)        # annual, 0.30 = 30 %
    dividend_yield: float = _float("DIVIDEND_YIELD", 0.0)
    day_count: int = _int("DAY_COUNT", 365)
    iv_price_source: str = _str("IV_PRICE_SOURCE", "mid").lower()                  # mid | last | close
    underlying_price_source: str = _str("UNDERLYING_PRICE_SOURCE", "last").lower() # last | close
    atm_band: float = _float("ATM_BAND", 0.01)                    # |K/S - 1| below this -> ATM

    # -- Web --------------------------------------------------------------
    cors_origins: tuple[str, ...] = _csv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")


settings = Settings()
