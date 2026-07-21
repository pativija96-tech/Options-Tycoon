"""Tests for routes/trading.py — Trade journal and trade listing API endpoints."""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from db.database import init_db, get_connection
from main import app


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Use a temporary database for each test."""
    test_db = str(tmp_path / "test.db")

    def mock_get_db_path():
        return test_db

    monkeypatch.setattr("db.database.get_db_path", mock_get_db_path)
    monkeypatch.setattr("routes.portfolio.get_connection", lambda db_path=None: get_connection(test_db))
    monkeypatch.setattr("routes.trading.get_connection", lambda db_path=None: get_connection(test_db))

    init_db(test_db)
    yield test_db


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def profile_with_trade(client, setup_test_db):
    """Create a profile and insert a trade record directly in the DB."""
    # Create profile via API
    resp = client.post("/api/profiles", json={"name": "Test Trader"})
    profile_id = resp.json()["id"]

    # Insert a trade record directly
    conn = get_connection(setup_test_db)
    legs = json.dumps([{"contract_type": "call", "strike": 100, "expiration": "2025-03-01", "quantity": 1, "action": "buy"}])
    cursor = conn.execute(
        """INSERT INTO trades (profile_id, ticker, strategy_type, legs, entry_price,
           position_size, position_pct, status, expiration_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (profile_id, "NIFTY", "long_call", legs, 150.0, 1000.0, 3.5, "open", "2025-03-01"),
    )
    conn.commit()
    trade_id = cursor.lastrowid
    conn.close()

    return {"profile_id": profile_id, "trade_id": trade_id}


class TestTradeJournal:
    def test_update_journal_success(self, client, profile_with_trade):
        """PUT /api/trades/{id}/journal updates the journal note."""
        trade_id = profile_with_trade["trade_id"]
        response = client.put(
            f"/api/trades/{trade_id}/journal",
            json={"note": "Good entry, followed my plan."},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["journal_note"] == "Good entry, followed my plan."
        assert data["id"] == trade_id

    def test_update_journal_replaces_existing_note(self, client, profile_with_trade):
        """Updating journal replaces the previous note."""
        trade_id = profile_with_trade["trade_id"]
        client.put(f"/api/trades/{trade_id}/journal", json={"note": "First note"})
        response = client.put(f"/api/trades/{trade_id}/journal", json={"note": "Updated note"})
        assert response.status_code == 200
        assert response.json()["journal_note"] == "Updated note"

    def test_update_journal_max_length(self, client, profile_with_trade):
        """Accepts a note exactly 1000 characters long."""
        trade_id = profile_with_trade["trade_id"]
        note = "x" * 1000
        response = client.put(f"/api/trades/{trade_id}/journal", json={"note": note})
        assert response.status_code == 200
        assert len(response.json()["journal_note"]) == 1000

    def test_update_journal_exceeds_max_length(self, client, profile_with_trade):
        """Rejects a note longer than 1000 characters with 422."""
        trade_id = profile_with_trade["trade_id"]
        note = "x" * 1001
        response = client.put(f"/api/trades/{trade_id}/journal", json={"note": note})
        assert response.status_code == 422

    def test_update_journal_nonexistent_trade(self, client):
        """Returns 404 for a trade that doesn't exist."""
        response = client.put("/api/trades/9999/journal", json={"note": "No trade"})
        assert response.status_code == 404

    def test_update_journal_empty_note(self, client, profile_with_trade):
        """Accepts an empty string as a journal note."""
        trade_id = profile_with_trade["trade_id"]
        response = client.put(f"/api/trades/{trade_id}/journal", json={"note": ""})
        assert response.status_code == 200
        assert response.json()["journal_note"] == ""


class TestExecuteTrade:
    """Tests for POST /api/trades — trade execution endpoint."""

    def _trade_payload(self, profile_id, **overrides):
        """Build a valid trade request payload."""
        payload = {
            "profile_id": profile_id,
            "ticker": "NIFTY",
            "strategy_type": "long_call",
            "legs": [
                {
                    "contract_type": "call",
                    "strike": 22500,
                    "expiration": "2025-02-27",
                    "quantity": 1,
                    "action": "buy",
                }
            ],
            "chain_opened_at": "2025-02-20T10:00:00",
            "confirmation_proceeded": True,
        }
        payload.update(overrides)
        return payload

    def test_execute_trade_success(self, client):
        """POST /api/trades creates a trade and deducts balance."""
        resp = client.post("/api/profiles", json={"name": "Trader"})
        profile_id = resp.json()["id"]

        payload = self._trade_payload(profile_id)
        response = client.post("/api/trades", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "NIFTY"
        assert data["strategy_type"] == "long_call"
        assert data["status"] == "open"
        assert data["slippage_cost"] >= 0
        assert data["entry_price"] > 0
        assert data["position_pct"] > 0
        assert data["updated_balance"] < 10000.0
        assert data["chain_opened_at"] == "2025-02-20T10:00:00"
        assert data["trade_executed_at"] is not None
        assert data["confirmation_proceeded"] == 1

    def test_execute_trade_insufficient_funds(self, client):
        """Returns 400 INSUFFICIENT_FUNDS when balance too low."""
        resp = client.post("/api/profiles", json={"name": "Poor Trader"})
        profile_id = resp.json()["id"]

        # Buy 1000 quantity of an expensive option to exceed 10000 balance
        payload = self._trade_payload(
            profile_id,
            legs=[{
                "contract_type": "call",
                "strike": 22000,
                "expiration": "2025-02-27",
                "quantity": 100,
                "action": "buy",
            }],
        )
        response = client.post("/api/trades", json=payload)
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["code"] == "INSUFFICIENT_FUNDS"

    def test_execute_trade_locked_profile(self, client, setup_test_db):
        """Returns 400 GAME_OVER for locked profile."""
        resp = client.post("/api/profiles", json={"name": "Locked"})
        profile_id = resp.json()["id"]

        # Lock the profile directly
        conn = get_connection(setup_test_db)
        conn.execute("UPDATE profiles SET is_locked = 1 WHERE id = ?", (profile_id,))
        conn.commit()
        conn.close()

        payload = self._trade_payload(profile_id)
        response = client.post("/api/trades", json=payload)
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["code"] == "GAME_OVER"

    def test_execute_trade_nonexistent_profile(self, client):
        """Returns 404 for nonexistent profile."""
        payload = self._trade_payload(9999)
        response = client.post("/api/trades", json=payload)
        assert response.status_code == 404

    def test_execute_trade_unknown_ticker(self, client):
        """Returns 404 for unknown ticker."""
        resp = client.post("/api/profiles", json={"name": "Trader"})
        profile_id = resp.json()["id"]

        payload = self._trade_payload(profile_id, ticker="UNKNOWN")
        response = client.post("/api/trades", json=payload)
        assert response.status_code == 404

    def test_execute_trade_deducts_balance(self, client):
        """Trade deducts total cost from profile balance."""
        resp = client.post("/api/profiles", json={"name": "Trader"})
        profile_id = resp.json()["id"]

        payload = self._trade_payload(profile_id)
        response = client.post("/api/trades", json=payload)
        data = response.json()

        # Verify balance reduced
        profile_resp = client.get(f"/api/profiles/{profile_id}")
        assert profile_resp.json()["balance"] == data["updated_balance"]

    def test_execute_trade_game_over_on_zero_balance(self, client, setup_test_db):
        """Profile is locked when balance reaches 0 after trade."""
        resp = client.post("/api/profiles", json={"name": "All In"})
        profile_id = resp.json()["id"]

        # Set balance to exactly what a single NIFTY call at 22500 costs (ask=140 + slippage)
        # ask=140 for 22500 call, slippage = 0.5*(140-135)*1 = 2.5, total = 142.5
        conn = get_connection(setup_test_db)
        conn.execute("UPDATE profiles SET balance = 142.5 WHERE id = ?", (profile_id,))
        conn.commit()
        conn.close()

        payload = self._trade_payload(profile_id)
        response = client.post("/api/trades", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["updated_balance"] <= 0

        # Profile should now be locked
        profile_resp = client.get(f"/api/profiles/{profile_id}")
        assert profile_resp.json()["is_locked"] is True

    def test_execute_trade_sell_leg_reduces_cost(self, client):
        """Sell legs reduce the total trade cost."""
        resp = client.post("/api/profiles", json={"name": "Spreader"})
        profile_id = resp.json()["id"]

        # Bull call spread: buy lower strike, sell higher strike
        payload = self._trade_payload(
            profile_id,
            strategy_type="bull_call_spread",
            legs=[
                {"contract_type": "call", "strike": 22500, "expiration": "2025-02-27", "quantity": 1, "action": "buy"},
                {"contract_type": "call", "strike": 22600, "expiration": "2025-02-27", "quantity": 1, "action": "sell"},
            ],
        )
        response = client.post("/api/trades", json=payload)
        assert response.status_code == 200
        data = response.json()
        # Net cost should be less than buying the call alone (140 ask - 88 bid = 52 net + slippage)
        assert data["entry_price"] < 140


class TestGetTrades:
    def test_get_trades_for_profile(self, client, profile_with_trade):
        """GET /api/trades/{profile_id} returns trades for a profile."""
        profile_id = profile_with_trade["profile_id"]
        response = client.get(f"/api/trades/{profile_id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "NIFTY"

    def test_get_trades_empty_profile(self, client):
        """Returns empty list for a profile with no trades."""
        resp = client.post("/api/profiles", json={"name": "Empty"})
        profile_id = resp.json()["id"]
        response = client.get(f"/api/trades/{profile_id}")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_trades_nonexistent_profile(self, client):
        """Returns 404 for a nonexistent profile."""
        response = client.get("/api/trades/9999")
        assert response.status_code == 404
