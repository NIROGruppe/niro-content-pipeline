"""
Stock Bot SQLite database — tickers, signals, trades, postmortems.
"""
import sqlite3
import json
from datetime import datetime, date

from stock_bot.config import DB_PATH


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS watchlist (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            sector TEXT,
            added_at TEXT,
            active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS sentiment_scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            sentiment_score REAL,
            confidence REAL,
            dominant_narrative TEXT,
            bullish_signals TEXT,
            bearish_signals TEXT,
            source_count INTEGER,
            source_quality TEXT,
            scanned_at TEXT
        );

        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            direction TEXT,
            strength TEXT,
            sentiment_score REAL,
            price_at_signal REAL,
            reasoning TEXT,
            position_type TEXT DEFAULT '',
            hold_duration TEXT DEFAULT '',
            check_interval TEXT DEFAULT '',
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            direction TEXT,
            entry_price REAL,
            exit_price REAL,
            size REAL,
            status TEXT DEFAULT 'open',
            pnl REAL DEFAULT 0,
            signal_id INTEGER,
            notes TEXT,
            opened_at TEXT,
            closed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS postmortems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER,
            ticker TEXT,
            loss_amount REAL,
            what_went_wrong TEXT,
            pattern_detected TEXT,
            parameter_changes TEXT,
            lessons_learned TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS bot_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT,
            agent TEXT,
            message TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS underdogs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            name TEXT,
            market_cap REAL,
            price REAL,
            volume_ratio REAL,
            reddit_mentions INTEGER,
            sentiment_score REAL,
            catalyst TEXT,
            score REAL,
            source TEXT,
            discovered_at TEXT
        );
    """)
    # Migrate: add new columns if missing
    for table, col, coltype in [
        ("signals", "position_type", "TEXT DEFAULT ''"),
        ("signals", "hold_duration", "TEXT DEFAULT ''"),
        ("signals", "check_interval", "TEXT DEFAULT ''"),
        ("underdogs", "position_type", "TEXT DEFAULT ''"),
        ("underdogs", "hold_duration", "TEXT DEFAULT ''"),
        ("underdogs", "check_interval", "TEXT DEFAULT ''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
        except Exception:
            pass
    conn.commit()
    conn.close()


# ─── WATCHLIST ────────────────────────────────────────────────────────────────

def add_ticker(ticker: str, name: str = "", sector: str = ""):
    conn = _conn()
    conn.execute(
        "INSERT OR REPLACE INTO watchlist (ticker, name, sector, added_at, active) "
        "VALUES (?, ?, ?, ?, 1)",
        (ticker.upper(), name, sector, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def remove_ticker(ticker: str):
    conn = _conn()
    conn.execute("UPDATE watchlist SET active = 0 WHERE ticker = ?", (ticker.upper(),))
    conn.commit()
    conn.close()


def get_watchlist() -> list:
    conn = _conn()
    rows = conn.execute("SELECT * FROM watchlist WHERE active = 1 ORDER BY ticker").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── SENTIMENT ────────────────────────────────────────────────────────────────

def insert_sentiment(data: dict):
    conn = _conn()
    today = date.today().isoformat()
    ticker = data["ticker"]

    # Check if this ticker already has a sentiment scan today → update instead
    existing = conn.execute(
        "SELECT id FROM sentiment_scans WHERE ticker = ? AND scanned_at >= ?",
        (ticker, today)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE sentiment_scans SET sentiment_score=?, confidence=?, "
            "dominant_narrative=?, bullish_signals=?, bearish_signals=?, "
            "source_count=?, source_quality=?, scanned_at=? WHERE id=?",
            (
                data.get("sentiment_score", 0), data.get("confidence", 0),
                data.get("dominant_narrative", ""), json.dumps(data.get("bullish_signals", [])),
                json.dumps(data.get("bearish_signals", [])), data.get("source_count", 0),
                data.get("source_quality", "low"), datetime.now().isoformat(),
                existing["id"]
            )
        )
    else:
        conn.execute(
            "INSERT INTO sentiment_scans (ticker, sentiment_score, confidence, dominant_narrative, "
            "bullish_signals, bearish_signals, source_count, source_quality, scanned_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ticker, data.get("sentiment_score", 0), data.get("confidence", 0),
                data.get("dominant_narrative", ""), json.dumps(data.get("bullish_signals", [])),
                json.dumps(data.get("bearish_signals", [])), data.get("source_count", 0),
                data.get("source_quality", "low"), datetime.now().isoformat()
            )
        )

    conn.commit()
    conn.close()


def get_latest_sentiment(ticker: str) -> dict:
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM sentiment_scans WHERE ticker = ? ORDER BY id DESC LIMIT 1",
        (ticker,)
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_all_latest_sentiments() -> list:
    conn = _conn()
    rows = conn.execute("""
        SELECT s.* FROM sentiment_scans s
        INNER JOIN (SELECT ticker, MAX(id) as max_id FROM sentiment_scans GROUP BY ticker) m
        ON s.id = m.max_id ORDER BY s.ticker
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── SIGNALS ──────────────────────────────────────────────────────────────────

def insert_signal(data: dict) -> int:
    conn = _conn()
    today = date.today().isoformat()
    ticker = data["ticker"]

    # Check if this ticker already has a signal today → update instead
    existing = conn.execute(
        "SELECT id FROM signals WHERE ticker = ? AND created_at >= ?",
        (ticker, today)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE signals SET direction=?, strength=?, sentiment_score=?, "
            "price_at_signal=?, reasoning=?, position_type=?, hold_duration=?, "
            "check_interval=?, created_at=? WHERE id=?",
            (
                data["direction"], data.get("strength", "MODERATE"),
                data.get("sentiment_score", 0), data.get("price_at_signal", 0),
                data.get("reasoning", ""), data.get("position_type", ""),
                data.get("hold_duration", ""), data.get("check_interval", ""),
                datetime.now().isoformat(), existing["id"]
            )
        )
        conn.commit()
        signal_id = existing["id"]
    else:
        cur = conn.execute(
            "INSERT INTO signals (ticker, direction, strength, sentiment_score, price_at_signal, "
            "reasoning, position_type, hold_duration, check_interval, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ticker, data["direction"], data.get("strength", "MODERATE"),
                data.get("sentiment_score", 0), data.get("price_at_signal", 0),
                data.get("reasoning", ""), data.get("position_type", ""),
                data.get("hold_duration", ""), data.get("check_interval", ""),
                datetime.now().isoformat()
            )
        )
        conn.commit()
        signal_id = cur.lastrowid

    conn.close()
    return signal_id


def get_signals(limit: int = 50) -> list:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_signals_for_ticker(ticker: str, limit: int = 20) -> list:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM signals WHERE ticker = ? ORDER BY id DESC LIMIT ?",
        (ticker, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── TRADES ───────────────────────────────────────────────────────────────────

def insert_trade(data: dict) -> int:
    conn = _conn()
    opened_at = data.get("opened_at") or datetime.now().isoformat()
    status = data.get("status", "open")
    exit_price = data.get("exit_price")
    pnl = data.get("pnl", 0)
    closed_at = data.get("closed_at")

    cur = conn.execute(
        "INSERT INTO trades (ticker, direction, entry_price, exit_price, size, status, "
        "pnl, signal_id, notes, opened_at, closed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            data["ticker"], data["direction"], data["entry_price"],
            exit_price, data.get("size", 0), status, pnl,
            data.get("signal_id"), data.get("notes", ""),
            opened_at, closed_at
        )
    )
    conn.commit()
    trade_id = cur.lastrowid
    conn.close()
    return trade_id


def close_trade(trade_id: int, exit_price: float) -> dict:
    conn = _conn()
    row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    if not row:
        conn.close()
        return {}

    trade = dict(row)
    entry = trade["entry_price"]
    size = trade["size"]

    if trade["direction"] == "LONG":
        pnl = (exit_price - entry) * size
    else:
        pnl = (entry - exit_price) * size

    pnl = round(pnl, 2)
    conn.execute(
        "UPDATE trades SET exit_price = ?, pnl = ?, status = 'closed', closed_at = ? WHERE id = ?",
        (exit_price, pnl, datetime.now().isoformat(), trade_id)
    )
    conn.commit()
    conn.close()

    trade.update({"exit_price": exit_price, "pnl": pnl, "status": "closed"})
    return trade


def get_open_trades() -> list:
    conn = _conn()
    rows = conn.execute("SELECT * FROM trades WHERE status = 'open' ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_closed_trades() -> list:
    conn = _conn()
    rows = conn.execute("SELECT * FROM trades WHERE status = 'closed' ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_trades() -> list:
    conn = _conn()
    rows = conn.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── POSTMORTEMS ──────────────────────────────────────────────────────────────

def insert_postmortem(data: dict) -> int:
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO postmortems (trade_id, ticker, loss_amount, what_went_wrong, "
        "pattern_detected, parameter_changes, lessons_learned, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            data.get("trade_id"), data.get("ticker"), data.get("loss_amount", 0),
            data.get("what_went_wrong", ""), data.get("pattern_detected", ""),
            json.dumps(data.get("parameter_changes", {})),
            json.dumps(data.get("lessons_learned", [])),
            datetime.now().isoformat()
        )
    )
    conn.commit()
    pm_id = cur.lastrowid
    conn.close()
    return pm_id


def get_postmortems(limit: int = 50) -> list:
    conn = _conn()
    rows = conn.execute("SELECT * FROM postmortems ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_postmortems_for_ticker(ticker: str) -> list:
    """Get all postmortems for a specific ticker."""
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM postmortems WHERE ticker = ? ORDER BY id DESC",
        (ticker.upper(),)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_lessons(limit: int = 10) -> list:
    """Get recent lessons learned across all tickers for pattern awareness."""
    conn = _conn()
    rows = conn.execute(
        "SELECT ticker, pattern_detected, lessons_learned, what_went_wrong, loss_amount "
        "FROM postmortems ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── UNDERDOGS ────────────────────────────────────────────────────────────

def insert_underdog(data: dict) -> int:
    conn = _conn()
    today = date.today().isoformat()
    ticker = data["ticker"]

    # Check if this ticker was already discovered today → update instead
    existing = conn.execute(
        "SELECT id FROM underdogs WHERE ticker = ? AND discovered_at >= ?",
        (ticker, today)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE underdogs SET name=?, market_cap=?, price=?, volume_ratio=?, "
            "reddit_mentions=?, sentiment_score=?, catalyst=?, score=?, source=?, "
            "position_type=?, hold_duration=?, check_interval=?, discovered_at=? "
            "WHERE id=?",
            (
                data.get("name", ""), data.get("market_cap", 0),
                data.get("price", 0), data.get("volume_ratio", 1.0),
                data.get("reddit_mentions", 0), data.get("sentiment_score", 0),
                data.get("catalyst", ""), data.get("score", 0),
                data.get("source", ""), data.get("position_type", ""),
                data.get("hold_duration", ""), data.get("check_interval", ""),
                datetime.now().isoformat(), existing["id"]
            )
        )
        conn.commit()
        underdog_id = existing["id"]
    else:
        cur = conn.execute(
            "INSERT INTO underdogs (ticker, name, market_cap, price, volume_ratio, "
            "reddit_mentions, sentiment_score, catalyst, score, source, "
            "position_type, hold_duration, check_interval, discovered_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ticker, data.get("name", ""), data.get("market_cap", 0),
                data.get("price", 0), data.get("volume_ratio", 1.0),
                data.get("reddit_mentions", 0), data.get("sentiment_score", 0),
                data.get("catalyst", ""), data.get("score", 0),
                data.get("source", ""), data.get("position_type", ""),
                data.get("hold_duration", ""), data.get("check_interval", ""),
                datetime.now().isoformat()
            )
        )
        conn.commit()
        underdog_id = cur.lastrowid

    conn.close()
    return underdog_id


def get_underdogs(limit: int = 20) -> list:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM underdogs ORDER BY score DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_underdogs(days: int = 7) -> list:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM underdogs WHERE discovered_at >= datetime('now', ?) "
        "ORDER BY score DESC, id DESC",
        (f"-{days} days",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── SETTINGS ─────────────────────────────────────────────────────────────────

def get_settings() -> dict:
    conn = _conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    result = {}
    for r in rows:
        try:
            result[r["key"]] = json.loads(r["value"])
        except (json.JSONDecodeError, TypeError):
            result[r["key"]] = r["value"]
    return result


def save_settings(settings: dict):
    conn = _conn()
    now = datetime.now().isoformat()
    for key, value in settings.items():
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), now)
        )
    conn.commit()
    conn.close()


# ─── LOGS ─────────────────────────────────────────────────────────────────────

def log_event(level: str, agent: str, message: str):
    conn = _conn()
    conn.execute(
        "INSERT INTO bot_log (level, agent, message, created_at) VALUES (?, ?, ?, ?)",
        (level, agent, message, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_recent_logs(limit: int = 30) -> list:
    conn = _conn()
    rows = conn.execute("SELECT * FROM bot_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── STATS ────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    conn = _conn()
    total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    open_count = conn.execute("SELECT COUNT(*) FROM trades WHERE status = 'open'").fetchone()[0]
    closed = conn.execute("SELECT * FROM trades WHERE status = 'closed'").fetchall()

    wins = sum(1 for t in closed if t["pnl"] > 0)
    losses = sum(1 for t in closed if t["pnl"] < 0)
    total_pnl = sum(t["pnl"] for t in closed)

    today = date.today().isoformat()
    today_pnl = sum(t["pnl"] for t in closed if t["closed_at"] and t["closed_at"][:10] == today)

    win_rate = round(wins / max(wins + losses, 1) * 100)

    conn.close()
    return {
        "total_trades": total,
        "open_trades": open_count,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_pnl": round(total_pnl, 2),
        "today_pnl": round(today_pnl, 2),
    }
