"""
Phases 2–4 of the trading desk: real-fill journal, tradebook import, position
monitor / exit ticket, risk budget and weekly review.

Run: python -m pytest tests/test_desk_journal.py -v
"""

import io
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.desk import trades as T  # noqa: E402
from engine.desk.monitor import monitor_position  # noqa: E402
from engine.desk.review import review_stats, risk_budget  # noqa: E402

# The real Aug 26 2026 iron condor (BRD): entry fills
TICKET_ORDERS = [
    {"step": 1, "side": "BUY", "strike": 24000, "option": "PE", "symbol": "NIFTY2690124000PE", "qty": 65, "price": 12.6},
    {"step": 2, "side": "BUY", "strike": 24700, "option": "CE", "symbol": "NIFTY2690124700CE", "qty": 65, "price": 22.55},
    {"step": 3, "side": "SELL", "strike": 24100, "option": "PE", "symbol": "NIFTY2690124100PE", "qty": 65, "price": 20.5},
    {"step": 4, "side": "SELL", "strike": 24600, "option": "CE", "symbol": "NIFTY2690124600CE", "qty": 65, "price": 42.45},
]


def kite_order(sym, side, qty, avg, status="COMPLETE", exch="NFO"):
    return {"tradingsymbol": sym, "transaction_type": side, "filled_quantity": qty, "quantity": qty,
            "average_price": avg, "status": status, "exchange": exch}


ENTRY_ORDERS = [kite_order(o["symbol"], o["side"], 65, o["price"]) for o in TICKET_ORDERS]


class TestFills:
    def test_symbol_filter_excludes_other_indices(self):
        assert T.is_nifty_option("NIFTY2690124000PE")
        assert T.is_nifty_option("NIFTY26SEP24000CE")
        for s in ("BANKNIFTY2690150000CE", "FINNIFTY2690124000PE", "NIFTYNXT5026SEP70000CE", "NIFTY26SEPFUT"):
            assert not T.is_nifty_option(s)

    def test_aggregate_uses_completed_fills_only(self):
        orders = ENTRY_ORDERS + [kite_order("NIFTY2690124000PE", "BUY", 65, 99, status="REJECTED"),
                                 kite_order("BANKNIFTY2690150000CE", "SELL", 30, 100)]
        agg = T.aggregate_kite_orders(orders)
        assert agg[("NIFTY2690124000PE", "BUY")] == {"qty": 65, "avg": 12.6}
        assert len(agg) == 4

    def test_split_fills_average_correctly(self):
        orders = [kite_order("NIFTY2690124000PE", "BUY", 40, 12.0), kite_order("NIFTY2690124000PE", "BUY", 25, 13.0)]
        assert T.aggregate_kite_orders(orders)[("NIFTY2690124000PE", "BUY")] == {"qty": 65, "avg": 12.38}

    def test_open_from_fills_and_credit(self):
        legs, problems = T.open_from_fills(TICKET_ORDERS, T.aggregate_kite_orders(ENTRY_ORDERS))
        assert not problems
        assert T.entry_credit_per_share(legs) == 27.8

    def test_missing_or_partial_leg_blocks_open(self):
        partial = ENTRY_ORDERS[:3] + [kite_order("NIFTY2690124600CE", "SELL", 30, 42.45)]
        legs, problems = T.open_from_fills(TICKET_ORDERS, T.aggregate_kite_orders(partial))
        assert legs is None and "filled 30 of 65" in problems[0]
        legs, problems = T.open_from_fills(TICKET_ORDERS, T.aggregate_kite_orders(ENTRY_ORDERS[:2]))
        assert legs is None and len(problems) == 2

    def test_close_and_gross_pnl(self):
        legs, _ = T.open_from_fills(TICKET_ORDERS, T.aggregate_kite_orders(ENTRY_ORDERS))
        exits = [kite_order("NIFTY2690124100PE", "BUY", 65, 8.0), kite_order("NIFTY2690124600CE", "BUY", 65, 15.0),
                 kite_order("NIFTY2690124000PE", "SELL", 65, 3.0), kite_order("NIFTY2690124700CE", "SELL", 65, 5.0)]
        closed, problems = T.close_from_fills(legs, T.aggregate_kite_orders(exits))
        assert not problems
        # close cost 8 + 15 − 3 − 5 = 15 per share; P&L = (27.80 − 15) × 65 = 832
        assert T.gross_pnl(closed) == pytest.approx(832.0)

    def test_charges_estimate(self):
        assert T.estimate_charges(8) == pytest.approx(160 + 28.8 + 50)
        from engine.signals.simple_ic_engine import _calculate_charges
        assert T.estimate_charges(8) == _calculate_charges()["total"]   # same as the signal engine


TRADEBOOK = """symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,trade_id,order_id,order_execution_time,expiry_date
NIFTY2690124000PE,,2026-08-26,NSE,FO,,buy,false,65,12.60,1,1,2026-08-26T09:22:00,2026-09-01
NIFTY2690124700CE,,2026-08-26,NSE,FO,,buy,false,65,22.55,2,2,2026-08-26T09:25:00,2026-09-01
NIFTY2690124100PE,,2026-08-26,NSE,FO,,sell,false,65,20.50,3,3,2026-08-26T09:28:00,2026-09-01
NIFTY2690124600CE,,2026-08-26,NSE,FO,,sell,false,65,42.45,4,4,2026-08-26T09:32:00,2026-09-01
NIFTY2690124100PE,,2026-08-28,NSE,FO,,buy,false,65,40.00,5,5,2026-08-28T10:00:00,2026-09-01
NIFTY2690124600CE,,2026-08-28,NSE,FO,,buy,false,65,30.00,6,6,2026-08-28T10:01:00,2026-09-01
NIFTY2690124000PE,,2026-08-28,NSE,FO,,sell,false,65,18.00,7,7,2026-08-28T10:02:00,2026-09-01
NIFTY2690124700CE,,2026-08-28,NSE,FO,,sell,false,65,15.00,8,8,2026-08-28T10:03:00,2026-09-01
NIFTY2680524950CE,,2026-08-05,NSE,FO,,buy,false,65,50.00,9,9,2026-08-05T09:30:00,2026-08-05
NIFTY2680524950CE,,2026-08-05,NSE,FO,,sell,false,65,61.00,10,10,2026-08-05T10:30:00,2026-08-05
BANKNIFTY2690150000CE,,2026-08-26,NSE,FO,,sell,false,30,100.00,11,11,2026-08-26T09:40:00,2026-09-01
"""


class TestTradebook:
    def test_iron_condor_found_and_scalp_skipped(self):
        fills = T.parse_tradebook(TRADEBOOK)
        assert len(fills) == 10                       # BANKNIFTY excluded
        trades, skipped = T.condors_from_tradebook(fills)
        assert len(trades) == 1 and len(skipped) == 1
        assert "not a 4-leg iron condor" in skipped[0]["reason"]
        t = trades[0]
        assert t["status"] == "closed" and t["opened_on"] == "2026-08-26" and t["closed_on"] == "2026-08-28"
        assert t["entry_credit"] == 27.8
        # close cost 40 + 30 − 18 − 15 = 37 → (27.80 − 37) × 65 = −598
        assert t["pnl_gross"] == pytest.approx(-598.0)
        assert t["pnl_net"] == pytest.approx(-598.0 - T.estimate_charges(8))

    def test_charges_count_orders_not_fills(self):
        f = lambda sym, side, oid: {"symbol": sym, "side": side, "order_id": oid}
        split = [f("A", "BUY", "1"), f("A", "BUY", "1"), f("B", "SELL", "2")]   # order 1 filled in two rows
        assert T._order_count(split) == 2
        no_ids = [f("A", "BUY", None), f("A", "BUY", None), f("B", "SELL", None)]
        assert T._order_count(no_ids) == 2
        assert T.parse_tradebook(TRADEBOOK)[0]["order_id"] == "1"

    def test_open_condor_from_tradebook(self):
        fills = [f for f in T.parse_tradebook(TRADEBOOK) if f["date"] == "2026-08-26"]
        trades, _ = T.condors_from_tradebook(fills)
        assert trades[0]["status"] == "open" and "pnl_net" not in trades[0]


def open_trade(**over):
    legs, _ = T.open_from_fills(TICKET_ORDERS, T.aggregate_kite_orders(ENTRY_ORDERS))
    t = {"id": 1, "status": "open", "opened_on": "2026-08-26", "expiry": "2026-09-01", "lot": 65, "legs": legs,
         "entry_credit": 27.8, "exit_plan": {"profit_target_pct": 0.5, "loss_exit": 1500, "exit_by": "2026-08-31"}}
    t.update(over)
    return t


def quotes(sp, sc, lp, lc):
    return {"NIFTY2690124100PE": sp, "NIFTY2690124600CE": sc, "NIFTY2690124000PE": lp, "NIFTY2690124700CE": lc}


class TestMonitor:
    def test_live_pnl_and_progress(self):
        m = monitor_position(open_trade(), date(2026, 8, 27), quotes=quotes(8, 15, 3, 5), spot=24400)
        assert m["live"] and m["pnl"] == pytest.approx(832.0)
        assert m["target_profit"] == pytest.approx(903.5)
        assert m["target_progress"] == pytest.approx(92.1, abs=0.1)
        assert m["status"] == "hold"
        assert m["distance_to_short_call"] == 200 and m["distance_to_short_put"] == 300
        assert m["days_to_exit_by"] == 4

    def test_target_and_loss_alerts(self):
        m = monitor_position(open_trade(), date(2026, 8, 27), quotes=quotes(5, 10, 2, 3), spot=24350)
        assert m["status"] == "target"
        m = monitor_position(open_trade(), date(2026, 8, 27), quotes=quotes(10, 80, 2, 30), spot=24580)   # close cost 58 → −1,963
        assert m["pnl"] < -1500 and m["status"] == "loss_exit"

    def test_exit_day_alert(self):
        m = monitor_position(open_trade(), date(2026, 8, 31), quotes=quotes(8, 15, 3, 5), spot=24400)
        assert m["status"] == "exit_day"

    def test_exit_orders_buy_back_shorts_first(self):
        m = monitor_position(open_trade(), date(2026, 8, 27), quotes=quotes(8, 15, 3, 5), spot=24400)
        assert [(o["side"], o["strike"]) for o in m["exit_orders"]] == [
            ("BUY", 24100), ("BUY", 24600), ("SELL", 24000), ("SELL", 24700)]
        assert m["exit_orders"][0]["price"] == 8

    def test_exit_orders_are_nrml(self):
        m = monitor_position(open_trade(), date(2026, 8, 27), quotes=quotes(8, 15, 3, 5), spot=24400)
        assert all(o["product"] == "NRML" for o in m["exit_orders"])

    def test_without_quotes(self):
        m = monitor_position(open_trade(), date(2026, 8, 27))
        assert m["pnl"] is None and m["status"] == "no_data" and m["exit_orders"][0]["price"] is None


def closed(i, opened, closed_on, pnl, followed=None, risk=1500):
    return {"id": i, "status": "closed", "opened_on": opened, "closed_on": closed_on, "pnl_net": pnl,
            "pnl_gross": pnl + 239, "charges_est": 239, "lot": 65, "entry_credit": 25, "legs": [],
            "planned_risk": risk, "followed_plan": followed, "strikes": "x"}


HISTORY = [closed(1, "2026-08-12", "2026-08-17", 1335.75, "yes"),
           closed(2, "2026-08-19", "2026-08-24", 1771.25, "yes"),
           closed(3, "2026-08-26", "2026-08-28", -1459.25, "no")]


class TestReview:
    def test_stats(self):
        s = review_stats(HISTORY)
        assert s["trades"] == 3 and s["net"] == pytest.approx(1647.75)
        assert s["expectancy"] == pytest.approx(549.25)
        assert s["avg_win"] == pytest.approx(1553.5) and s["avg_loss"] == pytest.approx(-1459.25)
        assert s["max_drawdown"] == pytest.approx(-1459.25)
        assert s["followed"]["trades"] == 2 and s["deviated"]["net"] == pytest.approx(-1459.25)
        assert s["rows"][0]["id"] == 3 and s["rows"][0]["r"] == pytest.approx(-0.97, abs=0.01)
        assert [e["equity"] for e in s["equity"]] == pytest.approx([1335.75, 3107.0, 1647.75])

    def test_empty(self):
        assert review_stats([])["trades"] == 0

    def test_risk_budget_breaches(self):
        plan = {"weekly_loss_limit": 1000, "monthly_loss_limit": 5000, "pause_after_losses": 1}
        r = risk_budget(HISTORY, plan, date(2026, 8, 28))   # week of Mon 24 Aug: +1771.25 − 1459.25
        assert r["week_net"] == pytest.approx(312.0) and r["losing_streak"] == 1
        assert len(r["breaches"]) == 1 and "losses in a row" in r["breaches"][0]

    def test_risk_budget_unconfigured(self):
        r = risk_budget(HISTORY, {}, date(2026, 8, 28))
        assert not r["configured"] and not r["breaches"]

    def test_ticket_fails_on_breach(self):
        sys.path.insert(0, str(PROJECT_ROOT / "tests"))
        from test_desk import make_signal, full_plan, SYMBOLS, QUOTES
        from engine.desk.ticket import build_ticket
        risk = risk_budget(HISTORY, {"pause_after_losses": 1}, date(2026, 8, 28))
        t = build_ticket(make_signal(), full_plan(min_rr=0.3), date(2026, 8, 26), symbols=SYMBOLS, quotes=QUOTES,
                         expiry=date(2026, 9, 1), risk=risk)
        c = next(c for c in t["checks"] if c["key"] == "risk_budget")
        assert c["status"] == "fail" and t["verdict"] == "NO-GO"


class TestJournalEndpoints:
    @pytest.fixture(autouse=True)
    def client(self, tmp_path, monkeypatch):
        import db.database as dbm
        if dbm.USE_POSTGRES:
            pytest.skip("SQLite only")
        path = str(tmp_path / "t.db")
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
        app.dependency_overrides[require_founder] = lambda: {"user_id": 5, "email": "t@t", "name": "T"}
        self.c = TestClient(app)
        self.ticket = {"orders": TICKET_ORDERS, "expiry": "2026-09-01", "credit_per_share": 30.0,
                       "market": {"spot": 24350, "vix": 11.2}, "exit_plan": {"exit_by": "2026-08-31"}}

    def _kite(self, orders):
        kite = MagicMock()
        kite.orders.return_value = orders
        kite.quote.return_value = {f"NFO:{s}": {"last_price": p, "depth": {}} for s, p in quotes(8, 15, 3, 5).items()}
        kite.ltp.return_value = {"NSE:NIFTY 50": {"last_price": 24400.0}}
        return kite

    def test_full_cycle_with_kite(self):
        kite = self._kite(ENTRY_ORDERS)
        with patch("routes.live._kite_or_none", return_value=kite):
            r = self.c.post("/api/live/desk/sync-entry", json={"ticket": self.ticket})
            assert r.status_code == 200 and r.json()["entry_credit"] == 27.8
            assert self.c.post("/api/live/desk/sync-entry", json={"ticket": self.ticket}).status_code == 409
            pos = self.c.get("/api/live/desk/position").json()["position"]
            assert pos["pnl"] == pytest.approx(832.0) and pos["spot"] == 24400.0
            kite.orders.return_value = [kite_order("NIFTY2690124100PE", "BUY", 65, 8.0)]
            r = self.c.post("/api/live/desk/sync-exit", json={"exit_reason": "target"})
            assert r.status_code == 409 and len(r.json()["problems"]) == 3
            kite.orders.return_value = [kite_order("NIFTY2690124100PE", "BUY", 65, 8.0), kite_order("NIFTY2690124600CE", "BUY", 65, 15.0),
                                        kite_order("NIFTY2690124000PE", "SELL", 65, 3.0), kite_order("NIFTY2690124700CE", "SELL", 65, 5.0)]
            r = self.c.post("/api/live/desk/sync-exit", json={"exit_reason": "target"})
            assert r.status_code == 200 and r.json()["pnl_gross"] == pytest.approx(832.0)
        assert self.c.get("/api/live/desk/position").json()["position"] is None
        rev = self.c.get("/api/live/desk/review").json()
        tid = rev["stats"]["rows"][0]["id"]
        assert rev["stats"]["trades"] == 1 and rev["stats"]["rows"][0]["exit_reason"] == "target"
        assert self.c.post(f"/api/live/desk/trades/{tid}/review", json={"followed_plan": "yes", "note": "clean"}).status_code == 200
        assert self.c.get("/api/live/desk/review").json()["stats"]["followed"]["trades"] == 1

    def test_manual_open_and_close_without_kite(self):
        prices = {o["symbol"]: o["price"] for o in TICKET_ORDERS}
        with patch("routes.live._kite_or_none", return_value=None):
            assert self.c.post("/api/live/desk/sync-entry", json={"ticket": self.ticket}).status_code == 401
            ticket = {**self.ticket, "exit_plan": {"exit_by": None}}
            r = self.c.post("/api/live/desk/manual-open", json={"ticket": ticket, "prices": prices})
            assert r.status_code == 200 and r.json()["entry_credit"] == 27.8
            pos = self.c.get("/api/live/desk/position").json()["position"]
            assert pos["pnl"] is None and pos["status"] == "no_data"
            bad = self.c.post("/api/live/desk/manual-close", json={"prices": {"NIFTY2690124100PE": 8}})
            assert bad.status_code == 400
            r = self.c.post("/api/live/desk/manual-close", json={"prices": quotes(8, 15, 3, 5), "exit_reason": "manual"})
            assert r.status_code == 200 and r.json()["pnl_gross"] == pytest.approx(832.0)

    def test_tradebook_import_dedupes(self):
        files = {"file": ("tradebook.csv", io.BytesIO(TRADEBOOK.encode()), "text/csv")}
        r = self.c.post("/api/live/desk/import-tradebook", files=files).json()
        assert len(r["imported"]) == 1 and len(r["skipped"]) == 1 and r["fills"] == 10
        files = {"file": ("tradebook.csv", io.BytesIO(TRADEBOOK.encode()), "text/csv")}
        r = self.c.post("/api/live/desk/import-tradebook", files=files).json()
        assert r["imported"] == [] and r["duplicates"] == 1

    def test_import_rejects_non_csv(self):
        files = {"file": ("tb.xlsx", io.BytesIO(b"x"), "application/octet-stream")}
        assert self.c.post("/api/live/desk/import-tradebook", files=files).status_code == 400


class TestDeskPage:
    """The desk page wires every desk endpoint and never sends a browser-chosen user id."""

    def test_endpoints_and_no_user_header(self):
        html = (PROJECT_ROOT / "static" / "desk.html").read_text(encoding="utf-8")
        for path in ("/api/live/trade-ticket", "/api/live/plan", "/api/live/desk/sync-entry", "/api/live/desk/manual-open",
                     "/api/live/desk/position", "/api/live/desk/sync-exit", "/api/live/desk/manual-close",
                     "/api/live/desk/review", "/api/live/desk/import-tradebook", "/review'"):
            assert path in html, path
        assert "X-User-Id" not in html
        assert "live-execute" not in html      # the desk never places orders
