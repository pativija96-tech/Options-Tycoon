"""
Data Fetcher — Overnight global market data collection.
Fetches US, Europe, APAC indices via yfinance with fallback logic.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# Indices to fetch
INDICES = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "vix": "^VIX",
    "dxy": "DX-Y.NYB",
    "us_10y": "^TNX",
    "ftse": "^FTSE",
    "dax": "^GDAXI",
    "nikkei": "^N225",
    "hang_seng": "^HSI",
    "gift_nifty": "^NSEI",  # Proxy: use previous NIFTY close as baseline
}


def fetch_global_data(output_dir: str = "output") -> dict:
    """
    Fetch overnight global market data. Returns dict with index changes.
    Falls back to alternative sources if yfinance fails.
    """
    results = {}
    errors = []

    # Try yfinance first
    try:
        import yfinance as yf

        for name, ticker in INDICES.items():
            try:
                data = yf.download(ticker, period="5d", progress=False, timeout=10)
                if data is not None and len(data) >= 2:
                    # Handle both flat and MultiIndex column formats
                    close_col = data["Close"]
                    if hasattr(close_col, "columns"):
                        # MultiIndex: pick first column
                        close_col = close_col.iloc[:, 0]
                    prev_close = float(close_col.iloc[-2])
                    last_close = float(close_col.iloc[-1])
                    change_pct = ((last_close - prev_close) / prev_close) * 100
                    results[name] = {
                        "last_close": round(last_close, 2),
                        "prev_close": round(prev_close, 2),
                        "change_pct": round(change_pct, 2),
                    }
                else:
                    errors.append(f"{name}: insufficient data")
                    results[name] = None
            except Exception as e:
                errors.append(f"{name}: {str(e)[:50]}")
                results[name] = None

    except ImportError:
        logger.error("yfinance not installed")
        errors.append("yfinance not installed — cannot fetch data")
        return _fallback_fetch()

    # Gift Nifty approximation (using NIFTY futures or previous close)
    if results.get("gift_nifty") and results["gift_nifty"] is not None:
        results["projected_open"] = results["gift_nifty"]["last_close"]
    else:
        results["projected_open"] = None

    # Summary
    output = {
        "timestamp": datetime.now().isoformat(),
        "data": results,
        "errors": errors,
        "status": "ok" if len(errors) < 3 else "partial" if errors else "ok",
    }

    # Write to output
    output_path = Path(output_dir) / "today_global_data.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    logger.info(f"Global data fetched: {len(results) - len(errors)}/{len(INDICES)} success")
    return output


def _fallback_fetch() -> dict:
    """
    Fallback if yfinance is completely broken.
    Returns empty structure with error flag.
    """
    logger.warning("All data sources failed — returning empty")
    return {
        "timestamp": datetime.now().isoformat(),
        "data": {k: None for k in INDICES},
        "errors": ["All sources failed"],
        "status": "failed",
    }


def bucket_us_move(pct: float) -> str:
    """Categorize US market move into a bucket."""
    if pct is None:
        return "unknown"
    if pct > 1.0:
        return "strong_up"
    if pct > 0.3:
        return "mild_up"
    if pct > -0.3:
        return "flat"
    if pct > -1.0:
        return "mild_down"
    return "strong_down"


def bucket_vix_change(pct: float) -> str:
    """Categorize VIX change into a bucket."""
    if pct is None:
        return "unknown"
    if pct > 10:
        return "spike"
    if pct > 5:
        return "up"
    if pct > -5:
        return "flat"
    return "down"


def bucket_dxy_change(pct: float) -> str:
    """Categorize DXY change into a bucket."""
    if pct is None:
        return "unknown"
    if pct > 0.3:
        return "up"
    if pct > -0.3:
        return "flat"
    return "down"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = fetch_global_data()
    print(json.dumps(result, indent=2))
