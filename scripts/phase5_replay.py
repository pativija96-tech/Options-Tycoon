"""
Phase 5 — run the iron condor replay over the NIFTY option rows saved by
phase5_fetch_bhavcopy.py and print a comparison table.

    python scripts/phase5_replay.py                       # ±200…±400, no loss exit and ₹1,500 loss exit
    python scripts/phase5_replay.py --slippage 0.5        # 0.5 pt per leg per order (less optimistic)

Writes output/phase5_report.json with every trade, so any number can be checked.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.research.bhavcopy import as_date, build_days, read_compact  # noqa: E402
from engine.research.condor_replay import replay, summarize  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "nse_fo"))
    ap.add_argument("--offsets", default="200,250,300,350,400")
    ap.add_argument("--loss-exits", default="none,1500")
    ap.add_argument("--slippage", type=float, default=0.0)
    ap.add_argument("--entry", default="expiry_day")
    a = ap.parse_args()

    # Only near expiries are ever traded (next week's contract), so keep expiries up to
    # 21 days out — the full chain does not fit in memory on a small laptop.
    rows = []
    for p in sorted(Path(a.data).glob("nifty_*.csv")):
        rows += [r for r in read_compact(p) if (as_date(r["expiry"]) - as_date(r["date"])).days <= 21]
    if not rows:
        sys.exit(f"No data in {a.data} — run phase5_fetch_bhavcopy.py first.")
    days = build_days(rows)
    print(f"{len(days)} trading days, {min(days)} to {max(days)}\n")

    entry = a.entry if a.entry == "expiry_day" else int(a.entry)
    report = []
    hdr = f"{'Strikes':<8}{'Loss exit':<11}{'Trades':>7}{'Win %':>7}{'Avg win':>9}{'Avg loss':>10}{'Net ₹':>11}{'Max DD':>10}{'Worst':>9}  Exits"
    print(hdr)
    print("-" * len(hdr))
    for off in [int(x) for x in a.offsets.split(",")]:
        for le in a.loss_exits.split(","):
            le_v = None if le.lower() == "none" else float(le)
            res = replay(days, offset=off, loss_exit=le_v, slippage_pts=a.slippage, entry=entry)
            s = summarize(res)
            report.append({"summary": s, "trades": res["trades"], "skipped": res["skipped"]})
            print(f"±{off:<7}{('₹' + format(int(le_v), ',')) if le_v else 'none':<11}{s['trades']:>7}"
                  f"{(s['win_rate'] or 0):>7.1f}{(s['avg_win'] or 0):>9,.0f}{(s['avg_loss'] or 0):>10,.0f}"
                  f"{(s['net'] or 0):>11,.0f}{(s['max_drawdown'] or 0):>10,.0f}"
                  f"{(s['worst_trade'] or {}).get('pnl_net', 0):>9,.0f}  {s['exit_reasons']}")
    print("\n" + report[0]["summary"]["limits"])
    out = ROOT / "output" / "phase5_report.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"Every trade: {out}")


if __name__ == "__main__":
    main()
