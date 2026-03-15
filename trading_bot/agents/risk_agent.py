"""
Agent 4: Risk Agent — Kelly Criterion sizing, risk checks, and trade execution.
"""
from datetime import datetime
from trading_bot.config import load_settings
from trading_bot.db.database import insert_trade, get_open_trades, log_event


def evaluate_and_trade(prediction: dict, market: dict, dry_run: bool = True) -> dict:
    """
    Apply Kelly Criterion, run risk checks, and place/block trade.
    Returns trade record.
    """
    settings = load_settings()

    edge = prediction.get("edge", 0)
    confidence = prediction.get("confidence", 0)
    position = prediction.get("position")
    true_prob = prediction.get("true_prob", 0.5)
    market_prob = prediction.get("market_prob", 0.5)

    # Get current bankroll
    bankroll = settings.get("initial_bankroll", 1000)
    open_trades = get_open_trades()
    total_open_exposure = sum(t.get("size", 0) for t in open_trades)
    available_bankroll = bankroll - total_open_exposure

    log_event("INFO", "risk_agent",
              f"Evaluating: {prediction.get('question', '')[:50]}... edge={edge:.1%} conf={confidence}")

    # ─── RISK CHECKS ─────────────────────────────────────────────────────

    block_reasons = []

    # Check 1: Min edge
    min_edge = settings.get("min_edge", 0.05)
    if edge < min_edge:
        block_reasons.append(f"Edge too low: {edge:.1%} < {min_edge:.1%}")

    # Check 2: Min confidence
    conf_threshold = settings.get("confidence_threshold", 70)
    if confidence < conf_threshold:
        block_reasons.append(f"Confidence too low: {confidence} < {conf_threshold}")

    # Check 3: No position determined
    if not position:
        block_reasons.append("No clear position (edge ≈ 0)")

    # Check 4: Available bankroll
    if available_bankroll <= 0:
        block_reasons.append(f"No available bankroll (${available_bankroll:.2f})")

    if block_reasons:
        trade = {
            "market_id": market.get("id"),
            "market_question": prediction.get("question", ""),
            "position": position or "NONE",
            "entry_price": market_prob,
            "current_price": market_prob,
            "size": 0,
            "edge": edge,
            "confidence": confidence,
            "true_prob": true_prob,
            "market_prob": market_prob,
            "kelly_size": 0,
            "status": "blocked",
            "pnl": 0,
            "placed_at": datetime.now().isoformat(),
            "dry_run": dry_run,
            "block_reason": " | ".join(block_reasons),
        }
        trade_id = insert_trade(trade)
        log_event("WARN", "risk_agent", f"BLOCKED: {' | '.join(block_reasons)}")
        return {**trade, "id": trade_id}

    # ─── KELLY CRITERION ─────────────────────────────────────────────────

    # Kelly fraction: f* = (bp - q) / b
    # where b = odds, p = true prob, q = 1-p
    if position == "YES":
        odds = (1 / market_prob) - 1  # decimal odds
        p = true_prob
    else:
        odds = (1 / (1 - market_prob)) - 1
        p = 1 - true_prob  # prob of NO winning

    q = 1 - p
    if odds <= 0:
        kelly_full = 0
    else:
        kelly_full = max(0, (odds * p - q) / odds)

    kelly_fraction = settings.get("kelly_fraction", 0.25)
    kelly_bet = kelly_full * kelly_fraction

    # Apply max bet constraint
    max_bet_pct = settings.get("max_bet_pct", 0.05)
    bet_pct = min(kelly_bet, max_bet_pct)
    bet_size = round(available_bankroll * bet_pct, 2)

    if bet_size < 1:
        trade = {
            "market_id": market.get("id"),
            "market_question": prediction.get("question", ""),
            "position": position,
            "entry_price": market_prob,
            "current_price": market_prob,
            "size": 0,
            "edge": edge,
            "confidence": confidence,
            "true_prob": true_prob,
            "market_prob": market_prob,
            "kelly_size": kelly_bet,
            "status": "blocked",
            "pnl": 0,
            "placed_at": datetime.now().isoformat(),
            "dry_run": dry_run,
            "block_reason": f"Bet size too small: ${bet_size:.2f}",
        }
        trade_id = insert_trade(trade)
        return {**trade, "id": trade_id}

    # ─── PLACE TRADE ─────────────────────────────────────────────────────

    entry_price = market_prob if position == "YES" else (1 - market_prob)

    trade = {
        "market_id": market.get("id"),
        "market_question": prediction.get("question", ""),
        "position": position,
        "entry_price": entry_price,
        "current_price": entry_price,
        "size": bet_size,
        "edge": edge,
        "confidence": confidence,
        "true_prob": true_prob,
        "market_prob": prediction.get("market_prob"),
        "kelly_size": round(kelly_bet, 4),
        "status": "open",
        "pnl": 0,
        "placed_at": datetime.now().isoformat(),
        "dry_run": dry_run,
        "block_reason": None,
    }

    if not dry_run:
        # TODO: On-chain execution via Web3
        log_event("INFO", "risk_agent", f"LIVE TRADE: {position} ${bet_size:.2f} on '{prediction.get('question', '')[:40]}...'")
    else:
        log_event("INFO", "risk_agent", f"DRY RUN: {position} ${bet_size:.2f} on '{prediction.get('question', '')[:40]}...'")

    trade_id = insert_trade(trade)
    return {**trade, "id": trade_id}
