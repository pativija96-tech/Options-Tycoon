"""Tests for db/database.py module."""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.database import get_db_path, get_connection, init_db


def test_get_db_path():
    """get_db_path returns path ending with options_tycoon.db in project root."""
    db_path = get_db_path()
    assert db_path.endswith("options_tycoon.db"), f"Unexpected path: {db_path}"
    print("  get_db_path() OK")


def test_init_and_connection():
    """init_db creates all tables, get_connection enables WAL and foreign keys."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = os.path.join(tmpdir, "test.db")

        # init_db creates database and all tables
        init_db(test_db)
        print("  init_db() OK")

        # get_connection returns connection with WAL mode
        conn = get_connection(test_db)

        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal", f"Expected wal, got {result[0]}"
        print("  WAL mode OK")

        result = conn.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1, f"Expected 1, got {result[0]}"
        print("  Foreign keys OK")

        # Verify all 9 tables exist
        tables = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name != 'sqlite_sequence' "
            "ORDER BY name"
        ).fetchall()
        table_names = [t[0] for t in tables]
        print(f"  Tables created: {table_names}")

        expected_tables = sorted([
            "profiles", "strategy_profiles", "trades", "real_trades",
            "behavioral_metrics", "telemetry", "earnings_calendar",
            "market_data_cache", "monthly_pnl"
        ])
        assert table_names == expected_tables, f"Expected {expected_tables}, got {table_names}"
        print("  All 9 tables verified OK")

        # Test idempotency
        init_db(test_db)
        print("  Idempotent re-init OK")

        conn.close()


def test_defaults():
    """New profile rows get correct default values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = os.path.join(tmpdir, "test.db")
        init_db(test_db)
        conn = get_connection(test_db)

        conn.execute("INSERT INTO profiles (name) VALUES (?)", ("TestUser",))
        conn.commit()

        row = conn.execute("SELECT * FROM profiles WHERE name = ?", ("TestUser",)).fetchone()
        assert row["name"] == "TestUser"
        assert row["balance"] == 10000.0
        assert row["mode"] == "sim_only"
        assert row["is_locked"] == 0
        assert row["disclaimer_acknowledged"] == 0
        assert row["payment_status"] == "unpaid"
        print("  Row factory + defaults OK")

        conn.close()


if __name__ == "__main__":
    test_get_db_path()
    test_init_and_connection()
    test_defaults()
    print("\nAll tests passed!")
