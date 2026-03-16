"""
Signal Agent — combines sentiment + price data to generate Buy/Sell/Hold signals.
"""
from stock_bot.config import load_settings
from stock_bot.db.database import insert_signal, log_event


def generate_signal(ticker: str, sentiment: dict, price_data: dict, technicals: dict) -> dict:
    """Generate a trading signal from sentiment + price data."""
    settings = load_settings()

    score = sentiment.get("sentiment_score", 0)
    confidence = sentiment.get("confidence", 0)
    catalyst = sentiment.get("catalyst_detected", False)
    trend = technicals.get("trend", "NEUTRAL")
    price = price_data.get("price", 0)

    bullish_threshold = settings.get("sentiment_bullish_threshold", 0.3)
    bearish_threshold = settings.get("sentiment_bearish_threshold", -0.3)
    min_confidence = settings.get("signal_confidence_min", 40)

    # Low confidence = HOLD
    if confidence < min_confidence:
        return _make_signal(ticker, "HOLD", "WEAK", score, price,
                            f"Low confidence ({confidence:.0f}%). Not enough data.")

    # Determine direction
    if score >= bullish_threshold:
        if trend == "BULLISH":
            strength = "STRONG"
            reasoning = (f"Bullish sentiment ({score:.2f}) confirmed by upward price trend. "
                         f"{'Catalyst detected. ' if catalyst else ''}"
                         f"RSI: {technicals.get('rsi_14', 50):.0f}.")
        elif trend == "BEARISH":
            strength = "MODERATE"
            reasoning = (f"Bullish sentiment ({score:.2f}) against bearish trend — contrarian signal. "
                         f"{'Catalyst detected. ' if catalyst else ''}"
                         f"Watch for trend reversal.")
        else:
            strength = "MODERATE"
            reasoning = f"Bullish sentiment ({score:.2f}) with neutral trend."

        direction = "BUY"

    elif score <= bearish_threshold:
        if trend == "BEARISH":
            strength = "STRONG"
            reasoning = (f"Bearish sentiment ({score:.2f}) confirmed by downward trend. "
                         f"{'Catalyst detected. ' if catalyst else ''}"
                         f"RSI: {technicals.get('rsi_14', 50):.0f}.")
        elif trend == "BULLISH":
            strength = "MODERATE"
            reasoning = (f"Bearish sentiment ({score:.2f}) against bullish trend — contrarian warning. "
                         f"Watch for momentum shift.")
        else:
            strength = "MODERATE"
            reasoning = f"Bearish sentiment ({score:.2f}) with neutral trend."

        direction = "SELL"

    else:
        direction = "HOLD"
        strength = "WEAK"
        reasoning = f"Neutral sentiment ({score:.2f}). No clear directional signal."

    # Catalyst boost
    if catalyst and strength == "MODERATE":
        strength = "STRONG"
        reasoning += " Catalyst boosts conviction."

    # RSI extremes
    rsi = technicals.get("rsi_14", 50)
    if rsi > 70 and direction == "BUY":
        strength = "WEAK"
        reasoning += f" Warning: RSI overbought ({rsi:.0f})."
    elif rsi < 30 and direction == "SELL":
        strength = "WEAK"
        reasoning += f" Warning: RSI oversold ({rsi:.0f})."

    return _make_signal(ticker, direction, strength, score, price, reasoning)


def _make_signal(ticker: str, direction: str, strength: str, score: float,
                 price: float, reasoning: str) -> dict:
    """Create and store a signal."""
    signal = {
        "ticker": ticker,
        "direction": direction,
        "strength": strength,
        "sentiment_score": score,
        "price_at_signal": price,
        "reasoning": reasoning,
    }

    signal_id = insert_signal(signal)
    signal["id"] = signal_id

    emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}.get(direction, "⚪")
    log_event("INFO", "signal_agent",
              f"{emoji} {ticker}: {direction} ({strength}) @ ${price:.2f} — {reasoning[:80]}")

    return signal
