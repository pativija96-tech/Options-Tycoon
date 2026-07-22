"""
Realistic Iron Condor EV — Regime-specific premium + transaction costs.

Fixes the flat-premium assumption:
- Premium scales with volatility (higher vol = more credit collected)
- Transaction costs deducted per trade
- Monte Carlo on 30-trade sequences to check variance

Uses actual volatility data to estimate what premium WOULD have been
on each historical day (via Black-Scholes approximation).

Usage:
    python scripts/ev_realistic.py
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


def estimate_ic_credit(spot, vol_10d_annualized, days_to_expiry=3, offset_pts=150, wing_width=100):
    """
    Estimate Iron Condor net credit using Black-Scholes.
    
    Premium collected = short_call_premium + short_put_premium 
                       - long_call_premium - long_put_premium
    """
    T = days_to_expiry / 365.0
    if T <= 0:
        T = 1/365.0
    r = 0.065
    sigma = vol_10d_annualized
    
    if sigma <= 0:
        sigma = 0.12  # floor
    
    S = spot
    
    def bs_price(strike, option_type):
        K = strike
        try:
            sqrt_T = math.sqrt(T)
            d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
            d2 = d1 - sigma * sqrt_T
            if option_type == "call":
                return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
            else:
                return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        except:
            return 0
    
    short_call = S + offset_pts
    long_call = short_call + wing_width
    short_put = S - offset_pts
    long_put = short_put - wing_width
    
    credit = (bs_price(short_call, "call") - bs_price(long_call, "call") +
              bs_price(short_put, "put") - bs_price(long_put, "put"))
    
    return max(0, credit)


def run_realistic_ev():
    df = load_historical_data()
    df = enrich_with_conditions(df)
    
    # Calculate annualized volatility from 10-day rolling std
    df["vol_annualized"] = df["volatility_10d"] * math.sqrt(252) / 100
    df = df.dropna(subset=["vol_annualized"]).reset_index(drop=True)
    
    # Parameters
    lot_size = 65
    offset_pts = 150  # short strikes ±150 from ATM
    wing_width = 100
    days_to_expiry = 3
    
    # Transaction costs per trade (4-leg IC, entry + exit)
    brokerage = 20 * 4 * 2  # Rs.20 per order × 4 legs × 2 (entry+exit)
    gst = brokerage * 0.18
    # STT, exchange, stamp (approximate for IC)
    other_charges = 50  # conservative estimate for IC
    total_charges = brokerage + gst + other_charges  # ~240 per trade
    
    print("=" * 80)
    print("REALISTIC IRON CONDOR EV (Regime-Specific Premium + Costs)")
    print("=" * 80)
    print(f"\nParameters:")
    print(f"  Short strikes: ±{offset_pts} pts from ATM")
    print(f"  Wing width: {wing_width} pts")
    print(f"  Lot size: {lot_size}")
    print(f"  Days to expiry: {days_to_expiry}")
    print(f"  Transaction costs: Rs.{total_charges:.0f} per trade")
    print(f"  Data: {len(df)} trading days with volatility data")
    
    # Simulate each day
    results = []
    for _, row in df.iterrows():
        spot = row["Close"]
        vol = row["vol_annualized"]
        daily_move_pct = abs(row["change_pct"])
        daily_move_pts = daily_move_pct / 100 * spot
        regime = row["vol_regime"]
        
        # Estimate premium that would have been collected
        credit_per_share = estimate_ic_credit(spot, vol, days_to_expiry, offset_pts, wing_width)
        credit_total = credit_per_share * lot_size
        max_loss = (wing_width - credit_per_share) * lot_size
        
        # Did NIFTY stay in range? (within ±offset_pts)
        in_range = daily_move_pts <= offset_pts
        
        if in_range:
            pnl = credit_total - total_charges  # Win: keep premium minus costs
        else:
            pnl = -max_loss - total_charges  # Loss: max loss plus costs
        
        results.append({
            "date": row["Date"],
            "regime": regime,
            "vol": vol,
            "credit": credit_total,
            "max_loss": max_loss,
            "in_range": in_range,
            "pnl": pnl,
        })
    
    rdf = pd.DataFrame(results)
    
    # Overall stats
    print(f"\n{'='*80}")
    print("RESULTS BY REGIME")
    print(f"{'='*80}")
    print(f"\n{'Regime':<10} {'Trades':<8} {'Wins':<6} {'Win%':<8} {'Avg Credit':<12} {'Avg PnL':<12} {'Total PnL':<12} {'EV/Trade'}")
    print("-" * 85)
    
    for regime in ["low", "normal", "high"]:
        subset = rdf[rdf["regime"] == regime]
        if len(subset) == 0:
            continue
        wins = subset["in_range"].sum()
        win_pct = wins / len(subset) * 100
        avg_credit = subset["credit"].mean()
        avg_pnl = subset["pnl"].mean()
        total_pnl = subset["pnl"].sum()
        print(f"{regime:<10} {len(subset):<8} {wins:<6} {win_pct:<7.1f}% Rs.{avg_credit:<8.0f}  Rs.{avg_pnl:<9.0f} Rs.{total_pnl:<9.0f} Rs.{avg_pnl:.0f}")
    
    # All combined
    total_wins = rdf["in_range"].sum()
    total_win_pct = total_wins / len(rdf) * 100
    avg_pnl_all = rdf["pnl"].mean()
    total_pnl_all = rdf["pnl"].sum()
    avg_credit_all = rdf["credit"].mean()
    
    print(f"{'ALL':<10} {len(rdf):<8} {total_wins:<6} {total_win_pct:<7.1f}% Rs.{avg_credit_all:<8.0f}  Rs.{avg_pnl_all:<9.0f} Rs.{total_pnl_all:<9.0f} Rs.{avg_pnl_all:.0f}")

    # Strategy: only trade in low-vol regime
    low_vol = rdf[rdf["regime"] == "low"]
    if len(low_vol) > 0:
        print(f"\n{'='*80}")
        print("STRATEGY: Only trade when VIX regime = LOW")
        print(f"{'='*80}")
        print(f"  Trades taken: {len(low_vol)} out of {len(rdf)} total days ({len(low_vol)/len(rdf)*100:.0f}%)")
        print(f"  Win rate: {low_vol['in_range'].sum()/len(low_vol)*100:.1f}%")
        print(f"  Avg P&L per trade: Rs.{low_vol['pnl'].mean():.0f}")
        print(f"  Total P&L: Rs.{low_vol['pnl'].sum():.0f}")
        print(f"  Avg credit collected: Rs.{low_vol['credit'].mean():.0f}")
        print(f"  Max consecutive losses: ", end="")
        # Compute max consecutive losses
        streak = 0
        max_streak = 0
        for _, r in low_vol.iterrows():
            if not r["in_range"]:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        print(f"{max_streak}")
    
    # Monte Carlo: what's the distribution of 30-trade outcomes?
    print(f"\n{'='*80}")
    print("MONTE CARLO: Distribution of 30-trade sequences (10,000 simulations)")
    print(f"{'='*80}")
    
    # Use low-vol regime PnL distribution
    trade_pool = low_vol["pnl"].values if len(low_vol) > 50 else rdf["pnl"].values
    pool_label = "low-vol only" if len(low_vol) > 50 else "all regimes"
    
    np.random.seed(42)
    n_sims = 10000
    n_trades = 30
    
    sim_totals = []
    for _ in range(n_sims):
        sample = np.random.choice(trade_pool, size=n_trades, replace=True)
        sim_totals.append(sample.sum())
    
    sim_totals = np.array(sim_totals)
    
    print(f"\n  Pool: {pool_label} ({len(trade_pool)} historical trades)")
    print(f"  Simulations: {n_sims}")
    print(f"  Trades per sim: {n_trades}")
    print(f"\n  Results:")
    print(f"    Mean 30-trade P&L:    Rs.{sim_totals.mean():.0f}")
    print(f"    Median:               Rs.{np.median(sim_totals):.0f}")
    print(f"    5th percentile:       Rs.{np.percentile(sim_totals, 5):.0f}")
    print(f"    25th percentile:      Rs.{np.percentile(sim_totals, 25):.0f}")
    print(f"    75th percentile:      Rs.{np.percentile(sim_totals, 75):.0f}")
    print(f"    95th percentile:      Rs.{np.percentile(sim_totals, 95):.0f}")
    print(f"    % profitable (>0):    {(sim_totals > 0).sum()/n_sims*100:.1f}%")
    print(f"    % losing >Rs.5000:    {(sim_totals < -5000).sum()/n_sims*100:.1f}%")
    print(f"    Worst case:           Rs.{sim_totals.min():.0f}")
    print(f"    Best case:            Rs.{sim_totals.max():.0f}")
    
    # Is 30 trades enough?
    print(f"\n  Is 30 trades enough to validate?")
    ci_width = np.percentile(sim_totals, 95) - np.percentile(sim_totals, 5)
    if (sim_totals > 0).sum()/n_sims > 0.80:
        print(f"    ✅ 80%+ of 30-trade runs are profitable — 30 trades is sufficient")
    elif (sim_totals > 0).sum()/n_sims > 0.65:
        print(f"    ⚠️ Only {(sim_totals > 0).sum()/n_sims*100:.0f}% profitable — 30 trades is marginal, consider 50+")
    else:
        print(f"    ❌ Only {(sim_totals > 0).sum()/n_sims*100:.0f}% profitable — 30 trades not sufficient, high variance")
    
    print(f"\n{'='*80}")
    print("FINAL ANSWER")
    print(f"{'='*80}")
    
    low_vol_ev = low_vol["pnl"].mean() if len(low_vol) > 0 else 0
    all_ev = rdf["pnl"].mean()
    
    print(f"""
After regime-specific premium + Rs.{total_charges:.0f} transaction costs per trade:

  Unconditional EV (all days):  Rs.{all_ev:.0f}/trade
  Low-vol only EV:              Rs.{low_vol_ev:.0f}/trade
  
  Monte Carlo 30-trade median:  Rs.{np.median(sim_totals):.0f}
  Probability of profit (30 trades): {(sim_totals > 0).sum()/n_sims*100:.1f}%

If EV is still positive → proceed with VIX-gated Iron Condor strategy.
If EV is near-zero or negative → the VRP is real but costs eat it.
""")


if __name__ == "__main__":
    run_realistic_ev()
