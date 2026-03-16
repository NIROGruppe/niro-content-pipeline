"""
Stock-specific sentiment analysis via Claude.
"""
import json
from stock_bot.config import ANTHROPIC_API_KEY


def analyze_stock_sentiment(ticker: str, company_name: str, sources: list) -> dict:
    """Analyze news/social sentiment for a stock ticker using Claude."""
    if not ANTHROPIC_API_KEY:
        return {"sentiment_score": 0, "confidence": 0, "error": "No API key"}

    if not sources or all(s.get("error") for s in sources):
        return {
            "sentiment_score": 0,
            "confidence": 0,
            "dominant_narrative": "No sources available",
            "bullish_signals": [],
            "bearish_signals": [],
            "source_quality": "none",
        }

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Format sources
    source_text = ""
    for i, s in enumerate(sources[:25]):
        if s.get("error"):
            continue
        source_text += f"\n[{i+1}] ({s.get('source', '?')}) {s.get('title', '')}\n{s.get('text', '')[:300]}\n"

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"""Analyze the sentiment of these news/social media posts about {ticker} ({company_name}).

SOURCES:
{source_text}

Determine the overall market sentiment. Consider:
1. Is the news bullish or bearish for the stock?
2. Are there specific catalysts mentioned (earnings, product launches, lawsuits, etc.)?
3. What is the general tone: fear, greed, uncertainty, excitement?
4. How reliable are these sources?

Respond with ONLY valid JSON:
{{
    "sentiment_score": <float -1.0 to 1.0, -1=very bearish, +1=very bullish>,
    "confidence": <float 0-100>,
    "dominant_narrative": "<1-2 sentence summary>",
    "bullish_signals": ["<signal 1>", "<signal 2>"],
    "bearish_signals": ["<signal 1>", "<signal 2>"],
    "source_quality": "<none/low/medium/high>",
    "catalyst_detected": <true/false>
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
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return {"sentiment_score": 0, "confidence": 0, "error": f"Parse failed: {raw[:100]}"}
