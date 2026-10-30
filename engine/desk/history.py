"""
Market history for the morning range check — daily candles stored in market_history.

Sources, in order of preference:
  NIFTY 50 / India VIX  — Kite historical candles (needs a Kite login and the Connect
                          plan's historical data); Yahoo (^NSEI, ^INDIAVIX) only as a
                          labelled fallback when Kite is not available.
  World indices         — Yahoo, the same tickers the signal engine's data fetcher uses
                          (engine/signals/data_fetcher.py INDICES). Kite has no foreign
                          indices.

Nothing here runs on its own: loading happens only when the founder presses
"Load history" on the desk. Every loader reports problems in `errors` instead of raising.
"""

import logging
from datetime import date, datetime, timedelta

from engine.signals.data_fetcher import INDICES

logger = logging.getLogger("options_tycoon.desk.history")

# Kite tradingsymbols on the NSE indices segment.
INDIA = {"nifty": "NIFTY 50", "india_vix": "INDIA VIX"}
INDIA_YAHOO = {"nifty": "^NSEI", "india_vix": "^INDIAVIX"}
# The fetcher's "gift_nifty" is only NIFTY's own last close, not GIFT Nifty — left out.
WORLD = {k: v for k, v in INDICES.items() if k != "gift_nifty"}
WORLD_NAMES = {"sp500": "S&P 500", "nasdaq": "Nasdaq", "vix": "US VIX", "dxy": "US dollar index",
               "us_10y": "US 10-year yield", "ftse": "FTSE 100", "dax": "DAX", "nikkei": "Nikkei 225",
               "hang_seng": "Hang Seng"}

KITE_CHUNK_DAYS = 365   # well inside Kite's per-request window for day candles


def _day(v):
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v)[:10]


def _row(symbol, d, o, h, l, c, source):
    if c is None:
        return None
    f = lambda x: None if x is None else round(float(x), 4)
    return {"symbol": symbol, "date": _day(d), "open": f(o), "high": f(h), "low": f(l), "close": f(c), "source": source}


# ── Loaders ─────────────────────────────────────────────────────────────────

def kite_index_tokens(kite, errors):
    """{name: instrument_token} for NIFTY 50 and India VIX from Kite's NSE instrument list."""
    try:
        rows = kite.instruments("NSE")
    except Exception as e:
        errors.append(f"Kite instrument list: {str(e)[:120]}")
        return {}
    by_symbol = {r.get("tradingsymbol"): r.get("instrument_token") for r in rows}
    tokens = {}
    for name, sym in INDIA.items():
        if by_symbol.get(sym):
            tokens[name] = by_symbol[sym]
        else:
            errors.append(f"Kite has no NSE instrument named {sym!r}")
    return tokens


def load_kite(kite, today: date, years: int, errors):
    """Daily candles for NIFTY 50 and India VIX from Kite, fetched a year at a time."""
    rows = []
    start = today - timedelta(days=365 * years)
    for name, token in kite_index_tokens(kite, errors).items():
        frm = start
        while frm <= today:
            to = min(frm + timedelta(days=KITE_CHUNK_DAYS - 1), today)
            try:
                candles = kite.historical_data(token, frm, to, "day")
            except Exception as e:
                errors.append(f"Kite history {INDIA[name]} {frm}–{to}: {str(e)[:120]}")
                break
            for c in candles or []:
                r = _row(name, c.get("date"), c.get("open"), c.get("high"), c.get("low"), c.get("close"), "kite")
                if r:
                    rows.append(r)
            frm = to + timedelta(days=1)
    return rows


def load_yahoo(tickers: dict, today: date, years: int, errors, downloader=None):
    """Daily candles from Yahoo for {name: ticker}. `downloader` is yfinance.download (tests pass a fake)."""
    if downloader is None:
        try:
            import yfinance as yf
            downloader = yf.download
        except ImportError:
            errors.append("yfinance not installed")
            return []
    start = today - timedelta(days=365 * years)
    rows = []
    for name, ticker in tickers.items():
        try:
            df = downloader(ticker, start=start.isoformat(), end=(today + timedelta(days=1)).isoformat(),
                            interval="1d", progress=False, auto_adjust=False, timeout=20)
        except Exception as e:
            errors.append(f"Yahoo {ticker}: {str(e)[:120]}")
            continue
        if df is None or len(df) == 0:
            errors.append(f"Yahoo {ticker}: no data")
            continue

        def col(field):
            c = df[field]
            return c.iloc[:, 0] if hasattr(c, "columns") else c   # yfinance may return MultiIndex columns

        o, h, l, c = col("Open"), col("High"), col("Low"), col("Close")
        for i, idx in enumerate(df.index):
            close = c.iloc[i]
            if close != close:   # NaN
                continue
            val = lambda s: None if s.iloc[i] != s.iloc[i] else s.iloc[i]
            r = _row(name, idx, val(o), val(h), val(l), close, "yahoo")
            if r:
                rows.append(r)
    return rows


def load_all(kite, today: date, years: int = 6, downloader=None):
    """Load India (Kite, else Yahoo fallback) and world (Yahoo) history and store it."""
    errors, rows = [], []
    india_source = "kite"
    if kite is not None:
        rows += load_kite(kite, today, years, errors)
    got = {r["symbol"] for r in rows}
    missing = {k: v for k, v in INDIA_YAHOO.items() if k not in got}
    if missing:
        india_source = "yahoo (fallback)" if kite is None or not got else "kite + yahoo (fallback)"
        if kite is None:
            errors.append("Kite not connected — NIFTY / India VIX loaded from Yahoo as a fallback")
        rows += load_yahoo(missing, today, years, errors, downloader)
    rows += load_yahoo(WORLD, today, years, errors, downloader)
    saved = save_rows(rows)
    return {"saved": saved, "india_source": india_source, "errors": errors, "status": history_status()}


# ── Storage ─────────────────────────────────────────────────────────────────

def save_rows(rows) -> int:
    """Upsert candles. A Kite row is never replaced by a Yahoo row for the same day."""
    if not rows:
        return 0
    from db.database import get_connection
    conn = get_connection()
    try:
        for r in rows:
            conn.execute(
                """INSERT INTO market_history (symbol, date, open, high, low, close, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (symbol, date) DO UPDATE SET open = excluded.open, high = excluded.high,
                       low = excluded.low, close = excluded.close, source = excluded.source
                   WHERE market_history.source <> 'kite' OR excluded.source = 'kite'""",
                (r["symbol"], r["date"], r["open"], r["high"], r["low"], r["close"], r["source"]),
            )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def load_series(symbols=None) -> dict:
    """{symbol: [rows sorted by date]} from market_history."""
    from db.database import get_connection
    conn = get_connection()
    try:
        rows = conn.execute("SELECT symbol, date, open, high, low, close, source FROM market_history ORDER BY symbol, date").fetchall()
    finally:
        conn.close()
    out = {}
    for r in rows:
        r = dict(r)
        if symbols and r["symbol"] not in symbols:
            continue
        out.setdefault(r["symbol"], []).append(r)
    return out


def history_status() -> list:
    """Per symbol: rows, first and last date, and sources."""
    series = load_series()
    out = []
    for name in list(INDIA) + list(WORLD):
        rows = series.get(name) or []
        out.append({"symbol": name,
                    "label": {"nifty": "NIFTY 50", "india_vix": "India VIX"}.get(name, WORLD_NAMES.get(name, name)),
                    "rows": len(rows), "first": rows[0]["date"] if rows else None,
                    "last": rows[-1]["date"] if rows else None,
                    "sources": sorted({r["source"] for r in rows})})
    return out
