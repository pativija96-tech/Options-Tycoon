"""Tests for market data API endpoints (routes/data.py)."""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class TestGetTickers:
    """Tests for GET /api/tickers."""

    def test_returns_list_of_tickers(self):
        response = client.get("/api/tickers")
        assert response.status_code == 200
        data = response.json()
        assert "tickers" in data
        assert isinstance(data["tickers"], list)
        assert len(data["tickers"]) > 0

    def test_contains_known_tickers(self):
        response = client.get("/api/tickers")
        data = response.json()
        # These exist as mock JSON files
        assert "NIFTY" in data["tickers"]
        assert "RELIANCE" in data["tickers"]
        assert "TCS" in data["tickers"]

    def test_excludes_earnings_file(self):
        response = client.get("/api/tickers")
        data = response.json()
        assert "EARNINGS" not in data["tickers"]
        assert "earnings" not in data["tickers"]


class TestGetOptionsChain:
    """Tests for GET /api/chain/{ticker}."""

    def test_returns_chain_for_valid_ticker(self):
        response = client.get("/api/chain/NIFTY")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "NIFTY"
        assert "underlying_price" in data
        assert "expirations" in data
        assert len(data["expirations"]) > 0

    def test_chain_rows_have_greeks(self):
        response = client.get("/api/chain/NIFTY")
        data = response.json()
        first_chain = data["expirations"][0]["chain"]
        assert len(first_chain) > 0
        row = first_chain[0]
        # Check call Greeks
        assert "call_delta" in row
        assert "call_gamma" in row
        assert "call_theta" in row
        assert "call_vega" in row
        # Check put Greeks
        assert "put_delta" in row
        assert "put_gamma" in row
        assert "put_theta" in row
        assert "put_vega" in row

    def test_chain_rows_have_market_data(self):
        response = client.get("/api/chain/NIFTY")
        data = response.json()
        row = data["expirations"][0]["chain"][0]
        assert "strike" in row
        assert "call_bid" in row
        assert "call_ask" in row
        assert "call_volume" in row
        assert "call_oi" in row
        assert "call_iv" in row
        assert "put_bid" in row
        assert "put_ask" in row

    def test_filter_by_expiry(self):
        response = client.get("/api/chain/NIFTY?expiry=2025-02-27")
        assert response.status_code == 200
        data = response.json()
        assert len(data["expirations"]) == 1
        assert data["expirations"][0]["date"] == "2025-02-27"

    def test_filter_by_nonexistent_expiry_returns_empty(self):
        response = client.get("/api/chain/NIFTY?expiry=2099-01-01")
        assert response.status_code == 200
        data = response.json()
        assert len(data["expirations"]) == 0

    def test_unknown_ticker_returns_404(self):
        response = client.get("/api/chain/UNKNOWN")
        assert response.status_code == 404
        data = response.json()
        assert "No data available for UNKNOWN" in data["detail"]

    def test_case_insensitive_ticker(self):
        response = client.get("/api/chain/nifty")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "NIFTY"


class TestGetIVRank:
    """Tests for GET /api/iv-rank/{ticker}."""

    def test_returns_iv_rank_for_valid_ticker(self):
        response = client.get("/api/iv-rank/NIFTY")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "NIFTY"
        assert "iv_rank" in data
        assert "current_iv" in data
        assert "iv_high" in data
        assert "iv_low" in data

    def test_iv_rank_is_valid_percentage(self):
        response = client.get("/api/iv-rank/NIFTY")
        data = response.json()
        assert 0 <= data["iv_rank"] <= 100

    def test_unknown_ticker_returns_404(self):
        response = client.get("/api/iv-rank/UNKNOWN")
        assert response.status_code == 404
        data = response.json()
        assert "No data available for UNKNOWN" in data["detail"]

    def test_case_insensitive_ticker(self):
        response = client.get("/api/iv-rank/reliance")
        assert response.status_code == 200
        assert response.json()["ticker"] == "RELIANCE"


class TestGetEarnings:
    """Tests for GET /api/earnings/{ticker}."""

    def test_returns_earnings_for_valid_ticker(self):
        response = client.get("/api/earnings/TCS")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "TCS"
        assert "upcoming_earnings" in data
        assert isinstance(data["upcoming_earnings"], list)

    def test_unknown_ticker_returns_404(self):
        response = client.get("/api/earnings/UNKNOWN")
        assert response.status_code == 404
        data = response.json()
        assert "No data available for UNKNOWN" in data["detail"]

    def test_case_insensitive_ticker(self):
        response = client.get("/api/earnings/tcs")
        assert response.status_code == 200
        assert response.json()["ticker"] == "TCS"
