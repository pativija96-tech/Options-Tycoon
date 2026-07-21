"""
Per-Filter Predictive Value Analysis — Correlates individual filter results with trade outcomes.

After 10+ resolved trades, this script answers:
- Does win rate improve monotonically as more filters pass?
- Which individual filters are correlated with wins vs noise?
- Should any filters be removed/replaced?

Usage:
    python scripts/filter_analysis.py

Requires: 10+ resolved trades in live_trades + matching signal_history records.
"""

import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.database import get_connection


def run_filter_analysis():
    """
    Join signal_history with live_trades on date, analyze filter→outcome correlation.
    """
    conn = get_connection()
    try:
        # Get resolved trades with their signal data
        rows = conn.execute("""
            SELECT sh.signal_date, sh.quality_filters_json, sh.filters_passed,
                   lt.status, lt.pnl
            FROM signal_history sh
            INNER JOIN live_trades lt ON sh.signal_date = lt.date
            WHERE lt.status IN ('win', 'loss')
            ORDER BY sh.signal_date
        """).fetchall()
        
        if not rows:
            print("No resolved trades with matching signals found.")
            print("Need: signal_history records + live_trades with status='win'/'loss' on same dates.")
            return
        
        trades = [dict(r) for r in rows]
        print(f"Found {len(trades)} resolved trades with signal data.\n")
        
        # Analysis 1: Win rate by filter count
        print("=" * 60)
        print("WIN RATE BY FILTER COUNT")
        print("=" * 60)
        count_buckets = {}
        for t in trades:
            fp = t.get("filters_passed", 0) or 0
            if fp not in count_buckets:
                count_buckets[fp] = {"wins": 0, "total": 0}
            count_buckets[fp]["total"] += 1
            if t["status"] == "win":
                count_buckets[fp]["wins"] += 1
        
        print(f"{'Filters Passed':<16} {'Trades':<8} {'Wins':<6} {'Win Rate'}")
        print("-" * 50)
        for fp in sorted(count_buckets.keys()):
            b = count_buckets[fp]
            wr = b["wins"] / b["total"] * 100 if b["total"] > 0 else 0
            bar = "█" * int(wr / 5)
            print(f"{fp}/7{'':<12} {b['total']:<8} {b['wins']:<6} {wr:>5.1f}% {bar}")
        
        # Check monotonicity
        rates = [(fp, count_buckets[fp]["wins"] / count_buckets[fp]["total"])
                 for fp in sorted(count_buckets.keys()) if count_buckets[fp]["total"] >= 2]
        if len(rates) >= 2:
            is_monotonic = all(rates[i][1] <= rates[i+1][1] for i in range(len(rates)-1))
            if is_monotonic:
                print("\n✅ Win rate increases monotonically with filter count.")
            else:
                print("\n⚠️ Win rate is NOT monotonic — some filter counts outperform higher ones.")
        
        # Analysis 2: Per-filter correlation
        print("\n" + "=" * 60)
        print("PER-FILTER WIN RATE (does each filter add signal?)")
        print("=" * 60)
        
        filter_stats = {}  # filter_name -> {pass_wins, pass_total, fail_wins, fail_total}
        
        for t in trades:
            qf_json = t.get("quality_filters_json")
            if not qf_json:
                continue
            try:
                qf = json.loads(qf_json)
                filters = qf.get("filters", {})
            except (json.JSONDecodeError, TypeError):
                continue
            
            is_win = t["status"] == "win"
            
            for name, f in filters.items():
                if name not in filter_stats:
                    filter_stats[name] = {"pass_wins": 0, "pass_total": 0, "fail_wins": 0, "fail_total": 0}
                
                passed = f.get("pass")
                # Handle string/bool
                if isinstance(passed, str):
                    passed = passed.lower() == "true"
                
                if passed:
                    filter_stats[name]["pass_total"] += 1
                    if is_win:
                        filter_stats[name]["pass_wins"] += 1
                else:
                    filter_stats[name]["fail_total"] += 1
                    if is_win:
                        filter_stats[name]["fail_wins"] += 1
        
        print(f"\n{'Filter':<25} {'When PASS':<15} {'When FAIL':<15} {'Lift'}")
        print("-" * 65)
        
        for name, s in filter_stats.items():
            pass_wr = s["pass_wins"] / s["pass_total"] * 100 if s["pass_total"] > 0 else 0
            fail_wr = s["fail_wins"] / s["fail_total"] * 100 if s["fail_total"] > 0 else 0
            lift = pass_wr - fail_wr
            indicator = "✅" if lift > 5 else "⚠️" if lift > 0 else "❌"
            
            pass_str = f"{pass_wr:.0f}% (n={s['pass_total']})"
            fail_str = f"{fail_wr:.0f}% (n={s['fail_total']})" if s["fail_total"] > 0 else "N/A"
            
            print(f"{name:<25} {pass_str:<15} {fail_str:<15} {lift:>+5.1f}% {indicator}")
        
        # Summary
        print("\n" + "=" * 60)
        useful = [n for n, s in filter_stats.items()
                  if s["pass_total"] > 0 and s["fail_total"] > 0
                  and (s["pass_wins"]/s["pass_total"] > s["fail_wins"]/s["fail_total"])]
        noise = [n for n, s in filter_stats.items()
                 if s["pass_total"] > 0 and s["fail_total"] > 0
                 and (s["pass_wins"]/s["pass_total"] <= s["fail_wins"]/s["fail_total"])]
        
        if useful:
            print(f"USEFUL FILTERS (higher win rate when passing): {', '.join(useful)}")
        if noise:
            print(f"NOISE FILTERS (no benefit when passing): {', '.join(noise)}")
        if not useful and not noise:
            print("Need more data to determine filter usefulness.")
    
    finally:
        conn.close()


if __name__ == "__main__":
    run_filter_analysis()
