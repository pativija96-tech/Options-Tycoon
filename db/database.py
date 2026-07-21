"""
Options Tycoon - Database connection and schema initialization.

Supports:
- SQLite (local development, default when no DATABASE_URL set)
- PostgreSQL (production on Railway, when DATABASE_URL is set)

The database is auto-created/migrated on first launch via init_db().
"""

import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

# Check if we should use PostgreSQL (Railway sets DATABASE_URL)
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith("postgres")

if USE_POSTGRES:
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        # psycopg2 not installed — fall back to SQLite
        USE_POSTGRES = False


def get_db_path() -> str:
    """Return the path to the SQLite database file (local dev only)."""
    project_root = Path(__file__).parent.parent
    return str(project_root / "options_tycoon.db")


def get_connection():
    """
    Return a database connection.
    
    - PostgreSQL in production (Railway)
    - SQLite in local development
    
    Both return connections with row_factory/cursor that support dict-like access.
    """
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return PostgresConnectionWrapper(conn)
    else:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


def init_db(db_path: str | None = None) -> None:
    """
    Initialize the database schema, creating all tables if they don't exist.
    Idempotent — safe to call on every startup.
    """
    if USE_POSTGRES:
        _init_postgres()
    else:
        _init_sqlite(db_path)


def _init_sqlite(db_path: str | None = None):
    """Initialize SQLite schema."""
    if db_path:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    else:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.executescript(_SQLITE_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def _init_postgres():
    """Initialize PostgreSQL schema."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(_POSTGRES_SCHEMA)
    finally:
        conn.close()


class PostgresConnectionWrapper:
    """
    Wraps psycopg2 connection to provide sqlite3.Row-like dict access.
    This allows the same code to work with both SQLite and PostgreSQL.
    """
    
    def __init__(self, conn):
        self._conn = conn
    
    def execute(self, sql, params=None):
        """Execute SQL and return a cursor wrapper with dict-like rows."""
        # Convert SQLite ? placeholders to PostgreSQL %s
        sql = sql.replace("?", "%s")
        # Convert SQLite-specific syntax
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        sql = sql.replace("datetime('now')", "NOW()")
        
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return PostgresCursorWrapper(cur)
    
    def executescript(self, sql):
        """Execute multiple SQL statements."""
        cur = self._conn.cursor()
        cur.execute(sql)
        self._conn.commit()
    
    def commit(self):
        self._conn.commit()
    
    def close(self):
        self._conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


class PostgresCursorWrapper:
    """Wraps psycopg2 cursor to match sqlite3 cursor interface."""
    
    def __init__(self, cursor):
        self._cursor = cursor
    
    def fetchone(self):
        return self._cursor.fetchone()
    
    def fetchall(self):
        return self._cursor.fetchall()
    
    @property
    def lastrowid(self):
        # For PostgreSQL, we need RETURNING clause — handled at call site
        # This is a fallback
        try:
            self._cursor.execute("SELECT lastval()")
            row = self._cursor.fetchone()
            return row['lastval'] if row else None
        except Exception:
            return None


# ===========================================================================
# SCHEMA — SQLite version
# ===========================================================================

_SQLITE_SCHEMA = """
-- Core profile table
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    balance REAL NOT NULL DEFAULT 10000.0,
    mode TEXT NOT NULL DEFAULT 'sim_only',
    is_locked INTEGER NOT NULL DEFAULT 0,
    penalty_until TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    disclaimer_acknowledged INTEGER NOT NULL DEFAULT 0,
    payment_status TEXT NOT NULL DEFAULT 'unpaid'
);

-- Strategy sub-profiles (max 5 per profile)
CREATE TABLE IF NOT EXISTS strategy_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    name TEXT NOT NULL,
    balance REAL NOT NULL DEFAULT 10000.0,
    is_locked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Trade records (simulated)
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    strategy_profile_id INTEGER REFERENCES strategy_profiles(id),
    ticker TEXT NOT NULL,
    strategy_type TEXT NOT NULL,
    legs TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    slippage_cost REAL NOT NULL DEFAULT 0,
    position_size REAL NOT NULL,
    position_pct REAL NOT NULL,
    max_unrealized_pnl REAL,
    realized_pnl REAL,
    status TEXT NOT NULL DEFAULT 'open',
    outcome_tag TEXT,
    opened_at TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at TEXT,
    expiration_date TEXT NOT NULL,
    is_revenge_trade INTEGER NOT NULL DEFAULT 0,
    is_overconfidence_trap INTEGER NOT NULL DEFAULT 0,
    is_impulse_early_exit INTEGER NOT NULL DEFAULT 0,
    pre_trade_discipline REAL,
    pre_trade_patience REAL,
    pre_trade_sizing REAL,
    pre_trade_emotional REAL,
    risk_gate_shown INTEGER NOT NULL DEFAULT 0,
    risk_gate_proceeded INTEGER,
    iv_crush_warning_shown INTEGER NOT NULL DEFAULT 0,
    confirmation_proceeded INTEGER,
    journal_note TEXT,
    chain_opened_at TEXT,
    trade_executed_at TEXT
);

-- Real trade journal entries (parallel mode)
CREATE TABLE IF NOT EXISTS real_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    ticker TEXT NOT NULL,
    option_type TEXT NOT NULL,
    strike_price REAL NOT NULL,
    position_size REAL NOT NULL,
    entry_time TEXT NOT NULL,
    exit_time TEXT,
    outcome_amount REAL,
    behavioral_state TEXT,
    is_revenge_trade INTEGER NOT NULL DEFAULT 0,
    is_overconfidence_trap INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Behavioral metrics (cached, recomputed on each trade)
CREATE TABLE IF NOT EXISTS behavioral_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    source TEXT NOT NULL DEFAULT 'sim',
    discipline_rating REAL,
    patience_score REAL,
    sizing_consistency REAL,
    emotional_reactivity REAL,
    loss_disposition_ratio REAL,
    loss_disposition_flagged INTEGER NOT NULL DEFAULT 0,
    current_streak INTEGER NOT NULL DEFAULT 0,
    longest_streak INTEGER NOT NULL DEFAULT 0,
    total_trades INTEGER NOT NULL DEFAULT 0,
    phase TEXT NOT NULL DEFAULT 'A',
    diagnostic_summary TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Telemetry log
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    trade_id INTEGER REFERENCES trades(id),
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    discipline_rating REAL,
    patience_score REAL,
    sizing_consistency REAL,
    emotional_reactivity REAL,
    risk_gate_warnings TEXT,
    trader_decision TEXT NOT NULL
);

-- Earnings calendar (static data)
CREATE TABLE IF NOT EXISTS earnings_calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    earnings_date TEXT NOT NULL,
    source TEXT DEFAULT 'manual'
);

-- Cached external market data
CREATE TABLE IF NOT EXISTS market_data_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    data_date TEXT NOT NULL,
    data_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ticker, data_date, data_type)
);

-- Monthly P&L tracking
CREATE TABLE IF NOT EXISTS monthly_pnl (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    year_month TEXT NOT NULL,
    realized_pnl REAL NOT NULL DEFAULT 0,
    trade_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(profile_id, year_month)
);

-- Users table (Google Sign-In)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    google_id TEXT UNIQUE,
    picture TEXT,
    is_premium INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_login TEXT
);

-- Upload history (per user, tracks each CSV upload and resulting scores)
CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    upload_date TEXT NOT NULL DEFAULT (datetime('now')),
    filename TEXT,
    trades_count INTEGER NOT NULL DEFAULT 0,
    dna_score INTEGER,
    behavioral_pct REAL,
    total_pnl REAL,
    persona TEXT,
    fix_one_thing TEXT,
    report_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Signal history (append-only — every generated signal is preserved for model learning)
CREATE TABLE IF NOT EXISTS signal_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_date TEXT NOT NULL,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    action TEXT NOT NULL,
    direction TEXT,
    confidence INTEGER,
    strategy_type TEXT,
    projected_open REAL,
    trade_json TEXT,
    reasoning TEXT,
    conditions_json TEXT,
    pattern_result_json TEXT,
    quality_filters_json TEXT,
    filters_passed INTEGER,
    filters_total INTEGER,
    filter_strength TEXT,
    position_sizing_json TEXT,
    risk_check_json TEXT,
    stock_signals_json TEXT,
    skip_reason TEXT,
    full_signal_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signal_history_date ON signal_history(signal_date);
CREATE INDEX IF NOT EXISTS idx_signal_history_direction ON signal_history(direction);
CREATE INDEX IF NOT EXISTS idx_signal_history_action ON signal_history(action);

-- Live signal engine trades (per-user paper/live trading)
CREATE TABLE IF NOT EXISTS live_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    date TEXT NOT NULL,
    direction TEXT,
    confidence INTEGER,
    strategy TEXT,
    legs TEXT,
    entry_cost REAL DEFAULT 0,
    max_loss REAL DEFAULT 0,
    max_profit REAL DEFAULT 0,
    sl_value REAL DEFAULT 0,
    projected_open REAL,
    width INTEGER,
    status TEXT DEFAULT 'open',
    pnl REAL,
    nifty_close REAL,
    exit_reason TEXT,
    mode TEXT DEFAULT 'paper',
    executed_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT
);
"""

# ===========================================================================
# SCHEMA — PostgreSQL version
# ===========================================================================

_POSTGRES_SCHEMA = """
-- Core profile table
CREATE TABLE IF NOT EXISTS profiles (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    balance REAL NOT NULL DEFAULT 10000.0,
    mode TEXT NOT NULL DEFAULT 'sim_only',
    is_locked INTEGER NOT NULL DEFAULT 0,
    penalty_until TEXT,
    created_at TEXT NOT NULL DEFAULT NOW()::TEXT,
    disclaimer_acknowledged INTEGER NOT NULL DEFAULT 0,
    payment_status TEXT NOT NULL DEFAULT 'unpaid'
);

-- Strategy sub-profiles
CREATE TABLE IF NOT EXISTS strategy_profiles (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    name TEXT NOT NULL,
    balance REAL NOT NULL DEFAULT 10000.0,
    is_locked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT NOW()::TEXT
);

-- Trade records
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    strategy_profile_id INTEGER REFERENCES strategy_profiles(id),
    ticker TEXT NOT NULL,
    strategy_type TEXT NOT NULL,
    legs TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    slippage_cost REAL NOT NULL DEFAULT 0,
    position_size REAL NOT NULL,
    position_pct REAL NOT NULL,
    max_unrealized_pnl REAL,
    realized_pnl REAL,
    status TEXT NOT NULL DEFAULT 'open',
    outcome_tag TEXT,
    opened_at TEXT NOT NULL DEFAULT NOW()::TEXT,
    closed_at TEXT,
    expiration_date TEXT NOT NULL,
    is_revenge_trade INTEGER NOT NULL DEFAULT 0,
    is_overconfidence_trap INTEGER NOT NULL DEFAULT 0,
    is_impulse_early_exit INTEGER NOT NULL DEFAULT 0,
    pre_trade_discipline REAL,
    pre_trade_patience REAL,
    pre_trade_sizing REAL,
    pre_trade_emotional REAL,
    risk_gate_shown INTEGER NOT NULL DEFAULT 0,
    risk_gate_proceeded INTEGER,
    iv_crush_warning_shown INTEGER NOT NULL DEFAULT 0,
    confirmation_proceeded INTEGER,
    journal_note TEXT,
    chain_opened_at TEXT,
    trade_executed_at TEXT
);

-- Real trade journal entries
CREATE TABLE IF NOT EXISTS real_trades (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    ticker TEXT NOT NULL,
    option_type TEXT NOT NULL,
    strike_price REAL NOT NULL,
    position_size REAL NOT NULL,
    entry_time TEXT NOT NULL,
    exit_time TEXT,
    outcome_amount REAL,
    behavioral_state TEXT,
    is_revenge_trade INTEGER NOT NULL DEFAULT 0,
    is_overconfidence_trap INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT NOW()::TEXT
);

-- Behavioral metrics
CREATE TABLE IF NOT EXISTS behavioral_metrics (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    source TEXT NOT NULL DEFAULT 'sim',
    discipline_rating REAL,
    patience_score REAL,
    sizing_consistency REAL,
    emotional_reactivity REAL,
    loss_disposition_ratio REAL,
    loss_disposition_flagged INTEGER NOT NULL DEFAULT 0,
    current_streak INTEGER NOT NULL DEFAULT 0,
    longest_streak INTEGER NOT NULL DEFAULT 0,
    total_trades INTEGER NOT NULL DEFAULT 0,
    phase TEXT NOT NULL DEFAULT 'A',
    diagnostic_summary TEXT,
    updated_at TEXT NOT NULL DEFAULT NOW()::TEXT
);

-- Telemetry
CREATE TABLE IF NOT EXISTS telemetry (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    trade_id INTEGER REFERENCES trades(id),
    timestamp TEXT NOT NULL DEFAULT NOW()::TEXT,
    discipline_rating REAL,
    patience_score REAL,
    sizing_consistency REAL,
    emotional_reactivity REAL,
    risk_gate_warnings TEXT,
    trader_decision TEXT NOT NULL
);

-- Earnings calendar
CREATE TABLE IF NOT EXISTS earnings_calendar (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    earnings_date TEXT NOT NULL,
    source TEXT DEFAULT 'manual'
);

-- Market data cache
CREATE TABLE IF NOT EXISTS market_data_cache (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    data_date TEXT NOT NULL,
    data_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT NOW()::TEXT,
    UNIQUE(ticker, data_date, data_type)
);

-- Monthly P&L
CREATE TABLE IF NOT EXISTS monthly_pnl (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    year_month TEXT NOT NULL,
    realized_pnl REAL NOT NULL DEFAULT 0,
    trade_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(profile_id, year_month)
);

-- Users (Google Sign-In)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    google_id TEXT UNIQUE,
    picture TEXT,
    is_premium INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_login TEXT
);

-- Upload history
CREATE TABLE IF NOT EXISTS upload_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    upload_date TEXT NOT NULL DEFAULT NOW()::TEXT,
    filename TEXT,
    trades_count INTEGER NOT NULL DEFAULT 0,
    dna_score INTEGER,
    behavioral_pct REAL,
    total_pnl REAL,
    persona TEXT,
    fix_one_thing TEXT,
    report_json TEXT,
    created_at TEXT NOT NULL DEFAULT NOW()::TEXT
);

-- Signal history (append-only — every generated signal is preserved for model learning)
CREATE TABLE IF NOT EXISTS signal_history (
    id SERIAL PRIMARY KEY,
    signal_date TEXT NOT NULL,
    generated_at TEXT NOT NULL DEFAULT NOW()::TEXT,
    action TEXT NOT NULL,
    direction TEXT,
    confidence INTEGER,
    strategy_type TEXT,
    projected_open REAL,
    trade_json TEXT,
    reasoning TEXT,
    conditions_json TEXT,
    pattern_result_json TEXT,
    quality_filters_json TEXT,
    filters_passed INTEGER,
    filters_total INTEGER,
    filter_strength TEXT,
    position_sizing_json TEXT,
    risk_check_json TEXT,
    stock_signals_json TEXT,
    skip_reason TEXT,
    full_signal_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signal_history_date ON signal_history(signal_date);
CREATE INDEX IF NOT EXISTS idx_signal_history_direction ON signal_history(direction);
CREATE INDEX IF NOT EXISTS idx_signal_history_action ON signal_history(action);

-- Live signal engine trades (per-user paper/live trading)
CREATE TABLE IF NOT EXISTS live_trades (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    date TEXT NOT NULL,
    direction TEXT,
    confidence INTEGER,
    strategy TEXT,
    legs TEXT,
    entry_cost REAL DEFAULT 0,
    max_loss REAL DEFAULT 0,
    max_profit REAL DEFAULT 0,
    sl_value REAL DEFAULT 0,
    projected_open REAL,
    width INTEGER,
    status TEXT DEFAULT 'open',
    pnl REAL,
    nifty_close REAL,
    exit_reason TEXT,
    mode TEXT DEFAULT 'paper',
    executed_at TEXT NOT NULL DEFAULT NOW()::TEXT,
    resolved_at TEXT
);
"""
