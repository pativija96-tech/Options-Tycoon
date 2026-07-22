"""
Tail Risk Validation — The final gate before declaring the strategy validated.

Reviewer's challenges:
1. Does the 5-year dataset contain a real crisis/tail event?
2. Max drawdown + consecutive loss depth (block bootstrap Monte Carlo)
3. Modeled credit vs realistic bid-ask at ±250pt strikes
4. Return on margin (capital efficiency)

Usage:
    python scripts/tail_risk_validation.py
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
    T = days_to_expiry / 365.0
    if T <= 0: T = 1/365.0
    r = 0.065; sigma = max(vol_ann, 0.08); S = spot
    def bs(strike, opt_type):
        K = strike
        try:
            sqrt_T = math.sqrt(T)
            d1 = (math.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*sqrt_T)
            d2 = d1 - sigma*sqrt_T
            if opt_type == "call": return S*norm.cdf(d1) - K*math.exp(-r*T)*norm.cdf(d2)
            else: return K*math.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1)
        except: return 0
    sc = S + offset_pts; lc = sc + wing_width
    sp = S - offset_pts; lp = sp - wing_width
    return max(0, bs(sc,"call") - bs(lc,"call") + bs(sp,"put") - bs(lp,"put"))


def run_tail_validation():
    df = load_historical_data()
    df = enrich_with_conditions(df)
    df["vol_annualized"] = df["volatility_10d"] * math.sqrt(252) / 100
    df = df.dropna(subset=["vol_annualized"]).reset_index(drop=True)
    
    offset = 250; wing = 100; lot_size = 65; charges = 239
    
    print("=" * 80)
    print("TAIL RISK VALIDATION — Final Gate")
    print(f"Strategy: ±{offset}pt IC, {wing}pt wings, every day")
    print("=" * 80)
    
    # =========================================================================
    # CHALLENGE 1: Does the dataset contain a real tail event?
    # =========================================================================
    print("\n" + "=" * 80)
    print("CHALLENGE 1: Tail Events in Dataset")
    print("=" * 80)
    
    # Find largest single-day moves
    df_sorted = df.nlargest(20, "change_pct", keep="first")
    df_sorted_neg = df.nsmallest(20, "change_pct", keep="first")
    
    print(f"\n  Dataset range: {df['Date'].min().strftime('%Y-%m-%d')} to {df['Date'].max().strftime('%Y-%m-%d')}")
    print(f"  Total days: {len(df)}")
    
    print(f"\n  TOP 10 WORST DAYS (largest down moves):")
    print(f"  {'Date':<12} {'Move %':<8} {'Move Pts':<10} {'Would breach ±{offset}?'}")
    print(f"  {'-'*50}")
    for _, row in df_sorted_neg.head(10).iterrows():
        move_pts = abs(row["change_pct"]) / 100 * row["Close"]
        breach = "YES ❌" if move_pts > offset else "no"
        print(f"  {row['Date'].strftime('%Y-%m-%d'):<12} {row['change_pct']:>+6.2f}%  {move_pts:>6.0f} pts   {breach}")
    
    print(f"\n  TOP 10 BEST DAYS (largest up moves):")
    print(f"  {'Date':<12} {'Move %':<8} {'Move Pts':<10} {'Would breach ±{offset}?'}")
    print(f"  {'-'*50}")
    for _, row in df_sorted.head(10).iterrows():
        move_pts = abs(row["change_pct"]) / 100 * row["Close"]
        breach = "YES ❌" if move_pts > offset else "no"
        print(f"  {row['Date'].strftime('%Y-%m-%d'):<12} {row['change_pct']:>+6.2f}%  {move_pts:>6.0f} pts   {breach}")
    
    # Tail event assessment
    max_down = df["change_pct"].min()
    max_up = df["change_pct"].max()
    days_over_3pct = len(df[df["change_pct"].abs() > 3.0])
    days_over_2pct = len(df[df["change_pct"].abs() > 2.0])
    
    print(f"\n  TAIL STATISTICS:")
    print(f"    Worst single day: {max_down:+.2f}%")
    print(f"    Best single day:  {max_up:+.2f}%")
    print(f"    Days with >2% move: {days_over_2pct} ({days_over_2pct/len(df)*100:.1f}%)")
    print(f"    Days with >3% move: {days_over_3pct} ({days_over_3pct/len(df)*100:.1f}%)")
    
    if abs(max_down) < 4.0:
        print(f"\n  ⚠️ WARNING: Worst day is only {max_down:+.2f}%.")
        print(f"    NIFTY has historically had 5-10%+ gap days (demonetization 2016: -6.3%,")
        print(f"    COVID Mar 2020: -13%, Budget days: -3-5%).")
        print(f"    Your dataset may NOT contain a true crisis tail event.")
        print(f"    Strategy is UNVALIDATED for crisis conditions.")
    else:
        print(f"\n  ✅ Dataset contains genuine tail events (>{4}% moves).")

    # =========================================================================
    # CHALLENGE 2: Max Drawdown + Block Bootstrap Monte Carlo
    # =========================================================================
    print("\n" + "=" * 80)
    print("CHALLENGE 2: Drawdown + Block Bootstrap Monte Carlo")
    print("=" * 80)
    
    # Compute daily PnL sequence
    pnl_series = []
    for _, row in df.iterrows():
        spot = row["Close"]
        vol = row["vol_annualized"]
        move_pts = abs(row["change_pct"]) / 100 * spot
        credit = estimate_ic_credit(spot, vol, 3, offset, wing)
        credit_total = credit * lot_size
        max_loss_total = (wing - credit) * lot_size
        if max_loss_total <= 0: continue
        in_range = move_pts <= offset
        pnl = (credit_total - charges) if in_range else (-max_loss_total - charges)
        pnl_series.append(pnl)
    
    pnl_arr = np.array(pnl_series)
    
    # Max drawdown from cumulative equity
    cum_pnl = np.cumsum(pnl_arr)
    running_max = np.maximum.accumulate(cum_pnl)
    drawdowns = running_max - cum_pnl
    max_dd = drawdowns.max()
    max_dd_idx = drawdowns.argmax()
    
    # Max consecutive losses
    max_consec = 0
    current_consec = 0
    for p in pnl_arr:
        if p < 0:
            current_consec += 1
            max_consec = max(max_consec, current_consec)
        else:
            current_consec = 0
    
    print(f"\n  Backtest equity curve stats:")
    print(f"    Total trades: {len(pnl_arr)}")
    print(f"    Total P&L: Rs.{cum_pnl[-1]:.0f}")
    print(f"    Max drawdown: Rs.{max_dd:.0f} (at trade #{max_dd_idx})")
    print(f"    Max consecutive losses: {max_consec}")
    print(f"    Avg win: Rs.{pnl_arr[pnl_arr > 0].mean():.0f}")
    print(f"    Avg loss: Rs.{pnl_arr[pnl_arr < 0].mean():.0f}")
    
    # Block Bootstrap Monte Carlo (blocks of 5 consecutive days)
    print(f"\n  Block Bootstrap Monte Carlo (block size = 5 days, 10,000 sims, 30 trades):")
    
    block_size = 5
    n_sims = 10000
    n_trades = 30
    
    # Create blocks
    blocks = []
    for i in range(0, len(pnl_arr) - block_size + 1, block_size):
        blocks.append(pnl_arr[i:i+block_size])
    blocks = np.array(blocks)
    
    np.random.seed(42)
    sim_results = []
    sim_max_dds = []
    
    for _ in range(n_sims):
        # Sample enough blocks to get 30 trades
        n_blocks_needed = math.ceil(n_trades / block_size)
        sampled_blocks = blocks[np.random.choice(len(blocks), size=n_blocks_needed, replace=True)]
        sim_pnl = sampled_blocks.flatten()[:n_trades]
        sim_total = sim_pnl.sum()
        sim_results.append(sim_total)
        
        # Compute drawdown within this sim
        sim_cum = np.cumsum(sim_pnl)
        sim_running_max = np.maximum.accumulate(sim_cum)
        sim_dd = (sim_running_max - sim_cum).max()
        sim_max_dds.append(sim_dd)
    
    sim_results = np.array(sim_results)
    sim_max_dds = np.array(sim_max_dds)
    
    print(f"    Mean 30-trade P&L:     Rs.{sim_results.mean():.0f}")
    print(f"    Median:                Rs.{np.median(sim_results):.0f}")
    print(f"    5th percentile:        Rs.{np.percentile(sim_results, 5):.0f}")
    print(f"    95th percentile:       Rs.{np.percentile(sim_results, 95):.0f}")
    print(f"    % profitable:          {(sim_results > 0).sum()/n_sims*100:.1f}%")
    print(f"    Worst case (30 trades): Rs.{sim_results.min():.0f}")
    print(f"    Median max drawdown:   Rs.{np.median(sim_max_dds):.0f}")
    print(f"    95th pctile drawdown:  Rs.{np.percentile(sim_max_dds, 95):.0f}")
    
    # =========================================================================
    # CHALLENGE 3: Modeled credit vs realistic fills (slippage estimate)
    # =========================================================================
    print("\n" + "=" * 80)
    print("CHALLENGE 3: Credit Sensitivity to Slippage")
    print("=" * 80)
    
    avg_credit = pnl_arr[pnl_arr > 0].mean() + charges  # gross credit on winning trades
    
    print(f"\n  Avg gross credit (modeled): Rs.{avg_credit:.0f}/trade")
    print(f"  Strategy EV at modeled fills: Rs.{pnl_arr.mean():.0f}/trade")
    print(f"\n  Sensitivity to slippage (credit reduction per trade):")
    print(f"  {'Slippage':<12} {'Adj EV':<12} {'Still profitable?'}")
    print(f"  {'-'*45}")
    
    for slip in [0, 50, 100, 150, 200, 250, 300]:
        adj_ev = pnl_arr.mean() - slip
        verdict = "✅ YES" if adj_ev > 0 else "❌ NO"
        print(f"  Rs.{slip:<9} Rs.{adj_ev:<9.0f} {verdict}")
    
    breakeven_slip = pnl_arr.mean()
    print(f"\n  Breakeven slippage: Rs.{breakeven_slip:.0f}/trade")
    print(f"  (If real fills are Rs.{breakeven_slip:.0f}+ worse than model, EV goes to zero)")
    
    # =========================================================================
    # CHALLENGE 4: Return on Margin
    # =========================================================================
    print("\n" + "=" * 80)
    print("CHALLENGE 4: Return on Margin / Capital Efficiency")
    print("=" * 80)
    
    # NIFTY IC margin (approximate): max_loss + SPAN margin ≈ wing_width * lot_size * 1.5
    margin_required = wing * lot_size * 1.5  # ~Rs.9,750 per IC
    ev_per_trade = pnl_arr.mean()
    annual_trades = 244  # trading days per year
    annual_ev = ev_per_trade * annual_trades
    annual_return_on_margin = annual_ev / margin_required * 100
    
    print(f"\n  Estimated margin per IC: Rs.{margin_required:.0f}")
    print(f"  EV per trade: Rs.{ev_per_trade:.0f}")
    print(f"  Trades per year: ~{annual_trades}")
    print(f"  Annual expected profit: Rs.{annual_ev:.0f}")
    print(f"  Annual return on margin: {annual_return_on_margin:.1f}%")
    print(f"  Annual return on Rs.10L capital: {annual_ev/1000000*100:.1f}%")
    
    # =========================================================================
    # FINAL VERDICT
    # =========================================================================
    print("\n" + "=" * 80)
    print("FINAL VERDICT")
    print("=" * 80)
    
    has_tail = abs(max_down) >= 4.0
    profitable_mc = (sim_results > 0).sum()/n_sims > 0.6
    slip_margin = breakeven_slip > 100
    
    print(f"""
  1. Tail coverage:     {'✅ Has crisis-level moves' if has_tail else '⚠️ NO genuine crisis in dataset — unvalidated for tail events'}
  2. Monte Carlo:       {'✅' if profitable_mc else '❌'} {(sim_results > 0).sum()/n_sims*100:.0f}% of 30-trade blocks profitable
  3. Slippage margin:   {'✅' if slip_margin else '❌'} Breakeven at Rs.{breakeven_slip:.0f} slippage ({'enough buffer' if slip_margin else 'too thin'})
  4. Return on margin:  {annual_return_on_margin:.1f}% annually on deployed margin
  
  OVERALL: {'Strategy appears viable with known limitations' if profitable_mc and slip_margin else 'Strategy has material risks that need addressing'}
  
  CAVEATS (must go in BRD):
  - {'Dataset lacks >4% crash days — strategy untested for Volmageddon-type events' if not has_tail else 'Dataset includes tail events'}
  - Defined risk (100pt wings) caps per-trade loss but consecutive-loss clustering is real
  - Real fills may differ from Black-Scholes model by Rs.50-150 (still within breakeven margin if >{int(breakeven_slip)})
  - Max drawdown in backtest: Rs.{max_dd:.0f} — must be psychologically tolerable
""")


if __name__ == "__main__":
    run_tail_validation()
