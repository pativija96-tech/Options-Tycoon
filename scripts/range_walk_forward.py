"""
Range Walk-Forward Validation — Tests whether range containment is predictable
from overnight macro conditions.

Instead of "did I get direction right?" (42.9% OOS — failing), this tests:
"Did NIFTY's daily move stay within ±X% of the open?"

For Iron Condors, the relevant question is: can we predict which days
NIFTY will stay in a tight range (profitable) vs. break out (loss)?

Uses same infrastructure as directional walk-forward:
- Same data: nifty_daily_5yr.csv
- Same buckets: US move, VIX change, DXY change
- Same train/test splits: years 1-3 train, year 4 test, roll forward

Output: bucket-level table showing range containment rates for various widths.

Usage:
    python scripts/range_walk_forward.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np
from datetime import timedelta

from engine.signals.pattern_matcher import load_historical_data, enrich_with_conditions


def run_range_validation(range_widths=[0.5, 0.75, 1.0, 1.25, 1.5]):
    """
    For each condition bucket, compute what % of days NIFTY stayed within ±X%.
    
    This answers: "If I sell an Iron Condor with strikes at ±X% from open,
    what % of the time would it have expired profitable?"
    """
    df = load_historical_data()
    df = enrich_with_conditions(df)
    
    print("=" * 80)
    print("RANGE WALK-FORWARD VALIDATION")
    print("Question: What % of days does NIFTY stay within ±X% of open?")
    print("=" * 80)
    print(f"\nData: {len(df)} trading days")
    print(f"Range widths tested: {range_widths}")
    print()
    
    # Overall baseline (no bucketing)
    print("-" * 80)
    print("BASELINE (All days, no condition filtering)")
    print("-" * 80)
    print(f"{'Width':<10} {'Days In Range':<15} {'Total':<8} {'Containment %':<15} {'Iron Condor Edge?'}")
    
    for width in range_widths:
        in_range = len(df[df["change_pct"].abs() <= width])
        total = len(df)
        pct = in_range / total * 100
        # Iron Condor needs ~65-70%+ containment to be profitable after charges
        edge = "✅ YES" if pct >= 70 else ("⚠️ MARGINAL" if pct >= 60 else "❌ NO")
        print(f"±{width}%{'':<5} {in_range:<15} {total:<8} {pct:.1f}%{'':<10} {edge}")
    
    print()
    
    # By VIX regime bucket
    print("-" * 80)
    print("BY VOLATILITY REGIME (does VIX level predict range?)")
    print("-" * 80)
    
    vol_results = {}
    for regime in ["low", "normal", "high"]:
        subset = df[df["vol_regime"] == regime]
        if len(subset) < 20:
            continue
        vol_results[regime] = {}
        for width in range_widths:
            in_range = len(subset[subset["change_pct"].abs() <= width])
            pct = in_range / len(subset) * 100
            vol_results[regime][width] = {"pct": pct, "n": len(subset)}
    
    print(f"{'Regime':<10} {'N days':<8}", end="")
    for w in range_widths:
        print(f" {'±'+str(w)+'%':<10}", end="")
    print()
    
    for regime in ["low", "normal", "high"]:
        if regime not in vol_results:
            continue
        n = vol_results[regime][range_widths[0]]["n"]
        print(f"{regime:<10} {n:<8}", end="")
        for w in range_widths:
            pct = vol_results[regime][w]["pct"]
            marker = "✅" if pct >= 70 else ("⚠️" if pct >= 60 else "  ")
            print(f" {pct:>5.1f}% {marker} ", end="")
        print()

    print()
    
    # By US move bucket (prev day)
    print("-" * 80)
    print("BY PREVIOUS DAY'S MOVE BUCKET (does yesterday's action predict today's range?)")
    print("-" * 80)
    
    bucket_results = {}
    for bucket in df["prev_1d_bucket"].unique():
        subset = df[df["prev_1d_bucket"] == bucket]
        if len(subset) < 20:
            continue
        bucket_results[bucket] = {}
        for width in range_widths:
            in_range = len(subset[subset["change_pct"].abs() <= width])
            pct = in_range / len(subset) * 100
            bucket_results[bucket][width] = {"pct": pct, "n": len(subset)}
    
    print(f"{'Bucket':<15} {'N days':<8}", end="")
    for w in range_widths:
        print(f" {'±'+str(w)+'%':<10}", end="")
    print()
    
    for bucket in sorted(bucket_results.keys()):
        n = bucket_results[bucket][range_widths[0]]["n"]
        print(f"{bucket:<15} {n:<8}", end="")
        for w in range_widths:
            pct = bucket_results[bucket][w]["pct"]
            marker = "✅" if pct >= 70 else ("⚠️" if pct >= 60 else "  ")
            print(f" {pct:>5.1f}% {marker} ", end="")
        print()
    
    print()
    
    # Combined: VIX regime + prev_1d_bucket
    print("-" * 80)
    print("COMBINED (VIX regime × Previous day bucket) — the actual signal")
    print("-" * 80)
    print("Looking for buckets where containment is significantly ABOVE baseline...")
    print()
    
    # Use 1.0% as the primary IC width (roughly 240 NIFTY pts at 24000 — typical IC width)
    target_width = 1.0
    baseline_pct = len(df[df["change_pct"].abs() <= target_width]) / len(df) * 100
    print(f"Baseline containment at ±{target_width}%: {baseline_pct:.1f}%")
    print(f"Need: significantly above baseline to confirm edge beyond 'VIX was low'\n")
    
    print(f"{'VIX Regime':<12} {'Prev Bucket':<15} {'N':<6} {'±1.0% Contain':<15} {'vs Baseline':<12} {'Signal?'}")
    print("-" * 75)
    
    combined_results = []
    for regime in ["low", "normal", "high"]:
        for bucket in sorted(bucket_results.keys()):
            subset = df[(df["vol_regime"] == regime) & (df["prev_1d_bucket"] == bucket)]
            if len(subset) < 15:
                continue
            in_range = len(subset[subset["change_pct"].abs() <= target_width])
            pct = in_range / len(subset) * 100
            diff = pct - baseline_pct
            signal = "✅ EDGE" if diff > 8 else ("⚠️ weak" if diff > 3 else "")
            combined_results.append({
                "regime": regime, "bucket": bucket, "n": len(subset),
                "pct": pct, "diff": diff, "signal": signal
            })
            if diff > 3 or diff < -8:  # Only show interesting ones
                print(f"{regime:<12} {bucket:<15} {len(subset):<6} {pct:>5.1f}%{'':<9} {diff:>+5.1f}%{'':<6} {signal}")
    
    print()
    
    # Walk-forward: does the range containment hold out-of-sample?
    print("-" * 80)
    print("WALK-FORWARD: Does range containment hold on UNSEEN data?")
    print("-" * 80)
    
    start_date = df["Date"].min()
    end_date = df["Date"].max()
    train_years = 3
    test_months = 6
    
    train_delta = timedelta(days=train_years * 365)
    test_delta = timedelta(days=test_months * 30)
    step_delta = timedelta(days=test_months * 30)
    
    window_start = start_date
    oos_results = []
    
    while window_start + train_delta + test_delta <= end_date:
        train_end = window_start + train_delta
        test_end = train_end + test_delta
        
        train_df = df[(df["Date"] >= window_start) & (df["Date"] < train_end)]
        test_df = df[(df["Date"] >= train_end) & (df["Date"] < test_end)]
        
        if len(train_df) < 100 or len(test_df) < 20:
            window_start += step_delta
            continue
        
        # In-sample: compute containment by vol_regime
        for regime in ["low", "normal", "high"]:
            train_subset = train_df[train_df["vol_regime"] == regime]
            test_subset = test_df[test_df["vol_regime"] == regime]
            
            if len(train_subset) < 20 or len(test_subset) < 10:
                continue
            
            is_contain = len(train_subset[train_subset["change_pct"].abs() <= target_width]) / len(train_subset) * 100
            oos_contain = len(test_subset[test_subset["change_pct"].abs() <= target_width]) / len(test_subset) * 100
            
            oos_results.append({
                "period": f"{train_end.strftime('%Y-%m')} to {test_end.strftime('%Y-%m')}",
                "regime": regime,
                "in_sample": is_contain,
                "out_of_sample": oos_contain,
                "decay": is_contain - oos_contain,
            })
        
        window_start += step_delta
    
    if oos_results:
        print(f"\n{'Period':<22} {'Regime':<10} {'In-Sample':<12} {'OOS':<12} {'Decay'}")
        print("-" * 65)
        for r in oos_results:
            flag = " ⚠️" if r["decay"] > 10 else ""
            print(f"{r['period']:<22} {r['regime']:<10} {r['in_sample']:>5.1f}%{'':<5} {r['out_of_sample']:>5.1f}%{'':<5} {r['decay']:>+5.1f}%{flag}")
        
        # Summary
        avg_oos = np.mean([r["out_of_sample"] for r in oos_results])
        avg_decay = np.mean([r["decay"] for r in oos_results])
        low_vol_oos = [r["out_of_sample"] for r in oos_results if r["regime"] == "low"]
        normal_vol_oos = [r["out_of_sample"] for r in oos_results if r["regime"] == "normal"]
        
        print(f"\n{'='*65}")
        print(f"SUMMARY (at ±{target_width}% range = ~{int(target_width/100*24000)} NIFTY pts)")
        print(f"  Average OOS containment: {avg_oos:.1f}%")
        print(f"  Average decay (IS - OOS): {avg_decay:+.1f}%")
        if low_vol_oos:
            print(f"  Low-vol regime OOS:      {np.mean(low_vol_oos):.1f}%")
        if normal_vol_oos:
            print(f"  Normal-vol regime OOS:   {np.mean(normal_vol_oos):.1f}%")
        print()
        
        if avg_oos >= 70:
            print("✅ VERDICT: Range containment holds well out-of-sample.")
            print("   Iron Condor approach has structural support.")
            print("   Proceed to Step 3 (add IV/options data for refinement).")
        elif avg_oos >= 60:
            print("⚠️ VERDICT: Marginal range containment OOS.")
            print("   May work with wider strikes but edge is thin.")
            print("   Consider: is this better than just 'sell at 1 SD regardless'?")
        else:
            print("❌ VERDICT: Range containment doesn't hold out-of-sample.")
            print("   Bucketing doesn't help predict range any better than baseline.")
            print("   Consider ALT PATH: pure theta strategy, no forecast needed.")
    else:
        print("Insufficient data for walk-forward analysis.")


if __name__ == "__main__":
    run_range_validation()
