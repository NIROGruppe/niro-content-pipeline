"""
Underdog Scanner Agent — discovers under-the-radar stocks with momentum.
Multi-source: volume screener (yfinance), RSS news scanning, Reddit fallback.
"""
import re
import json
import concurrent.futures
from collections import Counter
from datetime import datetime

from stock_bot.config import ANTHROPIC_API_KEY
from stock_bot.db.database import insert_underdog, log_event


# Regex to extract $TICKER mentions (1-5 uppercase letters after $)
TICKER_PATTERN = re.compile(r'\$([A-Z]{1,5})\b')
# Also match bare uppercase tickers in context like "buying PLTR" or "long SOFI"
BARE_TICKER_PATTERN = re.compile(r'\b(long|short|buying|selling|calls?|puts?|bullish|bearish)\s+([A-Z]{2,5})\b', re.IGNORECASE)

# Common words that look like tickers but aren't
TICKER_BLACKLIST = {
    "A", "I", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "IF", "IN",
    "IS", "IT", "ME", "MY", "NO", "OF", "OK", "ON", "OR", "SO", "TO", "UP",
    "US", "WE", "CEO", "IPO", "SEC", "FDA", "ETF", "ATH", "DD", "EPS",
    "GDP", "IMO", "LOL", "OMG", "USA", "LLC", "INC", "THE", "FOR", "ARE",
    "NOT", "ALL", "CAN", "HAD", "HAS", "HER", "HIM", "HIS", "HOW", "ITS",
    "LET", "MAY", "NEW", "NOW", "OLD", "OUR", "OUT", "OWN", "SAY", "SHE",
    "TOO", "USE", "WAY", "WHO", "BOY", "DID", "GET", "PUT", "RUN", "SAW",
    "TOP", "TEN", "BIG", "RED", "ANY", "DAY", "LONG", "SHORT", "CALL",
    "CALLS", "HOLD", "BUY", "SELL", "HIGH", "LOW", "YOLO", "MOON", "PUMP",
}

# Small/mid cap candidate universe — popular small/mid caps that could be underdogs
# These are scanned for unusual volume directly via yfinance
SCAN_UNIVERSE = [
    # High-growth small-mid caps
    "PLTR", "SOFI", "HOOD", "RKLB", "IONQ", "JOBY", "AFRM",
    "UPST", "DOCS", "OPEN", "LMND",
    # Small/Mid cap tech
    "ASTS", "LUNR", "RDW", "MNDY", "GTLB", "BRZE", "CFLT",
    "DUOL", "CWAN", "TOST", "GRAB", "SE",
    # Biotech / Healthcare
    "NNOX", "GDRX", "HIMS", "ACHR", "ARQT", "RXRX", "DNA",
    # Energy / Clean tech
    "PLUG", "FCEL", "BLNK", "CHPT", "QS", "ENPH", "SEDG", "RUN",
    # High retail interest
    "BB", "NOK", "SPCE", "LCID", "RIVN", "NIO", "XPEV", "LI",
    # Fintech / Crypto-adjacent
    "NU", "COIN", "MARA", "RIOT", "CLSK", "BITF", "HUT", "CORZ",
    # Small industrials / Materials / Space
    "MP", "LAC", "ALB", "IRDM", "BWXT",
    # Additional growth
    "PATH", "AI", "DDOG", "NET", "CRWD", "ZS", "BILL", "FRSH", "GLBE",
    # EU / German stocks
    "SAP", "SIE.DE", "IFX.DE", "DTE.DE", "BAS.DE",
    # Recent momentum names
    "SMCI", "ARM", "RDDT", "BIRK", "CART", "CAVA", "DJT",
    "OKLO", "VST", "VIAV", "SOUN", "GSAT",
]

# Market cap filter range
MIN_MARKET_CAP = 300_000_000     # $300M
MAX_MARKET_CAP = 15_000_000_000  # $15B


def extract_tickers_from_text(text: str) -> list:
    """Extract ticker mentions from text — both $TICKER and contextual bare tickers."""
    tickers = []
    # $TICKER pattern
    found = TICKER_PATTERN.findall(text)
    tickers.extend(t for t in found if t not in TICKER_BLACKLIST)
    # Contextual bare tickers ("buying PLTR", "long SOFI")
    bare = BARE_TICKER_PATTERN.findall(text)
    tickers.extend(t[1] for t in bare if t[1] not in TICKER_BLACKLIST)
    return tickers


def scan_volume_movers() -> list:
    """Scan universe for unusual volume via yfinance. Primary discovery method."""
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        log_event("ERROR", "underdog_agent", "yfinance not installed")
        return []

    log_event("INFO", "underdog_agent", f"Volume scanning {len(SCAN_UNIVERSE)} stocks...")

    results = []

    try:
        # Batch download — one request for all tickers (much faster than individual)
        data = yf.download(SCAN_UNIVERSE, period="5d", group_by="ticker", progress=False, threads=True)

        # Get info for tickers with unusual volume (only those that pass the filter)
        for ticker in SCAN_UNIVERSE:
            try:
                if len(SCAN_UNIVERSE) == 1:
                    ticker_data = data
                else:
                    ticker_data = data[ticker] if ticker in data.columns.get_level_values(0) else None

                if ticker_data is None or ticker_data.empty:
                    continue

                ticker_data = ticker_data.dropna(subset=["Close"])
                if len(ticker_data) < 2:
                    continue

                price = float(ticker_data["Close"].iloc[-1])
                volume = int(ticker_data["Volume"].iloc[-1])
                avg_volume = int(ticker_data["Volume"].iloc[:-1].mean()) if len(ticker_data) > 1 else 0

                if not price or not avg_volume:
                    continue

                volume_ratio = round(volume / avg_volume, 2) if avg_volume > 0 else 1.0

                if volume_ratio < 1.2:
                    continue

                results.append({
                    "ticker": ticker,
                    "name": ticker,
                    "price": round(price, 2),
                    "market_cap": 0,
                    "volume": volume,
                    "avg_volume": avg_volume,
                    "volume_ratio": volume_ratio,
                    "sector": "",
                    "industry": "",
                })
            except Exception:
                continue

        # Fetch market cap only for candidates that passed volume filter (few tickers)
        if results:
            log_event("INFO", "underdog_agent",
                      f"Fetching details for {len(results)} volume movers...")

            def enrich_ticker(stock):
                try:
                    t = yf.Ticker(stock["ticker"])
                    info = t.info or {}
                    market_cap = info.get("marketCap", 0)
                    if market_cap < MIN_MARKET_CAP or market_cap > MAX_MARKET_CAP:
                        return None
                    stock["market_cap"] = market_cap
                    stock["name"] = info.get("shortName", stock["ticker"])
                    stock["sector"] = info.get("sector", "")
                    stock["industry"] = info.get("industry", "")
                    return stock
                except Exception:
                    return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(enrich_ticker, s) for s in results]
                results = [f.result() for f in concurrent.futures.as_completed(futures)
                           if f.result() is not None]

    except Exception as e:
        log_event("ERROR", "underdog_agent", f"Volume scan error: {e}")
        return []

    log_event("INFO", "underdog_agent",
              f"Volume scan found {len(results)} stocks with unusual volume")
    return results


def scan_rss_for_tickers() -> Counter:
    """Scan financial RSS feeds for trending ticker mentions."""
    ticker_counts = Counter()

    try:
        from trading_bot.utils.scraper import search_rss
    except ImportError:
        log_event("WARN", "underdog_agent", "scraper import failed, skipping RSS")
        return ticker_counts

    rss_feeds = [
        "https://www.reddit.com/r/wallstreetbets/hot.rss",
        "https://www.reddit.com/r/stocks/hot.rss",
        "https://www.reddit.com/r/pennystocks/hot.rss",
        "https://www.reddit.com/r/smallstreetbets/hot.rss",
        "https://news.google.com/rss/search?q=stock+momentum+small+cap&hl=en-US",
        "https://news.google.com/rss/search?q=undervalued+stocks&hl=en-US",
    ]

    log_event("INFO", "underdog_agent", "Scanning RSS feeds for ticker mentions...")

    all_posts = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        for feed_url in rss_feeds:
            future = executor.submit(search_rss, "stocks", [feed_url], 25)
            futures[future] = feed_url

        for future in concurrent.futures.as_completed(futures):
            try:
                posts = future.result()
                all_posts.extend(posts)
            except Exception:
                pass

    for post in all_posts:
        if post.get("error"):
            continue
        text = f"{post.get('title', '')} {post.get('text', '')} {post.get('summary', '')}"
        tickers = extract_tickers_from_text(text)
        for t in tickers:
            ticker_counts[t] += 1

    log_event("INFO", "underdog_agent",
              f"RSS scan found {len(ticker_counts)} tickers in {len(all_posts)} posts")
    return ticker_counts


def score_underdogs(volume_movers: list, rss_mentions: Counter) -> list:
    """Score and rank underdog candidates from multiple sources."""
    scored = []

    for stock in volume_movers:
        ticker = stock["ticker"]
        volume_ratio = stock.get("volume_ratio", 1.0)
        market_cap = stock.get("market_cap", 0)
        mentions = rss_mentions.get(ticker, 0)

        # Volume score (max 50 pts) — primary signal
        volume_score = min(volume_ratio / 4.0, 1.0) * 50

        # Mention score (max 20 pts) — social confirmation
        mention_score = min(mentions / 5.0, 1.0) * 20

        # Market cap sweetspot score (max 30 pts)
        cap_billions = market_cap / 1e9
        if 1 <= cap_billions <= 5:
            cap_score = 30
        elif 0.5 <= cap_billions <= 8:
            cap_score = 20
        else:
            cap_score = 10

        composite_score = round(volume_score + mention_score + cap_score, 1)

        scored.append({
            **stock,
            "reddit_mentions": mentions,
            "score": composite_score,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def analyze_underdogs_with_claude(underdogs: list) -> list:
    """Use Claude to analyze top underdog candidates and add catalyst/reasoning."""
    if not ANTHROPIC_API_KEY or not underdogs:
        for u in underdogs:
            u.setdefault("sentiment_score", 0)
            u.setdefault("catalyst", "No API key — manual review needed")
            u.setdefault("is_genuine", True)
            u.setdefault("position_type", "LONG")
            u.setdefault("hold_duration", "")
            u.setdefault("check_interval", "")
        return underdogs

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    candidates_text = ""
    for i, u in enumerate(underdogs[:10]):
        cap_b = u["market_cap"] / 1e9
        candidates_text += (
            f"\n{i+1}. {u['ticker']} ({u['name']})\n"
            f"   Market Cap: ${cap_b:.1f}B | Price: ${u['price']:.2f}\n"
            f"   Volume Ratio: {u['volume_ratio']:.1f}x normal"
            + (f" | Reddit/RSS Mentions: {u['reddit_mentions']}" if u.get('reddit_mentions') else "")
            + "\n"
            f"   Sector: {u.get('sector', 'N/A')} | Score: {u['score']}\n"
        )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": f"""You are a stock analyst specializing in finding underdog stocks — small/mid-cap stocks flying under the radar but showing momentum signals.

These stocks were flagged for having unusual trading volume today:

{candidates_text}

For each stock, provide:
1. A sentiment score (-1.0 to 1.0) based on current outlook
2. A short catalyst/reason why this stock could be interesting (1-2 sentences)
3. Whether this is a genuine underdog opportunity or just noise
4. Position type: "LONG" or "SHORT"
5. Suggested hold duration (e.g. "1-2 Wochen", "3-5 Tage", "Intraday")
6. Price check interval (e.g. "2x taeglich", "Alle 4 Stunden", "Stuendlich")

Respond with ONLY valid JSON array:
[
    {{
        "ticker": "<TICKER>",
        "sentiment_score": <float -1.0 to 1.0>,
        "catalyst": "<1-2 sentence catalyst/reason>",
        "is_genuine": <true/false>,
        "position_type": "LONG or SHORT",
        "hold_duration": "<suggested hold duration>",
        "check_interval": "<price check frequency>"
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

        analysis_map = {a["ticker"]: a for a in analysis}
        for u in underdogs:
            if u["ticker"] in analysis_map:
                a = analysis_map[u["ticker"]]
                u["sentiment_score"] = a.get("sentiment_score", 0)
                u["catalyst"] = a.get("catalyst", "")
                u["is_genuine"] = a.get("is_genuine", True)
                u["position_type"] = a.get("position_type", "LONG")
                u["hold_duration"] = a.get("hold_duration", "")
                u["check_interval"] = a.get("check_interval", "")
            else:
                u["sentiment_score"] = 0
                u["catalyst"] = ""
                u["is_genuine"] = True
                u["position_type"] = "LONG"
                u["hold_duration"] = ""
                u["check_interval"] = ""

        log_event("INFO", "underdog_agent", "Claude analysis complete")

    except Exception as e:
        log_event("ERROR", "underdog_agent", f"Claude analysis failed: {e}")
        for u in underdogs:
            u.setdefault("sentiment_score", 0)
            u.setdefault("catalyst", "")
            u.setdefault("is_genuine", True)
            u.setdefault("position_type", "LONG")
            u.setdefault("hold_duration", "")
            u.setdefault("check_interval", "")

    return underdogs


def run_underdog_scan() -> list:
    """Full underdog scan pipeline: volume screen + RSS → score → Claude → DB."""
    log_event("INFO", "underdog_agent", "=== Underdog scan started ===")

    # Step 1: Volume screener (primary — always works)
    volume_movers = scan_volume_movers()

    # Step 2: RSS scan for social mentions (secondary — best effort)
    rss_mentions = Counter()
    try:
        rss_mentions = scan_rss_for_tickers()
    except Exception as e:
        log_event("WARN", "underdog_agent", f"RSS scan failed: {e}")

    if not volume_movers:
        log_event("INFO", "underdog_agent", "No stocks with unusual volume found")
        return []

    # Step 3: Score and rank
    underdogs = score_underdogs(volume_movers, rss_mentions)

    # Keep top 15
    underdogs = underdogs[:15]

    log_event("INFO", "underdog_agent",
              f"Scored {len(underdogs)} underdogs, top: {', '.join(u['ticker'] for u in underdogs[:5])}")

    if not underdogs:
        log_event("INFO", "underdog_agent", "No stocks passed underdog filters")
        return []

    # Step 4: Claude analysis for catalyst and sentiment
    underdogs = analyze_underdogs_with_claude(underdogs)

    # Step 5: Store in database
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
                "source": "volume+rss",
                "position_type": u.get("position_type", ""),
                "hold_duration": u.get("hold_duration", ""),
                "check_interval": u.get("check_interval", ""),
            })
            stored += 1
        except Exception as e:
            log_event("ERROR", "underdog_agent", f"Failed to store {u['ticker']}: {e}")

    log_event("INFO", "underdog_agent",
              f"=== Underdog scan complete: {stored} stocks stored ===")

    return underdogs
