"""Tests for the settlement engine."""

import json
import tempfile
from datetime import date, timedelta

from db.database import init_db, get_connection
from engine.settlement import settle_position, settle_expired_positions


def _setup_db():
    """Create a temporary database with schema initialized."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp.name
    tmp.close()
    init_db(db_path)
    return db_path


def _create_profile(db_path: str, balance: float = 10000.0) -> int:
    """Create a test profile and return its ID."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO profiles (name, balance) VALUES (?, ?)",
            ("test_user", balance),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _create_trade(db_path: str, profile_id: int, legs: list, entry_price: float,
                  ticker: str = "NIFTY", expiration_date: str = "2025-01-01") -> int:
    """Insert a trade record and return its ID."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO trades (
                profile_id, ticker, strategy_type, legs, entry_price,
                position_size, position_pct, status, expiration_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)""",
            (
                profile_id, ticker, "custom", json.dumps(legs),
                entry_price, entry_price, 5.0, expiration_date,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _get_balance(db_path: str, profile_id: int) -> float:
    """Get current profile balance."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT balance FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        return row["balance"]
    finally:
        conn.close()


class TestSettlePosition:
    """Tests for settle_position function."""

    def test_settle_itm_call_buy(self):
        """ITM call buy settles at intrinsic value."""
        db_path = _setup_db()
        profile_id = _create_profile(db_path, balance=9500.0)
        legs = [{"strike": 22000, "quantity": 1, "contract_type": "call",
                 "action": "buy", "expiration": "2025-01-01"}]
        trade_id = _create_trade(db_path, profile_id, legs, entry_price=500.0)

        # Underlying at 22500 -> intrinsic = max(0, 22500-22000)*1 = 500
        result = settle_position(trade_id, 22500.0, db_path)

        assert result["status"] == "settled"
        assert result["exit_price"] == 500.0
        assert result["realized_pnl"] == 0.0  # 500 - 500 = 0
        assert result["closed_at"] is not None

        # Balance should increase by exit_value
        balance = _get_balance(db_path, profile_id)
        assert balance == 10000.0  # 9500 + 500

    def test_settle_otm_call_buy(self):
        """OTM call buy settles at zero."""
        db_path = _setup_db()
        profile_id = _create_profile(db_path, balance=9500.0)
        legs = [{"strike": 23000, "quantity": 1, "contract_type": "call",
                 "action": "buy", "expiration": "2025-01-01"}]
        trade_id = _create_trade(db_path, profile_id, legs, entry_price=100.0)

        # Underlying at 22500 -> intrinsic = max(0, 22500-23000)*1 = 0
        result = settle_position(trade_id, 22500.0, db_path)

        assert result["status"] == "settled"
        assert result["exit_price"] == 0.0
        assert result["realized_pnl"] == -100.0  # 0 - 100 = -100
        balance = _get_balance(db_path, profile_id)
        assert balance == 9500.0  # 9500 + 0

    def test_settle_itm_put_buy(self):
        """ITM put buy settles at intrinsic value."""
        db_path = _setup_db()
        profile_id = _create_profile(db_path, balance=9500.0)
        legs = [{"strike": 23000, "quantity": 2, "contract_type": "put",
                 "action": "buy", "expiration": "2025-01-01"}]
        trade_id = _create_trade(db_path, profile_id, legs, entry_price=600.0)

        # Underlying at 22500 -> intrinsic = max(0, 23000-22500)*2 = 1000
        result = settle_position(trade_id, 22500.0, db_path)

        assert result["status"] == "settled"
        assert result["exit_price"] == 1000.0
        assert result["realized_pnl"] == 400.0  # 1000 - 600
        balance = _get_balance(db_path, profile_id)
        assert balance == 10500.0  # 9500 + 1000

    def test_settle_otm_put_buy(self):
        """OTM put buy settles at zero."""
        db_path = _setup_db()
        profile_id = _create_profile(db_path, balance=9800.0)
        legs = [{"strike": 22000, "quantity": 1, "contract_type": "put",
                 "action": "buy", "expiration": "2025-01-01"}]
        trade_id = _create_trade(db_path, profile_id, legs, entry_price=50.0)

        # Underlying at 22500 -> intrinsic = max(0, 22000-22500)*1 = 0
        result = settle_position(trade_id, 22500.0, db_path)

        assert result["status"] == "settled"
        assert result["exit_price"] == 0.0
        assert result["realized_pnl"] == -50.0
        balance = _get_balance(db_path, profile_id)
        assert balance == 9800.0  # unchanged (exit_value = 0)

    def test_settle_sell_call_itm_liability(self):
        """Sell call that ends ITM creates a liability (negative exit value)."""
        db_path = _setup_db()
        profile_id = _create_profile(db_path, balance=10200.0)
        legs = [{"strike": 22000, "quantity": 1, "contract_type": "call",
                 "action": "sell", "expiration": "2025-01-01"}]
        # Seller received premium (entry_price is negative cost = credit)
        trade_id = _create_trade(db_path, profile_id, legs, entry_price=-500.0)

        # Underlying at 22500 -> sell call liability = -max(0, 22500-22000)*1 = -500
        result = settle_position(trade_id, 22500.0, db_path)

        assert result["status"] == "settled"
        assert result["exit_price"] == -500.0
        assert result["realized_pnl"] == 0.0  # -500 - (-500) = 0
        balance = _get_balance(db_path, profile_id)
        assert balance == 9700.0  # 10200 + (-500)

    def test_settle_sell_put_otm(self):
        """Sell put that ends OTM settles at zero (full profit)."""
        db_path = _setup_db()
        profile_id = _create_profile(db_path, balance=10100.0)
        legs = [{"strike": 22000, "quantity": 1, "contract_type": "put",
                 "action": "sell", "expiration": "2025-01-01"}]
        trade_id = _create_trade(db_path, profile_id, legs, entry_price=-100.0)

        # Underlying at 22500 -> sell put liability = -max(0, 22000-22500)*1 = 0
        result = settle_position(trade_id, 22500.0, db_path)

        assert result["status"] == "settled"
        assert result["exit_price"] == 0.0
        assert result["realized_pnl"] == 100.0  # 0 - (-100) = 100
        balance = _get_balance(db_path, profile_id)
        assert balance == 10100.0  # 10100 + 0

    def test_settle_multi_leg_strategy(self):
        """Multi-leg strategy (bull call spread) settles correctly."""
        db_path = _setup_db()
        profile_id = _create_profile(db_path, balance=9800.0)
        legs = [
            {"strike": 22000, "quantity": 1, "contract_type": "call",
             "action": "buy", "expiration": "2025-01-01"},
            {"strike": 22500, "quantity": 1, "contract_type": "call",
             "action": "sell", "expiration": "2025-01-01"},
        ]
        trade_id = _create_trade(db_path, profile_id, legs, entry_price=200.0)

        # Underlying at 22300:
        # Buy call 22000: max(0, 22300-22000)*1 = 300
        # Sell call 22500: -max(0, 22300-22500)*1 = 0
        # Total exit_value = 300
        result = settle_position(trade_id, 22300.0, db_path)

        assert result["status"] == "settled"
        assert result["exit_price"] == 300.0
        assert result["realized_pnl"] == 100.0  # 300 - 200
        balance = _get_balance(db_path, profile_id)
        assert balance == 10100.0  # 9800 + 300

    def test_settle_already_settled_raises(self):
        """Attempting to settle a non-open trade raises ValueError."""
        db_path = _setup_db()
        profile_id = _create_profile(db_path)
        legs = [{"strike": 22000, "quantity": 1, "contract_type": "call",
                 "action": "buy", "expiration": "2025-01-01"}]
        trade_id = _create_trade(db_path, profile_id, legs, entry_price=500.0)

        # Settle once
        settle_position(trade_id, 22500.0, db_path)

        # Try to settle again
        try:
            settle_position(trade_id, 22500.0, db_path)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "not open" in str(e)

    def test_settle_nonexistent_trade_raises(self):
        """Settling a non-existent trade raises ValueError."""
        db_path = _setup_db()
        try:
            settle_position(9999, 22500.0, db_path)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "not found" in str(e)


class TestSettleExpiredPositions:
    """Tests for settle_expired_positions function."""

    def test_settles_expired_positions(self):
        """Positions past expiration date are settled."""
        db_path = _setup_db()
        profile_id = _create_profile(db_path, balance=9000.0)

        # Create a trade that expired yesterday
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        legs = [{"strike": 22000, "quantity": 1, "contract_type": "call",
                 "action": "buy", "expiration": yesterday}]
        _create_trade(db_path, profile_id, legs, entry_price=500.0,
                      ticker="NIFTY", expiration_date=yesterday)

        settled = settle_expired_positions(db_path)

        assert len(settled) == 1
        assert settled[0]["status"] == "settled"

    def test_does_not_settle_future_positions(self):
        """Positions with future expiration are not settled."""
        db_path = _setup_db()
        profile_id = _create_profile(db_path)

        # Create a trade expiring in the future
        future = (date.today() + timedelta(days=30)).isoformat()
        legs = [{"strike": 22000, "quantity": 1, "contract_type": "call",
                 "action": "buy", "expiration": future}]
        _create_trade(db_path, profile_id, legs, entry_price=500.0,
                      ticker="NIFTY", expiration_date=future)

        settled = settle_expired_positions(db_path)

        assert len(settled) == 0
