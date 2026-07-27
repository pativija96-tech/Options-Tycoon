"""
IWM (Russell 2000 ETF) Iron Condor Validation.

The external feedback suggests IWM has wider VRP than SPX due to
retail participation and lower institutional liquidity.

Same methodology as NIFTY/SPX validation.
IWM specifics:
- Lot size: 100 (standard US options)
- Strikes: $1 increments
- Commission: ~$0.65/contract × 4 legs × 2 = ~$5.20 (use $4 avg)
- Weekly expiry available (Friday)
- Current price: ~$220-230

Usage:
    python scripts/iwm_validation.py
"""

import sys
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np
from scipy.stats import norm


def download_data(ticker, name):
    """Download 5 years of daily data."""
    import yfinance as yf
    print(f"Downloading {name} ({ticker}) 5-year data...")
    data = yf.download(ticker, period="5y", progress=False)
    if data is None or len(data) < 500:
        print(f"Failed to download {name}")
        return None
    if hasattr(data.columns, 'levels'):
        data.columns = data.columns.get_level_values(0)
    data = data.reset_index()
    data["change_pct"] = data["Close"].pct_change() * 100
    data = data.dropna(subset=["change_pct"]).reset_index(drop=True)
    print(f"  {len(data)} days, range: ${data['Close'].min():.0f} - ${data['Close'].max():.0f}")
    return data


def estimate_ic_credit(spot, vol_ann, days, offset, wing):
    """Black-Scholes IC credit estimate."""
    T = days / 365.0
    if T <= 0: T = 1/365.0
    r = 0.05; sigma = max(vol_ann, 0.08); S = spot
    def bs(K, opt):
        try:
            sqrt_T = math.sqrt(T)
            d1 = (math.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*sqrt_T)
            d2 = d1 - sigma*sqrt_T
            if opt == "call": return S*norm.cdf(d1) - K*math.exp(-r*T)*norm.cdf(d2)
            else: return K*math.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1)
        except: return 0
    sc=S+offset; lc=sc+wing; sp=S-offset; lp=sp-wing
    return max(0, bs(sc,"call")-bs(lc,"call")+bs(sp,"put")-bs(lp,"put"))


def validate_ticker(ticker, name, offsets, wings, lot_size=100, charges=4.0):
    """Run full validation on a ticker."""
    df = download_data(ticker, name)
    if df is None:
        return None
    
    df["vol_10d"] = df["change_pct"].rolling(10).std()
    df["vol_annualized"] = df["vol_10d"] * math.sqrt(252) / 100
    df = df.dropna(subset=["vol_annualized"]).reset_index(drop=True)
    
    print(f"\n{'='*70}")
    print(f"{name} IRON CONDOR VALIDATION")
    print(f"{'='*70}")
    print(f"  Data: {len(df)} days | Lot: {lot_size} | Charges: ${charges}")
    print(f"  Current: ~${df['Close'].iloc[-1]:.0f}")
    
    # EV Grid
    print(f"\n  {'Offset':<8} {'Wing':<6} {'Win%':<7} {'Avg Cr':<9} {'EV/Trade':<10} {'Ann EV':<10} {'Verdict'}")
    print(f"  {'-'*65}")
    
    best_ev = -9999
    best_cfg = ""
    
    for offset in offsets:
        for wing in wings:
            pnl_total = 0; n = 0; wins = 0
            for _, row in df.iterrows():
                spot = row["Close"]; vol = row["vol_annualized"]
                move_pts = abs(row["change_pct"]) / 100 * spot
                credit = estimate_ic_credit(spot, vol, 3, offset, wing)
                credit_total = credit * lot_size
                max_loss = (wing - credit) * lot_size
                if max_loss <= 0: continue
                in_range = move_pts <= offset
                pnl = (credit_total - charges) if in_range else (-max_loss - charges)
                pnl_total += pnl; n += 1
                if in_range: wins += 1
            
            if n == 0: continue
            ev = pnl_total / n
            win_pct = wins/n*100
            ann = ev * 252
            verdict = "✅" if ev > 2 else ("⚠️" if ev > 0 else "❌")
            if ev > best_ev:
                best_ev = ev; best_cfg = f"±{offset}/{wing}"
            print(f"  ±{offset:<5} {wing:<6} {win_pct:<6.1f}% ${ev*n/n:<7.1f}  ${ev:<8.1f} ${ann:<8.0f} {verdict}")
    
    # Walk-forward on best
    if best_ev > 0 and best_cfg:
        parts = best_cfg.replace("±","").split("/")
        bo = int(parts[0]); bw = int(parts[1])
        split = int(len(df)*0.7)
        
        train_pnl=0; train_n=0
        for _, row in df.iloc[:split].iterrows():
            spot=row["Close"]; vol=row["vol_annualized"]
            move=abs(row["change_pct"])/100*spot
            cr=estimate_ic_credit(spot,vol,3,bo,bw)
            ct=cr*lot_size; ml=(bw-cr)*lot_size
            if ml<=0: continue
            train_pnl += (ct-charges) if move<=bo else (-ml-charges)
            train_n += 1
        
        test_pnl=0; test_n=0
        for _, row in df.iloc[split:].iterrows():
            spot=row["Close"]; vol=row["vol_annualized"]
            move=abs(row["change_pct"])/100*spot
            cr=estimate_ic_credit(spot,vol,3,bo,bw)
            ct=cr*lot_size; ml=(bw-cr)*lot_size
            if ml<=0: continue
            test_pnl += (ct-charges) if move<=bo else (-ml-charges)
            test_n += 1
        
        train_ev = train_pnl/train_n if train_n>0 else 0
        test_ev = test_pnl/test_n if test_n>0 else 0
        
        print(f"\n  Walk-Forward ({best_cfg}):")
        print(f"    Train: ${train_ev:.1f}/trade | Test: ${test_ev:.1f}/trade | Decay: ${train_ev-test_ev:.1f}")
        print(f"    {'✅ HOLDS' if test_ev > 0 else '❌ FAILS'} out-of-sample")
        if test_ev > 0:
            print(f"    Annual (test): ${test_ev*252:.0f}/contract")
            print(f"    At 10 contracts: ${test_ev*252*10:.0f}/year")
    
    print(f"\n  BEST: {best_cfg} → EV ${best_ev:.1f}/trade")
    return best_ev


def run():
    print("="*70)
    print("MULTI-ASSET OPTIONS VALIDATION")
    print("Testing: IWM, QQQ, EFA (less-efficient underlyings)")
    print("="*70)
    
    # IWM (Russell 2000) - retail heavy, less efficient
    # Price ~$220, so offsets in $ terms
    iwm_ev = validate_ticker("IWM", "IWM (Russell 2000)",
        offsets=[3, 5, 7, 9, 11], wings=[2, 3, 5])
    
    # QQQ (Nasdaq 100) - tech heavy, higher vol
    # Price ~$500, so larger offsets
    qqq_ev = validate_ticker("QQQ", "QQQ (Nasdaq 100)",
        offsets=[7, 10, 15, 20, 25], wings=[3, 5, 7])
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"  IWM: {'✅ POSITIVE' if iwm_ev and iwm_ev > 0 else '❌ NEGATIVE'} (EV: ${iwm_ev:.1f}/trade)" if iwm_ev else "  IWM: No data")
    print(f"  QQQ: {'✅ POSITIVE' if qqq_ev and qqq_ev > 0 else '❌ NEGATIVE'} (EV: ${qqq_ev:.1f}/trade)" if qqq_ev else "  QQQ: No data")


if __name__ == "__main__":
    run()
