"""
Pattern Matcher — Historical NIFTY pattern matching engine.
Buckets historical days by preceding global conditions, finds analogous days.
"""

import json
import logging
from pathlib import Path

import pandas as pd
import numpy as np

from engine.signals.data_fetcher import bucket_us_move, bucket_vix_change, bucket_dxy_change

logger = logging.getLogger(__name__)

HISTORICAL_DATA_PATH = "data/historical/nifty_daily_5yr.csv"


def load_historical_data() -> pd.DataFrame:
    """Load and prepare 5-year NIFTY historical data."""
    # yfinance CSVs may have extra header rows — skip them
    df = pd.read_csv(HISTORICAL_DATA_PATH)
    
    # Find the row that contains actual dates (skip metadata rows)
    date_col = df.columns[0]  # First column is usually the date
    
    # Skip rows until we find date-like values
    # Check if first rows are metadata (like "Ticker", "Date" labels)
    skip_rows = 0
    for i, val in enumerate(df[date_col].head(5)):
        try:
            pd.to_datetime(val)
            skip_rows = i
            break
        except (ValueError, TypeError):
            continue
    
    if skip_rows > 0:
        df = pd.read_csv(HISTORICAL_DATA_PATH, skiprows=range(1, skip_rows + 1))
    
    # Rename first column to "Date" if it isn't already
    first_col = df.columns[0]
    if first_col != "Date":
        df = df.rename(columns={first_col: "Date"})
    
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    
    # Find Close column
    close_col = [c for c in df.columns if "close" in c.lower()]
    if close_col and close_col[0] != "Close":
        df = df.rename(columns={close_col[0]: "Close"})
    
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])
    
    # Calculate daily change
    df = df.sort_values("Date").reset_index(drop=True)
    df["change_pct"] = df["Close"].pct_change() * 100
    
    return df.dropna(subset=["change_pct"]).reset_index(drop=True)


def enrich_with_conditions(df: pd.DataFrame, global_data_history: dict = None) -> pd.DataFrame:
    """
    For simplicity in Phase 1: use NIFTY's own previous-day moves as a proxy 
    for pattern matching. In Phase 2, this will be enriched with actual global data.
    
    Current approach: Bucket by NIFTY's own momentum patterns.
    - prev_1d_change: yesterday's move
    - prev_3d_trend: 3-day cumulative direction
    - volatility_regime: recent 10-day std dev
    """
    df = df.copy()
    
    # Previous day's change (proxy for "what happened before today")
    df["prev_1d_change"] = df["change_pct"].shift(1)
    df["prev_1d_bucket"] = df["prev_1d_change"].apply(bucket_us_move)  # reuse same bucket logic
    
    # 3-day cumulative trend
    df["prev_3d_change"] = df["change_pct"].rolling(3).sum().shift(1)
    df["prev_3d_bucket"] = df["prev_3d_change"].apply(lambda x: bucket_us_move(x / 3) if pd.notna(x) else "unknown")
    
    # Volatility regime (10-day rolling std)
    df["volatility_10d"] = df["change_pct"].rolling(10).std()
    df["vol_regime"] = df["volatility_10d"].apply(
        lambda x: "high" if pd.notna(x) and x > 1.5 else ("low" if pd.notna(x) and x < 0.8 else "normal")
    )
    
    return df.dropna().reset_index(drop=True)


def match_pattern(today_conditions: dict, min_matches: int = 10) -> dict:
    """
    Find historical days with similar conditions to today.
    Returns direction bias, confidence, and average expected move.
    
    Args:
        today_conditions: {
            "us_bucket": "strong_down",
            "vix_bucket": "spike", 
            "dxy_bucket": "up"
        }
    """
    df = load_historical_data()
    df = enrich_with_conditions(df)
    
    # Map today's global conditions to NIFTY pattern buckets
    # Primary match: use US bucket as proxy for prev_1d_bucket (correlation)
    us_bucket = today_conditions.get("us_bucket", "flat")
    
    # Find matching historical days
    matches = df[df["prev_1d_bucket"] == us_bucket]
    
    # If we have VIX info, refine by volatility regime
    vix_bucket = today_conditions.get("vix_bucket", "flat")
    if vix_bucket in ("spike", "up"):
        vol_matches = matches[matches["vol_regime"] == "high"]
        if len(vol_matches) >= min_matches:
            matches = vol_matches
    
    total_matches = len(matches)
    
    if total_matches < min_matches:
        return {
            "direction": "skip",
            "confidence": 0,
            "avg_move": 0,
            "matching_days": total_matches,
            "min_required": min_matches,
            "reason": f"Insufficient historical matches ({total_matches} < {min_matches})"
        }
    
    # Calculate direction probabilities
    up_days = len(matches[matches["change_pct"] > 0.1])
    down_days = len(matches[matches["change_pct"] < -0.1])
    flat_days = total_matches - up_days - down_days
    
    avg_move = float(matches["change_pct"].mean())
    median_move = float(matches["change_pct"].median())
    
    # Determine direction
    if down_days > up_days:
        direction = "bearish"
        confidence = round((down_days / total_matches) * 100)
    elif up_days > down_days:
        direction = "bullish"
        confidence = round((up_days / total_matches) * 100)
    else:
        direction = "neutral"
        confidence = round((flat_days / total_matches) * 100)
    
    return {
        "direction": direction,
        "confidence": confidence,
        "avg_move": round(avg_move, 2),
        "median_move": round(median_move, 2),
        "matching_days": total_matches,
        "up_days": up_days,
        "down_days": down_days,
        "flat_days": flat_days,
        "sample_description": f"{max(up_days, down_days)}/{total_matches} similar days moved {'down' if direction == 'bearish' else 'up'}"
    }


def generate_pattern_signal(global_data: dict) -> dict:
    """
    Main entry point: takes today's global data, returns pattern match result.
    """
    data = global_data.get("data", {})
    
    # Extract conditions
    sp500 = data.get("sp500")
    vix = data.get("vix")
    dxy = data.get("dxy")
    
    us_change = sp500["change_pct"] if sp500 else 0
    vix_change = vix["change_pct"] if vix else 0
    dxy_change = dxy["change_pct"] if dxy else 0
    
    conditions = {
        "us_bucket": bucket_us_move(us_change),
        "vix_bucket": bucket_vix_change(vix_change),
        "dxy_bucket": bucket_dxy_change(dxy_change),
        "us_change_pct": us_change,
        "vix_change_pct": vix_change,
        "dxy_change_pct": dxy_change,
    }
    
    result = match_pattern(conditions)
    result["conditions"] = conditions
    
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test with today's actual data
    global_data_path = Path("output/today_global_data.json")
    if global_data_path.exists():
        with open(global_data_path) as f:
            global_data = json.load(f)
        result = generate_pattern_signal(global_data)
        print(json.dumps(result, indent=2))
    else:
        print("Run data_fetcher.py first to generate today_global_data.json")
