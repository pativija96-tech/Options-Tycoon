"""
Simple database migration system for Options Tycoon.

Since we use raw SQL (not SQLAlchemy ORM), this is a lightweight
migration tracker that applies numbered SQL scripts in order.

Usage:
    from db.migrations import run_migrations
    run_migrations()  # Called on startup after init_db()
"""

import logging
from db.database import get_connection

logger = logging.getLogger("options_tycoon.migrations")

# Each migration is a tuple: (version_number, description, sql)
MIGRATIONS = [
    # Migration 1: Initial schema (handled by init_db, this is just the version marker)
    (1, "Initial schema", "SELECT 1"),
    
    # Migration 2: Signal history table (append-only for model learning)
    (2, "Add signal_history table", """
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
        )
    """),
    (3, "Add signal_history date index",
     "CREATE INDEX IF NOT EXISTS idx_signal_history_date ON signal_history(signal_date)"),
    (4, "Add signal_history direction index",
     "CREATE INDEX IF NOT EXISTS idx_signal_history_direction ON signal_history(direction)"),
    (5, "Add signal_history action index",
     "CREATE INDEX IF NOT EXISTS idx_signal_history_action ON signal_history(action)"),
]


def run_migrations():
    """
    Apply any pending migrations. Safe to call on every startup.
    Creates a schema_version table to track what's been applied.
    """
    conn = get_connection()
    try:
        # Ensure migration tracking table exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                description TEXT,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        
        # Get current version
        result = conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
        current_version = result['v'] if result and result['v'] else 0
        
        # Apply pending migrations
        applied = 0
        for version, description, sql in MIGRATIONS:
            if version > current_version:
                logger.info(f"Applying migration {version}: {description}")
                try:
                    conn.execute(sql)
                    conn.execute(
                        "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                        (version, description)
                    )
                    conn.commit()
                    applied += 1
                except Exception as e:
                    logger.error(f"Migration {version} failed: {e}")
                    conn.close()
                    raise
        
        if applied > 0:
            logger.info(f"Applied {applied} migration(s). Now at version {MIGRATIONS[-1][0] if MIGRATIONS else 0}")
        else:
            logger.debug(f"Database is up to date (version {current_version})")
    
    finally:
        conn.close()
