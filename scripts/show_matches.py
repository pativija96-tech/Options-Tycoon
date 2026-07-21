"""Show the 13 matching historical days and their outcomes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from engine.signals.pattern_matcher import load_historical_data, enrich_with_conditions

df = load_historical_data()
df = enrich_with_conditions(df)

matches = df[df['prev_1d_bucket'] == 'strong_down'].copy()
matches = matches.sort_values('Date')

print(f"Total matching days (after US dropped >1%): {len(matches)}")
print()
print("=" * 60)
print(f"{'Date':<12} {'NIFTY Move':<12} {'Outcome':<10} {'Close':<10}")
print("=" * 60)

for _, row in matches.iterrows():
    date_str = row['Date'].strftime('%Y-%m-%d')
    change = row['change_pct']
    outcome = 'UP' if change > 0.1 else ('DOWN' if change < -0.1 else 'FLAT')
    symbol = '+' if change > 0 else ''
    print(f"{date_str:<12} {symbol}{change:.2f}%{'':<6} {outcome:<10} {row['Close']:.0f}")

print("=" * 60)
winners = len(matches[matches['change_pct'] > 0.1])
losers = len(matches[matches['change_pct'] < -0.1])
print(f"\nWinners: {winners} | Losers: {losers} | Win Rate: {winners}/{len(matches)} = {winners/len(matches)*100:.0f}%")
print(f"Avg move on UP days: +{matches[matches['change_pct']>0]['change_pct'].mean():.2f}%")
print(f"Avg move on DOWN days: {matches[matches['change_pct']<0]['change_pct'].mean():.2f}%")
