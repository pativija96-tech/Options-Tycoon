"""
Morning range check: history loaders (mocked Kite / Yahoo), storage, the range
report and its honesty checks, and the desk endpoints. Runs offline.

Run: python -m pytest tests/test_range_odds.py -v
"""

import random
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.desk import range_odds as R  # noqa: E402
from engine.desk import history as H  # noqa: E402


def weekdays(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def synthetic(years=6, end=date(2026, 10, 27), seed=7):
    """Random-walk NIFTY, India VIX and world closes; deterministic."""
    rnd = random.Random(seed)
    days = list(weekdays(end - timedelta(days=365 * years), end))
    series = {k: [] for k in ["nifty", "india_vix"] + R.WORLD_SHOWN}
    px, vix = 15000.0, 15.0
    world = {k: 100.0 for k in R.WORLD_SHOWN}
    for d in days:
        o = px * (1 + rnd.gauss(0, 0.003))
        c = o * (1 + rnd.gauss(0, 0.008))
        series["nifty"].append({"date": d.isoformat(), "open": o, "high": max(o, c) * 1.003,
                                "low": min(o, c) * 0.997, "close": c})
        px = c
        vix = min(35, max(9, vix + rnd.gauss(0, 0.6)))
        series["india_vix"].append({"date": d.isoformat(), "open": vix, "high": vix, "low": vix, "close": vix})
        for k in R.WORLD_SHOWN:
            world[k] *= 1 + rnd.gauss(0, 0.01)
            series[k].append({"date": d.isoformat(), "open": None, "high": None, "low": None, "close": world[k]})
    return series


# ── Analysis ────────────────────────────────────────────────────────────────

class TestConditions:
    def test_only_closes_before_the_morning_are_used(self):
        rows = [{"date": "2026-10-26", "close": 100.0}, {"date": "2026-10-27", "close": 101.0},
                {"date": "2026-10-28", "close": 150.0}]                      # same-day close must be ignored
        chg, d = R.last_two_before(rows, date(2026, 10, 28))
        assert chg == 1.0 and d == "2026-10-27"

    def test_holiday_uses_last_available_close(self):
        rows = [{"date": "2026-10-22", "close": 100.0}, {"date": "2026-10-23", "close": 99.0}]
        chg, d = R.last_two_before(rows, date(2026, 10, 28))                 # market shut 26–27 Oct
        assert chg == -1.0 and d == "2026-10-23"

    def test_buckets_reuse_signal_engine_thresholds(self):
        cond = {"india_vix": 20.0, "nifty_5d_pct": 6.0, "world": {"sp500": {"change_pct": -1.4}}}
        b = R.buckets(cond, (12.0, 16.0))
        assert b == {"vix_band": "high", "us_bucket": "strong_down", "trend_bucket": "strong_up"}


class TestSamples:
    def _series(self):
        days = list(weekdays(date(2026, 9, 1), date(2026, 9, 30)))
        nifty = [{"date": d.isoformat(), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0} for d in days]
        # Tue 15 Sep entry, window 15–21 Sep: high 104 on the 17th, low 97 on the 21st
        idx = {r["date"]: r for r in nifty}
        idx["2026-09-17"]["high"] = 104.0
        idx["2026-09-21"]["low"], idx["2026-09-21"]["close"] = 97.0, 98.0
        return {"nifty": nifty}

    def test_window_uses_open_then_highs_and_lows(self):
        s = [x for x in R.build_samples(self._series(), date(2026, 10, 1), 5, 1) if x["date"] == "2026-09-15"][0]
        assert s["exit_date"] == "2026-09-21"
        assert s["up_pct"] == pytest.approx(4.0) and s["down_pct"] == pytest.approx(3.0)
        assert s["end_pct"] == pytest.approx(-2.0)

    def test_unfinished_windows_are_excluded(self):
        samples = R.build_samples(self._series(), date(2026, 9, 25), 5, 1)
        assert all(x["exit_date"] < "2026-09-25" for x in samples)


class TestReport:
    def test_report_shape_and_monotonic_odds(self):
        rep = R.report(synthetic(), date(2026, 10, 28), horizon=5, weekday=1, min_matches=20)
        assert rep["ready"] and rep["weekday"] == "Tue" and rep["matches"] >= 20
        assert rep["matched_on"], "should match on at least one condition"
        pcts = [r["all"]["pct"] for r in rep["rows"]]
        assert pcts == sorted(pcts)                                          # wider band never stays less often
        for r in rep["rows"]:
            lo, hi = r["matched"]["ci95"]
            assert lo <= r["matched"]["pct"] <= hi
        assert rep["walk_forward"]["tested_weeks"] > 0
        assert rep["episodes"] <= rep["matches"]

    def test_widths_scale_to_todays_level(self):
        rep = R.report(synthetic(), date(2026, 10, 28), weekday=1)
        row = next(r for r in rep["rows"] if r["width"] == 250)
        assert row["width_pct"] == pytest.approx(250 / rep["spot"] * 100, abs=0.01)

    def test_drops_conditions_when_matches_run_short(self):
        rep = R.report(synthetic(), date(2026, 10, 28), weekday=1, min_matches=60)
        assert len(rep["matched_on"]) < 3 or rep["matches"] >= 60

    def test_not_ready_without_history(self):
        rep = R.report({"nifty": synthetic()["nifty"][:100]}, date(2026, 10, 28))
        assert not rep["ready"] and "Load history" in rep["reason"]

    def test_missing_vix_and_us_are_noted_not_invented(self):
        s = synthetic()
        del s["india_vix"], s["sp500"]
        rep = R.report(s, date(2026, 10, 28), weekday=1)
        assert any("India VIX" in n for n in rep["notes"]) and any("S&P 500" in n for n in rep["notes"])
        assert "vix_band" not in rep["matched_on"] and "us_bucket" not in rep["matched_on"]

    def test_walk_forward_compares_against_plain_history(self):
        wf = R.report(synthetic(), date(2026, 10, 28), weekday=1)["walk_forward"]
        assert set(wf) == {"tested_weeks", "brier_matched", "brier_all_days", "verdict"}
        better = wf["brier_matched"] < wf["brier_all_days"]
        assert ("did NOT" not in wf["verdict"]) == better


# ── Loaders ─────────────────────────────────────────────────────────────────

class TestLoaders:
    def test_world_list_comes_from_signal_engine_without_fake_gift_nifty(self):
        from engine.signals.data_fetcher import INDICES
        assert "gift_nifty" not in H.WORLD and set(H.WORLD) == set(INDICES) - {"gift_nifty"}

    def test_kite_loader_finds_tokens_and_fetches_in_chunks(self):
        kite = MagicMock()
        kite.instruments.return_value = [{"tradingsymbol": "NIFTY 50", "instrument_token": 256},
                                         {"tradingsymbol": "INDIA VIX", "instrument_token": 264},
                                         {"tradingsymbol": "NIFTY BANK", "instrument_token": 260}]
        kite.historical_data.side_effect = lambda tok, frm, to, iv: [
            {"date": frm, "open": 1, "high": 2, "low": 0.5, "close": 1.5}]
        errors = []
        rows = H.load_kite(kite, date(2026, 10, 28), 2, errors)
        assert not errors
        kite.instruments.assert_called_once_with("NSE")
        tokens = {c.args[0] for c in kite.historical_data.call_args_list}
        assert tokens == {256, 264}
        assert all(c.args[3] == "day" and (c.args[2] - c.args[1]).days < H.KITE_CHUNK_DAYS
                   for c in kite.historical_data.call_args_list)
        assert {r["source"] for r in rows} == {"kite"} and {r["symbol"] for r in rows} == {"nifty", "india_vix"}

    def test_kite_errors_are_reported_not_raised(self):
        kite = MagicMock()
        kite.instruments.return_value = [{"tradingsymbol": "NIFTY 50", "instrument_token": 256}]
        kite.historical_data.side_effect = Exception("Insufficient permission for that call")
        errors = []
        assert H.load_kite(kite, date(2026, 10, 28), 1, errors) == []
        assert any("INDIA VIX" in e for e in errors) and any("Insufficient permission" in e for e in errors)

    def test_yahoo_loader_handles_multiindex_columns(self):
        import pandas as pd
        idx = pd.to_datetime(["2026-10-26", "2026-10-27"])
        cols = pd.MultiIndex.from_product([["Open", "High", "Low", "Close"], ["^GSPC"]])
        df = pd.DataFrame([[1, 2, 0.5, 1.5], [1.5, 2.5, 1.0, float("nan")]], index=idx, columns=cols)
        errors = []
        rows = H.load_yahoo({"sp500": "^GSPC"}, date(2026, 10, 28), 1, errors, downloader=lambda *a, **k: df)
        assert not errors and len(rows) == 1                                 # NaN close skipped
        assert rows[0] == {"symbol": "sp500", "date": "2026-10-26", "open": 1.0, "high": 2.0,
                           "low": 0.5, "close": 1.5, "source": "yahoo"}


# ── Storage + endpoints ─────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path, monkeypatch):
    import db.database as dbm
    if dbm.USE_POSTGRES:
        pytest.skip("runs on SQLite only")
    path = str(tmp_path / "test.db")
    monkeypatch.setattr(dbm, "get_db_path", lambda: path)
    dbm.init_db(path)
    from db.migrations import run_migrations
    run_migrations()
    return path


class TestStorage:
    def test_yahoo_never_replaces_kite_but_kite_replaces_yahoo(self, db):
        H.save_rows([{"symbol": "nifty", "date": "2026-10-27", "open": 1, "high": 1, "low": 1, "close": 100, "source": "kite"},
                     {"symbol": "nifty", "date": "2026-10-28", "open": 1, "high": 1, "low": 1, "close": 200, "source": "yahoo"}])
        H.save_rows([{"symbol": "nifty", "date": "2026-10-27", "open": 1, "high": 1, "low": 1, "close": 999, "source": "yahoo"},
                     {"symbol": "nifty", "date": "2026-10-28", "open": 1, "high": 1, "low": 1, "close": 201, "source": "kite"}])
        rows = {r["date"]: r for r in H.load_series()["nifty"]}
        assert rows["2026-10-27"]["close"] == 100 and rows["2026-10-27"]["source"] == "kite"
        assert rows["2026-10-28"]["close"] == 201 and rows["2026-10-28"]["source"] == "kite"

    def test_load_all_without_kite_labels_the_fallback(self, db):
        import pandas as pd
        df = pd.DataFrame({"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5]}, index=pd.to_datetime(["2026-10-27"]))
        out = H.load_all(None, date(2026, 10, 28), years=1, downloader=lambda *a, **k: df)
        assert out["india_source"] == "yahoo (fallback)"
        assert any("Kite not connected" in e for e in out["errors"])
        status = {s["symbol"]: s for s in out["status"]}
        assert status["nifty"]["sources"] == ["yahoo"] and status["sp500"]["rows"] == 1


class TestEndpoints:
    @pytest.fixture(autouse=True)
    def client(self, db, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from engine.session import require_founder
        from routes.live import router
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_founder] = lambda: {"user_id": 7, "email": "test@test.com", "name": "T"}
        self.c = TestClient(app)
        from engine.desk import kite_data
        monkeypatch.setattr(kite_data, "ist_today", lambda: date(2026, 10, 28))

    def test_range_odds_before_and_after_history(self):
        r = self.c.get("/api/live/desk/range-odds").json()
        assert r["success"] and not r["report"]["ready"]
        rows = [dict(row, symbol=k, source="kite" if k in ("nifty", "india_vix") else "yahoo")
                for k, v in synthetic().items() for row in v]
        H.save_rows(rows)
        rep = self.c.get("/api/live/desk/range-odds?horizon=5&weekday=Tue").json()["report"]
        assert rep["ready"] and rep["weekday"] == "Tue" and rep["min_matches"] == 20
        status = self.c.get("/api/live/desk/history/status").json()["status"]
        assert next(s for s in status if s["symbol"] == "nifty")["sources"] == ["kite"]

    def test_bad_parameters_rejected(self):
        assert self.c.get("/api/live/desk/range-odds?horizon=0").status_code == 400
        assert self.c.get("/api/live/desk/range-odds?weekday=Sun").status_code == 400

    def test_load_endpoint_uses_kite_when_connected(self, monkeypatch):
        import routes.live as live
        seen = {}

        def fake_load_all(kite, today):
            seen["kite"], seen["today"] = kite, today
            return {"saved": 0, "india_source": "kite", "errors": [], "status": []}

        monkeypatch.setattr(H, "load_all", fake_load_all)
        sentinel = object()
        monkeypatch.setattr(live, "_kite_or_none", lambda: sentinel)
        r = self.c.post("/api/live/desk/history/load").json()
        assert r["success"] and seen == {"kite": sentinel, "today": date(2026, 10, 28)}
