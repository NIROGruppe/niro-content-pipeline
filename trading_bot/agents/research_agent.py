"""
Agent 2: Research Agent — scrapes Twitter, Reddit, RSS for each flagged market.
Runs sentiment analysis and compares to market odds.
"""
import concurrent.futures
from trading_bot.config import load_settings, TWITTER_BEARER_TOKEN, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
from trading_bot.db.database import log_event
from trading_bot.utils.scraper import search_twitter, search_reddit, search_rss
from trading_bot.utils.sentiment import analyze_sentiment


def research_market(market: dict) -> dict:
    """Research a single market: scrape sources, analyze sentiment."""
    question = market.get("question", "")
    market_id = market.get("id", "")

    # Extract keywords from question (first 5 meaningful words)
    keywords = " ".join(question.split()[:8])

    log_event("INFO", "research_agent", f"Researching: {question[:60]}...")

    # Scrape all sources in parallel
    sources = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        twitter_future = executor.submit(
            search_twitter, keywords, 15, TWITTER_BEARER_TOKEN
        )
        reddit_future = executor.submit(
            search_reddit, keywords, 15, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
        )
        rss_future = executor.submit(search_rss, keywords, 10)

        sources.extend(twitter_future.result())
        sources.extend(reddit_future.result())
        sources.extend(rss_future.result())

    # Filter out error entries for counting
    valid_sources = [s for s in sources if not s.get("error")]
    log_event("INFO", "research_agent", f"Collected {len(valid_sources)} sources for '{question[:40]}...'")

    # Sentiment analysis via Claude
    sentiment = analyze_sentiment(question, sources)

    # Calculate divergence: sentiment direction vs market price
    sentiment_score = sentiment.get("sentiment_score", 0)
    market_prob = market.get("price_yes", 0.5)

    # If sentiment says YES (positive) but market price is low → opportunity
    # If sentiment says NO (negative) but market price is high → opportunity
    sentiment_implied_prob = (sentiment_score + 1) / 2  # Convert -1..1 to 0..1
    divergence = abs(sentiment_implied_prob - market_prob)

    result = {
        "market_id": market_id,
        "question": question,
        "sentiment_score": sentiment_score,
        "sentiment_confidence": sentiment.get("confidence", 0),
        "dominant_narrative": sentiment.get("dominant_narrative", ""),
        "yes_signals": sentiment.get("yes_signals", []),
        "no_signals": sentiment.get("no_signals", []),
        "source_quality": sentiment.get("source_quality", "low"),
        "num_sources": len(valid_sources),
        "divergence_score": round(divergence, 3),
        "market_prob": market_prob,
        "sources": sources,
    }

    log_event("INFO", "research_agent",
              f"Sentiment={sentiment_score:.2f}, Divergence={divergence:.2f} for '{question[:40]}...'")

    return result


def run_research(flagged_markets: list) -> list:
    """Research all flagged markets in parallel."""
    results = []

    # Run research in parallel (max 5 at a time to avoid rate limits)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(research_market, m): m for m in flagged_markets}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                market = futures[future]
                log_event("ERROR", "research_agent", f"Failed: {market.get('question', '?')}: {e}")

    return results
