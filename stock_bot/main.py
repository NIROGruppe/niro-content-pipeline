"""
Stock Bot Orchestrator — scan news, generate signals, manage trades.
"""
import time
import threading

from stock_bot.config import load_settings, save_settings
from stock_bot.db.database import init_db, log_event, get_watchlist, get_open_trades
from stock_bot.agents.news_agent import scan_ticker
from stock_bot.agents.signal_agent import generate_signal
from stock_bot.agents.postmortem_agent import run_postmortem
from stock_bot.utils.price_api import get_current_price, get_price_history, calculate_technicals
from stock_bot.db.database import close_trade as db_close_trade

_bot_thread = None
_bot_running = False


def run_scan_once():
    """Run a full scan cycle: prices → news → signals."""
    settings = load_settings()
    log_event("INFO", "orchestrator", "Scan cycle started")

    # Get watchlist
    watchlist = get_watchlist()
    if not watchlist:
        # Load from settings default
        tickers_str = settings.get("watchlist", "AAPL,TSLA,NVDA")
        tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
        from stock_bot.db.database import add_ticker
        for t in tickers:
            add_ticker(t)
        watchlist = get_watchlist()

    tickers = [w["ticker"] for w in watchlist]
    log_event("INFO", "orchestrator", f"Scanning {len(tickers)} tickers: {', '.join(tickers[:5])}...")

    signals = []
    for ticker in tickers:
        try:
            # 1. Get price data
            price_data = get_current_price(ticker)
            if price_data.get("error"):
                log_event("WARN", "orchestrator", f"Price fetch failed for {ticker}: {price_data['error']}")
                continue

            # 2. Get price history for technicals
            history = get_price_history(ticker, "1mo")
            technicals = calculate_technicals(history)

            # 3. Scan news + sentiment
            name = price_data.get("name", ticker)
            sentiment = scan_ticker(ticker, name)

            # 4. Generate signal
            signal = generate_signal(ticker, sentiment, price_data, technicals)
            signals.append(signal)

        except Exception as e:
            log_event("ERROR", "orchestrator", f"Failed {ticker}: {e}")

    # Summary
    buys = sum(1 for s in signals if s.get("direction") == "BUY")
    sells = sum(1 for s in signals if s.get("direction") == "SELL")
    holds = sum(1 for s in signals if s.get("direction") == "HOLD")
    log_event("INFO", "orchestrator",
              f"Scan complete: {buys} BUY, {sells} SELL, {holds} HOLD signals")

    return signals


def close_trade_with_postmortem(trade_id: int, exit_price: float) -> dict:
    """Close a trade and trigger postmortem if loss."""
    trade = db_close_trade(trade_id, exit_price)
    if not trade:
        return {}

    log_event("INFO", "orchestrator",
              f"Trade #{trade_id} closed: {trade['ticker']} "
              f"P&L ${trade['pnl']:+,.2f}")

    if trade.get("pnl", 0) < 0:
        log_event("INFO", "orchestrator",
                  f"Loss detected on {trade['ticker']}. Running postmortem...")
        trade["id"] = trade_id
        run_postmortem(trade)

    return trade


def _bot_loop():
    """Background loop for continuous scanning."""
    global _bot_running
    while _bot_running:
        try:
            settings = load_settings()
            status = settings.get("bot_status", "PAUSED")

            if status == "RUNNING":
                run_scan_once()
            else:
                log_event("DEBUG", "orchestrator", "Bot paused. Skipping scan.")

            interval = settings.get("scan_interval_seconds", 600)
            for _ in range(int(interval)):
                if not _bot_running:
                    break
                time.sleep(1)

        except Exception as e:
            log_event("ERROR", "orchestrator", f"Scan error: {e}")
            time.sleep(60)


def start_bot():
    global _bot_thread, _bot_running
    if _bot_running:
        return "Bot already running"
    _bot_running = True
    _bot_thread = threading.Thread(target=_bot_loop, daemon=True)
    _bot_thread.start()
    log_event("INFO", "orchestrator", "Bot started")
    return "Bot started"


def stop_bot():
    global _bot_running
    _bot_running = False
    log_event("INFO", "orchestrator", "Bot stopped")
    return "Bot stopped"


def is_bot_running() -> bool:
    return _bot_running
