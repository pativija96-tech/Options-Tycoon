"""Mock data loader with in-memory caching for Options Tycoon."""

import json
import os
from pathlib import Path
from typing import Optional

# In-memory cache for loaded mock data
_mock_cache: dict[str, dict] = {}
_earnings_cache: Optional[list[dict]] = None

MOCK_DIR = Path(__file__).parent / "mock"


def load_mock_data(ticker: str) -> Optional[dict]:
    """Load mock market data for a ticker from JSON file.

    Loads from data/mock/{TICKER}.json and caches in memory.
    Returns None if the ticker file does not exist.
    """
    ticker_upper = ticker.upper()

    if ticker_upper in _mock_cache:
        return _mock_cache[ticker_upper]

    file_path = MOCK_DIR / f"{ticker_upper}.json"
    if not file_path.exists():
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    _mock_cache[ticker_upper] = data
    return data


def get_available_tickers() -> list[str]:
    """Return list of available mock data tickers.

    Scans the mock directory for JSON files (excluding earnings.json).
    """
    tickers = []
    if not MOCK_DIR.exists():
        return tickers

    for file in sorted(MOCK_DIR.iterdir()):
        if file.suffix == ".json" and file.stem != "earnings":
            tickers.append(file.stem.upper())

    return tickers


def load_earnings_calendar() -> list[dict]:
    """Load static earnings calendar data from data/mock/earnings.json.

    Returns an empty list if the file does not exist.
    Caches in memory after first load.
    """
    global _earnings_cache

    if _earnings_cache is not None:
        return _earnings_cache

    file_path = MOCK_DIR / "earnings.json"
    if not file_path.exists():
        _earnings_cache = []
        return _earnings_cache

    with open(file_path, "r", encoding="utf-8") as f:
        _earnings_cache = json.load(f)

    return _earnings_cache


def clear_cache() -> None:
    """Clear all cached data. Useful for testing."""
    global _earnings_cache
    _mock_cache.clear()
    _earnings_cache = None
