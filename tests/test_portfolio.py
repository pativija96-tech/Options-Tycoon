"""Tests for routes/portfolio.py — Profile management API endpoints."""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from db.database import init_db, get_connection, get_db_path
from main import app


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Use a temporary database for each test."""
    test_db = str(tmp_path / "test.db")

    def mock_get_db_path():
        return test_db

    monkeypatch.setattr("db.database.get_db_path", mock_get_db_path)
    monkeypatch.setattr("routes.portfolio.get_connection", lambda db_path=None: get_connection(test_db))

    init_db(test_db)
    yield test_db


@pytest.fixture
def client():
    return TestClient(app)


class TestCreateProfile:
    def test_creates_profile_with_defaults(self, client):
        """POST /api/profiles creates a profile with $10,000 balance."""
        response = client.post("/api/profiles", json={"name": "Trader Alpha"})
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Trader Alpha"
        assert data["balance"] == 10000.0
        assert data["mode"] == "sim_only"
        assert data["is_locked"] is False
        assert data["phase"] == "A"
        assert data["total_trades"] == 0
        assert "id" in data

    def test_creates_multiple_profiles(self, client):
        """Can create multiple distinct profiles."""
        r1 = client.post("/api/profiles", json={"name": "Profile 1"})
        r2 = client.post("/api/profiles", json={"name": "Profile 2"})
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["id"] != r2.json()["id"]


class TestListProfiles:
    def test_empty_list(self, client):
        """GET /api/profiles returns empty list when no profiles exist."""
        response = client.get("/api/profiles")
        assert response.status_code == 200
        assert response.json() == []

    def test_lists_all_profiles(self, client):
        """GET /api/profiles returns all created profiles."""
        client.post("/api/profiles", json={"name": "Alpha"})
        client.post("/api/profiles", json={"name": "Beta"})
        response = client.get("/api/profiles")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = {p["name"] for p in data}
        assert names == {"Alpha", "Beta"}


class TestGetProfile:
    def test_get_existing_profile(self, client):
        """GET /api/profiles/{id} returns the profile."""
        create_resp = client.post("/api/profiles", json={"name": "Solo"})
        profile_id = create_resp.json()["id"]

        response = client.get(f"/api/profiles/{profile_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == profile_id
        assert data["name"] == "Solo"
        assert data["balance"] == 10000.0

    def test_get_nonexistent_profile(self, client):
        """GET /api/profiles/{id} returns 404 for missing profile."""
        response = client.get("/api/profiles/9999")
        assert response.status_code == 404


class TestDeleteProfile:
    def test_delete_existing_profile(self, client):
        """DELETE /api/profiles/{id} removes the profile."""
        create_resp = client.post("/api/profiles", json={"name": "ToDelete"})
        profile_id = create_resp.json()["id"]

        response = client.delete(f"/api/profiles/{profile_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_resp = client.get(f"/api/profiles/{profile_id}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent_profile(self, client):
        """DELETE /api/profiles/{id} returns 404 for missing profile."""
        response = client.delete("/api/profiles/9999")
        assert response.status_code == 404


class TestGameOver:
    def test_profile_locked_when_balance_zero(self, client, setup_test_db):
        """Profile is locked when balance reaches $0."""
        from routes.portfolio import check_game_over

        # Create a profile and manually set balance to 0
        create_resp = client.post("/api/profiles", json={"name": "Broke"})
        profile_id = create_resp.json()["id"]

        conn = get_connection(setup_test_db)
        conn.execute("UPDATE profiles SET balance = 0 WHERE id = ?", (profile_id,))
        conn.commit()
        conn.close()

        # check_game_over should lock it
        is_locked = check_game_over(profile_id)
        assert is_locked is True

        # Profile should now show as locked
        response = client.get(f"/api/profiles/{profile_id}")
        assert response.json()["is_locked"] is True

    def test_profile_not_locked_with_balance(self, client, setup_test_db):
        """Profile is not locked when balance is positive."""
        from routes.portfolio import check_game_over

        create_resp = client.post("/api/profiles", json={"name": "Healthy"})
        profile_id = create_resp.json()["id"]

        is_locked = check_game_over(profile_id)
        assert is_locked is False


class TestStrategyProfiles:
    def test_create_strategy_profile(self, client):
        """POST /profiles/{id}/strategy-profiles creates a sub-profile."""
        create_resp = client.post("/api/profiles", json={"name": "Main"})
        profile_id = create_resp.json()["id"]

        response = client.post(
            f"/api/profiles/{profile_id}/strategy-profiles",
            json={"name": "Iron Condor Strategy"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Iron Condor Strategy"
        assert data["profile_id"] == profile_id
        assert data["balance"] == 10000.0
        assert data["is_locked"] is False

    def test_list_strategy_profiles(self, client):
        """GET /profiles/{id}/strategy-profiles returns all sub-profiles."""
        create_resp = client.post("/api/profiles", json={"name": "Main"})
        profile_id = create_resp.json()["id"]

        client.post(f"/api/profiles/{profile_id}/strategy-profiles", json={"name": "Strat A"})
        client.post(f"/api/profiles/{profile_id}/strategy-profiles", json={"name": "Strat B"})

        response = client.get(f"/api/profiles/{profile_id}/strategy-profiles")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_max_five_strategy_profiles(self, client):
        """Cannot create more than 5 strategy profiles per profile."""
        create_resp = client.post("/api/profiles", json={"name": "Main"})
        profile_id = create_resp.json()["id"]

        for i in range(5):
            resp = client.post(
                f"/api/profiles/{profile_id}/strategy-profiles",
                json={"name": f"Strategy {i+1}"},
            )
            assert resp.status_code == 201

        # 6th should fail
        response = client.post(
            f"/api/profiles/{profile_id}/strategy-profiles",
            json={"name": "Strategy 6"},
        )
        assert response.status_code == 400
        assert "Maximum" in response.json()["detail"]

    def test_locked_profile_rejects_strategy_creation(self, client, setup_test_db):
        """Cannot create strategy profiles on a locked profile."""
        create_resp = client.post("/api/profiles", json={"name": "Locked"})
        profile_id = create_resp.json()["id"]

        # Lock the profile
        conn = get_connection(setup_test_db)
        conn.execute("UPDATE profiles SET is_locked = 1 WHERE id = ?", (profile_id,))
        conn.commit()
        conn.close()

        response = client.post(
            f"/api/profiles/{profile_id}/strategy-profiles",
            json={"name": "Nope"},
        )
        assert response.status_code == 403

    def test_strategy_profile_nonexistent_parent(self, client):
        """Cannot create strategy profiles for a nonexistent profile."""
        response = client.post(
            "/api/profiles/9999/strategy-profiles",
            json={"name": "Orphan"},
        )
        assert response.status_code == 404
