"""
Simple Iron Condor Engine — The validated strategy.

No directional prediction. No pattern matching. No bucket lookups.
Just: get NIFTY price → sell ±250pt IC with 100pt wings → collect premium.

Replaces the complex signal_engine.py pipeline with a mechanical,
daily trade generator.

Usage:
    from engine.signals.simple_ic_engine import generate_daily_signal
    signal = generate_daily_signal()
"""

import json
import math
import logging
from datetime import datetime, date, timedelta
from pathlib import Path

from scipy.stats import norm

logger = logging.getLogger("simple_ic_engine")

# Strategy parameters (validated through 5 rounds of testing)
OFFSET_PTS = 250       # Short strikes ±250 pts from ATM
WING_WIDTH = 100       # Long strikes 100 pts beyond short strikes
DAYS_TO_EXPIRY = 3     # Weekly expiry (Tuesday)
VIX_MAX = 40           # Don't trade if VIX > 40 (too chaotic)
RISK_CAP_PCT = 0.02    # Max 2% of capital per trade

# Phase-aware lot size
import os as _os
_TRADING_PHASE = int(_os.environ.get("TRADING_PHASE", "1"))
if _TRADING_PHASE <= 2:
    LOT_SIZE = 25      # Phase 1-2: 1 lot (NIFTY lot size = 25 as of 2024)
else:
    LOT_SIZE = 50      # Phase 3: 2 lots


def _get_nifty_price() -> dict:
    """
    Fetch current NIFTY price and VIX level.
    Priority: Kite API (live, real-time) → yfinance (fallback, may lag).
    """
    result = {"nifty": None, "vix": None, "source": None, "errors": []}
    
    # Try Kite first (real-time, no lag)
    try:
        from engine.broker.kite_auth import is_authenticated, get_kite_client
        if is_authenticated():
            kite = get_kite_client()
            if kite:
                ltp_data = kite.ltp(["NSE:NIFTY 50", "NSE:INDIA VIX"])
                if "NSE:NIFTY 50" in ltp_data:
                    result["nifty"] = ltp_data["NSE:NIFTY 50"]["last_price"]
                    result["source"] = "kite"
                if "NSE:INDIA VIX" in ltp_data:
                    result["vix"] = ltp_data["NSE:INDIA VIX"]["last_price"]
                if result["nifty"]:
                    logger.info(f"Kite live: NIFTY={result['nifty']}, VIX={result['vix']}")
                    return result
    except Exception as e:
        result["errors"].append(f"Kite: {str(e)[:100]}")
    
    # Fallback to yfinance (may have 1-day lag)
    import yfinance as yf
    try:
        nifty_data = yf.download("^NSEI", period="2d", progress=False, timeout=15)
        if nifty_data is not None and len(nifty_data) >= 1:
            close_col = nifty_data["Close"]
            if hasattr(close_col, "columns"):
                close_col = close_col.iloc[:, 0]
            result["nifty"] = float(close_col.iloc[-1])
            result["source"] = "yfinance"
    except Exception as e:
        result["errors"].append(f"NIFTY yfinance: {str(e)[:100]}")
    
    try:
        vix_data = yf.download("^INDIAVIX", period="2d", progress=False, timeout=15)
        if vix_data is not None and len(vix_data) >= 1:
            close_col = vix_data["Close"]
            if hasattr(close_col, "columns"):
                close_col = close_col.iloc[:, 0]
            result["vix"] = float(close_col.iloc[-1])
    except Exception as e:
        result["errors"].append(f"VIX yfinance: {str(e)[:100]}")
        result["vix"] = 15.0
    
    return result


def _estimate_premium(spot: float, strike: float, days: int, option_type: str, iv: float) -> float:
    """Black-Scholes premium estimate."""
    T = days / 365.0
    if T <= 0: T = 1/365.0
    S = spot; K = strike; r = 0.065; sigma = iv
    try:
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*sqrt_T)
        d2 = d1 - sigma*sqrt_T
        if option_type == "call":
            return max(0.5, S*norm.cdf(d1) - K*math.exp(-r*T)*norm.cdf(d2))
        else:
            return max(0.5, K*math.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1))
    except:
        return 5.0  # fallback


def _get_expiry_date() -> tuple:
    """Get nearest Tuesday (NIFTY weekly expiry) and formatted string."""
    today = date.today()
    days_until_tuesday = (1 - today.weekday()) % 7
    if days_until_tuesday == 0:
        days_until_tuesday = 7
    expiry = today + timedelta(days=days_until_tuesday)
    days_to_exp = (expiry - today).days
    expiry_str = expiry.strftime("%d %b %Y") + " (Tue)"
    return expiry, days_to_exp, expiry_str


def _calculate_charges(num_legs: int = 4) -> dict:
    """Zerodha charges for IC (4 legs, entry + exit)."""
    brokerage = 20 * num_legs * 2
    gst = round(brokerage * 0.18, 2)
    other = 50  # STT + exchange + stamp (approximate)
    total = round(brokerage + gst + other, 2)
    return {"brokerage": brokerage, "gst": gst, "other": other, "total": total}


def _round_strike(price: float, step: int = 50) -> int:
    """Round to nearest NIFTY strike (multiples of 50)."""
    return int(round(price / step) * step)


def generate_daily_signal(capital: float = 1000000) -> dict:
    """
    Generate today's Iron Condor signal.
    
    No prediction. No pattern matching. Just mechanical IC at ±250pt.
    
    Returns a trade card dict compatible with the existing UI.
    """
    logger.info("Simple IC Engine: generating daily signal...")
    
    # Step 1: Get NIFTY price
    market_data = _get_nifty_price()
    nifty_price = market_data["nifty"]
    vix_level = market_data["vix"] or 15.0
    
    if not nifty_price:
        return {
            "action": "skip",
            "reason": f"Could not fetch NIFTY price. Errors: {market_data['errors']}",
            "date": date.today().strftime("%Y-%m-%d"),
        }
    
    # Step 2: VIX sanity check
    if vix_level > VIX_MAX:
        return {
            "action": "skip",
            "reason": f"VIX at {vix_level:.1f} (>{VIX_MAX}). Too chaotic for Iron Condor. Sitting out.",
            "date": date.today().strftime("%Y-%m-%d"),
            "conditions": {"nifty": nifty_price, "vix": vix_level},
        }
    
    # Step 3: Calculate strikes
    spot = _round_strike(nifty_price)
    short_call = spot + OFFSET_PTS
    short_put = spot - OFFSET_PTS
    long_call = short_call + WING_WIDTH
    long_put = short_put - WING_WIDTH
    
    # Step 4: Estimate premiums
    iv = vix_level / 100  # VIX is annualized vol in %
    _, days_to_exp, expiry_str = _get_expiry_date()
    
    short_call_prem = round(_estimate_premium(nifty_price, short_call, days_to_exp, "call", iv), 2)
    long_call_prem = round(_estimate_premium(nifty_price, long_call, days_to_exp, "call", iv), 2)
    short_put_prem = round(_estimate_premium(nifty_price, short_put, days_to_exp, "put", iv), 2)
    long_put_prem = round(_estimate_premium(nifty_price, long_put, days_to_exp, "put", iv), 2)
    
    net_credit = (short_call_prem - long_call_prem) + (short_put_prem - long_put_prem)
    net_credit_total = round(net_credit * LOT_SIZE, 2)
    max_loss_per_unit = WING_WIDTH - net_credit
    max_loss = round(max_loss_per_unit * LOT_SIZE, 2)
    max_profit = net_credit_total
    
    # Step 5: Risk cap check
    max_risk = capital * RISK_CAP_PCT
    if max_loss > max_risk:
        return {
            "action": "skip",
            "reason": f"Max loss Rs.{max_loss:.0f} exceeds 2% cap (Rs.{max_risk:.0f}). Capital too low for this strategy.",
            "date": date.today().strftime("%Y-%m-%d"),
            "conditions": {"nifty": nifty_price, "vix": vix_level},
        }
    
    # Step 6: Calculate charges
    charges = _calculate_charges()
    net_max_profit = round(max_profit - charges["total"], 2)
    net_max_loss = round(max_loss + charges["total"], 2)
    rr = round(max_profit / max_loss, 2) if max_loss > 0 else 0
    
    # Step 7: Build trade card (compatible with existing UI)
    trade_card = {
        "action": "trade",
        "timestamp": datetime.now().isoformat(),
        "date": date.today().strftime("%Y-%m-%d"),
        "direction": "neutral",
        "confidence": None,  # No prediction — mechanical strategy
        "strategy_type": "iron_condor_250_100",
        "projected_open": nifty_price,
        "trade": {
            "type": "iron_condor",
            "legs": [
                {"action": "SELL", "option": "CE", "strike": short_call, "premium_est": short_call_prem},
                {"action": "BUY", "option": "CE", "strike": long_call, "premium_est": long_call_prem},
                {"action": "SELL", "option": "PE", "strike": short_put, "premium_est": short_put_prem},
                {"action": "BUY", "option": "PE", "strike": long_put, "premium_est": long_put_prem},
            ],
            "net_cost": round(-net_credit, 2),
            "net_cost_total": round(-net_credit_total, 2),
            "max_profit": round(max_profit, 2),
            "max_loss": round(max_loss, 2),
            "net_max_profit": net_max_profit,
            "net_max_loss": net_max_loss,
            "sl_value": round(net_credit * 0.5 * LOT_SIZE, 2),
            "risk_reward": rr,
            "breakeven": f"{short_put + net_credit:.0f} / {short_call - net_credit:.0f}",
            "expiry_days": days_to_exp,
            "expiry_date": expiry_str,
            "width": WING_WIDTH,
            "charges": charges,
        },
        "reasoning": (
            f"Mechanical ±{OFFSET_PTS}pt Iron Condor. "
            f"NIFTY at {nifty_price:.0f} (source: {market_data.get('source', 'unknown')}), VIX at {vix_level:.1f}%. "
            f"Collect Rs.{net_credit_total:.0f} premium. "
            f"Win if NIFTY stays between {short_put} and {short_call} by expiry."
        ),
        "conditions": {
            "nifty_price": nifty_price,
            "vix_level": vix_level,
            "us_change_pct": 0,  # Not used in new engine
            "vix_change_pct": 0,
            "dxy_change_pct": 0,
        },
        "pattern_result": {
            "direction": "neutral",
            "confidence": None,
            "note": "No directional prediction. Mechanical premium selling.",
        },
        "quality_filters": {
            "filters": {
                "vix_sanity": {"pass": True, "name": "VIX Sanity", "reason": f"VIX {vix_level:.1f} < {VIX_MAX}"},
                "risk_cap": {"pass": True, "name": "Risk Cap", "reason": f"Max loss Rs.{max_loss:.0f} < 2% cap Rs.{max_risk:.0f}"},
            },
            "passed": 2,
            "total": 2,
            "strength": "MECHANICAL",
            "recommendation": "Validated strategy. Execute daily.",
            "position_sizing": {"size": "half" if _TRADING_PHASE <= 2 else "full", "lots": 0.5 if _TRADING_PHASE <= 2 else 1, "label": f"Phase {_TRADING_PHASE}: {'half lot (32 qty)' if _TRADING_PHASE <= 2 else 'full lot (65 qty)'}", "conviction": "mechanical"},
        },
        "position_sizing": {"size": "half" if _TRADING_PHASE <= 2 else "full", "lots": 0.5 if _TRADING_PHASE <= 2 else 1, "label": f"Phase {_TRADING_PHASE}: {'half lot (32 qty)' if _TRADING_PHASE <= 2 else 'full lot (65 qty)'}", "conviction": "mechanical"},
        "risk_check": {
            "max_loss": net_max_loss,
            "max_loss_pct": round(net_max_loss / capital * 100, 2),
            "within_2pct_cap": net_max_loss <= max_risk,
            "capital": capital,
        },
    }
    
    logger.info(f"Signal generated: IC ±{OFFSET_PTS} at {nifty_price:.0f}, "
                f"credit Rs.{net_credit_total:.0f}, max loss Rs.{max_loss:.0f}")
    
    return trade_card


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    signal = generate_daily_signal()
    print(json.dumps(signal, indent=2, default=str))
