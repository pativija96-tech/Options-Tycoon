"""
High-Vol Edge Validation — Pressure-tests the "15/15 positive in high-vol" finding.

Reviewer's challenges:
1. How many DISTINCT episodes do those 72 days represent?
2. Walk-forward: does the edge hold on unseen data?
3. If walk-forward passes: block-bootstrap Monte Carlo (episode-level, not day-level)

Usage:
    python scripts/high_vol_validation.py
"""

import sys
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np
from datetime import timedelta
from scipy.stats import norm

from engine.signals.pattern_matcher import load_historical_data, enrich_with_conditions


def estimate_ic_credit(spot, vol_ann, days_to_expiry, offset_pts, wing_width):
    """Estimate IC net credit via Black-Scholes."""
    T = days_to_expiry / 365.0
    if T <= 0: T = 1/365.0
    r = 0.065
    sigma = max(vol_ann, 0.08)
    S = spot
    def bs(strike, opt_type):
        K = strike
        try:
            sqrt_T = math.sqrt(T)
            d1 = (math.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*sqrt_T)
            d2 = d1 - sigma*sqrt_T
            if opt_type == "call":
                return S*norm.cdf(d1) - K*math.exp(-r*T)*norm.cdf(d2)
            else:
                return K*math.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1)
        except: return 0
    sc = S + offset_pts; lc = sc + wing_width
    sp = S - offset_pts; lp = sp - wing_width
    return max(0, bs(sc,"call") - bs(lc,"call") + bs(sp,"put") - bs(lp,"put"))


def simulate_trade(row, offset, wing, lot_size, charges):
    """Simulate one IC trade, return PnL."""
    spot = row["Close"]
    vol = row["vol_annualized"]
    move_pts = abs(row["change_pct"]) / 100 * spot
    credit = estimate_ic_credit(spot, vol, 3, offset, wing)
    credit_total = credit * lot_size
    max_loss_total = (wing - credit) * lot_size
    if max_loss_total <= 0: return None
    in_range = move_pts <= offset
    return (credit_total - charges) if in_range else (-max_loss_total - charges)


def run_validation():
    df = load_historical_data()
    df = enrich_with_conditions(df)
    df["vol_annualized"] = df["volatility_10d"] * math.sqrt(252) / 100
    df = df.dropna(subset=["vol_annualized"]).reset_index(drop=True)
    
    high_vol = df[df["vol_regime"] == "high"].copy().reset_index(drop=True)
    
    lot_size = 65
    charges = 239
    # Best config from grid: ±250, 100pt wings
    offset = 250
    wing = 100
    
    print("=" * 80)
    print("HIGH-VOL EDGE VALIDATION")
    print(f"Config: ±{offset}pt offset, {wing}pt wings, high-vol regime only")
    print(f"High-vol days: {len(high_vol)}")
    print("=" * 80)
    
    # =========================================================================
    # CHALLENGE 1: Episode clustering
    # =========================================================================
    print("\n" + "=" * 80)
    print("CHALLENGE 1: How many DISTINCT volatility episodes?")
    print("=" * 80)
    
    # Cluster: days within 5 trading days of each other = same episode
    episodes = []
    current_episode = []
    
    for i, row in high_vol.iterrows():
        if not current_episode:
            current_episode = [row]
        else:
            last_date = current_episode[-1]["Date"]
            gap = (row["Date"] - last_date).days
            if gap <= 7:  # Within 1 week = same episode
                current_episode.append(row)
            else:
                episodes.append(current_episode)
                current_episode = [row]
    if current_episode:
        episodes.append(current_episode)
    
    print(f"\n  Total high-vol days: {len(high_vol)}")
    print(f"  Distinct episodes (gap > 7 calendar days): {len(episodes)}")
    print(f"  Effective sample size: n ≈ {len(episodes)} (not {len(high_vol)})")
    print(f"\n  Episode breakdown:")
    print(f"  {'#':<4} {'Start':<12} {'End':<12} {'Days':<6} {'Avg Vol':<10}")
    print(f"  {'-'*48}")
    
    episode_pnls = []
    for i, ep in enumerate(episodes):
        ep_df = pd.DataFrame(ep)
        start = ep_df["Date"].min().strftime("%Y-%m-%d")
        end = ep_df["Date"].max().strftime("%Y-%m-%d")
        avg_vol = ep_df["vol_annualized"].mean()
        
        # Simulate trades for this episode
        ep_pnl = 0
        for _, row in ep_df.iterrows():
            pnl = simulate_trade(row, offset, wing, lot_size, charges)
            if pnl is not None:
                ep_pnl += pnl
        
        episode_pnls.append(ep_pnl)
        pnl_marker = "✅" if ep_pnl > 0 else "❌"
        print(f"  {i+1:<4} {start:<12} {end:<12} {len(ep):<6} {avg_vol:.2f}      Rs.{ep_pnl:>7.0f} {pnl_marker}")
    
    winning_episodes = sum(1 for p in episode_pnls if p > 0)
    print(f"\n  Episodes profitable: {winning_episodes}/{len(episodes)} ({winning_episodes/len(episodes)*100:.0f}%)")
    print(f"  Total P&L across all episodes: Rs.{sum(episode_pnls):.0f}")
    print(f"  Average P&L per episode: Rs.{np.mean(episode_pnls):.0f}")

    # =========================================================================
    # CHALLENGE 2: Walk-forward (train on first episodes, test on last)
    # =========================================================================
    print("\n" + "=" * 80)
    print("CHALLENGE 2: Walk-forward (is edge present in LATER episodes?)")
    print("=" * 80)
    
    if len(episodes) < 4:
        print(f"\n  Only {len(episodes)} episodes — insufficient for train/test split.")
        print("  Cannot validate out-of-sample with so few episodes.")
    else:
        # Split: first 60% of episodes = train, last 40% = test
        split_idx = int(len(episodes) * 0.6)
        train_episodes = episodes[:split_idx]
        test_episodes = episodes[split_idx:]
        
        train_pnls = episode_pnls[:split_idx]
        test_pnls = episode_pnls[split_idx:]
        
        train_ev = np.mean(train_pnls)
        test_ev = np.mean(test_pnls)
        
        print(f"\n  Train episodes (first {split_idx}): avg P&L Rs.{train_ev:.0f}/episode")
        print(f"  Test episodes (last {len(episodes)-split_idx}):  avg P&L Rs.{test_ev:.0f}/episode")
        print(f"  Decay: {train_ev - test_ev:+.0f}")
        
        if test_ev > 0:
            print(f"\n  ✅ Edge survives out-of-sample at episode level")
        else:
            print(f"\n  ❌ Edge does NOT survive out-of-sample")
    
    # =========================================================================
    # CHALLENGE 2b: Walk-forward on "any regime, wide strikes" config
    # =========================================================================
    print("\n" + "=" * 80)
    print("CHALLENGE 2b: Walk-forward for 'any regime, ±250, 100-wing' config")
    print("=" * 80)
    
    # Use ALL data, split chronologically
    all_data = df.copy()
    split_date = all_data["Date"].quantile(0.7)  # First 70% train, last 30% test
    train_all = all_data[all_data["Date"] <= split_date]
    test_all = all_data[all_data["Date"] > split_date]
    
    train_pnl_sum = 0
    train_n = 0
    for _, row in train_all.iterrows():
        pnl = simulate_trade(row, 250, 100, lot_size, charges)
        if pnl is not None:
            train_pnl_sum += pnl
            train_n += 1
    
    test_pnl_sum = 0
    test_n = 0
    for _, row in test_all.iterrows():
        pnl = simulate_trade(row, 250, 100, lot_size, charges)
        if pnl is not None:
            test_pnl_sum += pnl
            test_n += 1
    
    train_ev_all = train_pnl_sum / train_n if train_n > 0 else 0
    test_ev_all = test_pnl_sum / test_n if test_n > 0 else 0
    
    print(f"\n  Config: ±250, 100-wing, ALL regimes")
    print(f"  Train (first 70%): {train_n} trades, EV = Rs.{train_ev_all:.0f}/trade")
    print(f"  Test (last 30%):   {test_n} trades, EV = Rs.{test_ev_all:.0f}/trade")
    print(f"  Decay: {train_ev_all - test_ev_all:+.0f}")
    
    if test_ev_all > 0:
        print(f"\n  ✅ 'Wide-strike any-regime' config holds out-of-sample")
    else:
        print(f"\n  ❌ 'Wide-strike any-regime' config fails out-of-sample")
    
    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print(f"""
  High-Vol Finding:
    - {len(high_vol)} days across {len(episodes)} distinct episodes
    - {winning_episodes}/{len(episodes)} episodes profitable ({winning_episodes/len(episodes)*100:.0f}%)
    - Effective n = {len(episodes)} (NOT {len(high_vol)})
    - Walk-forward (episode-level): {'PASS' if len(episodes) >= 4 and test_ev > 0 else 'INSUFFICIENT DATA or FAIL'}
    
  Wide-Strike Any-Regime Finding:
    - Walk-forward: {'PASS (Rs.'+str(int(test_ev_all))+'/trade)' if test_ev_all > 0 else 'FAIL'}
    
  Practical constraint:
    - High-vol only: ~{len(high_vol)//5} tradeable days/year → {30 * 5 // max(1,len(high_vol)//5):.0f}+ years for 30-trade gate
    - Any-regime wide: ~{len(df)//5} tradeable days/year → gate fills in ~{30 * 5 // max(1,len(df)//5):.0f} days
""")


if __name__ == "__main__":
    run_validation()
