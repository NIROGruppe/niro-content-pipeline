"""
Agent 1: Scan Agent — scans prediction markets and flags opportunities.
"""
from trading_bot.config import load_settings
from trading_bot.db.database import upsert_markets, log_event
from trading_bot.utils.market_api import fetch_polymarket_markets


def run_scan() -> list:
    """Scan markets and flag opportunities. Returns list of flagged markets."""
    settings = load_settings()
    log_event("INFO", "scan_agent", "Starting market scan...")

    markets = fetch_polymarket_markets(
        min_liquidity=settings.get("min_liquidity", 10000),
        min_volume=settings.get("min_volume_24h", 1000),
        min_hours=settings.get("min_time_to_resolution_hours", 1),
        max_days=settings.get("max_time_to_resolution_days", 7),
    )

    log_event("INFO", "scan_agent", f"Fetched {len(markets)} markets after filtering")

    # Save to DB
    if markets:
        upsert_markets(markets)

    # Return only flagged markets
    flagged = [m for m in markets if m.get("flagged_reason")]
    log_event("INFO", "scan_agent", f"Flagged {len(flagged)} markets with opportunities")

    return flagged
