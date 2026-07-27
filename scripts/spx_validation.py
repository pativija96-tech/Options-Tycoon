"""
SPX Iron Condor Validation — Same methodology as NIFTY, applied to S&P 500.

Tests: Does selling ±X point Iron Condors on SPX produce positive EV
after costs, with regime-specific premiums?

SPX specifics:
- Lot size: 100 (1 contract = 100 shares)
- Strikes: $1 increments (much more granular than NIFTY's 50pt)
- Expiry: Mon/Wed/Fri (0DTE available), weekly (Friday), monthly
- VIX: same index used for volatility
- Commission: ~$0.65/contract × 4 legs × 2 (entry+exit) = ~$5.20/trade
- No STT or exchange charges (US market)

Usage:
    python scripts/spx_validation.py
"""

import sys
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np
from scipy.stats import norm


def download_spx_data():
    """Download 5 years of SPX daily OHLC data from yfinance."""
    import yfinance as yf
    print("Downloading SPX 5-year data...")
    data = yf.download("^GSPC", period="5y", progress=False)
    if data is None or len(data) < 500:
        print("Failed to download sufficient SPX data")
        return None
    
    # Flatten multi-index columns if present
    if hasattr(data.columns, 'levels'):
        data.columns = data.columns.get_level_values(0)
    
    data = data.reset_index()
    data["change_pct"] = data["Close"].pct_change() * 100
    data = data.dropna(subset=["change_pct"]).reset_index(drop=True)
    print(f"Downloaded {len(data)} trading days of SPX data")
    return data


def estimate_ic_credit_spx(spot, vol_ann, days_to_expiry, offset_pts, wing_width):
    """Estimate SPX Iron Condor net credit using Black-Scholes."""
    T = days_to_expiry / 365.0
    if T <= 0: T = 1/365.0
    r = 0.05  # US risk-free rate
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
    
    credit = bs(sc, "call") - bs(lc, "call") + bs(sp, "put") - bs(lp, "put")
    return max(0, credit)


def run_spx_validation():
    """Run the full validation on SPX data."""
    df = download_spx_data()
    if df is None:
        return
    
    # Calculate rolling volatility (annualized)
    df["vol_10d"] = df["change_pct"].rolling(10).std()
    df["vol_annualized"] = df["vol_10d"] * math.sqrt(252) / 100
    df = df.dropna(subset=["vol_annualized"]).reset_index(drop=True)
    
    # SPX parameters
    lot_size = 100  # 1 SPX contract = 100 multiplier
    # Commission: $0.65/contract × 4 legs × 2 (entry + exit) = $5.20
    # But for defined-risk spreads, many expire worthless (no exit needed)
    # Approximate: $4 per trade average
    charges_per_trade = 4.0  # USD
    
    # Test grid of offsets (in SPX points, not %)
    # SPX at ~5500, so percentages:
    # 1% = 55 pts, 2% = 110 pts, 3% = 165 pts, 4% = 220 pts
    offsets = [30, 50, 70, 90, 110]  # Points from ATM
    wings = [10, 20, 30]  # Wing width in points
    
    print("=" * 80)
    print("SPX IRON CONDOR VALIDATION (Same methodology as NIFTY)")
    print("=" * 80)
    print(f"Data: {len(df)} trading days")
    print(f"SPX range: {df['Close'].min():.0f} to {df['Close'].max():.0f}")
    print(f"Lot size: {lot_size} (multiplier)")
    print(f"Commission: ${charges_per_trade}/trade")
    print()
    
    # Baseline containment
    print("-" * 80)
    print("BASELINE: What % of days does SPX stay within ±X points?")
    print("-" * 80)
    
    for offset in offsets:
        # Convert points to % for each day (since SPX level changes)
        in_range = 0
        for _, row in df.iterrows():
            move_pts = abs(row["change_pct"]) / 100 * row["Close"]
            if move_pts <= offset:
                in_range += 1
        pct = in_range / len(df) * 100
        edge = "✅" if pct >= 70 else ("⚠️" if pct >= 60 else "❌")
        print(f"  ±{offset} pts: {pct:.1f}% containment {edge}")
    
    print()
    
    # Full grid with regime-specific premium + costs
    print("-" * 80)
    print("EV GRID (Regime-Specific Premium + Costs)")
    print("-" * 80)
    print(f"\n{'Offset':<8} {'Wing':<6} {'Win%':<7} {'Avg Credit':<12} {'EV/Trade':<10} {'Annual EV':<12} {'Verdict'}")
    print("-" * 75)
    
    best_ev = 0
    best_config = None
    
    for offset in offsets:
        for wing in wings:
            total_pnl = 0
            n = 0
            wins = 0
            credits = []
            
            for _, row in df.iterrows():
                spot = row["Close"]
                vol = row["vol_annualized"]
                move_pts = abs(row["change_pct"]) / 100 * spot
                
                credit = estimate_ic_credit_spx(spot, vol, 1, offset, wing)
                credit_total = credit * lot_size  # Per contract
                max_loss = (wing - credit) * lot_size
                
                if max_loss <= 0:
                    continue
                
                in_range = move_pts <= offset
                
                if in_range:
                    pnl = credit_total - charges_per_trade
                    wins += 1
                else:
                    pnl = -max_loss - charges_per_trade
                
                total_pnl += pnl
                credits.append(credit_total)
                n += 1
            
            if n == 0:
                continue
            
            win_pct = wins / n * 100
            avg_credit = np.mean(credits)
            ev = total_pnl / n
            annual_ev = ev * 252  # Daily trading
            
            if ev > best_ev:
                best_ev = ev
                best_config = f"±{offset}/{wing}"
            
            verdict = "✅" if ev > 5 else ("⚠️" if ev > 0 else "❌")
            print(f"±{offset:<5} {wing:<6} {win_pct:<6.1f}% ${avg_credit:<9.0f}  ${ev:<8.1f} ${annual_ev:<9.0f} {verdict}")
    
    # Walk-forward on best config
    print(f"\n{'='*80}")
    print(f"BEST CONFIG: {best_config} (EV: ${best_ev:.1f}/trade)")
    print(f"{'='*80}")
    
    if best_config:
        parts = best_config.replace("±", "").split("/")
        best_offset = int(parts[0])
        best_wing = int(parts[1])
        
        # Walk-forward split: 70% train, 30% test
        split_idx = int(len(df) * 0.7)
        train = df.iloc[:split_idx]
        test = df.iloc[split_idx:]
        
        train_pnl = 0
        train_n = 0
        for _, row in train.iterrows():
            spot = row["Close"]
            vol = row["vol_annualized"]
            move_pts = abs(row["change_pct"]) / 100 * spot
            credit = estimate_ic_credit_spx(spot, vol, 1, best_offset, best_wing)
            credit_total = credit * lot_size
            max_loss = (best_wing - credit) * lot_size
            if max_loss <= 0: continue
            pnl = (credit_total - charges_per_trade) if move_pts <= best_offset else (-max_loss - charges_per_trade)
            train_pnl += pnl
            train_n += 1
        
        test_pnl = 0
        test_n = 0
        for _, row in test.iterrows():
            spot = row["Close"]
            vol = row["vol_annualized"]
            move_pts = abs(row["change_pct"]) / 100 * spot
            credit = estimate_ic_credit_spx(spot, vol, 1, best_offset, best_wing)
            credit_total = credit * lot_size
            max_loss = (best_wing - credit) * lot_size
            if max_loss <= 0: continue
            pnl = (credit_total - charges_per_trade) if move_pts <= best_offset else (-max_loss - charges_per_trade)
            test_pnl += pnl
            test_n += 1
        
        train_ev = train_pnl / train_n if train_n > 0 else 0
        test_ev = test_pnl / test_n if test_n > 0 else 0
        
        print(f"\n  Walk-Forward:")
        print(f"    Train (first 70%): {train_n} trades, EV = ${train_ev:.1f}/trade")
        print(f"    Test (last 30%):   {test_n} trades, EV = ${test_ev:.1f}/trade")
        print(f"    Decay: ${train_ev - test_ev:.1f}")
        
        if test_ev > 0:
            print(f"\n  ✅ Strategy holds out-of-sample on SPX")
            print(f"     Annual expected: ${test_ev * 252:.0f}/contract/year")
            print(f"     At 10 contracts: ${test_ev * 252 * 10:.0f}/year")
        else:
            print(f"\n  ❌ Strategy does NOT hold on SPX")
    
    # Summary
    print(f"\n{'='*80}")
    print("COMPARISON: NIFTY vs SPX")
    print(f"{'='*80}")
    print(f"""
  NIFTY:  EV = Rs.192/trade (Rs.46K/year at 1 lot) — validated ✅
  SPX:    EV = ${best_ev:.1f}/trade (${best_ev*252:.0f}/year at 1 contract)
  
  SPX advantages:
    - Much lower commissions ($4 vs Rs.239 = $2.85)
    - 0% tax in Philippines (vs 30% NRI tax in India)
    - More liquid (tighter spreads)
    - Multiple expiries per week (Mon/Wed/Fri)
    
  SPX considerations:
    - Night trading (10:30 PM - 5 AM PH time)
    - Higher absolute capital needed ($5,000+ per contract)
    - Different volatility regime than NIFTY
""")


if __name__ == "__main__":
    run_spx_validation()
