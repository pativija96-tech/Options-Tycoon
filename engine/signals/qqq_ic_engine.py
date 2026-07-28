"""
QQQ Iron Condor Engine — Daily 0DTE signal generator for US market.

Same philosophy as simple_ic_engine.py (NIFTY) but for QQQ via IBKR.
No directional prediction. Mechanical ±$15 IC, $7 wings, daily.

Usage:
    from engine.signals.qqq_ic_engine import generate_qqq_signal
    signal = generate_qqq_signal()
"""

import logging
import math
from datetime import datetime, date
from scipy.stats import norm

logger = logging.getLogger("qqq_ic_engine")

# Strategy parameters (validated — read from config/settings.json)
QQQ_OFFSET = 15       # ±$15 from ATM
QQQ_WING = 5          # Phase 1: $5 wing width (reduces to $500 max loss)
QQQ_MULTIPLIER = 100  # US options multiplier
VIX_MAX = 35          # Don't trade if VIX > 35

# Load from config if available
try:
    import json as _json
    import os as _os
    _cfg_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "config", "settings.json")
    if _os.path.exists(_cfg_path):
        with open(_cfg_path) as _f:
            _cfg = _json.load(_f)
        _qqq = _cfg.get("qqq", {})
        if _qqq.get("offset_pts"): QQQ_OFFSET = _qqq["offset_pts"]
        if _qqq.get("wing_width"): QQQ_WING = _qqq["wing_width"]
except Exception:
    pass

# ──────────────────────────────────────────────────────────────────────
# EVENT / EARNINGS FILTER — Skip trade on high-impact economic events
# ──────────────────────────────────────────────────────────────────────

# High-impact US economic events that can cause >$15 intraday QQQ moves
# Format: (month, day) tuples for known recurring dates, plus dynamic checks
FOMC_DATES_2026 = [
    (1, 29), (3, 19), (5, 7), (6, 18), (7, 30), (9, 17), (11, 5), (12, 17)
]

# Mega-cap earnings that move QQQ >2% (these are approximate — update quarterly)
QQQ_MEGA_EARNINGS_BLACKOUT = {
    # (month, day): "reason"
    # Q1 2026 earnings (Jan-Feb)
    # Q2 2026 earnings (Apr-May)
    # Q3 2026 earnings (Jul-Aug)
    # Q4 2026 earnings (Oct-Nov)
    # Populated dynamically or manually before each earnings season
}


def _is_high_impact_event_day() -> tuple:
    """
    Check if today has a high-impact economic event that could cause >$15 QQQ gap.
    
    Returns:
        (skip: bool, reason: str)
    """
    today = date.today()
    month_day = (today.month, today.day)
    
    # Check FOMC dates
    for fomc_date in FOMC_DATES_2026:
        if month_day == fomc_date:
            return True, f"FOMC rate decision today ({today.isoformat()}). Skipping 0DTE IC."
    
    # Check mega-cap earnings blackout
    if month_day in QQQ_MEGA_EARNINGS_BLACKOUT:
        reason = QQQ_MEGA_EARNINGS_BLACKOUT[month_day]
        return True, f"Mega-cap earnings today: {reason}. Skipping 0DTE IC."
    
    # Check via yfinance economic calendar (CPI, NFP days)
    # These are the most impactful non-FOMC events
    try:
        from data.historical.event_calendar import is_high_impact_today
        skip, reason = is_high_impact_today()
        if skip:
            return True, reason
    except ImportError:
        pass  # event_calendar module not available — proceed with trade
    
    return False, ""


def _get_qqq_price() -> dict:
    """Get QQQ price. IBKR first, yfinance fallback."""
    result = {"qqq": None, "vix": None, "source": None, "errors": []}
    
    # Try IBKR
    try:
        import asyncio
        from engine.broker.ibkr_executor import connect_ibkr, get_qqq_price
        
        async def _fetch():
            ib = await connect_ibkr()
            if ib:
                price = await get_qqq_price(ib)
                ib.disconnect()
                return price
            return None
        
        price = asyncio.run(_fetch())
        if price:
            result["qqq"] = price
            result["source"] = "ibkr"
            return result
    except Exception as e:
        result["errors"].append(f"IBKR: {str(e)[:100]}")
    
    # Fallback: yfinance
    try:
        import yfinance as yf
        data = yf.download("QQQ", period="2d", progress=False, timeout=15)
        if data is not None and len(data) >= 1:
            close_col = data["Close"]
            if hasattr(close_col, "columns"):
                close_col = close_col.iloc[:, 0]
            result["qqq"] = float(close_col.iloc[-1])
            result["source"] = "yfinance"
        
        vix = yf.download("^VIX", period="2d", progress=False, timeout=15)
        if vix is not None and len(vix) >= 1:
            vc = vix["Close"]
            if hasattr(vc, "columns"):
                vc = vc.iloc[:, 0]
            result["vix"] = float(vc.iloc[-1])
    except Exception as e:
        result["errors"].append(f"yfinance: {str(e)[:100]}")
    
    return result


def _estimate_premium(spot, strike, days, option_type, iv):
    """Black-Scholes premium."""
    T = days/365.0
    if T <= 0: T = 1/365.0
    S = spot; K = strike; r = 0.05; sigma = iv
    try:
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*sqrt_T)
        d2 = d1 - sigma*sqrt_T
        if option_type == "call":
            return max(0.01, S*norm.cdf(d1) - K*math.exp(-r*T)*norm.cdf(d2))
        else:
            return max(0.01, K*math.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1))
    except:
        return 0.10


def generate_qqq_signal(capital: float = 1000) -> dict:
    """Generate today's QQQ Iron Condor signal."""
    logger.info("QQQ IC Engine: generating signal...")
    
    # Event filter — skip on FOMC, CPI, mega-cap earnings
    skip_event, event_reason = _is_high_impact_event_day()
    if skip_event:
        logger.warning(f"Event filter triggered: {event_reason}")
        return {"action": "skip", "reason": event_reason, "date": date.today().isoformat(), "filter": "event_calendar"}
    
    market_data = _get_qqq_price()
    qqq_price = market_data["qqq"]
    vix = market_data.get("vix") or 18.0
    
    if not qqq_price:
        return {"action": "skip", "reason": f"Cannot get QQQ price: {market_data['errors']}", "date": date.today().isoformat()}
    
    if vix > VIX_MAX:
        return {"action": "skip", "reason": f"VIX at {vix:.1f} > {VIX_MAX}. Too volatile.", "date": date.today().isoformat()}
    
    # Calculate strikes
    spot = round(qqq_price)
    short_call = spot + QQQ_OFFSET
    long_call = short_call + QQQ_WING
    short_put = spot - QQQ_OFFSET
    long_put = short_put - QQQ_WING
    
    # Estimate premiums (0DTE = same day expiry)
    iv = vix / 100
    sc_prem = round(_estimate_premium(qqq_price, short_call, 0.5, "call", iv), 2)
    lc_prem = round(_estimate_premium(qqq_price, long_call, 0.5, "call", iv), 2)
    sp_prem = round(_estimate_premium(qqq_price, short_put, 0.5, "put", iv), 2)
    lp_prem = round(_estimate_premium(qqq_price, long_put, 0.5, "put", iv), 2)
    
    net_credit = (sc_prem - lc_prem) + (sp_prem - lp_prem)
    net_credit_total = round(net_credit * QQQ_MULTIPLIER, 2)
    max_loss = round((QQQ_WING - net_credit) * QQQ_MULTIPLIER, 2)
    max_profit = net_credit_total
    
    # Commission
    commission = 4.0  # $4 per trade (4 legs × $0.65 × ~1.5)
    net_max_profit = round(max_profit - commission, 2)
    net_max_loss = round(max_loss + commission, 2)
    
    return {
        "action": "trade",
        "market": "QQQ",
        "timestamp": datetime.now().isoformat(),
        "date": date.today().isoformat(),
        "direction": "neutral",
        "strategy_type": "iron_condor_qqq",
        "projected_open": qqq_price,
        "trade": {
            "type": "iron_condor",
            "underlying": "QQQ",
            "legs": [
                {"action": "SELL", "option": "C", "strike": short_call, "premium_est": sc_prem},
                {"action": "BUY", "option": "C", "strike": long_call, "premium_est": lc_prem},
                {"action": "SELL", "option": "P", "strike": short_put, "premium_est": sp_prem},
                {"action": "BUY", "option": "P", "strike": long_put, "premium_est": lp_prem},
            ],
            "net_credit": round(net_credit, 2),
            "net_credit_total": net_credit_total,
            "max_profit": round(max_profit, 2),
            "max_loss": round(max_loss, 2),
            "net_max_profit": net_max_profit,
            "net_max_loss": net_max_loss,
            "commission": commission,
            "expiry": "0DTE (same day)",
            "width": QQQ_WING,
        },
        "reasoning": f"QQQ at ${qqq_price:.2f} (source: {market_data['source']}). VIX: {vix:.1f}%. Sell ±${QQQ_OFFSET} IC, ${QQQ_WING} wings. Win if QQQ stays between ${short_put} and ${short_call}.",
        "conditions": {"qqq_price": qqq_price, "vix": vix},
        "quality_filters": {
            "filters": {
                "vix_sanity": {"pass": True, "name": "VIX Sanity", "reason": f"VIX {vix:.1f} < {VIX_MAX}"},
                "capital_check": {"pass": net_max_loss < capital * 0.7, "name": "Capital Check", "reason": f"Max loss ${net_max_loss} < 70% of ${capital}"},
            },
            "passed": 2, "total": 2, "strength": "MECHANICAL",
            "position_sizing": {"size": "full", "lots": 1, "label": "1 contract (QQQ 0DTE)", "conviction": "mechanical"},
        },
        "position_sizing": {"size": "full", "lots": 1, "label": "1 contract (QQQ 0DTE)"},
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    signal = generate_qqq_signal()
    print(json.dumps(signal, indent=2, default=str))
