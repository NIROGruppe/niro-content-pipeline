"""
Stock price data via yfinance (free, no API key needed).
"""
import concurrent.futures


def get_current_price(ticker: str) -> dict:
    """Get current price and key stats for a ticker."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info or {}
        fast = t.fast_info

        price = getattr(fast, "last_price", None) or info.get("currentPrice", 0)
        prev_close = getattr(fast, "previous_close", None) or info.get("previousClose", price)
        change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0

        return {
            "ticker": ticker,
            "price": round(price, 2) if price else 0,
            "change_pct": round(change_pct, 2),
            "volume": info.get("volume", 0),
            "market_cap": info.get("marketCap", 0),
            "pe_ratio": info.get("trailingPE", 0),
            "name": info.get("shortName", ticker),
            "sector": info.get("sector", ""),
        }
    except Exception as e:
        return {"ticker": ticker, "price": 0, "change_pct": 0, "error": str(e)}


def get_price_history(ticker: str, period: str = "1mo") -> list:
    """Get daily OHLCV price history."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period=period)
        result = []
        for idx, row in hist.iterrows():
            result.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(row["Open"], 2),
                "high": round(row["High"], 2),
                "low": round(row["Low"], 2),
                "close": round(row["Close"], 2),
                "volume": int(row["Volume"]),
            })
        return result
    except Exception:
        return []


def get_batch_prices(tickers: list) -> dict:
    """Fetch prices for multiple tickers in parallel."""
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(get_current_price, t): t for t in tickers}
        for future in concurrent.futures.as_completed(futures):
            ticker = futures[future]
            try:
                results[ticker] = future.result()
            except Exception:
                results[ticker] = {"ticker": ticker, "price": 0, "error": "Failed"}
    return results


def calculate_technicals(history: list) -> dict:
    """Calculate simple technical indicators from price history."""
    if len(history) < 5:
        return {"trend": "NEUTRAL", "sma_20": 0, "sma_50": 0, "rsi_14": 50}

    closes = [h["close"] for h in history]

    # SMAs
    sma_20 = sum(closes[-20:]) / min(len(closes), 20)
    sma_50 = sum(closes[-50:]) / min(len(closes), 50)

    # RSI 14
    gains, losses = [], []
    for i in range(1, min(15, len(closes))):
        diff = closes[-i] - closes[-i - 1]
        if diff > 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))

    avg_gain = sum(gains) / 14 if gains else 0
    avg_loss = sum(losses) / 14 if losses else 0.001
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    # Trend
    current = closes[-1]
    if current > sma_20 > sma_50:
        trend = "BULLISH"
    elif current < sma_20 < sma_50:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    return {
        "trend": trend,
        "sma_20": round(sma_20, 2),
        "sma_50": round(sma_50, 2),
        "rsi_14": round(rsi, 1),
        "current_price": closes[-1],
    }
