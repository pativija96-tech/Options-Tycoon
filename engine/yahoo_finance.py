"""Optional Yahoo Finance end-of-day data fetcher."""
import httpx
from datetime import datetime


async def fetch_eod_price(ticker: str) -> dict | None:
    """
    Fetch end-of-day price data from Yahoo Finance.
    Returns None on failure (silent fallback to mock data).
    Timeout: 5 seconds.
    """
    # Map Indian tickers to Yahoo symbols
    TICKER_MAP = {
        "NIFTY": "^NSEI",
        "BANKNIFTY": "^NSEBANK",
        "RELIANCE": "RELIANCE.NS",
        "TCS": "TCS.NS",
        "INFY": "INFY.NS",
        "HDFCBANK": "HDFCBANK.NS",
        "ICICIBANK": "ICICIBANK.NS",
        "SBIN": "SBIN.NS",
        "TATAMOTORS": "TATAMOTORS.NS",
        "ITC": "ITC.NS",
    }

    symbol = TICKER_MAP.get(ticker.upper())
    if not symbol:
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                return None
            data = resp.json()
            result = data.get("chart", {}).get("result", [])
            if not result:
                return None
            meta = result[0].get("meta", {})
            return {
                "ticker": ticker.upper(),
                "price": meta.get("regularMarketPrice"),
                "previous_close": meta.get("previousClose"),
                "source": "yahoo_finance",
                "fetched_at": datetime.utcnow().isoformat(),
            }
    except Exception:
        return None
