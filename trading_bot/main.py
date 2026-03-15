"""
Trading Bot Orchestrator — runs the full pipeline in a loop.
Can be started as background thread or standalone CLI process.
"""
import time
import threading
from datetime import datetime

from trading_bot.config import load_settings, save_settings
from trading_bot.db.database import log_event, get_open_trades, settle_trade, init_db
from trading_bot.agents.scan_agent import run_scan
from trading_bot.agents.research_agent import run_research
from trading_bot.agents.prediction_agent import predict
from trading_bot.agents.risk_agent import evaluate_and_trade
from trading_bot.agents.postmortem_agent import run_postmortem
from trading_bot.utils.market_api import get_market_price


_bot_thread = None
_bot_running = False


def run_pipeline_once():
    """Run the full pipeline once: scan → research → predict → risk → trade."""
    settings = load_settings()
    dry_run = settings.get("dry_run", True)

    log_event("INFO", "orchestrator", f"Pipeline run started ({'DRY RUN' if dry_run else 'LIVE'})")

    # Step 1: Scan
    flagged = run_scan()
    if not flagged:
        log_event("INFO", "orchestrator", "No flagged markets found. Pipeline complete.")
        return

    # Step 2: Research top 5 flagged markets (parallel)
    research_results = run_research(flagged[:5])

    # Step 3-4: Predict & Risk for each researched market
    for research in research_results:
        market_id = research.get("market_id")
        market = next((m for m in flagged if m.get("id") == market_id), None)
        if not market:
            continue

        # Step 3: Prediction
        prediction = predict(market, research)
        if prediction.get("error") or not prediction.get("activate"):
            continue

        # Step 4: Risk evaluation & trade
        evaluate_and_trade(prediction, market, dry_run=dry_run)

    # Step 5: Check settled trades & run postmortems
    check_settlements()

    log_event("INFO", "orchestrator", "Pipeline run complete.")


def check_settlements():
    """Check open trades for settlement and trigger postmortems on losses."""
    open_trades = get_open_trades()

    for trade in open_trades:
        market_id = trade.get("market_id")
        if not market_id:
            continue

        # Get current price
        prices = get_market_price(market_id)
        current_price = prices.get("price_yes", 0.5)

        # For dry run: simulate settlement if market ended
        # In production: check if market is resolved via API
        # For now, just update current price
        from trading_bot.db.database import update_trade_price
        if trade.get("position") == "YES":
            update_trade_price(trade["id"], current_price)
        else:
            update_trade_price(trade["id"], 1 - current_price)


def settle_trade_manually(trade_id: int, outcome: str):
    """Manually settle a trade (for dry run testing). outcome: 'won' or 'lost'."""
    from trading_bot.db.database import get_all_trades
    trades = get_all_trades()
    trade = next((t for t in trades if t["id"] == trade_id), None)
    if not trade:
        return

    if outcome == "won":
        # Profit = potential payout - cost
        pnl = trade["size"] * ((1 / trade["entry_price"]) - 1)
    else:
        pnl = -trade["size"]

    settle_trade(trade_id, round(pnl, 2), "settled")
    log_event("INFO", "orchestrator", f"Trade #{trade_id} settled: {outcome} (P&L: ${pnl:.2f})")

    # Trigger postmortem on loss
    if pnl < 0:
        trade["pnl"] = pnl
        trade["id"] = trade_id
        run_postmortem(trade)


def _bot_loop():
    """Background loop that runs the pipeline on interval."""
    global _bot_running
    while _bot_running:
        try:
            settings = load_settings()
            status = settings.get("bot_status", "PAUSED")

            if status == "RUNNING" or status == "DRY RUN":
                run_pipeline_once()
            else:
                log_event("DEBUG", "orchestrator", "Bot is paused. Skipping pipeline run.")

            interval = settings.get("scan_interval_seconds", 300)
            # Sleep in small increments so we can stop quickly
            for _ in range(int(interval)):
                if not _bot_running:
                    break
                time.sleep(1)

        except Exception as e:
            log_event("ERROR", "orchestrator", f"Pipeline error: {e}")
            time.sleep(60)


def start_bot():
    """Start the bot as a background thread."""
    global _bot_thread, _bot_running
    if _bot_running:
        return "Bot already running"

    _bot_running = True
    _bot_thread = threading.Thread(target=_bot_loop, daemon=True)
    _bot_thread.start()
    log_event("INFO", "orchestrator", "Bot started")
    return "Bot started"


def stop_bot():
    """Stop the bot."""
    global _bot_running
    _bot_running = False
    log_event("INFO", "orchestrator", "Bot stopped")
    return "Bot stopped"


def is_bot_running() -> bool:
    return _bot_running


if __name__ == "__main__":
    import sys
    init_db()

    mode = sys.argv[1] if len(sys.argv) > 1 else "dry"
    settings = load_settings()

    if mode == "live":
        settings["dry_run"] = False
        settings["bot_status"] = "RUNNING"
    else:
        settings["dry_run"] = True
        settings["bot_status"] = "DRY RUN"

    save_settings(settings)
    print(f"Starting bot in {'LIVE' if mode == 'live' else 'DRY RUN'} mode...")

    _bot_running = True
    _bot_loop()
