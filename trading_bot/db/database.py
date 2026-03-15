"""
SQLite database for trading bot — trades, postmortems, settings, market scans.
"""
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "trading_bot.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS markets (
            id TEXT PRIMARY KEY,
            question TEXT,
            slug TEXT,
            liquidity REAL DEFAULT 0,
            volume_24h REAL DEFAULT 0,
            price_yes REAL DEFAULT 0,
            price_no REAL DEFAULT 0,
            spread REAL DEFAULT 0,
            end_date TEXT,
            category TEXT,
            flagged_reason TEXT,
            price_change_1h REAL DEFAULT 0,
            scanned_at TEXT,
            status TEXT DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT,
            market_question TEXT,
            position TEXT,
            entry_price REAL,
            current_price REAL,
            size REAL,
            edge REAL,
            confidence REAL,
            true_prob REAL,
            market_prob REAL,
            kelly_size REAL,
            status TEXT DEFAULT 'open',
            pnl REAL DEFAULT 0,
            placed_at TEXT,
            settled_at TEXT,
            dry_run INTEGER DEFAULT 1,
            block_reason TEXT,
            FOREIGN KEY (market_id) REFERENCES markets(id)
        );

        CREATE TABLE IF NOT EXISTS postmortems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER,
            market_question TEXT,
            loss_amount REAL,
            what_went_wrong TEXT,
            pattern_detected TEXT,
            parameter_changes TEXT,
            original_data TEXT,
            created_at TEXT,
            FOREIGN KEY (trade_id) REFERENCES trades(id)
        );

        CREATE TABLE IF NOT EXISTS sentiment_cache (
            market_id TEXT PRIMARY KEY,
            sentiment_score REAL,
            source_summary TEXT,
            divergence_score REAL,
            sources_data TEXT,
            cached_at TEXT
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
            data TEXT,
            created_at TEXT
        );
    """)
    conn.commit()
    conn.close()


# ─── SETTINGS ────────────────────────────────────────────────────────────────

def get_settings() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    settings = {}
    for row in rows:
        try:
            settings[row["key"]] = json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            settings[row["key"]] = row["value"]
    return settings


def save_settings(settings: dict):
    conn = get_conn()
    now = datetime.now().isoformat()
    for key, value in settings.items():
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), now)
        )
    conn.commit()
    conn.close()


# ─── MARKETS ─────────────────────────────────────────────────────────────────

def upsert_markets(markets: list):
    conn = get_conn()
    now = datetime.now().isoformat()
    for m in markets:
        conn.execute("""
            INSERT OR REPLACE INTO markets
            (id, question, slug, liquidity, volume_24h, price_yes, price_no, spread,
             end_date, category, flagged_reason, price_change_1h, scanned_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            m["id"], m.get("question", ""), m.get("slug", ""),
            m.get("liquidity", 0), m.get("volume_24h", 0),
            m.get("price_yes", 0), m.get("price_no", 0), m.get("spread", 0),
            m.get("end_date", ""), m.get("category", ""),
            m.get("flagged_reason", ""), m.get("price_change_1h", 0),
            now, m.get("status", "active")
        ))
    conn.commit()
    conn.close()


def get_flagged_markets() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM markets WHERE flagged_reason != '' AND status = 'active' ORDER BY scanned_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_markets() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM markets WHERE status = 'active' ORDER BY scanned_at DESC LIMIT 200").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── TRADES ──────────────────────────────────────────────────────────────────

def insert_trade(trade: dict) -> int:
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO trades
        (market_id, market_question, position, entry_price, current_price, size,
         edge, confidence, true_prob, market_prob, kelly_size, status, pnl,
         placed_at, dry_run, block_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade.get("market_id"), trade.get("market_question"),
        trade.get("position"), trade.get("entry_price"), trade.get("current_price"),
        trade.get("size"), trade.get("edge"), trade.get("confidence"),
        trade.get("true_prob"), trade.get("market_prob"), trade.get("kelly_size"),
        trade.get("status", "open"), trade.get("pnl", 0),
        trade.get("placed_at", datetime.now().isoformat()),
        1 if trade.get("dry_run", True) else 0,
        trade.get("block_reason"),
    ))
    trade_id = cur.lastrowid
    conn.commit()
    conn.close()
    return trade_id


def get_open_trades() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM trades WHERE status = 'open' ORDER BY placed_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trade_history(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trades WHERE status != 'open' ORDER BY settled_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_trades() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM trades ORDER BY placed_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def settle_trade(trade_id: int, pnl: float, status: str = "settled"):
    conn = get_conn()
    conn.execute(
        "UPDATE trades SET status = ?, pnl = ?, settled_at = ? WHERE id = ?",
        (status, pnl, datetime.now().isoformat(), trade_id)
    )
    conn.commit()
    conn.close()


def update_trade_price(trade_id: int, current_price: float):
    conn = get_conn()
    conn.execute("UPDATE trades SET current_price = ? WHERE id = ?", (current_price, trade_id))
    conn.commit()
    conn.close()


# ─── POSTMORTEMS ─────────────────────────────────────────────────────────────

def insert_postmortem(pm: dict):
    conn = get_conn()
    conn.execute("""
        INSERT INTO postmortems
        (trade_id, market_question, loss_amount, what_went_wrong,
         pattern_detected, parameter_changes, original_data, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        pm.get("trade_id"), pm.get("market_question"), pm.get("loss_amount"),
        pm.get("what_went_wrong"), pm.get("pattern_detected"),
        json.dumps(pm.get("parameter_changes", {})),
        json.dumps(pm.get("original_data", {})),
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()


def get_postmortems(limit: int = 50) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM postmortems ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── BOT LOG ─────────────────────────────────────────────────────────────────

def log_event(level: str, agent: str, message: str, data: dict = None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO bot_log (level, agent, message, data, created_at) VALUES (?, ?, ?, ?, ?)",
        (level, agent, message, json.dumps(data or {}), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_recent_logs(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM bot_log ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── STATS ───────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    conn = get_conn()

    total_trades = conn.execute("SELECT COUNT(*) as c FROM trades WHERE status != 'blocked'").fetchone()["c"]
    wins = conn.execute("SELECT COUNT(*) as c FROM trades WHERE pnl > 0 AND status = 'settled'").fetchone()["c"]
    losses = conn.execute("SELECT COUNT(*) as c FROM trades WHERE pnl < 0 AND status = 'settled'").fetchone()["c"]
    settled = wins + losses
    total_pnl = conn.execute("SELECT COALESCE(SUM(pnl), 0) as s FROM trades WHERE status = 'settled'").fetchone()["s"]
    open_trades = conn.execute("SELECT COUNT(*) as c FROM trades WHERE status = 'open'").fetchone()["c"]

    # Today's P&L
    today = datetime.now().strftime("%Y-%m-%d")
    today_pnl = conn.execute(
        "SELECT COALESCE(SUM(pnl), 0) as s FROM trades WHERE status = 'settled' AND settled_at LIKE ?",
        (f"{today}%",)
    ).fetchone()["s"]

    conn.close()

    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / settled * 100, 1) if settled > 0 else 0,
        "total_pnl": round(total_pnl, 2),
        "today_pnl": round(today_pnl, 2),
        "open_trades": open_trades,
    }


# Initialize DB on import
init_db()
