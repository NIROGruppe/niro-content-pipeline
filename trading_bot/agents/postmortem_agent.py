"""
Agent 5: Postmortem Agent — analyzes losses and updates knowledge base.
5 sub-agents: Data, Analysis, Pattern, Update, Calibration.
"""
import json
from trading_bot.config import ANTHROPIC_API_KEY, load_settings
from trading_bot.db.database import insert_postmortem, get_postmortems, get_all_trades, save_settings, log_event


def run_postmortem(trade: dict) -> dict:
    """Run full postmortem analysis on a losing trade."""
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not configured"}

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    log_event("INFO", "postmortem_agent", f"Running postmortem on trade #{trade.get('id')}: {trade.get('market_question', '')[:50]}...")

    # Sub-agent 1: Data Agent — collect all original inputs
    original_data = {
        "market_question": trade.get("market_question", ""),
        "position": trade.get("position"),
        "entry_price": trade.get("entry_price"),
        "true_prob": trade.get("true_prob"),
        "market_prob": trade.get("market_prob"),
        "edge": trade.get("edge"),
        "confidence": trade.get("confidence"),
        "size": trade.get("size"),
        "pnl": trade.get("pnl"),
    }

    # Sub-agent 2-5: Combined analysis via Claude
    past_postmortems = get_postmortems(limit=20)
    past_patterns = [pm.get("pattern_detected", "") for pm in past_postmortems if pm.get("pattern_detected")]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        messages=[{
            "role": "user",
            "content": f"""You are a trading postmortem analyst. A prediction market trade resulted in a loss.
Analyze what went wrong and suggest improvements.

LOSING TRADE:
{json.dumps(original_data, indent=2)}

PREVIOUS LOSS PATTERNS (from past postmortems):
{json.dumps(past_patterns[:10], indent=2) if past_patterns else "No previous losses"}

Perform these analyses:
1. ANALYSIS: What specifically went wrong? Was it bad research, bad timing, or bad luck?
2. PATTERN: Does this match any previous loss patterns? Is there a recurring issue?
3. CALIBRATION: Should any parameters be adjusted? (confidence threshold, min edge, kelly fraction, etc.)

Respond with ONLY valid JSON:
{{
    "what_went_wrong": "<detailed explanation>",
    "pattern_detected": "<pattern name or 'New pattern' or 'No pattern'>",
    "pattern_description": "<description of the pattern>",
    "parameter_changes": {{
        "<parameter_name>": {{
            "current": <value>,
            "suggested": <value>,
            "reason": "<why>"
        }}
    }},
    "lessons_learned": ["<lesson 1>", "<lesson 2>"],
    "severity": "<low/medium/high — how concerning is this loss>"
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
        analysis = {
            "what_went_wrong": raw[:500],
            "pattern_detected": "Parse error",
            "parameter_changes": {},
        }

    # Save postmortem to DB
    pm = {
        "trade_id": trade.get("id"),
        "market_question": trade.get("market_question", ""),
        "loss_amount": abs(trade.get("pnl", 0)),
        "what_went_wrong": analysis.get("what_went_wrong", ""),
        "pattern_detected": analysis.get("pattern_detected", ""),
        "parameter_changes": analysis.get("parameter_changes", {}),
        "original_data": original_data,
    }
    insert_postmortem(pm)

    # Sub-agent 5: Calibration — apply parameter changes if suggested
    param_changes = analysis.get("parameter_changes", {})
    if param_changes:
        settings = load_settings()
        applied = []
        for param, change in param_changes.items():
            if param in settings and change.get("suggested") is not None:
                old_val = settings[param]
                new_val = change["suggested"]
                # Safety: only apply conservative changes
                if param == "confidence_threshold" and isinstance(new_val, (int, float)):
                    new_val = max(50, min(95, new_val))  # Clamp 50-95
                elif param == "min_edge" and isinstance(new_val, (int, float)):
                    new_val = max(0.02, min(0.20, new_val))  # Clamp 2-20%
                elif param == "kelly_fraction" and isinstance(new_val, (int, float)):
                    new_val = max(0.1, min(0.5, new_val))  # Clamp 10-50%
                else:
                    continue  # Don't auto-adjust unknown params

                settings[param] = new_val
                applied.append(f"{param}: {old_val} → {new_val}")

        if applied:
            save_settings(settings)
            log_event("INFO", "postmortem_agent", f"Parameters adjusted: {', '.join(applied)}")

    log_event("INFO", "postmortem_agent",
              f"Postmortem complete: {analysis.get('pattern_detected', 'N/A')} — {analysis.get('what_went_wrong', '')[:100]}")

    return {**pm, "analysis": analysis}
