"""
Stock Scanner — Scans watchlist stocks for high-conviction signals.
Checks: earnings proximity, historical patterns, and news catalysts.
Filters to top 2-3 signals per day maximum.
"""

import json
import logging
import sys
from datetime import datetime, timedelta, date
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from engine.greeks import black_scholes_greeks
from engine.signals.data_fetcher import bucket_us_move

logger = logging.getLogger(__name__)

CONFIG_PATH = ROOT / "config" / "watchlist.json"
HISTORICAL_DIR = ROOT / "data" / "historical"
EARNINGS_PATH = ROOT / "data" / "historical" / "earnings_calendar.json"


def load_watchlist() -> dict:
    """Load stock watchlist config."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"stocks": [], "max_daily_signals": 3, "min_stock_confidence": 60}


def download_stock_history(symbol: str, period: str = "5y") -> pd.DataFrame:
    """Download and cache stock historical data."""
    cache_path = HISTORICAL_DIR / f"{symbol.replace('.', '_')}_5yr.csv"

    # Use cache if fresh (less than 1 day old)
    if cache_path.exists():
        mod_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if (datetime.now() - mod_time).days < 1:
            df = pd.read_csv(cache_path)
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            return df.dropna(subset=["Date"])

    # Download fresh
    try:
        import yfinance as yf
        data = yf.download(symbol, period=period, progress=False, timeout=10)
        if data is not None and len(data) > 100:
            # Handle MultiIndex columns
            if hasattr(data.columns, 'levels'):
                data.columns = [c[0] if isinstance(c, tuple) else c for c in data.columns]
            data = data.reset_index()
            # Rename first column to Date if needed
            first_col = data.columns[0]
            if first_col != "Date":
                data = data.rename(columns={first_col: "Date"})
            data.to_csv(cache_path, index=False)
            logger.info(f"Downloaded {len(data)} days for {symbol}")
            return data
    except Exception as e:
        logger.warning(f"Failed to download {symbol}: {e}")

    # Return empty if all fails
    return pd.DataFrame()


def get_earnings_dates(symbol: str) -> list:
    """
    Get upcoming/recent earnings dates for a stock.
    In Phase 1: uses a static JSON calendar (manually maintained).
    In Phase 2: can scrape from Moneycontrol/NSE.
    """
    if not EARNINGS_PATH.exists():
        return []
    with open(EARNINGS_PATH) as f:
        calendar = json.load(f)
    return calendar.get(symbol, calendar.get(symbol.replace(".NS", ""), []))


def check_earnings_catalyst(symbol: str, stock_name: str) -> dict:
    """
    Check if stock has earnings within ±2 days.
    Returns catalyst info if found.
    """
    today = date.today()
    earnings_dates = get_earnings_dates(symbol)

    for d in earnings_dates:
        try:
            earn_date = date.fromisoformat(d)
            days_away = (earn_date - today).days
            if -2 <= days_away <= 1:
                timing = "today" if days_away == 0 else (
                    "tomorrow" if days_away == 1 else f"{abs(days_away)} days ago"
                )
                return {
                    "has_catalyst": True,
                    "type": "earnings",
                    "date": d,
                    "timing": timing,
                    "description": f"{stock_name} quarterly results {timing}",
                }
        except (ValueError, TypeError):
            continue

    return {"has_catalyst": False}


def scan_stock_pattern(symbol: str, stock_name: str, global_conditions: dict) -> dict:
    """
    Run pattern matching on a single stock.
    Returns signal with confidence, or skip.
    """
    df = download_stock_history(symbol)
    if df.empty or len(df) < 100:
        return {"action": "skip", "reason": f"Insufficient data for {stock_name}"}

    # Ensure Close column
    close_col = [c for c in df.columns if "close" in c.lower()]
    if close_col:
        df = df.rename(columns={close_col[0]: "Close"})
    if "Close" not in df.columns:
        return {"action": "skip", "reason": f"No Close data for {stock_name}"}

    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)
    df["change_pct"] = df["Close"].pct_change() * 100
    df["prev_1d_change"] = df["change_pct"].shift(1)
    df["prev_1d_bucket"] = df["prev_1d_change"].apply(bucket_us_move)

    # Match by global US condition (correlation with US)
    us_bucket = global_conditions.get("us_bucket", "flat")
    matches = df[df["prev_1d_bucket"] == us_bucket].dropna(subset=["change_pct"])

    if len(matches) < 10:
        return {"action": "skip", "reason": f"Too few matches ({len(matches)}) for {stock_name}"}

    # Direction analysis
    up_days = len(matches[matches["change_pct"] > 0.2])
    down_days = len(matches[matches["change_pct"] < -0.2])
    total = len(matches)

    if up_days > down_days:
        direction = "bullish"
        confidence = round((up_days / total) * 100)
    elif down_days > up_days:
        direction = "bearish"
        confidence = round((down_days / total) * 100)
    else:
        return {"action": "skip", "reason": f"No clear direction for {stock_name}"}

    avg_move = float(matches["change_pct"].mean())
    last_close = float(df["Close"].iloc[-1])

    return {
        "action": "signal",
        "symbol": symbol,
        "name": stock_name,
        "direction": direction,
        "confidence": confidence,
        "avg_move": round(avg_move, 2),
        "matching_days": total,
        "last_close": round(last_close, 2),
        "sample": f"{max(up_days, down_days)}/{total} similar days moved {'up' if direction == 'bullish' else 'down'}",
    }


def scan_all_stocks(global_data: dict) -> list:
    """
    Scan all watchlist stocks. Return top signals (max 2-3, filtered by confidence).
    """
    config = load_watchlist()
    stocks = config.get("stocks", [])
    max_signals = config.get("max_daily_signals", 3)
    min_confidence = config.get("min_stock_confidence", 60)

    # Extract global conditions
    data = global_data.get("data", {})
    sp500 = data.get("sp500")
    us_change = sp500["change_pct"] if sp500 else 0
    conditions = {"us_bucket": bucket_us_move(us_change), "us_change_pct": us_change}

    signals = []

    for stock in stocks:
        symbol = stock["symbol"]
        name = stock["name"]
        lot_size = stock.get("lot_size", 100)

        # Check for earnings catalyst
        catalyst = check_earnings_catalyst(symbol, name)

        # Run pattern scan
        result = scan_stock_pattern(symbol, name, conditions)

        if result["action"] == "skip":
            continue

        if result["confidence"] < min_confidence and not catalyst.get("has_catalyst"):
            continue  # Skip low confidence unless earnings event

        # Boost confidence if earnings catalyst present
        if catalyst.get("has_catalyst"):
            result["catalyst"] = catalyst
            result["confidence"] = min(result["confidence"] + 10, 95)
            result["reasoning_extra"] = catalyst["description"]

        result["lot_size"] = lot_size
        signals.append(result)

    # Sort by confidence, take top N
    signals.sort(key=lambda x: x["confidence"], reverse=True)
    return signals[:max_signals]


def format_stock_signal(signal: dict) -> str:
    """Format a stock signal as readable text."""
    name = signal.get("name", "?")
    direction = signal.get("direction", "?").upper()
    confidence = signal.get("confidence", 0)
    avg_move = signal.get("avg_move", 0)
    sample = signal.get("sample", "")
    catalyst = signal.get("catalyst", {})

    text = f"{name}: {direction} ({confidence}% confidence)\n"
    text += f"  Historical: {sample}\n"
    text += f"  Avg move: {avg_move:+.2f}%\n"
    if catalyst.get("has_catalyst"):
        text += f"  CATALYST: {catalyst['description']}\n"
    return text


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test with today's global data
    global_data_path = ROOT / "output" / "today_global_data.json"
    if global_data_path.exists():
        with open(global_data_path) as f:
            global_data = json.load(f)
        signals = scan_all_stocks(global_data)
        print(f"\n{'='*50}")
        print(f"Stock Scanner: {len(signals)} signals found")
        print(f"{'='*50}")
        for s in signals:
            print(format_stock_signal(s))
    else:
        print("Run signal_engine.py first to generate global data.")
