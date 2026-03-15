"""
Agent 3: Prediction Agent — uses Claude with extended thinking to estimate true probability.
"""
import json
from trading_bot.config import ANTHROPIC_API_KEY, load_settings
from trading_bot.db.database import log_event


def predict(market: dict, research: dict) -> dict:
    """
    Use Claude with thinking to predict true probability.
    Returns prediction with edge, confidence, and recommended position.
    """
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not configured"}

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    settings = load_settings()

    question = market.get("question", "")
    market_prob = market.get("price_yes", 0.5)

    log_event("INFO", "prediction_agent", f"Predicting: {question[:60]}...")

    # Build context from research
    research_context = f"""
SENTIMENT ANALYSIS:
- Sentiment Score: {research.get('sentiment_score', 0)} (-1 = strong NO, +1 = strong YES)
- Confidence: {research.get('sentiment_confidence', 0)}%
- Dominant Narrative: {research.get('dominant_narrative', 'N/A')}
- YES Signals: {', '.join(research.get('yes_signals', []))}
- NO Signals: {', '.join(research.get('no_signals', []))}
- Source Quality: {research.get('source_quality', 'unknown')}
- Number of Sources: {research.get('num_sources', 0)}
- Market vs Sentiment Divergence: {research.get('divergence_score', 0)}
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        messages=[{
            "role": "user",
            "content": f"""You are an expert prediction market analyst. Analyze this market and estimate the TRUE probability.

MARKET: {question}
CURRENT MARKET PRICE (YES): {market_prob:.1%}
MARKET IMPLIED PROBABILITY: {market_prob:.1%}
LIQUIDITY: ${market.get('liquidity', 0):,.0f}
VOLUME 24H: ${market.get('volume_24h', 0):,.0f}
END DATE: {market.get('end_date', 'unknown')}

{research_context}

Think step by step. Consider:
1. Base rate / prior probability
2. What the research data tells us
3. Key factors that could change the outcome
4. Where the market might be wrong
5. Your confidence level in your estimate

Respond with ONLY valid JSON (no text before or after):
{{
    "true_probability": <float 0-100, your best estimate>,
    "confidence": <float 0-100, how confident you are in your estimate>,
    "reasoning": "<2-3 sentence summary of your reasoning>",
    "key_factors": ["<factor 1>", "<factor 2>", "<factor 3>"],
    "market_mispricing_reason": "<why you think the market is wrong, or 'Market is fairly priced'>"
}}"""
        }]
    )

    # Extract text response (skip thinking blocks)
    raw = ""
    for block in response.content:
        if block.type == "text":
            raw = block.text.strip()

    try:
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        prediction = json.loads(raw.strip())
    except json.JSONDecodeError:
        log_event("ERROR", "prediction_agent", f"Failed to parse prediction: {raw[:200]}")
        return {"error": "Failed to parse prediction", "raw": raw[:200]}

    true_prob = prediction.get("true_probability", 50) / 100
    confidence = prediction.get("confidence", 0)
    edge = true_prob - market_prob

    # Determine position
    if edge > 0:
        position = "YES"
    elif edge < 0:
        position = "NO"
        edge = abs(edge)  # Edge is always positive
        true_prob = 1 - true_prob  # Flip for NO position
        market_prob = 1 - market_prob
    else:
        position = None

    result = {
        "market_id": market.get("id"),
        "question": question,
        "true_prob": round(true_prob, 4),
        "market_prob": round(market.get("price_yes", 0.5), 4),
        "edge": round(edge, 4),
        "confidence": confidence,
        "position": position,
        "reasoning": prediction.get("reasoning", ""),
        "key_factors": prediction.get("key_factors", []),
        "mispricing_reason": prediction.get("market_mispricing_reason", ""),
        "activate": confidence >= settings.get("confidence_threshold", 70) and edge >= settings.get("min_edge", 0.05),
    }

    log_event("INFO", "prediction_agent",
              f"Prediction: {position} @ {true_prob:.1%} (edge={edge:.1%}, conf={confidence}%) — {'ACTIVATE' if result['activate'] else 'SKIP'}")

    return result
