"""
Mock Test Suite for IBKR Executor — Validates execute_qqq_sync flow.

Tests the full execution path with mocked IBKR REST API responses:
1. OAuth authentication (JWT → access token)
2. QQQ price fetch (market data snapshot)
3. Contract resolution (symbol → conid → option conids)
4. Iron Condor combo order placement
5. Order prompt auto-confirmation
6. Retry logic on timeout
7. Partial execution recovery

Run: pytest tests/test_ibkr_executor.py -v
"""

import os
import sys
import json
import time
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import date

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton executor between tests."""
    import engine.broker.ibkr_executor as mod
    mod._executor_instance = None
    yield
    mod._executor_instance = None


@pytest.fixture
def mock_env(monkeypatch):
    """Set required IBKR env vars."""
    monkeypatch.setenv("IBKR_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("IBKR_ACCOUNT_ID", "U12345678")
    monkeypatch.setenv("IBKR_PRIVATE_KEY_PEM", FAKE_RSA_KEY)


FAKE_RSA_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA2a2rwplBQLFqMkwB9m3WYJGQX6h9LJjH4PlCPr9fVjXjXkGn
eFUEQUo5bLcXPhljNX1cRmIWHJw5EXAMPLE_KEY_NOT_REAL_xxxxxxxxxxxxxxxx
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
-----END RSA PRIVATE KEY-----"""


def make_response(status_code=200, json_data=None):
    """Create a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = json.dumps(json_data or {})
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


# ─────────────────────────────────────────────────────────────────────
# TEST: Authentication
# ─────────────────────────────────────────────────────────────────────

class TestAuthentication:
    
    def test_not_configured_returns_false(self, monkeypatch):
        """If env vars are missing, authenticate returns False."""
        monkeypatch.setenv("IBKR_CLIENT_ID", "")
        monkeypatch.setenv("IBKR_ACCOUNT_ID", "")
        monkeypatch.setenv("IBKR_PRIVATE_KEY_PEM", "")
        
        from engine.broker.ibkr_executor import get_ibkr_executor
        executor = get_ibkr_executor()
        assert executor.authenticate() is False

    @patch("httpx.Client.post")
    def test_successful_auth(self, mock_post, mock_env):
        """Successful OAuth returns True and stores token."""
        mock_post.side_effect = [
            # Token response
            make_response(200, {"access_token": "test-token-123", "expires_in": 3600}),
            # Session validation
            make_response(200, {"authenticated": True}),
        ]
        
        from engine.broker.ibkr_executor import get_ibkr_executor
        executor = get_ibkr_executor()
        
        # Mock JWT encoding since we have a fake key
        with patch("jwt.encode", return_value="mocked-jwt"):
            result = executor.authenticate()
        
        assert result is True
        assert executor.access_token == "test-token-123"


# ─────────────────────────────────────────────────────────────────────
# TEST: Contract Resolution
# ─────────────────────────────────────────────────────────────────────

class TestContractResolution:

    @patch("httpx.Client.get")
    @patch("httpx.Client.post")
    def test_search_contract_success(self, mock_post, mock_get, mock_env):
        """search_contract resolves QQQ to conid."""
        from engine.broker.ibkr_executor import get_ibkr_executor
        executor = get_ibkr_executor()
        executor.access_token = "test-token"
        executor.token_expiry = time.time() + 3600
        
        mock_get.return_value = make_response(200, [{"conid": 320227571, "companyName": "INVESCO QQQ"}])
        
        conid = executor.search_contract("QQQ")
        assert conid == 320227571

    @patch("httpx.Client.get")
    @patch("httpx.Client.post")
    def test_search_contract_empty_response(self, mock_post, mock_get, mock_env):
        """search_contract returns None if IBKR returns empty."""
        from engine.broker.ibkr_executor import get_ibkr_executor
        executor = get_ibkr_executor()
        executor.access_token = "test-token"
        executor.token_expiry = time.time() + 3600
        
        mock_get.return_value = make_response(200, [])
        
        conid = executor.search_contract("INVALID")
        assert conid is None

    @patch("httpx.Client.get")
    @patch("httpx.Client.post")
    def test_resolve_option_conid_success(self, mock_post, mock_get, mock_env):
        """resolve_option_conid finds exact match."""
        from engine.broker.ibkr_executor import get_ibkr_executor
        executor = get_ibkr_executor()
        executor.access_token = "test-token"
        executor.token_expiry = time.time() + 3600
        
        today = date.today().strftime("%Y%m%d")
        mock_get.return_value = make_response(200, [
            {"conid": 99001, "strike": 700.0, "right": "C", "maturityDate": today},
            {"conid": 99002, "strike": 700.0, "right": "P", "maturityDate": today},
        ])
        
        conid = executor.resolve_option_conid(320227571, 700.0, "C", today)
        assert conid == 99001


# ─────────────────────────────────────────────────────────────────────
# TEST: QQQ Price
# ─────────────────────────────────────────────────────────────────────

class TestQQQPrice:

    @patch("httpx.Client.get")
    @patch("httpx.Client.post")
    def test_get_qqq_price_last(self, mock_post, mock_get, mock_env):
        """get_qqq_price returns last price from snapshot."""
        from engine.broker.ibkr_executor import get_ibkr_executor
        executor = get_ibkr_executor()
        executor.access_token = "test-token"
        executor.token_expiry = time.time() + 3600
        
        # First call: search_contract
        # Second call: market data snapshot
        mock_get.side_effect = [
            make_response(200, [{"conid": 320227571}]),
            make_response(200, [{"31": "682.50", "84": "682.40", "86": "682.60"}]),
        ]
        
        price = executor.get_qqq_price()
        assert price == 682.50

    @patch("httpx.Client.get")
    @patch("httpx.Client.post")
    def test_get_qqq_price_bid_ask_fallback(self, mock_post, mock_get, mock_env):
        """get_qqq_price falls back to mid bid/ask if last is unavailable."""
        from engine.broker.ibkr_executor import get_ibkr_executor
        executor = get_ibkr_executor()
        executor.access_token = "test-token"
        executor.token_expiry = time.time() + 3600
        
        mock_get.side_effect = [
            make_response(200, [{"conid": 320227571}]),
            make_response(200, [{"31": "C", "84": "680.00", "86": "682.00"}]),
        ]
        
        price = executor.get_qqq_price()
        assert price == 681.00


# ─────────────────────────────────────────────────────────────────────
# TEST: Iron Condor Placement
# ─────────────────────────────────────────────────────────────────────

class TestIronCondorPlacement:

    @patch("httpx.Client.get")
    @patch("httpx.Client.post")
    def test_place_iron_condor_combo_success(self, mock_post, mock_get, mock_env):
        """Full IC placement via combo order succeeds."""
        from engine.broker.ibkr_executor import get_ibkr_executor
        executor = get_ibkr_executor()
        executor.access_token = "test-token"
        executor.token_expiry = time.time() + 3600
        
        today = date.today().strftime("%Y%m%d")
        
        # Mock GET calls: search_contract + 4x resolve_option_conid + 1x credit snapshot
        mock_get.side_effect = [
            make_response(200, [{"conid": 320227571}]),  # QQQ conid
            make_response(200, [{"conid": 90001, "strike": 697.0, "right": "C", "maturityDate": today}]),
            make_response(200, [{"conid": 90002, "strike": 702.0, "right": "C", "maturityDate": today}]),
            make_response(200, [{"conid": 90003, "strike": 667.0, "right": "P", "maturityDate": today}]),
            make_response(200, [{"conid": 90004, "strike": 662.0, "right": "P", "maturityDate": today}]),
            # Credit-estimate snapshot: shorts richer than longs → net credit ~0.90
            make_response(200, [
                {"conid": 90001, "84": 1.00, "86": 1.10},  # short call mid 1.05
                {"conid": 90002, "84": 0.30, "86": 0.40},  # long call mid 0.35
                {"conid": 90003, "84": 1.00, "86": 1.10},  # short put mid 1.05
                {"conid": 90004, "84": 0.30, "86": 0.40},  # long put mid 0.35
            ]),
        ]
        
        # Mock POST: combo LMT order accepted with confirmation prompt, then reply
        mock_post.side_effect = [
            make_response(200, [{"id": "prompt-123"}]),  # Initial combo order response
            make_response(200, {"order_id": "ORD-456", "order_status": "Submitted"}),  # Reply
        ]
        
        result = executor.place_iron_condor(spot_price=682.0)
        
        assert result["success"] is True
        assert result["method"] == "combo"
        assert result["attempts"] == 1
        # Net credit estimate = (1.05 + 1.05) - (0.35 + 0.35) = 1.40; first attempt no concession
        assert result["limit_credit"] == 1.40
        assert result["strikes"]["short_call"] == 697
        assert result["strikes"]["long_call"] == 702   # 697 + 5 (wing width from config)
        assert result["strikes"]["short_put"] == 667
        assert result["strikes"]["long_put"] == 662    # 667 - 5

    @patch("httpx.Client.get")
    @patch("httpx.Client.post")
    def test_place_iron_condor_conid_failure(self, mock_post, mock_get, mock_env):
        """IC placement fails gracefully if option conid can't be resolved."""
        from engine.broker.ibkr_executor import get_ibkr_executor
        executor = get_ibkr_executor()
        executor.access_token = "test-token"
        executor.token_expiry = time.time() + 3600
        
        # search_contract succeeds, but first option conid returns empty
        mock_get.side_effect = [
            make_response(200, [{"conid": 320227571}]),  # QQQ conid
            make_response(200, []),  # Empty — no option found
        ]
        
        result = executor.place_iron_condor(spot_price=682.0)
        
        assert result["success"] is False
        assert "Cannot resolve conid" in result["error"]


# ─────────────────────────────────────────────────────────────────────
# TEST: Retry Logic
# ─────────────────────────────────────────────────────────────────────

class TestRetryLogic:

    @patch("httpx.Client.get")
    @patch("httpx.Client.post")
    def test_search_contract_retries_on_timeout(self, mock_post, mock_get, mock_env):
        """search_contract retries on timeout and succeeds on 2nd attempt."""
        import httpx as _httpx
        from engine.broker.ibkr_executor import get_ibkr_executor
        executor = get_ibkr_executor()
        executor.access_token = "test-token"
        executor.token_expiry = time.time() + 3600
        
        # First call: timeout, second call: success
        mock_get.side_effect = [
            _httpx.TimeoutException("Connection timed out"),
            make_response(200, [{"conid": 320227571}]),
        ]
        
        with patch("time.sleep"):  # Don't actually sleep in tests
            conid = executor.search_contract("QQQ")
        
        assert conid == 320227571
        assert mock_get.call_count == 2

    @patch("httpx.Client.get")
    @patch("httpx.Client.post")
    def test_search_contract_all_retries_exhausted(self, mock_post, mock_get, mock_env):
        """search_contract returns None after all retries exhausted."""
        import httpx as _httpx
        from engine.broker.ibkr_executor import get_ibkr_executor
        executor = get_ibkr_executor()
        executor.access_token = "test-token"
        executor.token_expiry = time.time() + 3600
        
        mock_get.side_effect = _httpx.TimeoutException("Connection timed out")
        
        with patch("time.sleep"):
            conid = executor.search_contract("QQQ")
        
        assert conid is None
        assert mock_get.call_count == 3  # MAX_RETRIES = 3


# ─────────────────────────────────────────────────────────────────────
# TEST: execute_qqq_sync (top-level entry point)
# ─────────────────────────────────────────────────────────────────────

class TestExecuteQQQSync:

    def test_not_configured_returns_error(self, monkeypatch):
        """execute_qqq_sync fails gracefully when not configured."""
        monkeypatch.setenv("IBKR_CLIENT_ID", "")
        monkeypatch.setenv("IBKR_ACCOUNT_ID", "")
        monkeypatch.setenv("IBKR_PRIVATE_KEY_PEM", "")
        
        from engine.broker.ibkr_executor import execute_qqq_sync
        result = execute_qqq_sync()
        
        assert result["success"] is False
        assert "not configured" in result["error"]

    @patch("httpx.Client.get")
    @patch("httpx.Client.post")
    def test_full_flow_with_spot_price(self, mock_post, mock_get, mock_env):
        """execute_qqq_sync with explicit spot_price skips price fetch."""
        from engine.broker.ibkr_executor import execute_qqq_sync
        import engine.broker.ibkr_executor as mod
        mod._executor_instance = None
        
        today = date.today().strftime("%Y%m%d")
        
        # Auth
        mock_post.side_effect = [
            make_response(200, {"access_token": "tok", "expires_in": 3600}),
            make_response(200, {"authenticated": True}),
            make_response(200, [{"id": "prompt-1"}]),  # combo order
            make_response(200, {"order_id": "X"}),  # reply
        ]
        
        # Contract resolution (5 GETs: search + 4 option conids)
        mock_get.side_effect = [
            make_response(200, [{"conid": 320227571}]),
            make_response(200, [{"conid": 90001, "strike": 697.0, "right": "C", "maturityDate": today}]),
            make_response(200, [{"conid": 90002, "strike": 702.0, "right": "C", "maturityDate": today}]),
            make_response(200, [{"conid": 90003, "strike": 667.0, "right": "P", "maturityDate": today}]),
            make_response(200, [{"conid": 90004, "strike": 662.0, "right": "P", "maturityDate": today}]),
        ]
        
        with patch("jwt.encode", return_value="mocked"):
            result = execute_qqq_sync(spot_price=682.0)
        
        assert result["success"] is True


# ─────────────────────────────────────────────────────────────────────
# TEST: Partial Execution
# ─────────────────────────────────────────────────────────────────────

class TestAtomicComboAbort:
    """Atomic-combo policy: NO individual-leg fallback. On repeated combo
    rejection the trade aborts and NO legs are placed (0DTE legging risk)."""

    @patch("httpx.Client.get")
    @patch("httpx.Client.post")
    def test_combo_rejection_aborts_no_legs_placed(self, mock_post, mock_get, mock_env):
        """When the combo order is rejected on every attempt, the IC aborts."""
        from engine.broker.ibkr_executor import get_ibkr_executor, MAX_RETRIES
        executor = get_ibkr_executor()
        executor.access_token = "test-token"
        executor.token_expiry = time.time() + 3600

        today = date.today().strftime("%Y%m%d")

        # GET: QQQ conid + 4 legs + credit snapshot
        mock_get.side_effect = [
            make_response(200, [{"conid": 320227571}]),
            make_response(200, [{"conid": 90001, "strike": 697.0, "right": "C", "maturityDate": today}]),
            make_response(200, [{"conid": 90002, "strike": 702.0, "right": "C", "maturityDate": today}]),
            make_response(200, [{"conid": 90003, "strike": 667.0, "right": "P", "maturityDate": today}]),
            make_response(200, [{"conid": 90004, "strike": 662.0, "right": "P", "maturityDate": today}]),
            make_response(200, [
                {"conid": 90001, "84": 1.00, "86": 1.10},
                {"conid": 90002, "84": 0.30, "86": 0.40},
                {"conid": 90003, "84": 1.00, "86": 1.10},
                {"conid": 90004, "84": 0.30, "86": 0.40},
            ]),
        ]

        # Every combo POST is rejected (e.g. no fill / order rejected)
        mock_post.return_value = make_response(400, {"error": "Order could not be filled"})

        result = executor.place_iron_condor(spot_price=682.0)

        assert result["success"] is False
        assert result["aborted"] is True
        assert result["method"] == "combo"
        assert result["attempts"] == MAX_RETRIES
        assert "aborted" in result["error"].lower()
        # No individual-leg method should ever run — only combo POSTs were attempted
        assert mock_post.call_count == MAX_RETRIES

    def test_deprecated_individual_legs_not_in_live_path(self, mock_env):
        """The old individual-leg method must not exist under its live name."""
        from engine.broker.ibkr_executor import get_ibkr_executor
        executor = get_ibkr_executor()
        assert not hasattr(executor, "_place_individual_legs"), (
            "Individual-leg fallback must be deprecated/renamed out of the live path"
        )
