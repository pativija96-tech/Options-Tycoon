"""
Phase 1 trading desk: Trading Plan storage, Trade Ticket logic, desk endpoints,
and the scheduled-jobs switch.

Run: python -m pytest tests/test_desk.py -v
"""

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.desk.plan import validate_plan, PlanError, default_plan  # noqa: E402
from engine.desk.ticket import build_ticket, subtract_trading_days  # noqa: E402


# Aug 26 2026 (a Wednesday) trade from the BRD: 24000/24100 PE, 24600/24700 CE.
def make_signal(live=True, action="trade"):
    if action != "trade":
        return {"action": "skip", "reason": "VIX too high", "conditions": {"nifty_price": 24350, "vix_level": 41}}
    return {
        "action": "trade",
        "conditions": {"nifty_price": 24350.0, "vix_level": 11.2,
                       "data_source": "kite" if live else "yfinance", "data_is_live": live},
        "trade": {
            "width": 100,
            "legs": [
                {"action": "SELL", "option": "CE", "strike": 24600, "premium_est": 40.0},
                {"action": "BUY", "option": "CE", "strike": 24700, "premium_est": 20.0},
                {"action": "SELL", "option": "PE", "strike": 24100, "premium_est": 22.0},
                {"action": "BUY", "option": "PE", "strike": 24000, "premium_est": 12.0},
            ],
            "charges": {"total": 239},
        },
    }


SYMBOLS = {(24000, "PE"): "NIFTY2690124000PE", (24100, "PE"): "NIFTY2690124100PE",
           (24600, "CE"): "NIFTY2690124600CE", (24700, "CE"): "NIFTY2690124700CE"}
QUOTES = {"NIFTY2690124000PE": {"ltp": 12.60, "bid": 12.5, "ask": 12.7},
          "NIFTY2690124700CE": {"ltp": 22.55, "bid": 22.4, "ask": 22.6},
          "NIFTY2690124100PE": {"ltp": 20.50, "bid": 20.4, "ask": 20.6},
          "NIFTY2690124600CE": {"ltp": 42.45, "bid": 42.3, "ask": 42.6}}
WED = date(2026, 8, 26)


def full_plan(**over):
    plan = validate_plan({
        "entry_days": ["Wed"], "vix_min": 10, "vix_max": 22, "min_credit": 1500, "min_rr": 0.6,
        "max_loss_per_trade": 5000, "profit_target_pct": 0.5, "loss_exit_rupees": 1500,
        "exit_days_before_expiry": 1, "expiry_margin_buffer": 54000, "events": [],
    })
    plan.update(over)
    return plan


def check(ticket, key):
    return next(c for c in ticket["checks"] if c["key"] == key)


# ── Plan validation ─────────────────────────────────────────────────────────

class TestPlanValidation:
    def test_defaults_leave_user_rules_unset(self):
        plan = default_plan()
        assert plan["entry_days"] == [] and plan["events"] == []
        for key in ("vix_min", "vix_max", "min_credit", "min_rr", "loss_exit_rupees"):
            assert plan[key] is None

    def test_valid_plan_is_cleaned(self):
        plan = validate_plan({"entry_days": ["Wed", "Tue"], "min_rr": "0.6", "unknown_key": 5,
                              "events": [{"date": "2026-10-01", "label": " RBI policy "}]})
        assert plan["entry_days"] == ["Tue", "Wed"]
        assert plan["min_rr"] == 0.6
        assert "unknown_key" not in plan
        assert plan["events"] == [{"date": "2026-10-01", "label": "RBI policy"}]

    @pytest.mark.parametrize("raw", [
        {"entry_days": ["Sat"]}, {"min_rr": "abc"}, {"min_credit": -1}, {"profit_target_pct": 1.5},
        {"vix_min": 25, "vix_max": 20}, {"events": [{"date": "01/10/2026"}]}, "not a dict",
    ])
    def test_invalid_values_rejected(self, raw):
        with pytest.raises(PlanError):
            validate_plan(raw)


class TestPlanStorage:
    @pytest.fixture(autouse=True)
    def temp_db(self, tmp_path, monkeypatch):
        import db.database as dbm
        if dbm.USE_POSTGRES:
            pytest.skip("storage test runs on SQLite only")
        path = str(tmp_path / "test.db")
        monkeypatch.setattr(dbm, "get_db_path", lambda: path)
        dbm.init_db(path)
        from db.migrations import run_migrations
        run_migrations()

    def test_save_then_load_round_trips_per_user(self):
        from engine.desk.plan import save_plan, load_plan
        save_plan(1, {"entry_days": ["Wed"], "min_rr": 0.6})
        save_plan(1, {"entry_days": ["Tue"], "min_rr": 0.7})   # upsert, not a second row
        save_plan(2, {"min_credit": 2000})
        assert load_plan(1)["entry_days"] == ["Tue"] and load_plan(1)["min_rr"] == 0.7
        assert load_plan(2)["min_credit"] == 2000 and load_plan(2)["entry_days"] == []
        assert load_plan(3)["min_rr"] is None                  # no row → defaults


# ── Ticket logic ────────────────────────────────────────────────────────────

class TestTicket:
    def test_live_prices_drive_credit_and_orders(self):
        t = build_ticket(make_signal(), full_plan(), WED, symbols=SYMBOLS, quotes=QUOTES,
                         expiry=date(2026, 9, 1), kite_connected=True)
        assert t["pricing"] == "kite_live"
        # 20.50 + 42.45 − 12.60 − 22.55 = 27.80 per share (the real Aug 26 credit)
        assert t["credit_per_share"] == 27.80
        assert t["credit"] == pytest.approx(1807.0)
        assert t["max_loss"] == pytest.approx(4693.0)
        assert t["reward_risk"] == pytest.approx(0.39, abs=0.01)
        assert [(o["side"], o["strike"], o["option"]) for o in t["orders"]] == [
            ("BUY", 24000, "PE"), ("BUY", 24700, "CE"), ("SELL", 24100, "PE"), ("SELL", 24600, "CE")]
        assert t["orders"][0]["symbol"] == "NIFTY2690124000PE"

    def test_rr_below_plan_is_no_go_and_named(self):
        t = build_ticket(make_signal(), full_plan(), WED, symbols=SYMBOLS, quotes=QUOTES, expiry=date(2026, 9, 1))
        assert t["verdict"] == "NO-GO"
        assert check(t, "min_rr")["status"] == "fail"
        assert "Reward : risk at or above your minimum" in t["failed"]

    def test_clean_day_is_go(self):
        t = build_ticket(make_signal(), full_plan(min_rr=0.3), WED, symbols=SYMBOLS, quotes=QUOTES,
                         expiry=date(2026, 9, 1), margin_required=67234, funds_available=130000, kite_connected=True)
        assert t["verdict"] == "GO", t["failed"]
        assert check(t, "margin")["status"] == "pass"

    def test_without_kite_uses_estimates_and_says_so(self):
        t = build_ticket(make_signal(live=False), full_plan(min_rr=0.3), WED)
        assert t["pricing"] == "estimate"
        assert t["credit_per_share"] == 30.0           # 22 + 40 − 12 − 20
        assert check(t, "prices_live")["status"] == "unknown"
        assert check(t, "data_live")["status"] == "fail"
        assert check(t, "margin")["status"] == "unknown"
        assert t["expiry"] == "2026-09-01" and t["expiry_confirmed"] is False

    def test_unset_rules_never_fail(self):
        t = build_ticket(make_signal(), default_plan(), WED, symbols=SYMBOLS, quotes=QUOTES, expiry=date(2026, 9, 1))
        for key in ("entry_day", "vix", "events", "min_credit", "min_rr"):
            assert check(t, key)["status"] == "unset"
        assert t["unset_count"] >= 5

    def test_wrong_entry_day_and_vix_fail(self):
        t = build_ticket(make_signal(), full_plan(entry_days=["Tue"], vix_min=12), WED,
                         symbols=SYMBOLS, quotes=QUOTES, expiry=date(2026, 9, 1))
        assert check(t, "entry_day")["status"] == "fail"
        assert check(t, "vix")["status"] == "fail"

    def test_event_before_expiry_fails_after_expiry_passes(self):
        plan = full_plan(events=[{"date": "2026-08-28", "label": "RBI policy"}])
        t = build_ticket(make_signal(), plan, WED, expiry=date(2026, 9, 1))
        assert check(t, "events")["status"] == "fail" and "RBI policy" in check(t, "events")["detail"]
        plan = full_plan(events=[{"date": "2026-09-05", "label": "Later"}])
        assert check(build_ticket(make_signal(), plan, WED, expiry=date(2026, 9, 1)), "events")["status"] == "pass"

    def test_margin_shortfall_fails(self):
        t = build_ticket(make_signal(), full_plan(), WED, symbols=SYMBOLS, quotes=QUOTES, expiry=date(2026, 9, 1),
                         margin_required=67234, funds_available=100000, kite_connected=True)
        assert check(t, "margin")["status"] == "fail"   # 67,234 + 54,000 buffer > 1,00,000

    def test_exit_plan_from_plan_values(self):
        t = build_ticket(make_signal(), full_plan(), WED, symbols=SYMBOLS, quotes=QUOTES, expiry=date(2026, 9, 1))
        ep = t["exit_plan"]
        assert ep["target"]["profit"] == pytest.approx(903.5)
        assert ep["target"]["buyback_total"] == pytest.approx(903.5)
        assert ep["target"]["buyback_per_share"] == pytest.approx(13.9)
        assert ep["loss_exit"] == 1500
        assert ep["exit_by"] == "2026-08-31"            # Tue 1 Sep minus 1 trading day = Mon

    def test_skip_signal_becomes_no_trade(self):
        t = build_ticket(make_signal(action="skip"), full_plan(), WED)
        assert t["action"] == "skip" and t["verdict"] == "NO TRADE" and "VIX" in t["skip_reason"]

    def test_partial_quotes_fall_back_to_estimates(self):
        quotes = {k: v for k, v in QUOTES.items() if not k.endswith("24700CE")}
        t = build_ticket(make_signal(), full_plan(), WED, symbols=SYMBOLS, quotes=quotes, expiry=date(2026, 9, 1))
        assert t["pricing"] == "estimate"

    def test_subtract_trading_days_skips_weekends(self):
        assert subtract_trading_days(date(2026, 9, 1), 1) == date(2026, 8, 31)   # Tue → Mon
        assert subtract_trading_days(date(2026, 8, 31), 1) == date(2026, 8, 28)  # Mon → Fri


# ── Kite helpers (mocked Kite) ──────────────────────────────────────────────

class TestKiteData:
    def setup_method(self):
        from engine.desk import kite_data
        kite_data._instrument_cache.update(day=None, rows=None)

    def _kite(self):
        kite = MagicMock()
        rows = []
        for exp, prefix in ((date(2026, 9, 1), "NIFTY26901"), (date(2026, 9, 8), "NIFTY26908")):
            for strike in (24000, 24100, 24600, 24700):
                for typ in ("CE", "PE"):
                    rows.append({"name": "NIFTY", "instrument_type": typ, "strike": float(strike),
                                 "expiry": exp, "tradingsymbol": f"{prefix}{strike}{typ}"})
        rows.append({"name": "BANKNIFTY", "instrument_type": "CE", "strike": 24000.0, "expiry": date(2026, 8, 27), "tradingsymbol": "X"})
        kite.instruments.return_value = rows
        return kite

    def test_resolve_symbols_uses_nearest_future_expiry(self):
        from engine.desk.kite_data import resolve_symbols
        legs = [{"strike": 24000, "option": "PE"}, {"strike": 24600, "option": "CE"}]
        errors = []
        expiry, syms = resolve_symbols(self._kite(), legs, WED, errors)
        assert expiry == date(2026, 9, 1) and not errors
        assert syms == {(24000, "PE"): "NIFTY2690124000PE", (24600, "CE"): "NIFTY2690124600CE"}

    def test_missing_contract_reported(self):
        from engine.desk.kite_data import resolve_symbols
        errors = []
        _, syms = resolve_symbols(self._kite(), [{"strike": 25000, "option": "CE"}], WED, errors)
        assert syms is None and "25000 CE" in errors[0]

    def test_quote_failure_is_reported_not_raised(self):
        from engine.desk.kite_data import fetch_quotes
        kite = MagicMock()
        kite.quote.side_effect = Exception("Insufficient permission")
        errors = []
        assert fetch_quotes(kite, ["A"], errors) is None and "Insufficient permission" in errors[0]

    def test_quotes_parse_ltp_and_depth(self):
        from engine.desk.kite_data import fetch_quotes
        kite = MagicMock()
        kite.quote.return_value = {"NFO:A": {"last_price": 20.5, "depth": {"buy": [{"price": 20.4}], "sell": [{"price": 20.6}]}}}
        assert fetch_quotes(kite, ["A"], []) == {"A": {"ltp": 20.5, "bid": 20.4, "ask": 20.6}}


# ── Endpoints ───────────────────────────────────────────────────────────────

class TestDeskEndpoints:
    @pytest.fixture(autouse=True)
    def client(self, tmp_path, monkeypatch):
        import db.database as dbm
        if dbm.USE_POSTGRES:
            pytest.skip("endpoint test runs on SQLite only")
        path = str(tmp_path / "test.db")
        monkeypatch.setattr(dbm, "get_db_path", lambda: path)
        dbm.init_db(path)
        from db.migrations import run_migrations
        run_migrations()

        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from engine.session import require_founder
        from routes.live import router
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_founder] = lambda: {"user_id": 7, "email": "test@test.com", "name": "T"}
        self.c = TestClient(app)
        self.out = tmp_path / "output"
        self.out.mkdir()

    def test_plan_get_put_round_trip(self):
        assert self.c.get("/api/live/plan").json()["plan"]["min_rr"] is None
        r = self.c.put("/api/live/plan", json={"plan": {"min_rr": 0.6, "entry_days": ["Wed"]}})
        assert r.status_code == 200 and r.json()["plan"]["min_rr"] == 0.6
        assert self.c.get("/api/live/plan").json()["plan"]["entry_days"] == ["Wed"]

    def test_plan_put_rejects_bad_values(self):
        r = self.c.put("/api/live/plan", json={"plan": {"min_rr": "abc"}})
        assert r.status_code == 400 and "number" in r.json()["error"]

    def test_trade_ticket_without_kite(self):
        sig = make_signal(live=False)

        async def fake_generate(request, mode=None):
            (self.out / "today_signal_nifty.json").write_text(json.dumps(sig))
            return {"success": True}

        with patch("routes.live.OUTPUT_DIR", self.out), patch("routes.live.generate_signal", fake_generate), \
             patch("engine.broker.kite_auth.is_authenticated", return_value=False):
            r = self.c.post("/api/live/trade-ticket")
        assert r.status_code == 200
        t = r.json()["ticket"]
        assert t["action"] == "trade" and t["pricing"] == "estimate"
        assert any("Not logged in to Kite" in n for n in t["kite_notes"])

    def test_trade_ticket_reports_signal_failure(self):
        from fastapi.responses import JSONResponse

        async def failing(request, mode=None):
            return JSONResponse(status_code=500, content={"success": False, "error": "boom"})

        with patch("routes.live.generate_signal", failing):
            r = self.c.post("/api/live/trade-ticket")
        assert r.status_code == 502 and "boom" in r.json()["error"]


# ── Scheduler switch ────────────────────────────────────────────────────────

class TestScheduledJobsSwitch:
    @pytest.mark.parametrize("value,expected", [(None, False), ("", False), ("0", False), ("false", False),
                                                ("1", True), ("true", True), ("YES", True)])
    def test_flag(self, monkeypatch, value, expected):
        from engine.scheduler import _scheduled_jobs_enabled
        if value is None:
            monkeypatch.delenv("SCHEDULED_JOBS_ENABLED", raising=False)
        else:
            monkeypatch.setenv("SCHEDULED_JOBS_ENABLED", value)
        assert _scheduled_jobs_enabled() is expected
