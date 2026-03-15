"""
Claude-powered sentiment analysis for market research data.
"""
import json
from trading_bot.config import ANTHROPIC_API_KEY


def analyze_sentiment(market_question: str, sources: list) -> dict:
    """
    Analyze sentiment of collected sources relative to a prediction market question.
    Returns sentiment score, narrative summary, and divergence assessment.
    """
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not configured", "sentiment_score": 0, "divergence_score": 0}

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build source summaries
    source_texts = []
    for s in sources[:30]:  # Limit context
        if s.get("error"):
            continue
        text = s.get("text", "") or s.get("title", "") or s.get("summary", "")
        if text:
            source_texts.append(f"[{s.get('source', '?')}] {text[:300]}")

    if not source_texts:
        return {"sentiment_score": 0, "divergence_score": 0, "summary": "No sources found"}

    sources_block = "\n".join(source_texts)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"""Analyze the sentiment of these sources regarding this prediction market question.

MARKET QUESTION: {market_question}

SOURCES:
{sources_block}

Respond with ONLY valid JSON (no text before or after):
{{
    "sentiment_score": <float -1.0 to 1.0, negative=NO likely, positive=YES likely>,
    "confidence": <float 0-100, how confident the sources make you>,
    "dominant_narrative": "<1-2 sentence summary of what sources say>",
    "yes_signals": ["<signal 1>", "<signal 2>"],
    "no_signals": ["<signal 1>", "<signal 2>"],
    "source_quality": "<low/medium/high — how reliable and diverse are the sources>"
}}"""
        }]
    )

    raw = response.content[0].text.strip()
    try:
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return {"sentiment_score": 0, "divergence_score": 0, "summary": raw[:200], "error": "parse_failed"}
