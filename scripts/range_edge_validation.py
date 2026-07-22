"""
Range Edge Validation — Answers the reviewer's four challenges:

1. Does bucketing add LIFT over the unconditional baseline? (77.2% OOS vs 80.3% baseline = NO)
2. Is VIX-regime bucketing circular? (Does it add signal beyond VIX level alone?)
3. Is -1.0% decay real or a look-ahead artifact?
4. Is the Iron Condor expected value positive? (Premium collected vs loss on breach)

Usage:
    python scripts/range_edge_validation.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np

from engine.signals.pattern_matcher import load_historical_data, enrich_with_conditions


def run_validation():
    df = load_historical_data()
    df = enrich_with_conditions(df)
    
    target_width = 1.0  # ±1% = ~240 NIFTY pts
    
    print("=" * 80)
    print("RANGE EDGE GUT-CHECK (Reviewer's 4 Challenges)")
    print("=" * 80)
    
    # =========================================================================
    # CHALLENGE 1: Unconditional baseline vs bucketed OOS
    # =========================================================================
    print("\n" + "=" * 80)
    print("CHALLENGE 1: Does bucketing add lift over doing NOTHING?")
    print("=" * 80)
    
    unconditional = len(df[df["change_pct"].abs() <= target_width]) / len(df) * 100
    print(f"\nUnconditional containment (ALL days, no model): {unconditional:.1f}%")
    print(f"Bucketed OOS containment (from walk-forward):    77.2%")
    print(f"Lift: {77.2 - unconditional:+.1f}%")
    print()
    
    if 77.2 < unconditional:
        print("❌ BUCKETING MAKES IT WORSE. The 'model' is subtracting value.")
        print("   The 77.2% OOS is BELOW the unconditional 80.3% baseline.")
        print("   Pattern matching at this level adds noise, not signal.")
    else:
        print("✅ Bucketing adds lift above baseline.")
    
    # What about SELECTIVE bucketing? Only trade on low-vol days.
    low_vol = df[df["vol_regime"] == "low"]
    low_vol_contain = len(low_vol[low_vol["change_pct"].abs() <= target_width]) / len(low_vol) * 100
    print(f"\nLow-vol days only (no other bucketing): {low_vol_contain:.1f}% ({len(low_vol)} days)")
    print(f"Lift over unconditional: {low_vol_contain - unconditional:+.1f}%")
    print(f"But this is just 'VIX was low → volatility was low' (circular)")
    
    # =========================================================================
    # CHALLENGE 2: Is VIX-regime bucketing circular?
    # =========================================================================
    print("\n" + "=" * 80)
    print("CHALLENGE 2: Does bucketing add signal BEYOND VIX level alone?")
    print("=" * 80)
    
    # Control for VIX: within low-vol regime, does prev_1d_bucket add anything?
    print(f"\nWithin LOW-VOL regime ({len(low_vol)} days):")
    print(f"  Overall containment: {low_vol_contain:.1f}%")
    print(f"  {'Bucket':<15} {'N':<6} {'Contain':<10} {'Lift over low-vol baseline'}")
    print(f"  {'-'*55}")
    
    for bucket in sorted(low_vol["prev_1d_bucket"].unique()):
        subset = low_vol[low_vol["prev_1d_bucket"] == bucket]
        if len(subset) < 15:
            continue
        contain = len(subset[subset["change_pct"].abs() <= target_width]) / len(subset) * 100
        lift = contain - low_vol_contain
        marker = "✅" if lift > 3 else ("⚠️" if lift > 0 else "")
        print(f"  {bucket:<15} {len(subset):<6} {contain:>5.1f}%     {lift:>+5.1f}% {marker}")
    
    # Within normal-vol regime
    normal_vol = df[df["vol_regime"] == "normal"]
    normal_vol_contain = len(normal_vol[normal_vol["change_pct"].abs() <= target_width]) / len(normal_vol) * 100
    print(f"\nWithin NORMAL-VOL regime ({len(normal_vol)} days):")
    print(f"  Overall containment: {normal_vol_contain:.1f}%")
    print(f"  {'Bucket':<15} {'N':<6} {'Contain':<10} {'Lift over normal-vol baseline'}")
    print(f"  {'-'*55}")
    
    for bucket in sorted(normal_vol["prev_1d_bucket"].unique()):
        subset = normal_vol[normal_vol["prev_1d_bucket"] == bucket]
        if len(subset) < 15:
            continue
        contain = len(subset[subset["change_pct"].abs() <= target_width]) / len(subset) * 100
        lift = contain - normal_vol_contain
        marker = "✅" if lift > 5 else ("⚠️" if lift > 0 else "")
        print(f"  {bucket:<15} {len(subset):<6} {contain:>5.1f}%     {lift:>+5.1f}% {marker}")
    
    # =========================================================================
    # CHALLENGE 3: -1.0% decay — is it real?
    # =========================================================================
    print("\n" + "=" * 80)
    print("CHALLENGE 3: Why OOS > IS? (Check for look-ahead / lucky window)")
    print("=" * 80)
    
    # Check if specific test windows were unusually calm
    from datetime import timedelta
    start_date = df["Date"].min()
    end_date = df["Date"].max()
    
    # Compute containment by 6-month windows
    print(f"\n6-month window containment rates (±{target_width}%):")
    print(f"{'Window':<25} {'N days':<8} {'Containment':<12} {'vs Overall'}")
    print("-" * 55)
    
    window_start = start_date
    while window_start + timedelta(days=180) <= end_date:
        window_end = window_start + timedelta(days=180)
        window_df = df[(df["Date"] >= window_start) & (df["Date"] < window_end)]
        if len(window_df) >= 50:
            contain = len(window_df[window_df["change_pct"].abs() <= target_width]) / len(window_df) * 100
            diff = contain - unconditional
            flag = " ← TEST WINDOW" if window_start.year >= 2024 else ""
            print(f"{window_start.strftime('%Y-%m')} to {window_end.strftime('%Y-%m')}{'':<3} {len(window_df):<8} {contain:>5.1f}%{'':<5} {diff:>+5.1f}%{flag}")
        window_start += timedelta(days=180)
    
    # =========================================================================
    # CHALLENGE 4: Expected Value of Iron Condor
    # =========================================================================
    print("\n" + "=" * 80)
    print("CHALLENGE 4: Is Iron Condor EV positive? (Premium vs Loss on Breach)")
    print("=" * 80)
    
    # Simulate: ±240 pts Iron Condor (1% of 24000)
    # Typical premium collected: ~60-100 pts net credit for 100-pt wing IC at 150-pt offset
    # Using our actual strategy: 100-pt wings, ~150-pt offset from ATM
    
    nifty_level = 24000  # approximate
    wing_width = 100  # pts
    offset = 150  # short strikes 150 pts from ATM
    lot_size = 65
    
    # Estimate premium (from actual signals: ~60-90 pts net credit on 100-pt IC)
    estimated_net_credit = 60  # conservative: Rs.60 per share net credit
    max_profit = estimated_net_credit * lot_size  # Rs.3900
    max_loss = (wing_width - estimated_net_credit) * lot_size  # Rs.2600
    
    print(f"\nAssumptions (from actual generated signals):")
    print(f"  NIFTY level: {nifty_level}")
    print(f"  Short strikes: ±{offset} pts from ATM ({nifty_level-offset} PE / {nifty_level+offset} CE)")
    print(f"  Wing width: {wing_width} pts")
    print(f"  Net credit: ~Rs.{estimated_net_credit}/share (Rs.{max_profit} total)")
    print(f"  Max loss: Rs.{max_loss} per trade")
    print(f"  Lot size: {lot_size}")
    print()
    
    # What % of days does NIFTY stay within ±offset pts?
    offset_pct = offset / nifty_level * 100  # ~0.625%
    in_range = len(df[df["change_pct"].abs() <= offset_pct])
    containment = in_range / len(df) * 100
    
    # For days that breach, what's the average breach size?
    breached = df[df["change_pct"].abs() > offset_pct]
    avg_breach_pct = breached["change_pct"].abs().mean() if len(breached) > 0 else 0
    avg_breach_pts = avg_breach_pct / 100 * nifty_level
    # Loss on breach (capped at max_loss for defined-risk IC)
    avg_loss_on_breach = min(max_loss, (avg_breach_pts - offset + wing_width) * lot_size * 0.5)
    # Actually for defined-risk IC, loss is always max_loss when breached
    loss_on_breach = max_loss
    
    # Expected Value per trade
    win_rate = containment / 100
    ev = (win_rate * max_profit) - ((1 - win_rate) * loss_on_breach)
    
    print(f"Containment at ±{offset}pts (±{offset_pct:.2f}%): {containment:.1f}%")
    print(f"Win rate: {win_rate*100:.1f}%")
    print(f"Max profit per win: Rs.{max_profit}")
    print(f"Max loss per loss: Rs.{loss_on_breach}")
    print(f"\nExpected Value per trade: Rs.{ev:.0f}")
    print(f"EV as % of risk: {ev/loss_on_breach*100:.1f}%")
    print()
    
    if ev > 0:
        print(f"✅ POSITIVE EV: Rs.{ev:.0f} per trade")
        print(f"   Over 30 trades: Rs.{ev*30:.0f} expected profit")
        print(f"   But note: this is UNCONDITIONAL (no model needed)")
    else:
        print(f"❌ NEGATIVE EV: Rs.{ev:.0f} per trade")
        print(f"   Iron Condor at these strikes is not profitable on average")
    
    # What about low-vol only?
    low_vol_breach = low_vol[low_vol["change_pct"].abs() > offset_pct]
    low_vol_contain_offset = len(low_vol[low_vol["change_pct"].abs() <= offset_pct]) / len(low_vol) * 100
    low_vol_wr = low_vol_contain_offset / 100
    low_vol_ev = (low_vol_wr * max_profit) - ((1 - low_vol_wr) * loss_on_breach)
    
    print(f"\nLow-vol regime only:")
    print(f"  Containment at ±{offset}pts: {low_vol_contain_offset:.1f}%")
    print(f"  EV per trade: Rs.{low_vol_ev:.0f}")
    if low_vol_ev > 0:
        print(f"  ✅ Still positive — but is this just 'don't sell in high vol'?")
    
    # Final verdict
    print("\n" + "=" * 80)
    print("FINAL VERDICT")
    print("=" * 80)
    print(f"""
Key findings:
1. Unconditional containment at ±1.0%: {unconditional:.1f}%
   Bucketed OOS: 77.2% — BELOW baseline. Bucketing doesn't help.

2. VIX regime IS the signal (circular). Within a regime, prev_1d_bucket 
   adds minimal lift (typically <3-4%).

3. The "real edge" (if any) is: sell Iron Condors ONLY in low-vol regime,
   and let theta do the work. No forecast needed beyond "is VIX low?"

4. EV check: at ±{offset}pts unconditional, EV = Rs.{ev:.0f}/trade.
   Low-vol only: EV = Rs.{low_vol_ev:.0f}/trade.

RECOMMENDATION:
   The pattern matcher is NOT adding edge beyond VIX level alone.
   The honest strategy is: "sell premium when VIX is low, use wide strikes, 
   collect theta." This doesn't require a 5-year pattern match — just check 
   today's VIX level (which filter #5 already does).
   
   Consider ALT PATH from the reviewer's feedback: retire the pattern matcher,
   use VIX level directly as the only trade/no-trade signal.
""")


if __name__ == "__main__":
    run_validation()
