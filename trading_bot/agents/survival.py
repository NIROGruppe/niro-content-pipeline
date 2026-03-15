"""
Survival Pressure System — adaptive risk based on bankroll health.
Start: $20, Goal: $1,000. Bot gets aggressive when winning, dies when losing.
"""
from trading_bot.config import load_settings
from trading_bot.db.database import log_event

STAGES = [
    {
        "name": "DEAD",
        "emoji": "💀",
        "color": "#FF0000",
        "min_ratio": 0.0,
        "max_ratio": 0.50,
        "kelly_fraction": 0,
        "max_bet_pct": 0,
        "min_edge": 1.0,
        "confidence_threshold": 100,
        "description": "Bankroll critically low. Bot auto-paused.",
    },
    {
        "name": "CRITICAL",
        "emoji": "🔴",
        "color": "#FF4444",
        "min_ratio": 0.50,
        "max_ratio": 0.75,
        "kelly_fraction": 0.10,
        "max_bet_pct": 0.02,
        "min_edge": 0.08,
        "confidence_threshold": 75,
        "description": "Last stand. Only highest-conviction trades.",
    },
    {
        "name": "SURVIVING",
        "emoji": "🟠",
        "color": "#FF8800",
        "min_ratio": 0.75,
        "max_ratio": 1.0,
        "kelly_fraction": 0.15,
        "max_bet_pct": 0.03,
        "min_edge": 0.05,
        "confidence_threshold": 60,
        "description": "Below starting capital. Protect what's left.",
    },
    {
        "name": "STABLE",
        "emoji": "🟡",
        "color": "#FFCC00",
        "min_ratio": 1.0,
        "max_ratio": 2.5,
        "kelly_fraction": 0.25,
        "max_bet_pct": 0.05,
        "min_edge": 0.03,
        "confidence_threshold": 45,
        "description": "Normal operation. Steady growth.",
    },
    {
        "name": "GROWING",
        "emoji": "🟢",
        "color": "#44BB44",
        "min_ratio": 2.5,
        "max_ratio": 10.0,
        "kelly_fraction": 0.35,
        "max_bet_pct": 0.08,
        "min_edge": 0.03,
        "confidence_threshold": 40,
        "description": "Momentum building. Compound gains.",
    },
    {
        "name": "THRIVING",
        "emoji": "🚀",
        "color": "#FFD700",
        "min_ratio": 10.0,
        "max_ratio": float("inf"),
        "kelly_fraction": 0.50,
        "max_bet_pct": 0.12,
        "min_edge": 0.02,
        "confidence_threshold": 35,
        "description": "Full aggression. Push to $1,000.",
    },
]


def get_current_bankroll() -> float:
    """Calculate current bankroll: starting + realized P&L from settled trades."""
    settings = load_settings()
    starting = settings.get("starting_bankroll", 20.0)

    try:
        import sqlite3
        from trading_bot.config import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE status = 'settled'"
        )
        total_pnl = cur.fetchone()[0]
        conn.close()
    except Exception:
        total_pnl = 0

    return round(starting + total_pnl, 2)


def get_survival_stage(current_bankroll: float, starting_bankroll: float) -> dict:
    """Get the survival stage based on bankroll ratio."""
    if starting_bankroll <= 0:
        return STAGES[0]

    ratio = current_bankroll / starting_bankroll

    for stage in STAGES:
        if stage["min_ratio"] <= ratio < stage["max_ratio"]:
            return stage

    return STAGES[-1]


def get_survival_status() -> dict:
    """Main entry point. Returns full survival status with adjusted parameters."""
    settings = load_settings()
    starting = settings.get("starting_bankroll", 20.0)
    goal = settings.get("bankroll_goal", 1000.0)

    current = get_current_bankroll()
    ratio = current / starting if starting > 0 else 0

    stage = get_survival_stage(current, starting)
    stage_index = next(i for i, s in enumerate(STAGES) if s["name"] == stage["name"])

    # Progress toward goal
    if goal > starting:
        progress = max(0, (current - starting) / (goal - starting) * 100)
    else:
        progress = 100

    # Next stage threshold
    next_stage_at = None
    if stage_index < len(STAGES) - 1:
        next_stage_at = round(STAGES[stage_index + 1]["min_ratio"] * starting, 2)

    return {
        "starting_bankroll": starting,
        "current_bankroll": current,
        "goal": goal,
        "ratio": round(ratio, 2),
        "stage_index": stage_index,
        "stage_name": stage["name"],
        "stage_emoji": stage["emoji"],
        "stage_color": stage["color"],
        "stage_description": stage["description"],
        "kelly_fraction": stage["kelly_fraction"],
        "max_bet_pct": stage["max_bet_pct"],
        "min_edge": stage["min_edge"],
        "confidence_threshold": stage["confidence_threshold"],
        "is_dead": stage["name"] == "DEAD",
        "progress_to_goal": round(progress, 1),
        "next_stage_at": next_stage_at,
        "stages": STAGES,
    }


def check_auto_pause() -> bool:
    """If stage is DEAD, auto-pause the bot. Returns True if paused."""
    status = get_survival_status()
    if status["is_dead"]:
        from trading_bot.db.database import save_settings as db_save
        db_save({"bot_status": "PAUSED"})
        log_event("CRITICAL", "survival",
                  f"BOT DEAD. Bankroll ${status['current_bankroll']:.2f} "
                  f"({status['ratio']:.0%} of start). Auto-paused.")
        return True
    return False
