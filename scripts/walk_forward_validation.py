"""
Walk-Forward Validation — Tests whether the pattern-matching edge holds out-of-sample.

Splits 5-year NIFTY history into rolling windows:
- Train: Years 1-3 (learn bucket probabilities)
- Test: Year 4 (out-of-sample predictions)
- Roll forward by 6 months, repeat

Output: validation report showing win rate on unseen data per window.
If out-of-sample win rate drops significantly, the bucket boundaries may be overfit.

Usage:
    python scripts/walk_forward_validation.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np
from datetime import timedelta

from engine.signals.pattern_matcher import load_historical_data, enrich_with_conditions
from engine.signals.data_fetcher import bucket_us_move


def run_walk_forward(train_years=3, test_months=6, min_matches=20):
    """
    Run walk-forward validation across rolling windows.
    
    Returns list of window results with in-sample vs out-of-sample win rates.
    """
    df = load_historical_data()
    df = enrich_with_conditions(df)
    
    if len(df) < 500:
        print(f"Insufficient data: {len(df)} rows. Need at least 500.")
        return []
    
    results = []
    start_date = df["Date"].min()
    end_date = df["Date"].max()
    
    train_delta = timedelta(days=train_years * 365)
    test_delta = timedelta(days=test_months * 30)
    step_delta = timedelta(days=test_months * 30)
    
    window_start = start_date
    window_num = 0
    
    while window_start + train_delta + test_delta <= end_date:
        window_num += 1
        train_end = window_start + train_delta
        test_end = train_end + test_delta
        
        train_df = df[(df["Date"] >= window_start) & (df["Date"] < train_end)]
        test_df = df[(df["Date"] >= train_end) & (df["Date"] < test_end)]

        if len(train_df) < 100 or len(test_df) < 20:
            window_start += step_delta
            continue
        
        # For each bucket in training data, compute direction probabilities
        buckets = train_df["prev_1d_bucket"].unique()
        bucket_predictions = {}
        
        for bucket in buckets:
            bucket_rows = train_df[train_df["prev_1d_bucket"] == bucket]
            if len(bucket_rows) < min_matches:
                continue
            
            up_days = len(bucket_rows[bucket_rows["change_pct"] > 0.1])
            down_days = len(bucket_rows[bucket_rows["change_pct"] < -0.1])
            total = len(bucket_rows)
            
            if up_days > down_days:
                predicted_dir = "bullish"
                confidence = up_days / total
            elif down_days > up_days:
                predicted_dir = "bearish"
                confidence = down_days / total
            else:
                predicted_dir = "neutral"
                confidence = 0.5
            
            bucket_predictions[bucket] = {
                "direction": predicted_dir,
                "confidence": confidence,
                "sample_size": total,
            }
        
        # Test on out-of-sample data
        correct = 0
        total_tested = 0
        
        for _, row in test_df.iterrows():
            bucket = row.get("prev_1d_bucket")
            if bucket not in bucket_predictions:
                continue
            
            pred = bucket_predictions[bucket]
            actual_move = row["change_pct"]
            
            if pred["direction"] == "bullish" and actual_move > 0.1:
                correct += 1
            elif pred["direction"] == "bearish" and actual_move < -0.1:
                correct += 1
            elif pred["direction"] == "neutral" and abs(actual_move) <= 0.1:
                correct += 1
            
            total_tested += 1
        
        oos_win_rate = correct / total_tested if total_tested > 0 else 0
        
        # In-sample win rate for comparison
        is_correct = 0
        is_total = 0
        for _, row in train_df.iterrows():
            bucket = row.get("prev_1d_bucket")
            if bucket not in bucket_predictions:
                continue
            pred = bucket_predictions[bucket]
            actual_move = row["change_pct"]
            if pred["direction"] == "bullish" and actual_move > 0.1:
                is_correct += 1
            elif pred["direction"] == "bearish" and actual_move < -0.1:
                is_correct += 1
            elif pred["direction"] == "neutral" and abs(actual_move) <= 0.1:
                is_correct += 1
            is_total += 1
        
        is_win_rate = is_correct / is_total if is_total > 0 else 0
        
        results.append({
            "window": window_num,
            "train_period": f"{window_start.strftime('%Y-%m')} to {train_end.strftime('%Y-%m')}",
            "test_period": f"{train_end.strftime('%Y-%m')} to {test_end.strftime('%Y-%m')}",
            "train_rows": len(train_df),
            "test_rows": len(test_df),
            "buckets_with_signal": len(bucket_predictions),
            "signals_tested": total_tested,
            "in_sample_win_rate": round(is_win_rate * 100, 1),
            "out_of_sample_win_rate": round(oos_win_rate * 100, 1),
            "edge_decay": round((is_win_rate - oos_win_rate) * 100, 1),
        })
        
        window_start += step_delta
    
    return results


def print_report(results):
    """Print a formatted validation report."""
    if not results:
        print("No results — insufficient data for walk-forward validation.")
        return
    
    print("=" * 80)
    print("WALK-FORWARD VALIDATION REPORT")
    print("=" * 80)
    print(f"{'Window':<8} {'Train Period':<22} {'Test Period':<22} {'In-Sample':<12} {'Out-of-Sample':<15} {'Edge Decay'}")
    print("-" * 80)
    
    for r in results:
        decay_flag = " ⚠️" if r["edge_decay"] > 10 else ""
        print(f"{r['window']:<8} {r['train_period']:<22} {r['test_period']:<22} "
              f"{r['in_sample_win_rate']:>5}%      {r['out_of_sample_win_rate']:>5}%        "
              f"{r['edge_decay']:>+5.1f}%{decay_flag}")
    
    print("-" * 80)
    avg_oos = np.mean([r["out_of_sample_win_rate"] for r in results])
    avg_decay = np.mean([r["edge_decay"] for r in results])
    print(f"\nAverage out-of-sample win rate: {avg_oos:.1f}%")
    print(f"Average edge decay (in-sample minus OOS): {avg_decay:+.1f}%")
    
    if avg_oos > 55:
        print("\n✅ VERDICT: Edge appears to hold on unseen data.")
    elif avg_oos > 50:
        print("\n⚠️ VERDICT: Marginal edge. Consider tightening bucket boundaries.")
    else:
        print("\n❌ VERDICT: No reliable edge on unseen data. Pattern matching may be overfit.")
    
    if avg_decay > 10:
        print("⚠️ HIGH DECAY: In-sample significantly overstates performance. Review bucket cutoffs.")


if __name__ == "__main__":
    results = run_walk_forward()
    print_report(results)
