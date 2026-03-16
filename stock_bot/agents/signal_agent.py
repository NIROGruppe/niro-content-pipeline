"""
Signal Agent — combines sentiment + price data to generate Buy/Sell/Hold signals.
Includes position type (LONG/SHORT), hold duration, and check interval.
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
    rsi = technicals.get("rsi_14", 50)
    price = price_data.get("price", 0)

    bullish_threshold = settings.get("sentiment_bullish_threshold", 0.3)
    bearish_threshold = settings.get("sentiment_bearish_threshold", -0.3)
    min_confidence = settings.get("signal_confidence_min", 40)

    # Low confidence = HOLD
    if confidence < min_confidence:
        return _make_signal(ticker, "HOLD", "WEAK", score, price,
                            f"Low confidence ({confidence:.0f}%). Not enough data.",
                            position_type="—",
                            hold_duration="—",
                            check_interval="—")

    # Determine direction and strength
    if score >= bullish_threshold:
        direction = "BUY"
        if trend == "BULLISH":
            strength = "STRONG"
            reasoning = (f"Bullish sentiment ({score:.2f}) confirmed by upward price trend. "
                         f"{'Catalyst detected. ' if catalyst else ''}"
                         f"RSI: {rsi:.0f}.")
        elif trend == "BEARISH":
            strength = "MODERATE"
            reasoning = (f"Bullish sentiment ({score:.2f}) against bearish trend — contrarian signal. "
                         f"{'Catalyst detected. ' if catalyst else ''}"
                         f"Watch for trend reversal.")
        else:
            strength = "MODERATE"
            reasoning = f"Bullish sentiment ({score:.2f}) with neutral trend."

    elif score <= bearish_threshold:
        direction = "SELL"
        if trend == "BEARISH":
            strength = "STRONG"
            reasoning = (f"Bearish sentiment ({score:.2f}) confirmed by downward trend. "
                         f"{'Catalyst detected. ' if catalyst else ''}"
                         f"RSI: {rsi:.0f}.")
        elif trend == "BULLISH":
            strength = "MODERATE"
            reasoning = (f"Bearish sentiment ({score:.2f}) against bullish trend — contrarian warning. "
                         f"Watch for momentum shift.")
        else:
            strength = "MODERATE"
            reasoning = f"Bearish sentiment ({score:.2f}) with neutral trend."

    else:
        direction = "HOLD"
        strength = "WEAK"
        reasoning = f"Neutral sentiment ({score:.2f}). No clear directional signal."

    # Catalyst boost
    if catalyst and strength == "MODERATE":
        strength = "STRONG"
        reasoning += " Catalyst boosts conviction."

    # RSI extremes
    if rsi > 70 and direction == "BUY":
        strength = "WEAK"
        reasoning += f" Warning: RSI overbought ({rsi:.0f})."
    elif rsi < 30 and direction == "SELL":
        strength = "WEAK"
        reasoning += f" Warning: RSI oversold ({rsi:.0f})."

    # Determine position type, hold duration, check interval
    position_type = _get_position_type(direction, score, trend, rsi)
    hold_duration = _get_hold_duration(strength, score, trend, catalyst, rsi)
    check_interval = _get_check_interval(strength, catalyst, rsi)

    return _make_signal(ticker, direction, strength, score, price, reasoning,
                        position_type=position_type,
                        hold_duration=hold_duration,
                        check_interval=check_interval)


def _get_position_type(direction: str, score: float, trend: str, rsi: float) -> str:
    """Determine LONG or SHORT position type."""
    if direction == "BUY":
        return "LONG"
    elif direction == "SELL":
        return "SHORT"
    else:
        # HOLD — suggest based on current trend
        if trend == "BULLISH" and rsi < 60:
            return "LONG (halten)"
        elif trend == "BEARISH" and rsi > 40:
            return "SHORT (halten)"
        return "Abwarten"


def _get_hold_duration(strength: str, score: float, trend: str,
                       catalyst: bool, rsi: float) -> str:
    """Estimate hold duration based on signal strength and context."""
    abs_score = abs(score)

    # Strong signal + trend alignment = longer hold
    if strength == "STRONG" and abs_score > 0.5:
        if catalyst:
            return "2–4 Wochen (Catalyst-Play)"
        return "1–3 Wochen"

    if strength == "STRONG":
        return "1–2 Wochen"

    if strength == "MODERATE":
        if catalyst:
            return "3–7 Tage (Catalyst abwarten)"
        return "3–5 Tage"

    # WEAK
    if 30 < rsi < 70:
        return "1–2 Tage (Scalp/Daytrade)"

    # RSI extreme
    return "Intraday / max 1 Tag"


def _get_check_interval(strength: str, catalyst: bool, rsi: float) -> str:
    """Recommend price check frequency."""
    if strength == "STRONG":
        if catalyst:
            return "Alle 2–4 Stunden"
        return "2x täglich (Morgen + Abend)"

    if strength == "MODERATE":
        if catalyst:
            return "Alle 1–2 Stunden"
        return "3x täglich"

    # WEAK or extreme RSI
    if rsi > 70 or rsi < 30:
        return "Stündlich (RSI extrem)"

    return "Alle 30 Min (kurzfristiges Signal)"


def _make_signal(ticker: str, direction: str, strength: str, score: float,
                 price: float, reasoning: str, position_type: str = "",
                 hold_duration: str = "", check_interval: str = "") -> dict:
    """Create and store a signal."""
    signal = {
        "ticker": ticker,
        "direction": direction,
        "strength": strength,
        "sentiment_score": score,
        "price_at_signal": price,
        "reasoning": reasoning,
        "position_type": position_type,
        "hold_duration": hold_duration,
        "check_interval": check_interval,
    }

    signal_id = insert_signal(signal)
    signal["id"] = signal_id

    emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}.get(direction, "⚪")
    pos = f" [{position_type}]" if position_type and position_type != "—" else ""
    log_event("INFO", "signal_agent",
              f"{emoji} {ticker}: {direction} ({strength}){pos} @ ${price:.2f} — {reasoning[:80]}")

    return signal
