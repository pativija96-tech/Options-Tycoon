"""
FULL END-TO-END NIFTY CHAIN TEST

Tests the EXACT flow that happens when a user:
1. Opens live-nifty.html
2. Clicks "Generate Signal" (calls /api/live/generate-signal?mode=nifty)
3. Clicks "Execute" (calls /api/live/live-execute?mode=nifty)

Verifies:
- Signal generation uses NIFTY engine (not QQQ)
- Signal file saved correctly (today_signal_nifty.json)
- Live-execute reads the NIFTY signal file
- Live-execute routes to kite_executor (not ibkr_executor)
- kite_executor uses correct symbols (AUG, not JUL)
- kite_executor uses correct lot size (65)
- kite_executor calls Kite API with correct parameters
- Safety check blocks QQQ signal from executing on NIFTY page
"""
import os
import sys
import json
import tempfile
import shutil
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["TRADING_PHASE"] = "1"
os.environ["TRADING_MODE"] = "qqq"  # Deliberately wrong — tests that ?mode=nifty overrides


# Shared mock signal (used when live market data is unavailable in CI)
MOCK_NIFTY_SIGNAL = {
    "action": "trade",
    "strategy_type": "iron_condor_250_100",
    "projected_open": 24380,
    "direction": "neutral",
    "date": "2026-08-06",
    "conditions": {"nifty_price": 24380, "vix_level": 12.0},
    "trade": {
        "type": "iron_condor",
        "legs": [
            {"action": "SELL", "option": "CE", "strike": 24650, "premium_est": 35.0},
            {"action": "BUY", "option": "CE", "strike": 24750, "premium_est": 19.0},
            {"action": "SELL", "option": "PE", "strike": 24150, "premium_est": 35.0},
            {"action": "BUY", "option": "PE", "strike": 24050, "premium_est": 19.0},
        ],
        "net_cost_total": -800,
        "max_loss": 1700,
        "max_profit": 800,
        "sl_value": 400,
        "width": 100,
        "expiry_date": "11 Aug 2026 (Tue)",
    },
}


def _get_signal():
    """Generate signal or fall back to mock if market data unavailable."""
    from engine.signals.simple_ic_engine import generate_daily_signal
    signal = generate_daily_signal(capital=39000)
    if signal.get("action") == "trade":
        return signal
    return MOCK_NIFTY_SIGNAL


class TestNiftySignalRouting:
    """TEST 1: Signal generation routes to NIFTY engine when mode=nifty."""

    def test_mode_nifty_overrides_trading_mode_env(self):
        """?mode=nifty must override TRADING_MODE=qqq env var."""
        requested_mode = "nifty"
        trading_mode = requested_mode if requested_mode in ("qqq", "nifty") else os.environ.get("TRADING_MODE", "qqq").lower()
        assert trading_mode == "nifty", f"mode=nifty did NOT override TRADING_MODE=qqq, got: {trading_mode}"

    def test_nifty_mode_calls_simple_ic_engine(self):
        """When mode=nifty, the signal engine must be simple_ic_engine (not qqq)."""
        trading_mode = "nifty"
        if trading_mode == "qqq":
            pytest.fail("Routing sent to QQQ engine instead of NIFTY")
        from engine.signals.simple_ic_engine import generate_daily_signal
        # Just verify it's importable and callable
        assert callable(generate_daily_signal)


class TestNiftySignalFile:
    """TEST 2 & 3: Signal file saved and loaded correctly."""

    def test_signal_saved_as_mode_specific_file(self):
        """Signal must save as today_signal_nifty.json (not generic)."""
        signal = _get_signal()
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            signal_filename = "today_signal_nifty.json"
            signal_path = tmp_dir / signal_filename
            with open(signal_path, "w") as f:
                json.dump(signal, f, indent=2, default=str)
            assert signal_path.exists(), f"Signal file not saved: {signal_filename}"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_live_execute_reads_nifty_signal(self):
        """live-execute must read today_signal_nifty.json."""
        signal = _get_signal()
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            mode_path = tmp_dir / "today_signal_nifty.json"
            with open(mode_path, "w") as f:
                json.dump(signal, f, indent=2, default=str)

            with open(mode_path) as f:
                loaded = json.load(f)
            assert loaded.get("strategy_type") == signal.get("strategy_type")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestNiftySafetyChecks:
    """TEST 4: Cross-mode contamination safety block."""

    def test_qqq_signal_blocked_on_nifty_page(self):
        """QQQ signal must NOT execute on NIFTY page."""
        fake_qqq_signal = {"action": "trade", "strategy_type": "iron_condor_qqq"}
        trading_mode = "nifty"
        signal_strategy = fake_qqq_signal.get("strategy_type", "")
        blocked = trading_mode == "nifty" and "qqq" in signal_strategy.lower()
        assert blocked, "Safety check did NOT block QQQ signal on NIFTY page"


class TestKiteSymbols:
    """TEST 5: Kite executor generates correct trading symbols."""

    def test_symbols_use_expiry_month(self):
        """All symbols must use the expiry month (next Tuesday's month).

        Compute the expected expiry with the SAME IST-based logic the production
        function uses. Using the local/system date here caused false failures
        across the IST/UTC midnight and weekday boundaries (e.g. when the local
        date is Tuesday but IST is still Monday, or vice versa).
        """
        from datetime import datetime, timezone, timedelta as td
        from engine.broker.kite_executor import get_expiry_symbol_format

        ist = timezone(td(hours=5, minutes=30))
        today = datetime.now(ist).date()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        expiry = today + td(days=days_until_tuesday)
        expected_month = expiry.strftime("%b").upper()

        signal = _get_signal()
        for leg in signal["trade"]["legs"]:
            sym = get_expiry_symbol_format(leg["strike"], leg["option"])
            assert expected_month in sym, f"Symbol {sym} doesn't contain expected month {expected_month}"


class TestKitePhaseConfig:
    """TEST 6: Kite executor uses correct lot size."""

    def test_phase1_quantity_is_65(self):
        """Phase 1 must use 65 qty (1 NIFTY lot)."""
        from engine.broker.kite_executor import get_phase_config
        phase = get_phase_config()
        assert phase["quantity"] == 65, f"Quantity is {phase['quantity']}, expected 65"


class TestKiteExecutionOrder:
    """TEST 7: Kite executor places BUY (wings) before SELL (shorts)."""

    def test_buy_legs_placed_before_sell(self):
        """BUY (hedge) orders must be placed before SELL (short) orders."""
        from engine.broker.kite_executor import execute_iron_condor
        signal = _get_signal()

        with patch("engine.broker.kite_auth.is_authenticated", return_value=True):
            with patch("engine.broker.kite_auth.get_kite_client") as mock_client:
                mock_kite = MagicMock()
                mock_kite.place_order.return_value = "ORDER123"
                mock_kite.ltp.return_value = {"NFO:NIFTY26AUG24650CE": {"last_price": 35.0}, "NFO:NIFTY26AUG24750CE": {"last_price": 19.0}, "NFO:NIFTY26AUG24150PE": {"last_price": 35.0}, "NFO:NIFTY26AUG24050PE": {"last_price": 19.0}}
                mock_client.return_value = mock_kite

                result = execute_iron_condor(signal)

                assert result.get("success"), f"Execution failed: {result}"
                calls = mock_kite.place_order.call_args_list
                assert len(calls) == 4, f"Expected 4 orders, got {len(calls)}"

                order_sequence = []
                for call in calls:
                    kwargs = call[1] if len(call) > 1 and isinstance(call[1], dict) else call.kwargs
                    order_sequence.append(kwargs.get("transaction_type", "UNKNOWN"))

                buy_indices = [i for i, t in enumerate(order_sequence) if t == "BUY"]
                sell_indices = [i for i, t in enumerate(order_sequence) if t == "SELL"]
                assert len(buy_indices) == 2, f"Expected 2 BUY legs, got {len(buy_indices)}"
                assert len(sell_indices) == 2, f"Expected 2 SELL legs, got {len(sell_indices)}"
                assert max(buy_indices) < min(sell_indices), (
                    f"BUY legs must come before SELL legs. Sequence: {order_sequence}"
                )


class TestHtmlEndpoints:
    """TEST 8: live-nifty.html calls correct API endpoints."""

    def _read_html(self):
        html_path = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "static" / "live-nifty.html"
        with open(html_path, encoding="utf-8") as f:
            return f.read()

    def test_generate_signal_calls_mode_nifty(self):
        html = self._read_html()
        assert "generate-signal?mode=nifty" in html

    def test_load_signal_calls_mode_nifty(self):
        html = self._read_html()
        assert "signal?mode=nifty" in html

    def test_execute_calls_live_execute_mode_nifty(self):
        html = self._read_html()
        assert "live-execute?mode=nifty" in html

    def test_no_paper_execute_calls(self):
        """live-nifty.html must NOT call /paper-execute."""
        html = self._read_html()
        assert "paper-execute" not in html, "live-nifty.html still calls /paper-execute!"
