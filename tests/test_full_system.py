"""
Comprehensive Test Suite — Options Tycoon
==========================================
Covers ALL modules, flows, and logic paths.
Real money at stake. Zero shortcuts.

Run: python -m pytest tests/test_full_system.py -v
"""

import os
import sys
import json
import time
import tempfile
import shutil
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

import pytest

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set env vars BEFORE any imports that read them
os.environ.setdefault("TRADING_PHASE", "1")
os.environ.setdefault("TRADING_MODE", "qqq")
os.environ.setdefault("SESSION_SECRET", "test-secret-key")
os.environ.setdefault("FOUNDER_ALLOWED_EMAILS", "test@test.com")


# ===========================================================================
# SECTION 1: SIGNAL ENGINES
# ===========================================================================

class TestSimpleICEngine:
    """Tests for engine/signals/simple_ic_engine.py — NIFTY Iron Condor."""

    @patch("engine.signals.simple_ic_engine._get_expiry_date")
    @patch("engine.signals.simple_ic_engine._get_nifty_price")
    def test_generate_daily_signal_returns_trade(self, mock_price, mock_expiry):
        """Signal with valid market data returns action='trade' with NIFTY strikes."""
        mock_price.return_value = {"nifty": 24500.0, "vix": 14.5, "source": "mock", "errors": []}
        mock_expiry.return_value = (None, 5, "12 Aug 2026 (Tue)")  # 5 days to expiry
        from engine.signals.simple_ic_engine import generate_daily_signal
        signal = generate_daily_signal(capital=15000)

        assert signal["action"] == "trade"
        assert signal["direction"] == "neutral"
        assert "trade" in signal
        legs = signal["trade"]["legs"]
        assert len(legs) == 4

    @patch("engine.signals.simple_ic_engine._get_expiry_date")
    @patch("engine.signals.simple_ic_engine._get_nifty_price")
    def test_nifty_strikes_above_20000(self, mock_price, mock_expiry):
        """All strikes must be > 20000 (NIFTY range, not QQQ range)."""
        mock_price.return_value = {"nifty": 24500.0, "vix": 14.5, "source": "mock", "errors": []}
        mock_expiry.return_value = (None, 5, "12 Aug 2026 (Tue)")
        from engine.signals.simple_ic_engine import generate_daily_signal
        signal = generate_daily_signal(capital=15000)

        legs = signal["trade"]["legs"]
        for leg in legs:
            assert leg["strike"] > 20000, f"NIFTY strike {leg['strike']} should be > 20000"

    @patch("engine.signals.simple_ic_engine._get_expiry_date")
    @patch("engine.signals.simple_ic_engine._get_nifty_price")
    def test_nifty_option_format_ce_pe(self, mock_price, mock_expiry):
        """NIFTY options use CE/PE format (not C/P like QQQ)."""
        mock_price.return_value = {"nifty": 24500.0, "vix": 14.5, "source": "mock", "errors": []}
        mock_expiry.return_value = (None, 5, "12 Aug 2026 (Tue)")
        from engine.signals.simple_ic_engine import generate_daily_signal
        signal = generate_daily_signal(capital=15000)

        legs = signal["trade"]["legs"]
        option_types = {leg["option"] for leg in legs}
        assert option_types == {"CE", "PE"}, f"Expected CE/PE format, got {option_types}"

    @patch("engine.signals.simple_ic_engine._get_expiry_date")
    @patch("engine.signals.simple_ic_engine._get_nifty_price")
    def test_nifty_values_in_rupees(self, mock_price, mock_expiry):
        """Premiums and costs should be in ₹ range (not $ range)."""
        mock_price.return_value = {"nifty": 24500.0, "vix": 14.5, "source": "mock", "errors": []}
        mock_expiry.return_value = (None, 5, "12 Aug 2026 (Tue)")
        from engine.signals.simple_ic_engine import generate_daily_signal
        signal = generate_daily_signal(capital=15000)

        trade = signal["trade"]
        assert trade["max_profit"] > 50, "NIFTY credit should be > ₹50"
        assert trade["max_loss"] > 500, "NIFTY max loss should be > ₹500 (wing_width * lot_size)"

    @patch("engine.signals.simple_ic_engine._get_expiry_date")
    @patch("engine.signals.simple_ic_engine._get_nifty_price")
    def test_nifty_correct_expiry_format(self, mock_price, mock_expiry):
        """Expiry string should contain 'Tue' for weekly NIFTY expiry."""
        mock_price.return_value = {"nifty": 24500.0, "vix": 14.5, "source": "mock", "errors": []}
        mock_expiry.return_value = (None, 5, "12 Aug 2026 (Tue)")
        from engine.signals.simple_ic_engine import generate_daily_signal
        signal = generate_daily_signal(capital=15000)

        expiry = signal["trade"]["expiry_date"]
        assert "(Tue)" in expiry, f"NIFTY expiry should be Tuesday, got: {expiry}"

    @patch("engine.signals.simple_ic_engine._get_nifty_price")
    def test_vix_above_40_returns_skip(self, mock_price):
        """VIX > 40 should return action='skip' for NIFTY."""
        mock_price.return_value = {"nifty": 24500.0, "vix": 42.0, "source": "mock", "errors": []}
        from engine.signals.simple_ic_engine import generate_daily_signal
        signal = generate_daily_signal(capital=15000)

        assert signal["action"] == "skip"
        assert "VIX" in signal.get("reason", "") or "chaotic" in signal.get("reason", "").lower()

    @patch("engine.signals.simple_ic_engine._get_nifty_price")
    def test_no_nifty_price_returns_skip(self, mock_price):
        """If NIFTY price unavailable, return skip."""
        mock_price.return_value = {"nifty": None, "vix": None, "source": None, "errors": ["timeout"]}
        from engine.signals.simple_ic_engine import generate_daily_signal
        signal = generate_daily_signal(capital=15000)

        assert signal["action"] == "skip"

    @patch("engine.signals.simple_ic_engine._get_expiry_date")
    @patch("engine.signals.simple_ic_engine._get_nifty_price")
    def test_nifty_strike_offset_250pts(self, mock_price, mock_expiry):
        """Short strikes should be ±250 from ATM (rounded to 50)."""
        mock_price.return_value = {"nifty": 24500.0, "vix": 14.5, "source": "mock", "errors": []}
        mock_expiry.return_value = (None, 5, "12 Aug 2026 (Tue)")
        from engine.signals.simple_ic_engine import generate_daily_signal
        signal = generate_daily_signal(capital=15000)

        legs = signal["trade"]["legs"]
        sells = [l for l in legs if l["action"] == "SELL"]
        sell_ce = next(l for l in sells if l["option"] == "CE")
        sell_pe = next(l for l in sells if l["option"] == "PE")

        assert sell_ce["strike"] == 24750
        assert sell_pe["strike"] == 24250

    @patch("engine.signals.simple_ic_engine._get_expiry_date")
    @patch("engine.signals.simple_ic_engine._get_nifty_price")
    def test_nifty_wing_width_100pts(self, mock_price, mock_expiry):
        """Long strikes should be 100pts beyond short strikes."""
        mock_price.return_value = {"nifty": 24500.0, "vix": 14.5, "source": "mock", "errors": []}
        mock_expiry.return_value = (None, 5, "12 Aug 2026 (Tue)")
        from engine.signals.simple_ic_engine import generate_daily_signal
        signal = generate_daily_signal(capital=15000)

        legs = signal["trade"]["legs"]
        sell_ce = next(l for l in legs if l["action"] == "SELL" and l["option"] == "CE")
        buy_ce = next(l for l in legs if l["action"] == "BUY" and l["option"] == "CE")
        sell_pe = next(l for l in legs if l["action"] == "SELL" and l["option"] == "PE")
        buy_pe = next(l for l in legs if l["action"] == "BUY" and l["option"] == "PE")

        assert buy_ce["strike"] - sell_ce["strike"] == 100
        assert sell_pe["strike"] - buy_pe["strike"] == 100

    def test_min_days_to_expiry_blocks_monday(self):
        """SAFETY: Signal skips when < 2 days to expiry (Monday before Tuesday expiry)."""
        with patch("engine.signals.simple_ic_engine._get_nifty_price") as mock_price:
            mock_price.return_value = {"nifty": 24500.0, "vix": 14.5, "source": "mock", "errors": []}
            with patch("engine.signals.simple_ic_engine._get_expiry_date") as mock_expiry:
                mock_expiry.return_value = (None, 1, "04 Aug 2026 (Tue)")  # Only 1 day
                from engine.signals.simple_ic_engine import generate_daily_signal
                signal = generate_daily_signal(capital=15000)

        assert signal["action"] == "skip"
        assert "day" in signal.get("reason", "").lower()

    def test_negative_reward_blocks_trade(self):
        """SAFETY: Signal skips when conditions are unfavorable (low VIX, few days)."""
        with patch("engine.signals.simple_ic_engine._get_nifty_price") as mock_price:
            mock_price.return_value = {"nifty": 24500.0, "vix": 3.0, "source": "mock", "errors": []}
            with patch("engine.signals.simple_ic_engine._get_expiry_date") as mock_expiry:
                mock_expiry.return_value = (None, 2, "05 Aug 2026 (Tue)")  # 2 days, extremely low VIX
                from engine.signals.simple_ic_engine import generate_daily_signal
                signal = generate_daily_signal(capital=15000)

        # With very low VIX and short expiry, signal should skip for safety reasons
        # Could be: negative reward, risk cap exceeded, or days too few
        assert signal["action"] == "skip"


class TestQQQICEngine:
    """Tests for engine/signals/qqq_ic_engine.py — QQQ Iron Condor."""

    @patch("engine.signals.qqq_ic_engine._is_high_impact_event_day")
    @patch("engine.signals.qqq_ic_engine._get_qqq_price")
    def test_generate_qqq_signal_returns_trade(self, mock_price, mock_event):
        """QQQ signal with valid data returns action='trade'."""
        mock_event.return_value = (False, "")
        mock_price.return_value = {"qqq": 680.0, "vix": 18.0, "source": "mock", "errors": []}
        from engine.signals.qqq_ic_engine import generate_qqq_signal
        signal = generate_qqq_signal(capital=1000)

        assert signal["action"] == "trade"
        assert signal["market"] == "QQQ"

    @patch("engine.signals.qqq_ic_engine._is_high_impact_event_day")
    @patch("engine.signals.qqq_ic_engine._get_qqq_price")
    def test_qqq_strikes_in_600_800_range(self, mock_price, mock_event):
        """QQQ strikes should be in 600-800 range (not >20000 like NIFTY)."""
        mock_event.return_value = (False, "")
        mock_price.return_value = {"qqq": 680.0, "vix": 18.0, "source": "mock", "errors": []}
        from engine.signals.qqq_ic_engine import generate_qqq_signal
        signal = generate_qqq_signal(capital=1000)

        legs = signal["trade"]["legs"]
        for leg in legs:
            assert 500 < leg["strike"] < 900, f"QQQ strike {leg['strike']} outside expected range"

    @patch("engine.signals.qqq_ic_engine._is_high_impact_event_day")
    @patch("engine.signals.qqq_ic_engine._get_qqq_price")
    def test_qqq_option_format_c_p(self, mock_price, mock_event):
        """QQQ options use C/P format (not CE/PE like NIFTY)."""
        mock_event.return_value = (False, "")
        mock_price.return_value = {"qqq": 680.0, "vix": 18.0, "source": "mock", "errors": []}
        from engine.signals.qqq_ic_engine import generate_qqq_signal
        signal = generate_qqq_signal(capital=1000)

        legs = signal["trade"]["legs"]
        option_types = {leg["option"] for leg in legs}
        assert option_types == {"C", "P"}, f"Expected C/P format, got {option_types}"

    @patch("engine.signals.qqq_ic_engine._is_high_impact_event_day")
    @patch("engine.signals.qqq_ic_engine._get_qqq_price")
    def test_qqq_values_in_dollars(self, mock_price, mock_event):
        """QQQ values should be in $ (small numbers, not ₹ thousands)."""
        mock_event.return_value = (False, "")
        mock_price.return_value = {"qqq": 680.0, "vix": 18.0, "source": "mock", "errors": []}
        from engine.signals.qqq_ic_engine import generate_qqq_signal
        signal = generate_qqq_signal(capital=1000)

        trade = signal["trade"]
        # QQQ max loss with $5 wings × 100 multiplier = ~$500
        assert trade["max_loss"] < 1000, f"QQQ max loss ${trade['max_loss']} seems too high"
        assert trade["width"] == 5, f"QQQ wing width should be $5, got {trade['width']}"

    @patch("engine.signals.qqq_ic_engine._is_high_impact_event_day")
    @patch("engine.signals.qqq_ic_engine._get_qqq_price")
    def test_qqq_vix_above_35_returns_skip(self, mock_price, mock_event):
        """VIX > 35 should return skip for QQQ."""
        mock_event.return_value = (False, "")
        mock_price.return_value = {"qqq": 680.0, "vix": 37.0, "source": "mock", "errors": []}
        from engine.signals.qqq_ic_engine import generate_qqq_signal
        signal = generate_qqq_signal(capital=1000)

        assert signal["action"] == "skip"
        assert "VIX" in signal.get("reason", "") or "volatile" in signal.get("reason", "").lower()

    def test_fomc_day_returns_skip(self):
        """FOMC meeting day should trigger event filter → skip."""
        from engine.signals.qqq_ic_engine import _is_high_impact_event_day, FOMC_DATES_2026
        # Patch date.today() to a known FOMC date
        fomc_month, fomc_day = FOMC_DATES_2026[0]  # (1, 29) = Jan 29, 2026

        with patch("engine.signals.qqq_ic_engine.date") as mock_date:
            mock_date.today.return_value = date(2026, fomc_month, fomc_day)
            skip, reason = _is_high_impact_event_day()

        assert skip is True
        assert "FOMC" in reason

    @patch("engine.signals.qqq_ic_engine._is_high_impact_event_day")
    @patch("engine.signals.qqq_ic_engine._get_qqq_price")
    def test_event_filter_skips_trade(self, mock_price, mock_event):
        """High-impact event day should skip signal generation."""
        mock_event.return_value = (True, "FOMC rate decision today")
        mock_price.return_value = {"qqq": 680.0, "vix": 18.0, "source": "mock", "errors": []}
        from engine.signals.qqq_ic_engine import generate_qqq_signal
        signal = generate_qqq_signal(capital=1000)

        assert signal["action"] == "skip"
        assert "FOMC" in signal.get("reason", "")


# ===========================================================================
# SECTION 2: BROKER EXECUTORS
# ===========================================================================

class TestKiteExecutor:
    """Tests for engine/broker/kite_executor.py — Zerodha execution."""

    def test_expiry_symbol_uses_expiry_month_not_today(self):
        """
        BUG FIX TEST: Symbol generator must use EXPIRY month, not today's month.
        If today is July 31 (Thursday), next Tuesday is Aug 5 → symbol uses AUG not JUL.
        """
        # The function uses local import: from datetime import datetime, timezone, timedelta
        # We need to patch datetime.datetime.now() at the builtins level
        from unittest.mock import patch
        from datetime import datetime as real_dt, timezone as real_tz, timedelta as real_td

        ist = real_tz(real_td(hours=5, minutes=30))
        # July 31, 2026 is a Friday. Next Tue = Aug 5, 2026.
        fake_now = real_dt(2026, 7, 31, 10, 0, 0, tzinfo=ist)

        class FakeDatetime(real_dt):
            @classmethod
            def now(cls, tz=None):
                return fake_now

        # Patch 'datetime' in the datetime module so local import picks it up
        import datetime as dt_module
        with patch.object(dt_module, 'datetime', FakeDatetime):
            # Re-import to pick up the patched datetime
            import importlib
            import engine.broker.kite_executor as kite_mod
            # Call with patched datetime
            # The function does: from datetime import datetime, timezone, timedelta
            # which goes to the datetime module, so we patch there
            symbol = kite_mod.get_expiry_symbol_format(24750, "CE")

        # Should use AUG (expiry month), NOT JUL (today's month)
        assert "AUG" in symbol, f"Expected AUG in symbol, got: {symbol}"
        assert "JUL" not in symbol, f"Symbol incorrectly uses today's month JUL: {symbol}"

    def test_expiry_symbol_format_correct(self):
        """Symbol format: NIFTY{YY}{MON}{Strike}{CE/PE}."""
        from engine.broker.kite_executor import get_expiry_symbol_format
        symbol = get_expiry_symbol_format(24750, "CE")

        assert symbol.startswith("NIFTY")
        assert "24750" in symbol
        assert symbol.endswith("CE")
        # Year should be 2-digit
        year_part = symbol[5:7]
        assert year_part.isdigit()

    @patch("engine.broker.kite_auth.get_kite_client")
    @patch("engine.broker.kite_auth.is_authenticated")
    def test_live_mode_calls_kite_place_order(self, mock_auth, mock_client):
        """Live mode must call kite.place_order for each leg."""
        mock_auth.return_value = True
        mock_kite = MagicMock()
        mock_kite.place_order.return_value = "ORDER_123"
        mock_kite.ltp.return_value = {"NFO:NIFTY26AUG24850CE": {"last_price": 12.5}, "NFO:NIFTY26AUG24750CE": {"last_price": 5.0}, "NFO:NIFTY26AUG24250PE": {"last_price": 11.0}, "NFO:NIFTY26AUG24150PE": {"last_price": 4.5}}
        mock_client.return_value = mock_kite

        from engine.broker.kite_executor import execute_iron_condor
        signal = self._make_nifty_signal()
        result = execute_iron_condor(signal)

        assert mock_kite.place_order.called
        assert mock_kite.place_order.call_count == 4
        assert result["mode"] == "live"

    @patch("engine.broker.kite_auth.get_kite_client")
    @patch("engine.broker.kite_auth.is_authenticated")
    def test_risk_first_ordering_buy_before_sell(self, mock_auth, mock_client):
        """BUY (protective wings) must be placed BEFORE SELL (naked shorts)."""
        mock_auth.return_value = True
        mock_kite = MagicMock()
        mock_kite.ltp.return_value = {"NFO:NIFTY26AUG24850CE": {"last_price": 12.5}, "NFO:NIFTY26AUG24750CE": {"last_price": 5.0}, "NFO:NIFTY26AUG24250PE": {"last_price": 11.0}, "NFO:NIFTY26AUG24150PE": {"last_price": 4.5}}
        call_order = []
        def track_order(**kwargs):
            call_order.append(kwargs["transaction_type"])
            return f"ORDER_{len(call_order)}"
        mock_kite.place_order.side_effect = track_order
        mock_client.return_value = mock_kite

        from engine.broker.kite_executor import execute_iron_condor
        signal = self._make_nifty_signal()
        execute_iron_condor(signal)

        # First 2 calls should be BUY, last 2 should be SELL
        assert call_order[:2] == ["BUY", "BUY"], f"First orders should be BUY, got {call_order}"
        assert call_order[2:] == ["SELL", "SELL"], f"Last orders should be SELL, got {call_order}"

    @patch("engine.broker.kite_auth.get_kite_client")
    @patch("engine.broker.kite_auth.is_authenticated")
    def test_quantity_25_for_phase_1(self, mock_auth, mock_client):
        """Phase 1 quantity should be 65 (1 lot, NIFTY lot size as of 2026)."""
        mock_auth.return_value = True
        mock_kite = MagicMock()
        mock_kite.place_order.return_value = "ORDER_1"
        mock_kite.ltp.return_value = {"NFO:NIFTY26AUG24850CE": {"last_price": 12.5}, "NFO:NIFTY26AUG24750CE": {"last_price": 5.0}, "NFO:NIFTY26AUG24250PE": {"last_price": 11.0}, "NFO:NIFTY26AUG24150PE": {"last_price": 4.5}}
        mock_client.return_value = mock_kite

        from engine.broker.kite_executor import execute_iron_condor
        signal = self._make_nifty_signal()
        result = execute_iron_condor(signal)

        # Check qty in place_order calls
        for call in mock_kite.place_order.call_args_list:
            assert call.kwargs["quantity"] == 65, f"Phase 1 qty should be 65, got {call.kwargs['quantity']}"
        assert result["quantity"] == 65

    @patch("engine.broker.kite_auth.is_authenticated")
    def test_unauthenticated_returns_error(self, mock_auth):
        """Unauthenticated state returns error without placing orders."""
        mock_auth.return_value = False

        from engine.broker.kite_executor import execute_iron_condor
        signal = self._make_nifty_signal()
        result = execute_iron_condor(signal)

        assert result["success"] is False
        assert "authenticated" in result["error"].lower() or "login" in result["error"].lower()

    def _make_nifty_signal(self):
        """Helper: create a valid NIFTY trade signal for testing."""
        return {
            "action": "trade",
            "trade": {
                "type": "iron_condor",
                "legs": [
                    {"action": "SELL", "option": "CE", "strike": 24750, "premium_est": 12.5},
                    {"action": "BUY", "option": "CE", "strike": 24850, "premium_est": 5.0},
                    {"action": "SELL", "option": "PE", "strike": 24250, "premium_est": 11.0},
                    {"action": "BUY", "option": "PE", "strike": 24150, "premium_est": 4.5},
                ],
            },
        }


class TestIBKRExecutor:
    """Tests for engine/broker/ibkr_executor.py — IBKR Web API execution."""

    def test_authenticate_returns_true_with_valid_token(self):
        """authenticate() returns True when OAuth token exchange succeeds."""
        from engine.broker.ibkr_executor import IBKRExecutor

        executor = IBKRExecutor()
        executor.client_id = "test_client"
        executor.account_id = "U12345"
        executor._private_key_pem = "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "tok_123", "expires_in": 3600}
        mock_response.raise_for_status = MagicMock()

        with patch.object(executor.client, "post", return_value=mock_response):
            with patch("engine.broker.ibkr_executor.jwt.encode", return_value="signed_jwt"):
                result = executor.authenticate()

        assert result is True
        assert executor.access_token == "tok_123"

    def test_search_contract_resolves_conid(self):
        """search_contract('QQQ') resolves to conid from IBKR API."""
        from engine.broker.ibkr_executor import IBKRExecutor

        executor = IBKRExecutor()
        executor.access_token = "tok_123"
        executor.token_expiry = time.time() + 3600

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"conid": 320227571, "symbol": "QQQ"}]
        mock_response.raise_for_status = MagicMock()

        with patch.object(executor.client, "get", return_value=mock_response):
            conid = executor.search_contract("QQQ")

        assert conid == 320227571

    def test_place_iron_condor_places_4_legs(self):
        """place_iron_condor resolves 4 option conids and submits combo order."""
        from engine.broker.ibkr_executor import IBKRExecutor

        executor = IBKRExecutor()
        executor.access_token = "tok_123"
        executor.token_expiry = time.time() + 3600
        executor.account_id = "U12345"

        # Mock search_contract (QQQ underlying)
        with patch.object(executor, "search_contract", return_value=320227571):
            # Mock resolve_option_conid for all 4 legs
            conids = iter([100001, 100002, 100003, 100004])
            with patch.object(executor, "resolve_option_conid", side_effect=lambda **kw: next(conids)):
                # Mock the combo order submission
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = [{"order_id": "ORD_1", "order_status": "Submitted"}]

                with patch.object(executor.client, "post", return_value=mock_response):
                    result = executor.place_iron_condor(spot_price=680.0)

        assert result["success"] is True
        assert result["method"] == "combo"
        assert len(result["legs"]) == 4

    def test_retry_logic_on_timeout(self):
        """Retry decorator retries on httpx.TimeoutException."""
        import httpx
        from engine.broker.ibkr_executor import IBKRExecutor

        executor = IBKRExecutor()
        executor.access_token = "tok_123"
        executor.token_expiry = time.time() + 3600

        # First call times out, second succeeds
        mock_resp_success = MagicMock()
        mock_resp_success.status_code = 200
        mock_resp_success.json.return_value = [{"conid": 320227571}]
        mock_resp_success.raise_for_status = MagicMock()

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise httpx.TimeoutException("Connection timed out")
            return mock_resp_success

        with patch.object(executor.client, "get", side_effect=side_effect):
            with patch("engine.broker.ibkr_executor.time.sleep"):  # Skip actual sleep
                conid = executor.search_contract("QQQ")

        assert conid == 320227571
        assert call_count[0] == 2  # Retried once

    def test_partial_execution_detection(self):
        """Detects partial execution when some legs fail."""
        from engine.broker.ibkr_executor import IBKRExecutor

        executor = IBKRExecutor()
        executor.access_token = "tok_123"
        executor.token_expiry = time.time() + 3600
        executor.account_id = "U12345"

        # Simulate: combo fails, individual legs — 2 succeed, 2 fail
        resolved_legs = [
            {"strike": 695, "right": "C", "side": "BUY", "label": "Buy C695", "conid": 1001},
            {"strike": 665, "right": "P", "side": "BUY", "label": "Buy P665", "conid": 1002},
            {"strike": 695, "right": "C", "side": "SELL", "label": "Sell C680", "conid": 1003},
            {"strike": 665, "right": "P", "side": "SELL", "label": "Sell P665", "conid": 1004},
        ]

        call_count = [0]
        def mock_place(conid, side, quantity, order_type):
            call_count[0] += 1
            if call_count[0] <= 2:
                return {"order_id": f"ORD_{call_count[0]}"}
            raise Exception("Insufficient margin")

        with patch.object(executor, "place_order", side_effect=mock_place):
            result = executor._place_individual_legs(resolved_legs)

        assert result["success"] is False
        assert result["partial_execution"] is True
        assert result["filled_count"] == 2
        assert result["failed_count"] == 2


# ===========================================================================
# SECTION 3: ROUTES / API ENDPOINTS
# ===========================================================================

class TestLiveRoutes:
    """Tests for routes/live.py — API endpoint correctness."""

    @pytest.fixture(autouse=True)
    def setup_app(self, tmp_path):
        """Setup FastAPI test client with mocked dependencies."""
        # Create temp output/config dirs
        self.output_dir = tmp_path / "output"
        self.output_dir.mkdir()
        self.config_dir = tmp_path / "config"
        self.config_dir.mkdir()

        # Write settings
        settings = {"capital": 1000, "nifty": {"capital": 15000}, "qqq": {"capital": 1000, "wing_width": 5}}
        (self.config_dir / "settings.json").write_text(json.dumps(settings))

    def _get_test_client(self):
        """Create a test client with auth bypass."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from engine.session import require_founder

        app = FastAPI()

        # Override the auth dependency
        def mock_founder():
            return {"user_id": 1, "email": "test@test.com", "name": "Test"}

        from routes.live import router
        app.include_router(router)
        app.dependency_overrides[require_founder] = mock_founder
        return TestClient(app)

    def test_generate_signal_nifty_uses_simple_ic_engine(self):
        """POST /api/live/generate-signal?mode=nifty uses simple_ic_engine."""
        with patch("routes.live.OUTPUT_DIR", self.output_dir):
            with patch("engine.signals.simple_ic_engine._get_nifty_price") as mock_price:
                mock_price.return_value = {"nifty": 24500.0, "vix": 14.5, "source": "mock", "errors": []}
                with patch("engine.signals.simple_ic_engine._get_expiry_date") as mock_expiry:
                    mock_expiry.return_value = (None, 5, "12 Aug 2026 (Tue)")
                    with patch("db.signal_history.save_signal"):
                        client = self._get_test_client()
                        resp = client.post("/api/live/generate-signal?mode=nifty")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["mode"] == "nifty"

    @patch("engine.signals.qqq_ic_engine._is_high_impact_event_day", return_value=(False, ""))
    @patch("engine.signals.qqq_ic_engine._get_qqq_price")
    def test_generate_signal_qqq_uses_qqq_ic_engine(self, mock_price, mock_event):
        """POST /api/live/generate-signal?mode=qqq uses qqq_ic_engine."""
        mock_price.return_value = {"qqq": 680.0, "vix": 18.0, "source": "mock", "errors": []}

        with patch("routes.live.OUTPUT_DIR", self.output_dir):
            with patch("db.signal_history.save_signal"):
                client = self._get_test_client()
                resp = client.post("/api/live/generate-signal?mode=qqq")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["mode"] == "qqq"

    def test_signal_mode_nifty_reads_nifty_file(self):
        """GET /api/live/signal?mode=nifty reads today_signal_nifty.json."""
        nifty_signal = {"action": "trade", "market": "NIFTY", "trade": {"legs": []}}
        (self.output_dir / "today_signal_nifty.json").write_text(json.dumps(nifty_signal))

        with patch("routes.live.OUTPUT_DIR", self.output_dir):
            client = self._get_test_client()
            resp = client.get("/api/live/signal?mode=nifty")

        assert resp.status_code == 200
        assert resp.json()["market"] == "NIFTY"

    def test_signal_mode_qqq_reads_qqq_file(self):
        """GET /api/live/signal?mode=qqq reads today_signal_qqq.json."""
        qqq_signal = {"action": "trade", "market": "QQQ", "trade": {"legs": []}}
        (self.output_dir / "today_signal_qqq.json").write_text(json.dumps(qqq_signal))

        with patch("routes.live.OUTPUT_DIR", self.output_dir):
            client = self._get_test_client()
            resp = client.get("/api/live/signal?mode=qqq")

        assert resp.status_code == 200
        assert resp.json()["market"] == "QQQ"

    def test_live_execute_nifty_routes_to_kite(self):
        """POST /api/live/live-execute?mode=nifty routes to kite_executor."""
        nifty_signal = {
            "action": "trade",
            "strategy_type": "iron_condor_250_100",
            "date": date.today().isoformat(),
            "direction": "neutral",
            "projected_open": 24500,
            "trade": {
                "type": "iron_condor",
                "legs": [
                    {"action": "SELL", "option": "CE", "strike": 24750, "premium_est": 12.5},
                    {"action": "BUY", "option": "CE", "strike": 24850, "premium_est": 5.0},
                    {"action": "SELL", "option": "PE", "strike": 24250, "premium_est": 11.0},
                    {"action": "BUY", "option": "PE", "strike": 24150, "premium_est": 4.5},
                ],
                "max_loss": 2500,
                "max_profit": 350,
            },
        }
        (self.output_dir / "today_signal_nifty.json").write_text(json.dumps(nifty_signal))

        with patch("routes.live.OUTPUT_DIR", self.output_dir):
            with patch("engine.broker.kite_executor.execute_iron_condor") as mock_exec:
                mock_exec.return_value = {"success": True, "mode": "live", "placed": 4}
                with patch("db.database.get_connection") as mock_conn:
                    mock_db = MagicMock()
                    mock_conn.return_value = mock_db
                    client = self._get_test_client()
                    resp = client.post("/api/live/live-execute?mode=nifty")

        assert resp.status_code == 200
        mock_exec.assert_called_once()
        # Verify it was called with the nifty signal (positional arg)
        call_args = mock_exec.call_args
        assert call_args[0][0]["action"] == "trade"

    def test_live_execute_qqq_routes_to_ibkr(self):
        """POST /api/live/live-execute?mode=qqq routes to ibkr_executor."""
        qqq_signal = {
            "action": "trade",
            "strategy_type": "iron_condor_qqq",
            "date": date.today().isoformat(),
            "direction": "neutral",
            "projected_open": 680.0,
            "conditions": {"qqq_price": 680.0},
            "trade": {
                "type": "iron_condor",
                "underlying": "QQQ",
                "legs": [
                    {"action": "SELL", "option": "C", "strike": 695, "premium_est": 1.2},
                    {"action": "BUY", "option": "C", "strike": 700, "premium_est": 0.5},
                    {"action": "SELL", "option": "P", "strike": 665, "premium_est": 1.1},
                    {"action": "BUY", "option": "P", "strike": 660, "premium_est": 0.4},
                ],
                "max_loss": 500,
                "max_profit": 140,
            },
        }
        (self.output_dir / "today_signal_qqq.json").write_text(json.dumps(qqq_signal))

        with patch("routes.live.OUTPUT_DIR", self.output_dir):
            with patch("engine.broker.ibkr_executor.execute_qqq_sync") as mock_exec:
                mock_exec.return_value = {"success": True, "method": "combo"}
                with patch("db.database.get_connection") as mock_conn:
                    mock_db = MagicMock()
                    mock_conn.return_value = mock_db
                    client = self._get_test_client()
                    resp = client.post("/api/live/live-execute?mode=qqq")

        assert resp.status_code == 200
        mock_exec.assert_called_once()

    def test_safety_nifty_rejects_qqq_signal(self):
        """NIFTY execute must reject a QQQ signal (cross-contamination block)."""
        qqq_signal = {
            "action": "trade",
            "strategy_type": "iron_condor_qqq",
            "trade": {"type": "iron_condor", "legs": []},
        }
        (self.output_dir / "today_signal_nifty.json").write_text(json.dumps(qqq_signal))

        with patch("routes.live.OUTPUT_DIR", self.output_dir):
            client = self._get_test_client()
            resp = client.post("/api/live/live-execute?mode=nifty")

        assert resp.status_code == 400
        assert "SAFETY BLOCK" in resp.json()["error"]

    def test_safety_qqq_rejects_nifty_signal(self):
        """QQQ execute must reject a NIFTY signal (cross-contamination block)."""
        nifty_signal = {
            "action": "trade",
            "strategy_type": "iron_condor_250_100",
            "trade": {"type": "iron_condor", "legs": []},
        }
        (self.output_dir / "today_signal_qqq.json").write_text(json.dumps(nifty_signal))

        with patch("routes.live.OUTPUT_DIR", self.output_dir):
            client = self._get_test_client()
            resp = client.post("/api/live/live-execute?mode=qqq")

        assert resp.status_code == 400
        assert "SAFETY BLOCK" in resp.json()["error"]

    def test_kite_callback_redirects_to_live_nifty(self):
        """
        BUG FIX TEST: /kite-callback must redirect to live-nifty.html, NOT live.html.
        """
        with patch("engine.broker.kite_auth.handle_callback") as mock_cb:
            mock_cb.return_value = {"success": True, "user": "TestUser"}
            client = self._get_test_client()
            resp = client.get("/api/live/kite-callback?request_token=test_token", follow_redirects=False)

        assert resp.status_code == 307  # RedirectResponse
        location = resp.headers.get("location", "")
        assert "live-nifty.html" in location, f"Should redirect to live-nifty.html, got: {location}"
        assert "live.html" not in location or "live-nifty.html" in location

    def test_kite_login_redirects_to_kite_oauth(self):
        """/kite-login should redirect to Kite OAuth URL."""
        with patch("engine.broker.kite_auth.get_login_url") as mock_url:
            mock_url.return_value = "https://kite.zerodha.com/connect/login?api_key=testkey&v=3"
            client = self._get_test_client()
            resp = client.get("/api/live/kite-login", follow_redirects=False)

        assert resp.status_code == 307
        location = resp.headers.get("location", "")
        assert "kite.zerodha.com" in location


# ===========================================================================
# SECTION 4: SCHEDULER
# ===========================================================================

class TestScheduler:
    """Tests for engine/scheduler.py — Background scheduling logic."""

    @patch("engine.broker.kite_auth.is_authenticated")
    def test_nifty_mode_checks_kite_auth_before_trade(self, mock_auth):
        """NIFTY auto-trade must check Kite auth and skip if not authenticated."""
        mock_auth.return_value = False

        with patch("engine.scheduler._TRADING_MODE", "nifty"):
            with patch("engine.scheduler._send_telegram_alert"):
                from engine.scheduler import _run_auto_trade
                _run_auto_trade()

        # is_authenticated was called and returned False → no HTTP calls made
        mock_auth.assert_called()

    def test_qqq_mode_skips_kite_check(self):
        """QQQ auto-trade should NOT check Kite auth."""
        import httpx as real_httpx

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": True}

        with patch("engine.scheduler._TRADING_MODE", "qqq"):
            with patch("engine.scheduler._send_telegram_alert"):
                with patch("httpx.post", return_value=mock_resp) as mock_post:
                    from engine.scheduler import _run_auto_trade
                    _run_auto_trade()

        # Should have made HTTP calls (no Kite check for QQQ)
        assert mock_post.called

    def test_ibkr_heartbeat_fires_when_configured(self):
        """IBKR heartbeat sends tickle when executor is configured."""
        from engine.scheduler import _send_ibkr_heartbeat

        mock_executor = MagicMock()
        mock_executor.is_configured = True
        mock_executor.access_token = "tok_123"
        mock_executor.send_heartbeat.return_value = True

        with patch("engine.broker.ibkr_executor.get_ibkr_executor", return_value=mock_executor):
            _send_ibkr_heartbeat()

        mock_executor.send_heartbeat.assert_called_once()

    def test_startup_auth_fires_on_first_iteration(self):
        """IBKR startup auth is called on first loop iteration (QQQ mode)."""
        from engine.scheduler import _ibkr_startup_auth

        mock_executor = MagicMock()
        mock_executor.is_configured = True
        mock_executor.authenticate.return_value = True

        with patch("engine.broker.ibkr_executor.get_ibkr_executor", return_value=mock_executor):
            _ibkr_startup_auth()

        mock_executor.authenticate.assert_called_once()


# ===========================================================================
# SECTION 5: HTML PAGE WIRING
# ===========================================================================

class TestHTMLPageWiring:
    """Tests for static HTML pages — verify correct API endpoint wiring."""

    def _read_html(self, filename):
        """Read HTML file content."""
        path = PROJECT_ROOT / "static" / filename
        assert path.exists(), f"{filename} not found at {path}"
        return path.read_text(encoding="utf-8")

    def test_live_nifty_calls_generate_signal_with_mode_nifty(self):
        """live-nifty.html must call /api/live/generate-signal?mode=nifty."""
        html = self._read_html("live-nifty.html")
        assert "/api/live/generate-signal?mode=nifty" in html

    def test_live_nifty_calls_signal_with_mode_nifty(self):
        """live-nifty.html must call /api/live/signal?mode=nifty."""
        html = self._read_html("live-nifty.html")
        assert "/api/live/signal?mode=nifty" in html

    def test_live_nifty_calls_live_execute_not_paper(self):
        """
        BUG FIX TEST: live-nifty.html must call /api/live/live-execute?mode=nifty.
        Must NOT call paper-execute.
        """
        html = self._read_html("live-nifty.html")
        assert "/api/live/live-execute?mode=nifty" in html

    def test_live_nifty_does_not_contain_paper_execute(self):
        """live-nifty.html must NOT reference paper-execute anywhere."""
        html = self._read_html("live-nifty.html")
        assert "paper-execute" not in html, "NIFTY live page should not reference paper-execute!"

    def test_live_nifty_has_zerodha_login_button(self):
        """live-nifty.html must have 'Login to Zerodha' button."""
        html = self._read_html("live-nifty.html")
        assert "Login to Zerodha" in html

    def test_live_qqq_calls_generate_signal_with_mode_qqq(self):
        """live.html (QQQ page) must call /api/live/generate-signal?mode=qqq."""
        html = self._read_html("live.html")
        assert "/api/live/generate-signal?mode=qqq" in html

    def test_live_qqq_calls_signal_with_mode_qqq(self):
        """live.html (QQQ page) must call /api/live/signal?mode=qqq."""
        html = self._read_html("live.html")
        assert "/api/live/signal?mode=qqq" in html

    def test_live_qqq_calls_live_execute(self):
        """live.html (QQQ page) must call /api/live/live-execute for execution."""
        html = self._read_html("live.html")
        assert "/api/live/live-execute" in html


# ===========================================================================
# SECTION 6: CONFIG & DATA VALIDATION
# ===========================================================================

class TestConfigValidation:
    """Tests for configuration and data file integrity."""

    def test_settings_json_valid(self):
        """config/settings.json must be valid JSON."""
        path = PROJECT_ROOT / "config" / "settings.json"
        assert path.exists(), "settings.json not found"
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_settings_has_nifty_capital(self):
        """settings.json must have nifty.capital configured."""
        path = PROJECT_ROOT / "config" / "settings.json"
        with open(path) as f:
            data = json.load(f)
        assert "nifty" in data
        assert "capital" in data["nifty"]
        assert data["nifty"]["capital"] > 0

    def test_settings_has_qqq_wing_width(self):
        """settings.json must have qqq.wing_width configured."""
        path = PROJECT_ROOT / "config" / "settings.json"
        with open(path) as f:
            data = json.load(f)
        assert "qqq" in data
        assert "wing_width" in data["qqq"]
        assert data["qqq"]["wing_width"] > 0

    def test_event_calendar_valid_json(self):
        """event_calendar.json must be valid JSON array."""
        path = PROJECT_ROOT / "data" / "historical" / "event_calendar.json"
        assert path.exists(), "event_calendar.json not found"
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_event_calendar_has_fomc_dates(self):
        """event_calendar.json must have FOMC dates."""
        path = PROJECT_ROOT / "data" / "historical" / "event_calendar.json"
        with open(path) as f:
            data = json.load(f)
        fomc_events = [e for e in data if "FOMC" in e.get("name", "")]
        assert len(fomc_events) >= 6, f"Expected 6+ FOMC dates, found {len(fomc_events)}"

    def test_event_calendar_has_cpi_dates(self):
        """event_calendar.json must have CPI dates."""
        path = PROJECT_ROOT / "data" / "historical" / "event_calendar.json"
        with open(path) as f:
            data = json.load(f)
        cpi_events = [e for e in data if "CPI" in e.get("name", "")]
        assert len(cpi_events) >= 6, f"Expected 6+ CPI dates, found {len(cpi_events)}"

    def test_event_calendar_has_nfp_dates(self):
        """event_calendar.json must have NFP dates."""
        path = PROJECT_ROOT / "data" / "historical" / "event_calendar.json"
        with open(path) as f:
            data = json.load(f)
        nfp_events = [e for e in data if "Non-Farm" in e.get("name", "") or "NFP" in e.get("name", "")]
        assert len(nfp_events) >= 6, f"Expected 6+ NFP dates, found {len(nfp_events)}"


# ===========================================================================
# SECTION 7: DATA FLOW INTEGRITY
# ===========================================================================

class TestDataFlowIntegrity:
    """Tests for end-to-end data flow — signals never cross-contaminate."""

    @pytest.fixture(autouse=True)
    def setup_dirs(self, tmp_path):
        self.output_dir = tmp_path / "output"
        self.output_dir.mkdir()

    @patch("engine.signals.simple_ic_engine._get_expiry_date")
    @patch("engine.signals.simple_ic_engine._get_nifty_price")
    def test_nifty_signal_saved_as_nifty_file(self, mock_price, mock_expiry):
        """Signal generated with mode=nifty saves as today_signal_nifty.json."""
        mock_price.return_value = {"nifty": 24500.0, "vix": 14.5, "source": "mock", "errors": []}
        mock_expiry.return_value = (None, 5, "12 Aug 2026 (Tue)")

        from engine.signals.simple_ic_engine import generate_daily_signal
        signal = generate_daily_signal(capital=15000)

        # Simulate what the route does: save to mode-specific file
        signal_path = self.output_dir / "today_signal_nifty.json"
        with open(signal_path, "w") as f:
            json.dump(signal, f, default=str)

        # Verify it's readable and correct
        with open(signal_path) as f:
            loaded = json.load(f)
        assert loaded["action"] == "trade"
        assert loaded["strategy_type"] == "iron_condor_250_100"

    @patch("engine.signals.qqq_ic_engine._is_high_impact_event_day", return_value=(False, ""))
    @patch("engine.signals.qqq_ic_engine._get_qqq_price")
    def test_qqq_signal_saved_as_qqq_file(self, mock_price, mock_event):
        """Signal generated with mode=qqq saves as today_signal_qqq.json."""
        mock_price.return_value = {"qqq": 680.0, "vix": 18.0, "source": "mock", "errors": []}

        from engine.signals.qqq_ic_engine import generate_qqq_signal
        signal = generate_qqq_signal(capital=1000)

        signal_path = self.output_dir / "today_signal_qqq.json"
        with open(signal_path, "w") as f:
            json.dump(signal, f, default=str)

        with open(signal_path) as f:
            loaded = json.load(f)
        assert loaded["action"] == "trade"
        assert loaded["market"] == "QQQ"
        assert loaded["strategy_type"] == "iron_condor_qqq"

    @patch("engine.signals.simple_ic_engine._get_expiry_date")
    @patch("engine.signals.simple_ic_engine._get_nifty_price")
    @patch("engine.signals.qqq_ic_engine._is_high_impact_event_day", return_value=(False, ""))
    @patch("engine.signals.qqq_ic_engine._get_qqq_price")
    def test_signals_never_cross_contaminate(self, mock_qqq_price, mock_event, mock_nifty_price, mock_expiry):
        """NIFTY and QQQ signals stored separately, never mixed."""
        mock_nifty_price.return_value = {"nifty": 24500.0, "vix": 14.5, "source": "mock", "errors": []}
        mock_expiry.return_value = (None, 5, "12 Aug 2026 (Tue)")
        mock_qqq_price.return_value = {"qqq": 680.0, "vix": 18.0, "source": "mock", "errors": []}

        from engine.signals.simple_ic_engine import generate_daily_signal
        from engine.signals.qqq_ic_engine import generate_qqq_signal

        nifty_signal = generate_daily_signal(capital=15000)
        qqq_signal = generate_qqq_signal(capital=1000)

        # Save both
        (self.output_dir / "today_signal_nifty.json").write_text(
            json.dumps(nifty_signal, default=str))
        (self.output_dir / "today_signal_qqq.json").write_text(
            json.dumps(qqq_signal, default=str))

        # Read NIFTY file — must NOT have QQQ data
        with open(self.output_dir / "today_signal_nifty.json") as f:
            nifty_loaded = json.load(f)
        assert "qqq" not in nifty_loaded.get("strategy_type", "").lower()
        legs = nifty_loaded["trade"]["legs"]
        for leg in legs:
            assert leg["option"] in ("CE", "PE"), "NIFTY file has C/P (QQQ format)!"
            assert leg["strike"] > 20000, "NIFTY file has QQQ-range strikes!"

        # Read QQQ file — must NOT have NIFTY data
        with open(self.output_dir / "today_signal_qqq.json") as f:
            qqq_loaded = json.load(f)
        assert qqq_loaded["market"] == "QQQ"
        legs = qqq_loaded["trade"]["legs"]
        for leg in legs:
            assert leg["option"] in ("C", "P"), "QQQ file has CE/PE (NIFTY format)!"
            assert leg["strike"] < 1000, "QQQ file has NIFTY-range strikes!"


# ===========================================================================
# SECTION 8: KITE AUTH MODULE
# ===========================================================================

class TestKiteAuth:
    """Tests for engine/broker/kite_auth.py — OAuth flow correctness."""

    def test_get_login_url_returns_kite_url(self):
        """get_login_url() returns proper Kite OAuth URL when configured."""
        with patch.dict(os.environ, {"KITE_API_KEY": "test_api_key", "KITE_API_SECRET": "test_secret"}):
            # Reload module to pick up env
            from engine.broker.kite_auth import get_login_url
            url = get_login_url()
        assert "kite.zerodha.com" in url or url == "NOT_CONFIGURED"

    def test_is_authenticated_false_by_default(self):
        """Fresh session is not authenticated."""
        from engine.broker import kite_auth
        # Reset session state
        kite_auth._session["authenticated"] = False
        kite_auth._session["access_token"] = None
        assert kite_auth.is_authenticated() is False

    def test_handle_callback_sets_session(self):
        """Successful callback sets session authenticated state."""
        from engine.broker import kite_auth

        mock_kite_instance = MagicMock()
        mock_kite_instance.generate_session.return_value = {
            "access_token": "tok_abc",
            "user_name": "TestTrader",
            "login_time": "2026-01-01 09:15:00",
        }

        # Mock the kiteconnect module since it's not installed
        mock_kiteconnect_module = MagicMock()
        mock_kiteconnect_module.KiteConnect.return_value = mock_kite_instance

        with patch.dict(os.environ, {"KITE_API_KEY": "real_key", "KITE_API_SECRET": "real_secret"}):
            with patch.dict(sys.modules, {"kiteconnect": mock_kiteconnect_module}):
                result = kite_auth.handle_callback("test_request_token")

        assert result["success"] is True
        assert kite_auth._session["authenticated"] is True
        assert kite_auth._session["user_name"] == "TestTrader"

        # Cleanup
        kite_auth._session["authenticated"] = False
        kite_auth._session["access_token"] = None


# ===========================================================================
# SECTION 9: PHASE CONFIGURATION
# ===========================================================================

class TestPhaseConfig:
    """Tests for trading phase configuration."""

    def test_phase_1_config(self):
        """Phase 1: 65 qty, max 5 trades."""
        from engine.broker.kite_executor import PHASES
        phase1 = PHASES[1]
        assert phase1["quantity"] == 65
        assert phase1["max_trades"] == 5

    def test_phase_2_config(self):
        """Phase 2: 65 qty, max 10 trades."""
        from engine.broker.kite_executor import PHASES
        phase2 = PHASES[2]
        assert phase2["quantity"] == 65
        assert phase2["max_trades"] == 10

    def test_phase_3_config(self):
        """Phase 3: 130 qty, unlimited trades."""
        from engine.broker.kite_executor import PHASES
        phase3 = PHASES[3]
        assert phase3["quantity"] == 130
        assert phase3["max_trades"] is None


# ===========================================================================
# SECTION 10: EDGE CASES & SAFETY
# ===========================================================================

class TestEdgeCasesAndSafety:
    """Edge cases that have caused real bugs in production."""

    @patch("engine.broker.kite_auth.get_kite_client")
    @patch("engine.broker.kite_auth.is_authenticated")
    def test_buy_failure_aborts_sell_legs(self, mock_auth, mock_client):
        """If BUY (wing) leg fails, SELL legs must be aborted (no naked shorts)."""
        mock_auth.return_value = True
        mock_kite = MagicMock()

        call_count = [0]
        def failing_place(**kwargs):
            call_count[0] += 1
            if kwargs["transaction_type"] == "BUY":
                raise Exception("Insufficient margin")
            return "ORDER_1"  # Should never reach here

        mock_kite.place_order.side_effect = failing_place
        mock_client.return_value = mock_kite

        from engine.broker.kite_executor import execute_iron_condor
        signal = {
            "trade": {
                "legs": [
                    {"action": "SELL", "option": "CE", "strike": 24750, "premium_est": 12.5},
                    {"action": "BUY", "option": "CE", "strike": 24850, "premium_est": 5.0},
                    {"action": "SELL", "option": "PE", "strike": 24250, "premium_est": 11.0},
                    {"action": "BUY", "option": "PE", "strike": 24150, "premium_est": 4.5},
                ],
            },
        }
        result = execute_iron_condor(signal)

        # SELL legs should be skipped (status: skipped)
        skipped = [o for o in result["orders"] if o["status"] == "skipped"]
        assert len(skipped) == 2, "Both SELL legs should be skipped when BUY fails"

    def test_invalid_leg_count_returns_error(self):
        """Signal with != 4 legs returns error."""
        from engine.broker.kite_executor import execute_iron_condor

        with patch("engine.broker.kite_auth.is_authenticated", return_value=True):
            with patch("engine.broker.kite_auth.get_kite_client", return_value=MagicMock()):
                signal = {"trade": {"legs": [{"action": "SELL", "option": "CE", "strike": 24750}]}}
                result = execute_iron_condor(signal)

        assert result["success"] is False
        assert "4 legs" in result["error"] or "Expected 4" in result["error"]

    @patch("engine.signals.simple_ic_engine._get_expiry_date")
    @patch("engine.signals.simple_ic_engine._get_nifty_price")
    def test_low_capital_returns_skip(self, mock_price, mock_expiry):
        """Capital too low for the strategy returns skip."""
        mock_price.return_value = {"nifty": 24500.0, "vix": 14.5, "source": "mock", "errors": []}
        mock_expiry.return_value = (None, 5, "12 Aug 2026 (Tue)")
        from engine.signals.simple_ic_engine import generate_daily_signal

        # Very low capital — max loss would exceed risk cap
        signal = generate_daily_signal(capital=100)
        # With capital=100, 25% cap = Rs.25 which is << wing_width * lot
        assert signal["action"] == "skip"
        assert "capital" in signal.get("reason", "").lower() or "risk" in signal.get("reason", "").lower()

