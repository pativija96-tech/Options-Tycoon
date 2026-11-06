"""
Executable leg prices and quote-quality checks for the ticket and the position monitor.

Why not last traded price: on 3 Nov 2026 a ticket showed 187.30 / 144.85 / 31.90 / 22.20 for
legs whose 2 Nov NSE closes were exactly those numbers. Before a strike trades in a session,
Kite's last_price is still the previous close. So: sells are priced at the best bid, buys at
the best ask, and each quote's last trade time is checked.

STALE_SECONDS and SPREAD_WARN_PCT come from the action list agreed on 3 Nov 2026.

VOL_RATIO_MIN/MAX bound (average put implied vol) ÷ (average call implied vol), which must fit
one NIFTY level. Measured on 312 weekly ±250/100 condors from NSE closes, Nov 2020 – Oct 2026:
the ratio ran 1.07–1.47. With the previous day's prices against that day's NIFTY (this bug),
0.9–1.8 flagged all cases when NIFTY had moved 200+ points and none of the 312 normal ones.
"""

import math
from datetime import datetime

from scipy.optimize import brentq
from scipy.stats import norm

STALE_SECONDS = 120
SPREAD_WARN_PCT = 5.0
VOL_RATIO_MIN = 0.9
VOL_RATIO_MAX = 1.8
RISK_FREE = 0.065     # the signal engine's rate (simple_ic_engine._estimate_premium)


def parse_time(v):
    """Kite's timestamps: kiteconnect returns datetimes; the raw API returns 'YYYY-MM-DD HH:MM:SS'."""
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, str) and v.strip():
        try:
            return datetime.strptime(v.strip()[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    return None


def open_price(side, q):
    """Price to open a leg now: sell at the best bid, buy at the best ask; last price only if no depth."""
    return (q.get("bid") if side == "SELL" else q.get("ask")) or q.get("ltp")


def close_price(side, q):
    """Price to close an open leg now: buy back a short at the ask, sell a hedge at the bid."""
    return (q.get("ask") if side == "SELL" else q.get("bid")) or q.get("ltp")


def has_depth(side, q, closing=False):
    want = ("ask" if side == "SELL" else "bid") if closing else ("bid" if side == "SELL" else "ask")
    return bool(q.get(want))


def leg_quality(q, today):
    """Spread, last-trade age and flags for one quote. Age is measured on the exchange's own clock."""
    bid, ask = q.get("bid"), q.get("ask")
    spread = spread_pct = None
    if bid and ask:
        spread = round(ask - bid, 2)
        spread_pct = round((ask - bid) / ((ask + bid) / 2) * 100, 1)
    last = parse_time(q.get("last_trade_time"))
    now = parse_time(q.get("quote_time"))
    age = int((now - last).total_seconds()) if last and now else None
    previous_session = last is None or last.date() != today
    return {"spread": spread, "spread_pct": spread_pct, "last_trade_age": age,
            "last_trade_time": last.isoformat(sep=" ") if last else None,
            "previous_session": previous_session,
            "stale": previous_session or (age is not None and age > STALE_SECONDS),
            "wide": spread_pct is not None and spread_pct > SPREAD_WARN_PCT}


def _bs(S, K, T, sigma, opt):
    d1 = (math.log(S / K) + (RISK_FREE + sigma * sigma / 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if opt == "CE":
        return S * norm.cdf(d1) - K * math.exp(-RISK_FREE * T) * norm.cdf(d2)
    return K * math.exp(-RISK_FREE * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def implied_vol(price, spot, strike, days, opt):
    if not price or not spot or price <= 0:
        return None
    T = max(days, 1) / 365
    try:
        return brentq(lambda s: _bs(spot, strike, T, s, opt) - price, 0.005, 5)
    except ValueError:
        return None


def vol_ratio(legs, spot, days):
    """Put-side ÷ call-side implied vol. legs = [(strike, "PE"|"CE", price)]; None if it can't be worked out."""
    vols = {"PE": [], "CE": []}
    for strike, opt, px in legs:
        v = implied_vol(px, spot, strike, days, opt)
        if v is None:
            return None
        vols[opt].append(v)
    if not vols["PE"] or not vols["CE"]:
        return None
    return round((sum(vols["PE"]) / len(vols["PE"])) / (sum(vols["CE"]) / len(vols["CE"])), 2)


def mid(q):
    bid, ask = q.get("bid"), q.get("ask")
    return (bid + ask) / 2 if bid and ask else q.get("ltp")
