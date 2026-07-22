"""
EV Grid Search — Tests Iron Condor across multiple strike/wing configurations.

Before concluding "no edge exists," check whether the negative EV is:
- Configuration-specific (±150/100 doesn't work, but ±200/150 might)
- Fundamental (nothing works at retail NIFTY weekly cost structure)

Grid: offset × wing_width × regime
- Offsets: 100, 150, 200, 250, 300 pts from ATM
- Wings: 50, 100, 150 pts
- Regimes: low, normal, high, ALL

Usage:
    python scripts/ev_grid_search.py
"""

import sys
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np
from scipy.stats import norm

from engine.signals.pattern_matcher import load_historical_data, enrich_with_conditions


def estimate_ic_credit(spot, vol_ann, days_to_expiry, offset_pts, wing_width):
    """Estimate Iron Condor net credit using Black-Scholes."""
    T = days_to_expiry / 365.0
    if T <= 0:
        T = 1/365.0
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
        except:
            return 0
    
    sc = S + offset_pts
    lc = sc + wing_width
    sp = S - offset_pts
    lp = sp - wing_width
    
    credit = (bs(sc,"call") - bs(lc,"call") + bs(sp,"put") - bs(lp,"put"))
    return max(0, credit)


def run_grid():
    df = load_historical_data()
    df = enrich_with_conditions(df)
    df["vol_annualized"] = df["volatility_10d"] * math.sqrt(252) / 100
    df = df.dropna(subset=["vol_annualized"]).reset_index(drop=True)
    
    lot_size = 65
    days_to_expiry = 3
    charges_per_trade = 239  # From previous calculation
    
    offsets = [100, 150, 200, 250, 300]
    wings = [50, 100, 150]
    
    print("=" * 90)
    print("IRON CONDOR EV GRID SEARCH (Regime-Specific Premium + Costs)")
    print("=" * 90)
    print(f"Data: {len(df)} days | Lot: {lot_size} | Expiry: {days_to_expiry}d | Costs: Rs.{charges_per_trade}/trade")
    print(f"Grid: {len(offsets)} offsets × {len(wings)} wings = {len(offsets)*len(wings)} configurations")
    
    # Run grid for each regime
    for regime_filter in ["low", "normal", "high", "ALL"]:
        if regime_filter == "ALL":
            subset = df
        else:
            subset = df[df["vol_regime"] == regime_filter]
        
        if len(subset) < 50:
            continue
        
        print(f"\n{'='*90}")
        print(f"REGIME: {regime_filter.upper()} ({len(subset)} trading days)")
        print(f"{'='*90}")
        print(f"\n{'Offset':<8} {'Wing':<6} {'Win%':<7} {'Avg Credit':<12} {'Avg Loss':<10} {'EV/Trade':<10} {'30-Trade EV':<12} {'Verdict'}")
        print("-" * 85)
        
        for offset in offsets:
            for wing in wings:
                wins = 0
                total_pnl = 0
                credits = []
                losses = []
                
                for _, row in subset.iterrows():
                    spot = row["Close"]
                    vol = row["vol_annualized"]
                    move_pts = abs(row["change_pct"]) / 100 * spot
                    
                    credit = estimate_ic_credit(spot, vol, days_to_expiry, offset, wing)
                    credit_total = credit * lot_size
                    max_loss_total = (wing - credit) * lot_size
                    
                    if max_loss_total <= 0:
                        continue  # Skip if credit > wing (shouldn't happen)
                    
                    in_range = move_pts <= offset
                    
                    if in_range:
                        pnl = credit_total - charges_per_trade
                        wins += 1
                    else:
                        pnl = -max_loss_total - charges_per_trade
                        losses.append(-max_loss_total - charges_per_trade)
                    
                    total_pnl += pnl
                    credits.append(credit_total)
                
                n = len(credits)
                if n == 0:
                    continue
                
                win_pct = wins / n * 100
                avg_credit = np.mean(credits)
                avg_loss = np.mean(losses) if losses else 0
                ev = total_pnl / n
                ev_30 = ev * 30
                
                if ev > 100:
                    verdict = "✅ POSITIVE"
                elif ev > 0:
                    verdict = "⚠️ marginal"
                elif ev > -50:
                    verdict = "~zero"
                else:
                    verdict = "❌ negative"
                
                print(f"±{offset:<5} {wing:<6} {win_pct:<6.1f}% Rs.{avg_credit:<8.0f}  Rs.{avg_loss:<7.0f} Rs.{ev:<8.0f} Rs.{ev_30:<9.0f} {verdict}")
    
    # Summary: find the best configuration
    print(f"\n{'='*90}")
    print("BEST CONFIGURATIONS (if any are EV-positive)")
    print(f"{'='*90}")
    
    best_results = []
    for regime_filter in ["low", "normal", "high", "ALL"]:
        subset = df if regime_filter == "ALL" else df[df["vol_regime"] == regime_filter]
        if len(subset) < 50:
            continue
        
        for offset in offsets:
            for wing in wings:
                total_pnl = 0
                n = 0
                for _, row in subset.iterrows():
                    spot = row["Close"]
                    vol = row["vol_annualized"]
                    move_pts = abs(row["change_pct"]) / 100 * spot
                    credit = estimate_ic_credit(spot, vol, days_to_expiry, offset, wing)
                    credit_total = credit * lot_size
                    max_loss_total = (wing - credit) * lot_size
                    if max_loss_total <= 0:
                        continue
                    in_range = move_pts <= offset
                    pnl = (credit_total - charges_per_trade) if in_range else (-max_loss_total - charges_per_trade)
                    total_pnl += pnl
                    n += 1
                
                if n > 0:
                    ev = total_pnl / n
                    if ev > 0:
                        best_results.append({
                            "regime": regime_filter,
                            "offset": offset,
                            "wing": wing,
                            "ev": ev,
                            "n": n,
                        })
    
    if best_results:
        best_results.sort(key=lambda x: x["ev"], reverse=True)
        print(f"\n{'Regime':<8} {'Offset':<8} {'Wing':<6} {'EV/Trade':<10} {'N trades':<10}")
        print("-" * 45)
        for r in best_results[:10]:
            print(f"{r['regime']:<8} ±{r['offset']:<5} {r['wing']:<6} Rs.{r['ev']:<8.0f} {r['n']}")
    else:
        print("\n❌ NO CONFIGURATION IS EV-POSITIVE AFTER COSTS.")
        print("   Conclusion: At retail NIFTY weekly cost structure,")
        print("   Iron Condors do not have a structural edge regardless of")
        print("   strike selection, wing width, or volatility regime filtering.")
        print("\n   The signal engine's pattern-matching approach AND the")
        print("   'pure theta' alternative both fail validation.")
        print("\n   Recommended: Pause live-capital plans. The validation process")
        print("   (not the signal engine) is the product's real value at this stage.")


if __name__ == "__main__":
    run_grid()
