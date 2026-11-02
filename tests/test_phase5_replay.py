"""
Phase 5: bhavcopy reading (both NSE layouts) and the iron condor replay. Offline.

Run: python -m pytest tests/test_phase5_replay.py -v
"""

import sys
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from engine.research import bhavcopy as B  # noqa: E402
from engine.research.condor_replay import replay, summarize  # noqa: E402

OLD_CSV = """INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP,
OPTIDX,NIFTY,08-Sep-2022,17500,CE,100,120,90,110,110,10,1,1,1,01-SEP-2022,
OPTIDX,NIFTY,08-Sep-2022,17500,PE,80,90,70,75,75,10,1,1,1,01-SEP-2022,
OPTIDX,BANKNIFTY,08-Sep-2022,39000,CE,1,1,1,1,1,1,1,1,1,01-SEP-2022,
FUTIDX,NIFTY,29-Sep-2022,0,XX,1,1,1,1,1,1,1,1,1,01-SEP-2022,
OPTIDX,NIFTYNXT50,08-Sep-2022,40000,CE,1,1,1,1,1,1,1,1,1,01-SEP-2022,
"""
NEW_CSV = """TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric
2026-10-27,2026-10-27,FO,NSE,IDO,1,,NIFTY,,2026-11-03,2026-11-03,23000,PE,x,50,60,40,0,55,52,23050,48.5
2026-10-27,2026-10-27,FO,NSE,IDO,2,,BANKNIFTY,,2026-11-03,2026-11-03,51000,CE,x,1,1,1,1,1,1,1,1
2026-10-27,2026-10-27,FO,NSE,IDF,3,,NIFTY,,2026-11-25,2026-11-25,0,,x,1,1,1,1,1,1,1,1
"""


class TestBhavcopy:
    def test_old_layout_keeps_only_nifty_index_options(self):
        rows = B.nifty_options(OLD_CSV)
        assert [(r["strike"], r["opt"]) for r in rows] == [(17500, "CE"), (17500, "PE")]
        assert rows[0]["date"] == "2022-09-01" and rows[0]["expiry"] == "2022-09-08" and rows[0]["close"] == 110

    def test_new_layout_and_settle_fallback(self):
        rows = B.nifty_options(NEW_CSV)
        assert len(rows) == 1 and rows[0]["expiry"] == "2026-11-03" and rows[0]["opt"] == "PE"
        assert B.price(rows[0]) == 48.5                     # close 0 → settlement price

    def test_missing_column_is_named(self):
        bad = OLD_CSV.replace("SETTLE_PR", "SETTLE")
        with pytest.raises(B.BhavcopyFormatError, match="SETTLE_PR"):
            B.nifty_options(bad)

    def test_unknown_layout_rejected(self):
        with pytest.raises(B.BhavcopyFormatError):
            B.nifty_options("a,b,c\n1,2,3\n")

    def test_parity_spot(self):
        chain = {(24000, "CE"): {"close": 120}, (24000, "PE"): {"close": 100},
                 (24100, "CE"): {"close": 70}, (24100, "PE"): {"close": 160}}
        assert B.parity_spot(chain) == 24020.0               # 24000 + 120 − 100

    def test_compact_round_trip(self, tmp_path):
        rows = B.nifty_options(OLD_CSV)
        B.write_compact(rows, tmp_path / "x.csv")
        assert B.read_compact(tmp_path / "x.csv") == rows


# ── Replay on hand-made chains ──────────────────────────────────────────────
# Entry Tue 1 Sep (an expiry day) into the 8 Sep expiry. NIFTY 24,000 (ATM call = put).
E0, E1 = "2026-09-01", "2026-09-08"


def chain(sp_pe, sc_ce, lp_pe, lc_ce, atm=100):
    return {(24000, "CE"): {"close": atm}, (24000, "PE"): {"close": atm},
            (23750, "PE"): {"close": sp_pe}, (24250, "CE"): {"close": sc_ce},
            (23650, "PE"): {"close": lp_pe}, (24350, "CE"): {"close": lc_ce}}


def days(path):
    """path: {date: (sp, sc, lp, lc)} for the E1 contract; E0 also lists an E0 expiry so it is an expiry day."""
    d = {}
    for t, px in path.items():
        d[t] = {E1: chain(*px)}
    d[E0][E0] = {(24000, "CE"): {"close": 1}}
    return d


ENTRY = (30, 30, 10, 10)            # credit 40/share → ₹2,600, max loss (100 − 40) × 65 = ₹3,900


class TestReplay:
    def test_profit_target_exit(self):
        r = replay(days({E0: ENTRY, "2026-09-02": (22, 22, 10, 10), "2026-09-03": (12, 12, 8, 8)}))  # day 2: +16 × 65 = 1,040 < 1,300
        t = r["trades"][0]
        assert t["entry_credit"] == 40 and t["credit_rupees"] == 2600 and t["max_loss"] == 3900
        assert t["exit_reason"] == "target" and t["closed_on"] == "2026-09-03"   # cost 8 → +32 × 65
        assert t["pnl_gross"] == pytest.approx(2080) and t["pnl_net"] == pytest.approx(2080 - 238.8)

    def test_loss_exit(self):
        r = replay(days({E0: ENTRY, "2026-09-02": (70, 20, 30, 10)}), loss_exit=1500)
        t = r["trades"][0]                                   # cost 50 → −10 × 65 = −650: not yet
        assert t["exit_reason"] != "loss_exit"
        r = replay(days({E0: ENTRY, "2026-09-02": (90, 20, 30, 10)}), loss_exit=1500)
        t = r["trades"][0]                                   # cost 70 → −30 × 65 = −1,950
        assert t["exit_reason"] == "loss_exit" and t["pnl_gross"] == pytest.approx(-1950)

    def test_exit_day_is_one_trading_day_before_expiry(self):
        flat = {E0: ENTRY, "2026-09-02": ENTRY, "2026-09-03": ENTRY, "2026-09-04": ENTRY,
                "2026-09-07": ENTRY, E1: (0.05, 0.05, 0.05, 0.05)}
        t = replay(days(flat))["trades"][0]
        assert t["exit_reason"] == "exit_day" and t["closed_on"] == "2026-09-07" and t["pnl_gross"] == 0

    def test_hold_to_expiry_when_asked(self):
        flat = {E0: ENTRY, "2026-09-02": ENTRY, "2026-09-07": ENTRY, E1: (0.05, 0.05, 0.05, 0.05)}
        t = replay(days(flat), exit_days_before_expiry=0, target_pct=None)["trades"][0]
        assert t["exit_reason"] == "expiry" and t["closed_on"] == E1

    def test_slippage_reduces_credit_and_pnl(self):
        a = replay(days({E0: ENTRY, "2026-09-02": (12, 12, 8, 8)}))["trades"][0]
        b = replay(days({E0: ENTRY, "2026-09-02": (12, 12, 8, 8)}), slippage_pts=0.5)["trades"][0]
        assert b["entry_credit"] == 38 and b["pnl_gross"] < a["pnl_gross"]

    def test_missing_leg_is_skipped_with_reason(self):
        d = days({E0: ENTRY, "2026-09-02": ENTRY})
        del d[E0][E1][(23650, "PE")]
        r = replay(d)
        assert not r["trades"] and "23650 PE" in r["skipped"][0]["reason"]

    def test_missing_price_carries_last_and_is_counted(self):
        d = days({E0: ENTRY, "2026-09-02": ENTRY, "2026-09-07": ENTRY})
        del d["2026-09-02"][E1][(24250, "CE")]
        t = replay(d)["trades"][0]
        assert t["price_gaps"] == 1

    def test_summary_uses_desk_scorecard(self):
        s = summarize(replay(days({E0: ENTRY, "2026-09-02": (12, 12, 8, 8)})))
        assert s["trades"] == 1 and s["win_rate"] == 100.0 and s["exit_reasons"] == {"target": 1}
        assert s["by_year"]["2026"]["trades"] == 1 and "End-of-day prices only" in s["limits"]


class TestFetchUrls:
    def test_old_and_new_patterns(self):
        import phase5_fetch_bhavcopy as F
        old = F.urls(date(2022, 9, 1))
        assert old[0].endswith("/DERIVATIVES/2022/SEP/fo01SEP2022bhav.csv.zip")
        new = F.urls(date(2026, 10, 27))
        assert new[0].endswith("/content/fo/BhavCopy_NSE_FO_0_0_0_20261027_F_0000.csv.zip")


    def test_hold_to_expiry_reenters_on_the_expiry_day(self):
        E2 = "2026-09-15"
        d = days({E0: ENTRY, "2026-09-02": ENTRY, "2026-09-07": ENTRY, E1: (0.05, 0.05, 0.05, 0.05)})
        d[E1][E2] = chain(*ENTRY)                       # 8 Sep is also the entry day for the 15 Sep contract
        d["2026-09-09"] = {E2: chain(*ENTRY)}
        d["2026-09-14"] = {E2: chain(*ENTRY)}
        d["2026-09-15"] = {E2: chain(0.05, 0.05, 0.05, 0.05)}
        r = replay(d, exit_days_before_expiry=0, target_pct=None)
        assert [t["opened_on"] for t in r["trades"]] == [E0, E1]
