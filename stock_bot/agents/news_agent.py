"""
News Agent — scans Twitter, Reddit, RSS for stock sentiment.
Reuses scrapers from trading_bot.
"""
import concurrent.futures
from trading_bot.config import TWITTER_BEARER_TOKEN, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
from trading_bot.utils.scraper import search_twitter, search_reddit, search_rss
from stock_bot.utils.sentiment import analyze_stock_sentiment
from stock_bot.db.database import insert_sentiment, log_event


# Stock-specific RSS feeds
STOCK_RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US",
    "https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en",
]


def scan_ticker(ticker: str, company_name: str = "") -> dict:
    """Scan news/social for a single ticker. Returns sentiment result."""
    query = f"${ticker}" if not company_name else f"${ticker} {company_name}"
    query_stock = f"{ticker} stock"

    log_event("INFO", "news_agent", f"Scanning {ticker}...")

    sources = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(search_twitter, query, 10, TWITTER_BEARER_TOKEN),
            executor.submit(search_reddit, query_stock, 10, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT),
            executor.submit(search_rss, query_stock, None, 10),
        ]

        # Stock-specific RSS feeds
        for feed_url in STOCK_RSS_FEEDS:
            url = feed_url.format(ticker=ticker)
            futures.append(executor.submit(search_rss, ticker, [url], 5))

        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                sources.extend(result)
            except Exception:
                pass

    valid_sources = [s for s in sources if not s.get("error")]
    log_event("INFO", "news_agent", f"Collected {len(valid_sources)} sources for {ticker}")

    # Sentiment analysis
    sentiment = analyze_stock_sentiment(ticker, company_name, sources)

    # Store in DB
    scan_data = {
        "ticker": ticker,
        "sentiment_score": sentiment.get("sentiment_score", 0),
        "confidence": sentiment.get("confidence", 0),
        "dominant_narrative": sentiment.get("dominant_narrative", ""),
        "bullish_signals": sentiment.get("bullish_signals", []),
        "bearish_signals": sentiment.get("bearish_signals", []),
        "source_count": len(valid_sources),
        "source_quality": sentiment.get("source_quality", "low"),
    }
    insert_sentiment(scan_data)

    log_event("INFO", "news_agent",
              f"{ticker}: sentiment={sentiment.get('sentiment_score', 0):.2f}, "
              f"conf={sentiment.get('confidence', 0):.0f}%, "
              f"sources={len(valid_sources)}")

    return scan_data


def scan_watchlist(tickers: list) -> list:
    """Scan all tickers in parallel (max 3 at a time to avoid rate limits)."""
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(scan_ticker, t): t for t in tickers}
        for future in concurrent.futures.as_completed(futures):
            ticker = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                log_event("ERROR", "news_agent", f"Failed to scan {ticker}: {e}")
    return results
