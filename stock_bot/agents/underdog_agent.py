"""
Underdog Scanner Agent — discovers under-the-radar stocks with momentum.
Scans Reddit for trending tickers, checks unusual volume, filters small/mid cap.
"""
import re
import json
import concurrent.futures
from collections import Counter
from datetime import datetime

from stock_bot.config import ANTHROPIC_API_KEY
from stock_bot.db.database import insert_underdog, log_event


# Subreddits to scan for ticker mentions
REDDIT_SUBREDDITS = ["wallstreetbets", "stocks", "pennystocks", "smallstreetbets", "investing"]

# Regex to extract $TICKER mentions (1-5 uppercase letters after $)
TICKER_PATTERN = re.compile(r'\$([A-Z]{1,5})\b')

# Common words that look like tickers but aren't
TICKER_BLACKLIST = {
    "A", "I", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "IF", "IN",
    "IS", "IT", "ME", "MY", "NO", "OF", "OK", "ON", "OR", "SO", "TO", "UP",
    "US", "WE", "CEO", "IPO", "SEC", "FDA", "ETF", "ATH", "DD", "EPS",
    "GDP", "IMO", "LOL", "OMG", "USA", "LLC", "INC", "THE", "FOR", "ARE",
    "NOT", "ALL", "CAN", "HAD", "HAS", "HER", "HIM", "HIS", "HOW", "ITS",
    "LET", "MAY", "NEW", "NOW", "OLD", "OUR", "OUT", "OWN", "SAY", "SHE",
    "TOO", "USE", "WAY", "WHO", "BOY", "DID", "GET", "HAS", "HIM",
    "PUT", "RUN", "SAW", "TOP", "TEN", "BIG", "RED", "ANY", "DAY",
}

# Market cap filter range
MIN_MARKET_CAP = 500_000_000    # $500M
MAX_MARKET_CAP = 10_000_000_000  # $10B


def extract_tickers_from_text(text: str) -> list:
    """Extract $TICKER mentions from text."""
    found = TICKER_PATTERN.findall(text)
    return [t for t in found if t not in TICKER_BLACKLIST]


def scan_reddit_for_tickers() -> Counter:
    """Scan Reddit subreddits for trending ticker mentions."""
    from trading_bot.config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
    from trading_bot.utils.scraper import search_reddit, search_rss

    ticker_counts = Counter()
    all_posts = []

    log_event("INFO", "underdog_agent", "Scanning Reddit for ticker mentions...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for sub in REDDIT_SUBREDDITS:
            query = "stock OR stocks OR ticker OR $"
            future = executor.submit(
                search_reddit, query, 25,
                REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
            )
            futures[future] = sub

        # Also scan specific subreddit RSS feeds
        for sub in REDDIT_SUBREDDITS:
            rss_url = f"https://www.reddit.com/r/{sub}/hot.rss"
            future = executor.submit(search_rss, sub, [rss_url], 25)
            futures[future] = f"{sub}_rss"

        for future in concurrent.futures.as_completed(futures):
            sub = futures[future]
            try:
                posts = future.result()
                all_posts.extend(posts)
            except Exception as e:
                log_event("WARN", "underdog_agent", f"Failed scanning {sub}: {e}")

    # Extract tickers from all posts
    for post in all_posts:
        if post.get("error"):
            continue
        text = f"{post.get('title', '')} {post.get('text', '')} {post.get('summary', '')}"
        tickers = extract_tickers_from_text(text)
        for t in tickers:
            ticker_counts[t] += 1

    log_event("INFO", "underdog_agent",
              f"Found {len(ticker_counts)} unique tickers in {len(all_posts)} posts")

    return ticker_counts


def get_stock_data(ticker: str) -> dict:
    """Get price, volume, market cap data via yfinance."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info or {}
        fast = t.fast_info

        price = getattr(fast, "last_price", None) or info.get("currentPrice", 0)
        market_cap = info.get("marketCap", 0)
        volume = info.get("volume", 0)
        avg_volume = info.get("averageVolume", 0) or info.get("averageDailyVolume10Day", 0)
        name = info.get("shortName", ticker)

        # Calculate volume ratio
        volume_ratio = round(volume / avg_volume, 2) if avg_volume and avg_volume > 0 else 1.0

        return {
            "ticker": ticker,
            "name": name,
            "price": round(price, 2) if price else 0,
            "market_cap": market_cap or 0,
            "volume": volume or 0,
            "avg_volume": avg_volume or 0,
            "volume_ratio": volume_ratio,
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "error": None,
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


def filter_underdogs(ticker_counts: Counter, min_mentions: int = 2) -> list:
    """Filter tickers by market cap, volume, and minimum mentions."""
    # Only consider tickers with enough mentions
    candidates = [(t, c) for t, c in ticker_counts.items() if c >= min_mentions]
    candidates.sort(key=lambda x: x[1], reverse=True)

    # Take top 30 to avoid too many API calls
    candidates = candidates[:30]

    if not candidates:
        log_event("INFO", "underdog_agent", "No candidates with sufficient mentions")
        return []

    log_event("INFO", "underdog_agent",
              f"Checking {len(candidates)} candidates for market cap & volume...")

    # Fetch stock data in parallel
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(get_stock_data, ticker): (ticker, count)
            for ticker, count in candidates
        }
        for future in concurrent.futures.as_completed(futures):
            ticker, mention_count = futures[future]
            try:
                data = future.result()
                if data.get("error"):
                    continue

                market_cap = data.get("market_cap", 0)
                volume_ratio = data.get("volume_ratio", 1.0)

                # Filter: small/mid cap only
                if market_cap < MIN_MARKET_CAP or market_cap > MAX_MARKET_CAP:
                    continue

                # Calculate composite underdog score (0-100)
                # Factors: reddit mentions, volume ratio, market cap sweetspot
                mention_score = min(mention_count / 10.0, 1.0) * 30  # max 30 pts
                volume_score = min(volume_ratio / 5.0, 1.0) * 40     # max 40 pts (3-5x = high)
                # Mid-range market cap bonus (sweet spot around $2-5B)
                cap_billions = market_cap / 1e9
                if 2 <= cap_billions <= 5:
                    cap_score = 30
                elif 1 <= cap_billions <= 7:
                    cap_score = 20
                else:
                    cap_score = 10

                composite_score = round(mention_score + volume_score + cap_score, 1)

                results.append({
                    "ticker": ticker,
                    "name": data.get("name", ticker),
                    "market_cap": market_cap,
                    "price": data.get("price", 0),
                    "volume_ratio": volume_ratio,
                    "reddit_mentions": mention_count,
                    "score": composite_score,
                    "sector": data.get("sector", ""),
                    "industry": data.get("industry", ""),
                })
            except Exception as e:
                log_event("WARN", "underdog_agent", f"Error processing {ticker}: {e}")

    # Sort by score
    results.sort(key=lambda x: x["score"], reverse=True)
    log_event("INFO", "underdog_agent",
              f"Found {len(results)} underdogs passing filters")
    return results


def analyze_underdogs_with_claude(underdogs: list) -> list:
    """Use Claude to analyze top underdog candidates and add catalyst/reasoning."""
    if not ANTHROPIC_API_KEY or not underdogs:
        return underdogs

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Prepare summary of candidates
    candidates_text = ""
    for i, u in enumerate(underdogs[:10]):
        cap_b = u["market_cap"] / 1e9
        candidates_text += (
            f"\n{i+1}. {u['ticker']} ({u['name']})\n"
            f"   Market Cap: ${cap_b:.1f}B | Price: ${u['price']:.2f}\n"
            f"   Volume Ratio: {u['volume_ratio']:.1f}x normal | Reddit Mentions: {u['reddit_mentions']}\n"
            f"   Sector: {u.get('sector', 'N/A')} | Composite Score: {u['score']}\n"
        )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": f"""You are a stock analyst specializing in finding underdog stocks — small/mid-cap stocks flying under the radar but showing momentum signals.

Analyze these candidates that were found by scanning Reddit mentions and unusual volume:

{candidates_text}

For each stock, provide:
1. A sentiment score (-1.0 to 1.0) based on what you know about the company
2. A short catalyst/reason why this stock could be interesting (1-2 sentences)
3. Whether this is a genuine underdog opportunity or just noise

Respond with ONLY valid JSON array:
[
    {{
        "ticker": "<TICKER>",
        "sentiment_score": <float -1.0 to 1.0>,
        "catalyst": "<1-2 sentence catalyst/reason>",
        "is_genuine": <true/false>
    }},
    ...
]

Include ALL candidates from the list above."""
            }]
        )

        raw = ""
        for block in response.content:
            if block.type == "text":
                raw = block.text.strip()

        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        analysis = json.loads(raw.strip())

        # Merge Claude analysis into underdog data
        analysis_map = {a["ticker"]: a for a in analysis}
        for u in underdogs:
            if u["ticker"] in analysis_map:
                a = analysis_map[u["ticker"]]
                u["sentiment_score"] = a.get("sentiment_score", 0)
                u["catalyst"] = a.get("catalyst", "")
                u["is_genuine"] = a.get("is_genuine", True)
            else:
                u["sentiment_score"] = 0
                u["catalyst"] = ""
                u["is_genuine"] = True

        log_event("INFO", "underdog_agent", "Claude analysis complete")

    except Exception as e:
        log_event("ERROR", "underdog_agent", f"Claude analysis failed: {e}")
        for u in underdogs:
            u.setdefault("sentiment_score", 0)
            u.setdefault("catalyst", "")
            u.setdefault("is_genuine", True)

    return underdogs


def run_underdog_scan() -> list:
    """Full underdog scan pipeline: Reddit -> filter -> Claude analysis -> DB."""
    log_event("INFO", "underdog_agent", "=== Underdog scan started ===")

    # Step 1: Scan Reddit for ticker mentions
    ticker_counts = scan_reddit_for_tickers()

    if not ticker_counts:
        log_event("INFO", "underdog_agent", "No tickers found on Reddit")
        return []

    # Step 2: Filter by market cap, volume, score
    underdogs = filter_underdogs(ticker_counts, min_mentions=2)

    if not underdogs:
        log_event("INFO", "underdog_agent", "No stocks passed underdog filters")
        return []

    # Step 3: Claude analysis for catalyst and sentiment
    underdogs = analyze_underdogs_with_claude(underdogs)

    # Step 4: Store in database
    stored = 0
    for u in underdogs:
        if not u.get("is_genuine", True):
            continue
        try:
            insert_underdog({
                "ticker": u["ticker"],
                "name": u.get("name", u["ticker"]),
                "market_cap": u.get("market_cap", 0),
                "price": u.get("price", 0),
                "volume_ratio": u.get("volume_ratio", 1.0),
                "reddit_mentions": u.get("reddit_mentions", 0),
                "sentiment_score": u.get("sentiment_score", 0),
                "catalyst": u.get("catalyst", ""),
                "score": u.get("score", 0),
                "source": "reddit+volume",
            })
            stored += 1
        except Exception as e:
            log_event("ERROR", "underdog_agent", f"Failed to store {u['ticker']}: {e}")

    log_event("INFO", "underdog_agent",
              f"=== Underdog scan complete: {stored} stocks stored ===")

    return underdogs
