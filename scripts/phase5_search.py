"""
Phase 5 — search rule variants without fooling ourselves.

Every variant is replayed over the whole history, but variants are RANKED only on
trades opened before --split (default 2024-01-01). The top ones are then shown on
trades opened from --split onwards, which played no part in choosing them. A variant
that only looks good before the split is curve-fitting, not an edge.

    python scripts/phase5_search.py                 # writes output/phase5_search.json
    python scripts/phase5_search.py --slippage 0.5
"""

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.research.bhavcopy import as_date, build_days, read_compact  # noqa: E402
from engine.research.condor_replay import replay  # noqa: E402

GRID = {
    "offset": [200, 300, 400, 500, 600],
    "wing": [50, 100, 200],
    "target_pct": [0.25, 0.5, None],
    "exit_days_before_expiry": [0, 1, 2],
    "loss_exit": [None, 2500],
    "entry": ["expiry_day", 0, 2],          # expiry day (the desk), Monday, Wednesday
}
DESK = {"offset": 250, "wing": 100, "target_pct": 0.5, "exit_days_before_expiry": 1, "loss_exit": None, "entry": "expiry_day"}


def split_stats(trades, split):
    def s(ts):
        n = len(ts)
        net = round(sum(t["pnl_net"] for t in ts), 2)
        return {"trades": n, "net": net, "per_trade": round(net / n, 1) if n else None,
                "win_rate": round(sum(1 for t in ts if t["pnl_net"] > 0) / n * 100, 1) if n else None}
    return s([t for t in trades if t["opened_on"] < split]), s([t for t in trades if t["opened_on"] >= split])


def label(p):
    e = {"expiry_day": "expiry day", 0: "Mon", 2: "Wed"}[p["entry"]]
    tgt = f"{int(p['target_pct'] * 100)}%" if p["target_pct"] else "none"
    le = f"₹{p['loss_exit']:,}" if p["loss_exit"] else "none"
    return f"±{p['offset']} wing {p['wing']} · target {tgt} · exit {p['exit_days_before_expiry']}d early · loss {le} · enter {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "nse_fo"))
    ap.add_argument("--split", default="2024-01-01")
    ap.add_argument("--slippage", type=float, default=0.0)
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()

    rows = []
    for p in sorted(Path(a.data).glob("nifty_*.csv")):
        rows += [r for r in read_compact(p) if (as_date(r["expiry"]) - as_date(r["date"])).days <= 21]
    days = build_days(rows)
    del rows

    keys = list(GRID)
    combos = [dict(zip(keys, v)) for v in itertools.product(*GRID.values())]
    combos.insert(0, DESK)
    results, t0 = [], time.time()
    for i, p in enumerate(combos):
        res = replay(days, slippage_pts=a.slippage, **p)
        ins, oos = split_stats(res["trades"], a.split)
        results.append({"params": p, "label": label(p), "in_sample": ins, "out_of_sample": oos})
        if i % 50 == 0:
            print(f"{i}/{len(combos)} variants  ({time.time() - t0:.0f}s)", flush=True)

    desk = results[0]
    ranked = sorted(results[1:], key=lambda r: -(r["in_sample"]["per_trade"] or -1e9))
    pos_in = sum(1 for r in results[1:] if (r["in_sample"]["net"] or 0) > 0)
    pos_out = sum(1 for r in results[1:] if (r["out_of_sample"]["net"] or 0) > 0)
    top = ranked[:a.top]
    top_pos_out = sum(1 for r in top if (r["out_of_sample"]["net"] or 0) > 0)

    def fmt(r):
        i, o = r["in_sample"], r["out_of_sample"]
        return (f"{r['label']}\n      before {a.split}: {i['trades']} trades, win {i['win_rate']}%, ₹{i['per_trade']}/trade, net ₹{i['net']:,.0f}"
                f"   |   after: {o['trades']} trades, win {o['win_rate']}%, ₹{o['per_trade']}/trade, net ₹{o['net']:,.0f}")

    print(f"\n{len(results) - 1} variants, slippage {a.slippage} pt/leg/order. Ranked on trades before {a.split} only.\n")
    print("DESK RULES TODAY:\n  " + fmt(desk))
    print(f"\nTOP {a.top} BEFORE {a.split}, and how they did AFTER (unseen):")
    for r in top:
        print("  " + fmt(r))
    print(f"\nVariants with positive net before {a.split}: {pos_in} of {len(results) - 1}")
    print(f"Variants with positive net after  {a.split}: {pos_out} of {len(results) - 1}")
    print(f"Of the top {a.top} chosen on the earlier years, positive afterwards: {top_pos_out}")

    out = ROOT / "output" / f"phase5_search_slip{a.slippage}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"split": a.split, "slippage": a.slippage, "grid": {k: [str(x) for x in v] for k, v in GRID.items()},
                               "desk": desk, "ranked": ranked}, indent=2, default=str))
    print(f"\nAll variants: {out}")


if __name__ == "__main__":
    main()
