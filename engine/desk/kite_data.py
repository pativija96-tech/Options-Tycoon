"""
Read-only Kite helpers for the Trade Ticket: exact option symbols, live quotes,
basket margin and available funds. Never places or modifies orders.

Every helper returns None (and records why in `errors`) instead of raising, so the
ticket can fall back to model estimates and say so.
"""

import logging
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger("options_tycoon.desk.kite")

IST = timezone(timedelta(hours=5, minutes=30))

_instrument_cache = {"day": None, "rows": None}


def ist_today() -> date:
    """Today's date in India (the server runs in UTC)."""
    return datetime.now(IST).date()


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _nifty_options(kite, today, errors):
    """Kite's NFO instrument dump filtered to NIFTY options, cached for the day."""
    if _instrument_cache["day"] == today and _instrument_cache["rows"] is not None:
        return _instrument_cache["rows"]
    try:
        rows = kite.instruments("NFO")
    except Exception as e:
        errors.append(f"Instrument list unavailable: {str(e)[:120]}")
        return None
    nifty = [r for r in rows if r.get("name") == "NIFTY" and r.get("instrument_type") in ("CE", "PE")]
    _instrument_cache.update(day=today, rows=nifty)
    return nifty


def resolve_symbols(kite, legs, today, errors):
    """
    Find the exact Kite trading symbols for the signal's legs on the nearest NIFTY
    expiry after today, using Kite's own instrument list (handles weekly vs monthly
    symbol formats and holiday-shifted expiries).

    legs: [{"strike": 24100, "option": "PE"}, ...]
    Returns (expiry_date, {(strike, option): tradingsymbol}) or (None, None).
    """
    rows = _nifty_options(kite, today, errors)
    if not rows:
        return None, None
    expiries = sorted({d for d in (_as_date(r.get("expiry")) for r in rows) if d and d > today})
    if not expiries:
        errors.append("No upcoming NIFTY expiry in Kite's instrument list")
        return None, None
    expiry = expiries[0]
    wanted = {(int(l["strike"]), l["option"]) for l in legs}
    found = {}
    for r in rows:
        if _as_date(r.get("expiry")) != expiry:
            continue
        key = (int(round(float(r.get("strike", 0)))), r.get("instrument_type"))
        if key in wanted:
            found[key] = r.get("tradingsymbol")
    missing = wanted - set(found)
    if missing:
        errors.append("Kite has no contract for " + ", ".join(f"{k[0]} {k[1]}" for k in sorted(missing)))
        return expiry, None
    return expiry, found


def fetch_quotes(kite, symbols, errors):
    """{tradingsymbol: {"ltp", "bid", "ask"}} from kite.quote, or None."""
    try:
        data = kite.quote([f"NFO:{s}" for s in symbols])
    except Exception as e:
        errors.append(f"Live quotes unavailable: {str(e)[:120]}")
        return None
    out = {}
    for s in symbols:
        q = data.get(f"NFO:{s}") or {}
        depth = q.get("depth") or {}
        buy = (depth.get("buy") or [{}])[0]
        sell = (depth.get("sell") or [{}])[0]
        ltp = q.get("last_price")
        if not ltp:
            errors.append(f"No live price for {s}")
            return None
        out[s] = {"ltp": float(ltp), "bid": float(buy.get("price") or 0) or None, "ask": float(sell.get("price") or 0) or None}
    return out


def basket_margin(kite, orders, errors):
    """Kite's margin for the 4-leg basket (as entered, protective legs first), or None."""
    params = [{
        "exchange": "NFO", "tradingsymbol": o["symbol"], "transaction_type": o["side"],
        "variety": "regular", "product": "NRML", "order_type": "LIMIT",
        "quantity": o["qty"], "price": o["price"],
    } for o in orders]
    try:
        res = kite.basket_order_margins(params, consider_positions=False)
    except Exception as e:
        errors.append(f"Margin check unavailable: {str(e)[:120]}")
        return None
    for key in ("final", "initial"):
        total = (res or {}).get(key, {}).get("total") if isinstance(res, dict) else None
        if total:
            return float(total)
    errors.append("Margin check returned no total")
    return None


def available_funds(kite, errors):
    """Net equity funds available in the Kite account, or None."""
    try:
        m = kite.margins()
        net = (m.get("equity") or {}).get("net")
        return float(net) if net is not None else None
    except Exception as e:
        errors.append(f"Funds check unavailable: {str(e)[:120]}")
        return None
