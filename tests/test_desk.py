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

from engine.desk.plan import validate_plan, PlanError, default_plan, engine_plan  # noqa: E402
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
            "elm_estimate": {"additional_est": 53600, "total_requirement_est": 120600},
        },
        "risk_check": {"capital": 75000},
    }


SYMBOLS = {(24000, "PE"): "NIFTY2690124000PE", (24100, "PE"): "NIFTY2690124100PE",
           (24600, "CE"): "NIFTY2690124600CE", (24700, "CE"): "NIFTY2690124700CE"}
_TRADED = {"last_trade_time": "2026-08-26 09:25:00", "quote_time": "2026-08-26 09:25:30"}
QUOTES = {"NIFTY2690124000PE": {"ltp": 12.60, "bid": 12.5, "ask": 12.7, **_TRADED},
          "NIFTY2690124700CE": {"ltp": 22.55, "bid": 22.4, "ask": 22.6, **_TRADED},
          "NIFTY2690124100PE": {"ltp": 20.50, "bid": 20.4, "ask": 20.6, **_TRADED},
          "NIFTY2690124600CE": {"ltp": 42.45, "bid": 42.3, "ask": 42.6, **_TRADED}}
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
    def test_default_plan_is_the_book_rules(self):
        from engine.desk.book_rules import book_preset
        from engine.desk.kite_data import ist_today
        plan, book = default_plan(), book_preset(ist_today())
        for key, value in book["values"].items():
            assert plan[key] == value, key
        for key in book["not_filled"]:                     # no reliable book number → stays unset
            assert plan[key] is None, key

    def test_engine_plan_leaves_user_rules_unset(self):
        plan = engine_plan()
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
        assert load_plan(2)["min_credit"] == 2000 and load_plan(2)["entry_days"] == ["Tue"]   # rest = book default
        assert load_plan(3)["min_rr"] == 0.5                   # no row → book-rules default


# ── Ticket logic ────────────────────────────────────────────────────────────

class TestTicket:
    def test_live_prices_drive_credit_and_orders(self):
        t = build_ticket(make_signal(), full_plan(), WED, symbols=SYMBOLS, quotes=QUOTES,
                         expiry=date(2026, 9, 1), kite_connected=True)
        assert t["pricing"] == "kite_live"
        # Sells at bid, buys at ask: 20.40 + 42.30 − 12.70 − 22.60 = 27.40 per share
        # (at last traded prices these legs gave 27.80, the real Aug 26 credit)
        assert t["credit_per_share"] == 27.40
        assert t["credit"] == pytest.approx(1781.0)
        assert t["max_loss"] == pytest.approx(4719.0)
        assert t["reward_risk"] == pytest.approx(0.38)
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
                         expiry=date(2026, 9, 1), margin_required=67234, funds_available=140000, kite_connected=True)
        assert t["verdict"] == "GO", t["failed"]
        assert check(t, "margin")["status"] == "pass"

    def test_without_kite_uses_estimates_and_says_so(self):
        t = build_ticket(make_signal(live=False), full_plan(min_rr=0.3), WED)
        assert t["pricing"] == "estimate"
        assert t["credit_per_share"] == 30.0           # 22 + 40 − 12 − 20
        assert check(t, "prices_live")["status"] == "unknown"
        assert check(t, "data_live")["status"] == "unknown"   # a warning, not a NO-GO
        assert check(t, "margin")["status"] == "unknown"
        assert t["expiry"] == "2026-09-01" and t["expiry_confirmed"] is False

    def test_unset_rules_never_fail(self):
        t = build_ticket(make_signal(), engine_plan(), WED, symbols=SYMBOLS, quotes=QUOTES, expiry=date(2026, 9, 1))
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

    def test_margin_below_entry_with_cushion_fails(self):
        t = build_ticket(make_signal(), full_plan(), WED, symbols=SYMBOLS, quotes=QUOTES, expiry=date(2026, 9, 1),
                         margin_required=67234, funds_available=80000, kite_connected=True)
        assert check(t, "margin")["status"] == "fail"   # 67,234 × 1.2 = 80,681 > 80,000

    def test_exit_plan_from_plan_values(self):
        t = build_ticket(make_signal(), full_plan(), WED, symbols=SYMBOLS, quotes=QUOTES, expiry=date(2026, 9, 1))
        ep = t["exit_plan"]
        assert ep["target"]["profit"] == pytest.approx(890.5)
        assert ep["target"]["buyback_total"] == pytest.approx(890.5)
        assert ep["target"]["buyback_per_share"] == pytest.approx(13.7)
        assert ep["loss_exit"] == 1500
        assert ep["exit_by"] == "2026-08-31"            # Tue 1 Sep minus 1 trading day = Mon

    def test_skip_signal_becomes_no_trade(self):
        t = build_ticket(make_signal(action="skip"), full_plan(), WED)
        assert t["action"] == "skip" and t["verdict"] == "NO TRADE" and "VIX" in t["skip_reason"]

    def test_partial_quotes_fall_back_to_estimates(self):
        quotes = {k: v for k, v in QUOTES.items() if not k.endswith("24700CE")}
        t = build_ticket(make_signal(), full_plan(), WED, symbols=SYMBOLS, quotes=quotes, expiry=date(2026, 9, 1))
        assert t["pricing"] == "estimate"

    def test_profit_target_net_of_charges(self):
        t = build_ticket(make_signal(), full_plan(), WED, symbols=SYMBOLS, quotes=QUOTES, expiry=date(2026, 9, 1))
        assert t["exit_plan"]["target"]["profit_net"] == pytest.approx(890.5 - 239)

    def test_orders_are_nrml_and_elm_shown(self):
        t = build_ticket(make_signal(), full_plan(), WED, symbols=SYMBOLS, quotes=QUOTES, expiry=date(2026, 9, 1))
        assert all(o["product"] == "NRML" for o in t["orders"])
        assert t["elm_estimate"]["additional_est"] == 53600


# ── Audit fixes: the desk must not be stricter than the signal engine ───────

class TestMatchesSignalEngine:
    def test_engine_plan_has_only_engine_rules(self):
        plan = engine_plan()
        assert plan["max_loss_per_trade"] is None       # settings value is display-only in the engine
        assert plan["profit_target_pct"] == 0.5         # settings.json nifty.profit_target_pct
        assert plan["exit_days_before_expiry"] == 1     # engine: exit before expiry morning

    def test_engine_plan_passes_the_real_aug_26_trade(self):
        # Credit 27.40 at bid/ask → max loss 4,719: the engine accepted it (cap 25% of 75,000 = 18,750).
        t = build_ticket(make_signal(), engine_plan(), WED, symbols=SYMBOLS, quotes=QUOTES, expiry=date(2026, 9, 1))
        assert t["max_loss"] == pytest.approx(4719.0)
        assert t["verdict"] == "GO", t["failed"]
        assert check(t, "risk_cap")["status"] == "pass"
        assert check(t, "covers_charges")["status"] == "pass"
        assert t["exit_plan"]["exit_by"] == "2026-08-31"

    def test_delayed_data_alone_is_not_no_go(self):
        t = build_ticket(make_signal(live=False), engine_plan(), WED)
        assert t["verdict"] == "GO", t["failed"]

    def test_risk_cap_rechecked_on_live_prices(self):
        sig = make_signal()
        sig["risk_check"]["capital"] = 15000             # cap 3,750 < max loss 4,693
        t = build_ticket(sig, engine_plan(), WED, symbols=SYMBOLS, quotes=QUOTES, expiry=date(2026, 9, 1))
        assert check(t, "risk_cap")["status"] == "fail" and t["verdict"] == "NO-GO"

    def test_charges_rechecked_on_live_prices(self):
        sig = make_signal()
        sig["trade"]["charges"]["total"] = 2000          # more than the 1,807 credit
        t = build_ticket(sig, engine_plan(), WED, symbols=SYMBOLS, quotes=QUOTES, expiry=date(2026, 9, 1))
        assert check(t, "covers_charges")["status"] == "fail" and t["verdict"] == "NO-GO"

    def test_engine_checks_unknown_without_capital_or_charges(self):
        sig = make_signal()
        del sig["risk_check"]
        del sig["trade"]["charges"]
        t = build_ticket(sig, engine_plan(), WED, symbols=SYMBOLS, quotes=QUOTES, expiry=date(2026, 9, 1))
        assert check(t, "risk_cap")["status"] == "unknown"
        assert check(t, "covers_charges")["status"] == "unknown"

    def test_ticket_uses_engine_risk_cap_constant(self):
        from engine.signals.simple_ic_engine import RISK_CAP_PCT
        assert RISK_CAP_PCT == 0.25

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
        kite.quote.return_value = {"NFO:A": {"last_price": 20.5, "last_trade_time": "2026-11-03 10:00:00",
                                             "timestamp": "2026-11-03 10:00:05",
                                             "depth": {"buy": [{"price": 20.4}], "sell": [{"price": 20.6}]}}}
        assert fetch_quotes(kite, ["A"], []) == {"A": {"ltp": 20.5, "bid": 20.4, "ask": 20.6,
                                                       "last_trade_time": "2026-11-03 10:00:00",
                                                       "quote_time": "2026-11-03 10:00:05"}}

    def test_empty_depth_levels_are_no_bid_or_ask(self):
        from engine.desk.kite_data import fetch_quotes
        kite = MagicMock()
        kite.quote.return_value = {"NFO:A": {"last_price": 20.5, "depth": {"buy": [{"price": 0}], "sell": [{"price": 0}]}}}
        q = fetch_quotes(kite, ["A"], [])["A"]
        assert q["bid"] is None and q["ask"] is None


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
        assert self.c.get("/api/live/plan").json()["plan"]["min_rr"] == 0.5     # book-rules default
        r = self.c.put("/api/live/plan", json={"plan": {"min_rr": 0.6, "entry_days": ["Wed"]}})
        assert r.status_code == 200 and r.json()["plan"]["min_rr"] == 0.6
        assert self.c.get("/api/live/plan").json()["plan"]["entry_days"] == ["Wed"]

    def test_book_rules_endpoint_fills_but_never_saves(self):
        r = self.c.get("/api/live/plan/book-rules").json()
        assert r["success"] and r["values"]["min_credit"] == 2167 and r["sources"]["min_credit"]
        assert self.c.get("/api/live/plan").json()["plan"]["min_credit"] == 2167   # the default, nothing saved
        import db.database as dbm
        conn = dbm.get_connection()
        try:
            assert conn.execute("SELECT COUNT(*) AS n FROM trading_plans").fetchone()["n"] == 0
        finally:
            conn.close()

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


# ── Book-rules preset (fills the Plan form, never saves) ────────────────────

class TestBookRules:
    def _preset(self):
        from engine.desk.book_rules import book_preset
        return book_preset(date(2026, 10, 30))

    def test_values_follow_their_sources(self):
        v = self._preset()["values"]
        assert v["entry_days"] == ["Tue"]
        assert v["vix_max"] == 40                       # simple_ic_engine VIX_MAX
        assert v["min_credit"] == 2167                  # 100 / 3 × 65
        assert v["min_rr"] == 0.5
        assert v["loss_exit_rupees"] == 1500            # Elder 2% of 75,000
        assert v["monthly_loss_limit"] == 4500          # Elder 6% of 75,000
        assert v["expiry_margin_buffer"] == 53600       # 67,000 × ELM_FACTOR 0.80
        assert v["profit_target_pct"] == 0.5 and v["exit_days_before_expiry"] == 1

    def test_every_value_has_a_source_and_unsourced_fields_are_left_alone(self):
        p = self._preset()
        assert set(p["values"]) == set(p["sources"])
        assert set(p["not_filled"]) == {"vix_min", "max_loss_per_trade", "weekly_loss_limit", "pause_after_losses", "topup_reserve"}
        assert not set(p["not_filled"]) & set(p["values"])

    def test_preset_is_a_valid_plan(self):
        plan = validate_plan(self._preset()["values"])
        assert plan["max_loss_per_trade"] is None and plan["min_credit"] == 2167

    def test_events_are_not_copied_into_the_plan(self):
        assert "events" not in self._preset()["values"] and default_plan()["events"] == []

    def test_engine_elm_estimate_unchanged_by_shared_constant(self):
        from engine.signals.simple_ic_engine import ELM_FACTOR
        assert ELM_FACTOR == 0.80 and round(67000 * ELM_FACTOR) == 53600


# ── Time to hold (a ticket for a contract you can't hold is NO-GO) ──────────

class TestTimeToHold:
    def test_weekend_ticket_for_this_weeks_expiry_is_no_go(self):
        # Prepared Sunday 1 Nov for the Tue 3 Nov expiry: exit-by Mon 2 Nov = the next session.
        t = build_ticket(make_signal(), full_plan(), date(2026, 11, 1), expiry=date(2026, 11, 3))
        c = check(t, "time_to_hold")
        assert t["exit_plan"]["exit_by"] == "2026-11-02"
        assert c["status"] == "fail" and "No time to hold" in c["detail"] and t["verdict"] == "NO-GO"

    def test_expiry_day_ticket_for_next_week_passes(self):
        # Prepared Tue 3 Nov (expiry day) for the Mon 9 Nov contract: exit by Fri 6 Nov.
        t = build_ticket(make_signal(), full_plan(entry_days=["Tue"]), date(2026, 11, 3), expiry=date(2026, 11, 9))
        c = check(t, "time_to_hold")
        assert c["status"] == "pass" and "2026-11-06" in c["detail"]

    def test_unset_without_exit_rule(self):
        t = build_ticket(make_signal(), full_plan(exit_days_before_expiry=None), WED, expiry=date(2026, 9, 1))
        assert check(t, "time_to_hold")["status"] == "unset" and t["exit_plan"]["exit_by"] is None


class TestBookDefaultOnTicket:
    def test_book_default_blocks_the_low_credit_aug_26_trade(self):
        # ₹1,807 credit is below the ⅓-width ₹2,167 minimum, and Wednesday is not the Tuesday entry day.
        t = build_ticket(make_signal(), default_plan(), WED, symbols=SYMBOLS, quotes=QUOTES, expiry=date(2026, 9, 1))
        assert t["verdict"] == "NO-GO"
        assert check(t, "min_credit")["status"] == "fail" and check(t, "entry_day")["status"] == "fail"
        assert check(t, "max_loss")["status"] == "unset"


# ── Leg prices (action item 1): the two real tickets from 3 Nov 2026 ─────────

NOV3 = date(2026, 11, 3)
NOV_SYMBOLS = {(23250, "PE"): "P23250", (23350, "PE"): "P23350", (23850, "CE"): "C23850", (23950, "CE"): "C23950"}


def nov_signal():
    return {"action": "trade",
            "conditions": {"nifty_price": 23600.0, "vix_level": 15.0, "data_source": "kite", "data_is_live": True},
            "trade": {"width": 100, "charges": {"total": 239},
                      "legs": [{"action": "SELL", "option": "CE", "strike": 23850, "premium_est": 50.0},
                               {"action": "BUY", "option": "CE", "strike": 23950, "premium_est": 30.0},
                               {"action": "SELL", "option": "PE", "strike": 23350, "premium_est": 90.0},
                               {"action": "BUY", "option": "PE", "strike": 23250, "premium_est": 60.0}]},
            "risk_check": {"capital": 75000}}


def nov_quotes(p23350, p23250, c23850, c23950, traded="2026-11-03 09:40:00", now="2026-11-03 09:40:30", half_spread=0.5):
    def q(p):
        return {"ltp": p, "bid": p - half_spread, "ask": p + half_spread, "last_trade_time": traded, "quote_time": now}
    return {"P23350": q(p23350), "P23250": q(p23250), "C23850": q(c23850), "C23950": q(c23950)}


TICKET_1 = (187.30, 144.85, 31.90, 22.20)        # all four equal the 2 Nov NSE closes
TICKET_2 = (102.50, 77.25, 67.15, 45.30)         # all four inside the 3 Nov NSE day ranges


def nov_ticket(quotes):
    return build_ticket(nov_signal(), engine_plan(), NOV3, expiry=date(2026, 11, 9), symbols=NOV_SYMBOLS, quotes=quotes,
                        kite_connected=True)


class TestLegPrices:
    def test_ticket_1_prices_that_dont_fit_nifty_fail(self):
        t = nov_ticket(nov_quotes(*TICKET_1))
        c = check(t, "legs_consistent")
        assert c["status"] == "fail" and "Prices unreliable" in c["detail"] and "volatility ratio" in c["detail"]
        assert t["prices_unreliable"] is True and t["verdict"] == "NO-GO"

    def test_ticket_2_fits_nifty_and_passes(self):
        t = nov_ticket(nov_quotes(*TICKET_2))
        assert check(t, "legs_consistent")["status"] == "pass" and t["prices_unreliable"] is False
        assert 0.9 <= t["vol_ratio"] <= 1.8

    def test_previous_close_is_caught_by_last_trade_time_even_for_small_moves(self):
        t = nov_ticket(nov_quotes(*TICKET_2, traded="2026-11-02 15:29:59"))
        c = check(t, "legs_consistent")
        assert c["status"] == "fail" and "no trade yet this session" in c["detail"]
        assert all(o["previous_session"] and o["stale"] for o in t["orders"])
        assert check(t, "leg_quality")["status"] == "warn"          # never reported as fresh

    def test_never_traded_counts_as_no_trade_this_session(self):
        t = nov_ticket(nov_quotes(*TICKET_2, traded=None))
        assert check(t, "legs_consistent")["status"] == "fail"

    def test_sells_at_bid_buys_at_ask(self):
        t = nov_ticket(nov_quotes(*TICKET_2))
        by = {o["strike"]: o for o in t["orders"]}
        assert by[23350]["price"] == 102.0 and by[23850]["price"] == 66.65      # sells at bid
        assert by[23250]["price"] == 77.75 and by[23950]["price"] == 45.80      # buys at ask
        assert t["credit_per_share"] == pytest.approx(45.1)
        assert t["max_loss"] == pytest.approx((100 - 45.1) * 65)
        assert t["exit_plan"]["target"]["profit"] == pytest.approx(45.1 * 65 * 0.5)

    def test_missing_depth_fails_and_uses_last_price(self):
        q = nov_quotes(*TICKET_2)
        q["P23350"]["bid"] = None
        t = nov_ticket(q)
        c = check(t, "legs_consistent")
        assert c["status"] == "fail" and "no bid/ask for P23350" in c["detail"]
        assert next(o for o in t["orders"] if o["strike"] == 23350)["price"] == 102.50

    def test_wide_spread_and_stale_leg_warn_without_failing(self):
        q = nov_quotes(*TICKET_2)
        q["C23950"].update(bid=42.0, ask=48.0)                                  # 13% spread
        q["P23250"]["last_trade_time"] = "2026-11-03 09:35:00"                  # 5.5 min before the quote
        t = nov_ticket(q)
        c = check(t, "leg_quality")
        assert c["status"] == "warn" and "C23950" in c["detail"] and "P23250" in c["detail"]
        assert check(t, "legs_consistent")["status"] == "pass"

    def test_quality_shown_per_leg(self):
        o = nov_ticket(nov_quotes(*TICKET_2))["orders"][0]
        assert o["last_trade_age"] == 30 and o["stale"] is False and o["wide"] is False
        assert o["spread"] == 1.0 and o["bid"] and o["ask"] and o["ltp"]

    def test_real_kiteconnect_datetimes_are_understood(self):
        from datetime import datetime
        from engine.desk.leg_prices import leg_quality
        q = {"bid": 10, "ask": 10.2, "last_trade_time": datetime(2026, 11, 3, 9, 40), "quote_time": datetime(2026, 11, 3, 9, 43)}
        r = leg_quality(q, NOV3)
        assert r["last_trade_age"] == 180 and r["stale"] is True and r["previous_session"] is False

    def test_estimates_without_kite_skip_the_check(self):
        t = build_ticket(nov_signal(), engine_plan(), NOV3)
        assert check(t, "legs_consistent")["status"] == "unknown" and t["prices_unreliable"] is False

    def test_close_prices_are_the_cost_to_get_out(self):
        from engine.desk.leg_prices import close_price
        q = {"ltp": 10, "bid": 9.5, "ask": 10.5}
        assert close_price("SELL", q) == 10.5 and close_price("BUY", q) == 9.5
        assert close_price("SELL", {"ltp": 10}) == 10


# ── Margin (action item 2): cushion, expiry buffer, top-up reserve ──────────

class TestMargin:
    # Real 3 Nov numbers: margin 64,810, funds 76,737, buffer 53,600, exit-by Fri before Mon expiry.
    def _check(self, funds=76737, margin=64810, **plan_over):
        plan = engine_plan()
        plan.update(expiry_margin_buffer=53600, margin_cushion_pct=20, topup_reserve=None)
        plan.update(plan_over)
        t = build_ticket(make_signal(), plan, WED, expiry=date(2026, 9, 1), margin_required=margin,
                         funds_available=funds, kite_connected=True)
        return check(t, "margin"), t

    def test_below_entry_margin_with_cushion_fails(self):
        c, t = self._check()                                    # 64,810 × 1.2 = 77,772 > 76,737
        assert c["status"] == "fail" and "Short by" in c["detail"] and t["verdict"] == "NO-GO"

    def test_covers_everything_passes(self):
        assert self._check(funds=131372)[0]["status"] == "pass"  # 77,772 + 53,600

    def test_covered_only_with_reserve_warns_how_much_to_add(self):
        c, t = self._check(funds=90000, topup_reserve=50000)
        assert c["status"] == "warn" and "add ₹41,372" in c["detail"] and "expiry morning" in c["detail"]
        assert "Margin" not in " ".join(t["failed"])

    def test_buffer_short_even_with_reserve_only_warns_when_exiting_before_expiry(self):
        c, _ = self._check(funds=90000, topup_reserve=1000)
        assert c["status"] == "warn" and "before it applies" in c["detail"]

    def test_buffer_short_fails_when_exit_by_is_expiry_day(self):
        c, _ = self._check(funds=90000, topup_reserve=1000, exit_days_before_expiry=0)
        assert c["status"] == "fail" and "not before expiry" in c["detail"]

    def test_buffer_short_with_reserve_covering_warns_even_when_holding_to_expiry(self):
        assert self._check(funds=90000, topup_reserve=50000, exit_days_before_expiry=0)[0]["status"] == "warn"

    def test_no_exit_rule_counts_as_holding_to_expiry(self):
        assert self._check(funds=90000, exit_days_before_expiry=None)[0]["status"] == "fail"

    def test_empty_cushion_and_buffer_are_treated_as_none(self):
        c, _ = self._check(funds=64810, margin_cushion_pct=None, expiry_margin_buffer=None)
        assert c["status"] == "pass"

    def test_reserve_never_counts_towards_entry(self):
        assert self._check(funds=70000, topup_reserve=500000)[0]["status"] == "fail"

    def test_default_plan_has_the_cushion_but_no_invented_reserve(self):
        plan = default_plan()
        assert plan["margin_cushion_pct"] == 20 and plan["topup_reserve"] is None


# ── Events (action item 3): tiers, overnight impact, stale calendar ─────────

class TestEvents:
    CAL = {"last_updated": "2026-11-20", "events": [
        {"date": "2026-12-04", "name": "RBI policy decision", "tier": "high", "session": "india"},
        {"date": "2026-12-04", "name": "US jobs report", "tier": "medium", "session": "overnight"},
        {"date": "2026-12-09", "name": "Fed decision", "tier": "high", "session": "overnight"},
        {"date": "2026-11-27", "name": "US CPI", "tier": "medium", "session": "overnight"},
    ]}

    def _t(self, today, expiry, calendar=None, plan=None):
        return build_ticket(make_signal(), plan or engine_plan(), today, expiry=expiry, calendar=calendar or self.CAL)

    def test_high_tier_blocks_and_names_the_session(self):
        t = self._t(date(2026, 12, 1), date(2026, 12, 8))
        c = check(t, "events")
        assert c["status"] == "fail" and t["verdict"] == "NO-GO" and "RBI policy decision" in c["detail"]
        assert t["event_alert"]["name"] == "RBI policy decision" and t["event_alert"]["tier"] == "high"

    def test_medium_tier_only_warns(self):
        t = self._t(date(2026, 11, 24), date(2026, 12, 1))
        c = check(t, "events")
        assert c["status"] == "warn" and "US CPI" in c["detail"] and t["event_alert"] is None
        assert "No event before expiry" not in t["failed"]

    def test_overnight_event_hits_the_next_session_not_its_own_date(self):
        # Fed on Wed 9 Dec hits Thu 10 Dec: a contract expiring on the 9th is clear of it.
        assert "Fed" not in check(self._t(date(2026, 12, 7), date(2026, 12, 9)), "events")["detail"]
        c = check(self._t(date(2026, 12, 7), date(2026, 12, 10)), "events")
        assert c["status"] == "fail" and "hits the 2026-12-10 session" in c["detail"]

    def test_overnight_event_yesterday_still_hits_today(self):
        c = check(self._t(date(2026, 12, 10), date(2026, 12, 15)), "events")
        assert c["status"] == "fail" and "Fed decision" in c["detail"]

    def test_window_runs_to_expiry_not_exit_by(self):
        # RBI on Fri 4 Dec is after exit-by (Thu 3 Dec) but on the expiry day: still blocks.
        t = self._t(date(2026, 12, 1), date(2026, 12, 4))
        assert t["exit_plan"]["exit_by"] == "2026-12-03" and check(t, "events")["status"] == "fail"

    def test_overnight_skips_a_holiday(self):
        from engine.desk.market_calendar import impact_date
        # US CPI on Mon 9 Nov would hit Tue 10 Nov, a Diwali holiday: it hits Wed 11 Nov.
        assert impact_date({"date": "2026-11-09", "session": "overnight"}) == date(2026, 11, 11)

    def test_stale_by_age_or_empty_window_shows_not_set(self):
        old = {"last_updated": "2026-10-01", "events": self.CAL["events"]}
        c = check(self._t(date(2026, 11, 16), date(2026, 11, 17), calendar=old), "events")
        assert c["status"] == "unset" and "calendar stale" in c["detail"]
        empty = {"last_updated": "2026-11-20", "events": []}
        assert "calendar stale" in check(self._t(date(2026, 11, 23), date(2026, 11, 24), calendar=empty), "events")["detail"]

    def test_known_event_still_blocks_when_calendar_is_stale(self):
        old = {"last_updated": "2026-10-01", "events": self.CAL["events"]}
        assert check(self._t(date(2026, 12, 1), date(2026, 12, 8), calendar=old), "events")["status"] == "fail"

    def test_fresh_calendar_with_nothing_in_window_passes(self):
        assert check(self._t(date(2026, 11, 23), date(2026, 11, 26)), "events")["status"] == "pass"

    def test_plans_own_events_block_as_high(self):
        plan = engine_plan()
        plan["events"] = [{"date": "2026-11-25", "label": "Bihar results"}]
        c = check(self._t(date(2026, 11, 23), date(2026, 11, 26), plan=plan), "events")
        assert c["status"] == "fail" and "Bihar results" in c["detail"]

    def test_next_clear_entry_skips_high_event_weeks(self):
        plan = engine_plan()
        plan["entry_days"] = ["Tue"]
        t = self._t(date(2026, 12, 1), date(2026, 12, 8), plan=plan)
        assert t["next_clear_entry"] == "2026-12-15"            # Tue 8 Dec's week holds the Fed

    def test_real_calendar_file_is_valid_and_sourced(self):
        from engine.desk.market_calendar import load_events, impact_date
        cal = load_events()
        assert cal["last_updated"] and cal["sources"] and cal["not_covered"]
        for e in cal["events"]:
            assert e["tier"] in ("high", "medium") and e["session"] in ("india", "overnight") and impact_date(e)
        assert {"date": "2026-12-04", "name": "RBI policy decision", "tier": "high", "session": "india"} in cal["events"]
        assert not any(e["date"] == "2026-12-05" for e in cal["events"])   # the old calendar's wrong RBI date


# ── Holidays (action item 5) ────────────────────────────────────────────────

class TestHolidays:
    def test_exit_by_moves_earlier_for_a_holiday(self):
        # Expiry Wed 25 Nov, Tue 24 Nov is a holiday: one trading day before is Mon 23 Nov.
        assert subtract_trading_days(date(2026, 11, 25), 1) == date(2026, 11, 23)
        t = build_ticket(make_signal(), engine_plan(), date(2026, 11, 18), expiry=date(2026, 11, 25))
        assert t["exit_plan"]["exit_by"] == "2026-11-23"

    def test_fallback_expiry_moves_for_a_tuesday_holiday(self):
        # Without Kite on Tue 3 Nov: Tue 10 Nov is Diwali, so the expected expiry is Mon 9 Nov (NSE's real one).
        t = build_ticket(make_signal(), engine_plan(), date(2026, 11, 3))
        assert t["expiry"] == "2026-11-09" and t["expiry_confirmed"] is False
        assert t["exit_plan"]["exit_by"] == "2026-11-06"

    def test_on_a_shifted_expiry_day_the_next_week_is_used(self):
        from engine.desk.market_calendar import weekly_expiry_after
        assert weekly_expiry_after(date(2026, 11, 9)) == date(2026, 11, 17)
        assert weekly_expiry_after(date(2026, 11, 3)) == date(2026, 11, 9)
        assert weekly_expiry_after(date(2026, 11, 2)) == date(2026, 11, 3)

    def test_kite_expiry_always_wins(self):
        t = build_ticket(make_signal(), engine_plan(), date(2026, 11, 3), expiry=date(2026, 11, 12))
        assert t["expiry"] == "2026-11-12" and t["expiry_confirmed"] is True

    def test_hold_counts_trading_days_and_notes_the_holiday(self):
        t = build_ticket(make_signal(), engine_plan(), date(2026, 11, 3), expiry=date(2026, 11, 12))
        h = t["hold"]                                  # Tue 3 → Wed 11 Nov, without weekends and Tue 10 Nov
        assert t["exit_plan"]["exit_by"] == "2026-11-11"
        assert h["trading_days"] == 6 and h["covered"] is True
        assert h["holidays"] == [{"date": "2026-11-10", "name": "Diwali-Balipratipada"}]

    def test_expiry_beyond_the_holiday_list_is_flagged(self):
        t = build_ticket(make_signal(), engine_plan(), date(2026, 12, 29), expiry=date(2027, 1, 5))
        assert t["hold"]["covered"] is False

    def test_a_holiday_today_means_the_next_session_counts(self):
        # On Diwali Tue 10 Nov, with exit-by Wed 11 Nov: the next session is the exit-by day.
        t = build_ticket(make_signal(), engine_plan(), date(2026, 11, 10), expiry=date(2026, 11, 12))
        assert check(t, "time_to_hold")["status"] == "fail"

    def test_engine_expiry_uses_the_holiday_calendar(self):
        from unittest.mock import patch as p
        import engine.signals.simple_ic_engine as E

        class D(date):
            @classmethod
            def today(cls):
                return date(2026, 11, 3)

        with p.object(E, "date", D):
            import engine.desk.market_calendar  # noqa: F401
            expiry, days, label = E._get_expiry_date()
        assert expiry == date(2026, 11, 9) and days == 6 and label == "09 Nov 2026 (Mon)"


class TestNoLiveDepth:
    """Market closed: Kite gives last prices but no bid/ask. Seen for real on Sat 7 Nov 2026."""

    def _closed(self):
        q = nov_quotes(*TICKET_2, traded="2026-11-02 15:29:59")
        for v in q.values():
            v["bid"] = v["ask"] = None
        return q

    def test_labelled_as_last_traded_not_live(self):
        t = nov_ticket(self._closed())
        assert t["pricing"] == "kite_last"
        c = check(t, "prices_live")
        assert c["status"] == "warn" and "4 of 4 legs" in c["detail"] and "best bid" not in c["detail"]
        assert t["prices_unreliable"] is True and t["verdict"] == "NO-GO"

    def test_one_leg_without_depth_is_not_called_live(self):
        q = nov_quotes(*TICKET_2)
        q["C23950"]["ask"] = None                       # a buy needs the ask
        t = nov_ticket(q)
        assert t["pricing"] == "kite_last" and "1 of 4 legs" in check(t, "prices_live")["detail"]

    def test_full_depth_is_still_live(self):
        t = nov_ticket(nov_quotes(*TICKET_2))
        assert t["pricing"] == "kite_live" and check(t, "prices_live")["status"] == "pass"
