"""
Trading Bot Configuration — all thresholds and parameters.
Can be overridden via Streamlit Settings page (writes to SQLite).
"""
import os
import json
from dotenv import load_dotenv

load_dotenv()


def _secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


# ─── API KEYS ────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = _secret("ANTHROPIC_API_KEY")
POLYMARKET_API_KEY = _secret("POLYMARKET_API_KEY")
POLYMARKET_PRIVATE_KEY = _secret("POLYMARKET_PRIVATE_KEY")
TWITTER_BEARER_TOKEN = _secret("TWITTER_BEARER_TOKEN")
REDDIT_CLIENT_ID = _secret("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = _secret("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = _secret("REDDIT_USER_AGENT", "TradingBot/1.0")

# ─── DEFAULT PARAMETERS ─────────────────────────────────────────────────────

DEFAULTS = {
    # Scan Agent
    "min_liquidity": 1000,           # Min liquidity in $
    "min_volume_24h": 100,           # Min 24h volume in $
    "min_time_to_resolution_hours": 1,
    "max_time_to_resolution_days": 30,
    "price_move_threshold": 0.05,    # 5% move = flag
    "spread_threshold": 0.03,        # 3% spread = flag

    # Prediction Agent
    "confidence_threshold": 70,      # Min confidence to trade (0-100)

    # Risk Agent
    "kelly_fraction": 0.25,          # Fractional Kelly (25%)
    "max_bet_pct": 0.05,             # Max 5% of bankroll per trade
    "min_edge": 0.05,                # Min 5% edge to trade
    "initial_bankroll": 1000.0,      # Starting bankroll in $

    # Bot
    "scan_interval_seconds": 300,    # Scan every 5 minutes
    "dry_run": True,                 # Start in dry run mode
    "bot_status": "PAUSED",          # RUNNING / PAUSED / DRY RUN
}

DB_PATH = os.path.join(os.path.dirname(__file__), "db", "trading_bot.db")


def load_settings() -> dict:
    """Load settings from DB, falling back to defaults."""
    settings = DEFAULTS.copy()
    try:
        from trading_bot.db.database import get_settings
        db_settings = get_settings()
        settings.update(db_settings)
    except Exception:
        pass
    return settings


def save_settings(settings: dict):
    """Save settings to DB."""
    from trading_bot.db.database import save_settings as db_save
    db_save(settings)
