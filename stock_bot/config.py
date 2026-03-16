"""
Stock & News Bot Configuration.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


ANTHROPIC_API_KEY = _secret("ANTHROPIC_API_KEY")

DEFAULTS = {
    "watchlist": "AAPL,TSLA,NVDA,MSFT,AMZN,GOOGL,META,AMD,NFLX,SPY",
    "scan_interval_seconds": 600,
    "sentiment_bullish_threshold": 0.3,
    "sentiment_bearish_threshold": -0.3,
    "signal_confidence_min": 40,
    "bot_status": "PAUSED",
}

DB_PATH = os.path.join(os.path.dirname(__file__), "db", "stock_bot.db")


def load_settings() -> dict:
    settings = DEFAULTS.copy()
    try:
        from stock_bot.db.database import get_settings
        db_settings = get_settings()
        settings.update(db_settings)
    except Exception:
        pass
    return settings


def save_settings(settings: dict):
    from stock_bot.db.database import save_settings as db_save
    db_save(settings)
