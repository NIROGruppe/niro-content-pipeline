"""
Postmortem Agent — analyzes losing stock trades and suggests improvements.
"""
import json
from stock_bot.config import ANTHROPIC_API_KEY, load_settings, save_settings
from stock_bot.db.database import insert_postmortem, get_postmortems, get_latest_sentiment, log_event


def run_postmortem(trade: dict) -> dict:
    """Analyze a losing trade and extract lessons."""
    if not ANTHROPIC_API_KEY:
        return {"error": "No API key"}

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    ticker = trade.get("ticker", "?")
    settings = load_settings()

    # Get sentiment at time of trade
    sentiment = get_latest_sentiment(ticker)

    # Get past postmortems for pattern detection
    past = get_postmortems(20)
    past_patterns = [p.get("pattern_detected", "") for p in past if p.get("pattern_detected")]

    trade_context = f"""
TRADE DETAILS:
- Ticker: {ticker}
- Direction: {trade.get('direction', '?')}
- Entry Price: ${trade.get('entry_price', 0):.2f}
- Exit Price: ${trade.get('exit_price', 0):.2f}
- Size: {trade.get('size', 0)} shares
- P&L: ${trade.get('pnl', 0):.2f}
- Notes: {trade.get('notes', 'None')}

SENTIMENT AT ENTRY:
- Score: {sentiment.get('sentiment_score', 'N/A')}
- Confidence: {sentiment.get('confidence', 'N/A')}%
- Narrative: {sentiment.get('dominant_narrative', 'N/A')}

CURRENT SETTINGS:
- Bullish Threshold: {settings.get('sentiment_bullish_threshold', 0.3)}
- Bearish Threshold: {settings.get('sentiment_bearish_threshold', -0.3)}
- Min Signal Confidence: {settings.get('signal_confidence_min', 40)}

PAST LOSS PATTERNS:
{chr(10).join(f'- {p}' for p in past_patterns[-5:]) if past_patterns else '- No prior postmortems'}
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        messages=[{
            "role": "user",
            "content": f"""You are a stock trading postmortem analyst. A trade just lost money. Analyze it.

{trade_context}

Think carefully about what went wrong and how to prevent it. Consider:
1. Was the sentiment analysis wrong, or was the signal timing off?
2. Did a market-wide event cause the loss (not ticker-specific)?
3. Was the position size appropriate?
4. Are there patterns across multiple losses?

Respond with ONLY valid JSON:
{{
    "what_went_wrong": "<2-3 sentence analysis>",
    "pattern_detected": "<category: sentiment_miss / timing_error / market_event / position_sizing / insufficient_data / contrarian_trap>",
    "lessons_learned": ["<lesson 1>", "<lesson 2>", "<lesson 3>"],
    "parameter_changes": {{
        "<param_name>": {{
            "current": <current_value>,
            "suggested": <new_value>,
            "reason": "<why>"
        }}
    }}
}}"""
        }]
    )

    raw = ""
    for block in response.content:
        if block.type == "text":
            raw = block.text.strip()

    try:
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        analysis = json.loads(raw.strip())
    except json.JSONDecodeError:
        log_event("ERROR", "postmortem", f"Failed to parse: {raw[:100]}")
        analysis = {
            "what_went_wrong": "Analysis failed",
            "pattern_detected": "unknown",
            "lessons_learned": [],
            "parameter_changes": {},
        }

    # Store postmortem
    pm_data = {
        "trade_id": trade.get("id"),
        "ticker": ticker,
        "loss_amount": abs(trade.get("pnl", 0)),
        "what_went_wrong": analysis.get("what_went_wrong", ""),
        "pattern_detected": analysis.get("pattern_detected", ""),
        "parameter_changes": analysis.get("parameter_changes", {}),
        "lessons_learned": analysis.get("lessons_learned", []),
    }
    pm_id = insert_postmortem(pm_data)

    log_event("INFO", "postmortem",
              f"Postmortem #{pm_id} for {ticker}: {analysis.get('pattern_detected', '?')} — "
              f"{analysis.get('what_went_wrong', '')[:80]}")

    # Auto-apply safe parameter changes
    _apply_changes(analysis.get("parameter_changes", {}), settings)

    return {**pm_data, "id": pm_id}


def _apply_changes(changes: dict, settings: dict):
    """Auto-apply conservative parameter changes."""
    SAFE_RANGES = {
        "sentiment_bullish_threshold": (0.1, 0.7),
        "sentiment_bearish_threshold": (-0.7, -0.1),
        "signal_confidence_min": (20, 80),
    }

    updated = False
    for param, change in changes.items():
        if param not in SAFE_RANGES or not isinstance(change, dict):
            continue

        suggested = change.get("suggested")
        if suggested is None:
            continue

        lo, hi = SAFE_RANGES[param]
        clamped = max(lo, min(hi, float(suggested)))

        current = settings.get(param)
        if current is not None and clamped != current:
            settings[param] = clamped
            log_event("INFO", "postmortem",
                      f"Auto-adjusted {param}: {current} → {clamped} ({change.get('reason', '')})")
            updated = True

    if updated:
        save_settings(settings)
