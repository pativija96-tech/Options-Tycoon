"""
Strategy Picker — Maps market conditions to specific options trade recommendations.
Uses pattern matcher output + greeks.py for strike estimation.
"""

import json
import logging
import sys
from pathlib import Path

# Add project root to path for greeks import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from engine.greeks import black_scholes_greeks

logger = logging.getLogger(__name__)

# NIFTY lot size (revised January 2026 — from 75 to 65)
LOT_SIZE = 65

# Strategy mapping matrix
STRATEGY_MATRIX = {
    # (direction, confidence_tier, vol_regime) → strategy
    ("bearish", "high", "high"): "bear_put_spread_wide",
    ("bearish", "high", "normal"): "bear_put_spread",
    ("bearish", "high", "low"): "bear_put_spread",
    ("bearish", "moderate", "high"): "bear_put_spread_small",
    ("bearish", "moderate", "normal"): "bear_put_spread_small",
    ("bearish", "moderate", "low"): "bear_put_spread_small",
    ("bullish", "high", "high"): "bull_call_spread_wide",
    ("bullish", "high", "normal"): "bull_call_spread",
    ("bullish", "high", "low"): "bull_call_spread",
    ("bullish", "moderate", "high"): "bull_call_spread_small",
    ("bullish", "moderate", "normal"): "bull_call_spread_small",
    ("bullish", "moderate", "low"): "bull_call_spread_small",
    ("neutral", "high", "high"): "long_straddle",
    ("neutral", "high", "normal"): "iron_condor",
    ("neutral", "high", "low"): "iron_condor",
    ("neutral", "moderate", "high"): "long_straddle",
    ("neutral", "moderate", "normal"): "iron_condor",
    ("neutral", "moderate", "low"): "iron_condor",
}


def load_settings() -> dict:
    """Load capital and risk settings from config."""
    config_path = Path("config/settings.json")
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {"capital": 10000, "risk_per_trade": 0.02, "nifty_lot_size": 65}


def get_confidence_tier(confidence: int) -> str:
    """Map confidence percentage to tier."""
    if confidence >= 70:
        return "high"
    if confidence >= 55:
        return "moderate"
    return "low"


def get_vol_regime(vix_change: float) -> str:
    """Determine volatility regime from VIX change."""
    if vix_change > 10:
        return "high"
    if vix_change < -5:
        return "low"
    return "normal"


def round_to_strike(price: float, step: int = 50) -> int:
    """Round to nearest valid NIFTY strike price (multiples of 50)."""
    return int(round(price / step) * step)


def estimate_premium(spot: float, strike: float, days_to_expiry: int, 
                     option_type: str, iv: float = 0.18) -> float:
    """Estimate option premium using Black-Scholes formula directly."""
    import math
    from scipy.stats import norm
    
    T = days_to_expiry / 365.0
    if T <= 0:
        T = 1 / 365.0
    
    S = spot
    K = strike
    r = 0.065
    sigma = iv
    
    try:
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T
        
        if option_type == "call":
            price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        else:
            price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        
        return max(0.5, round(price, 2))
    except Exception as e:
        logger.warning(f"Premium calc failed: {e}")
        # Rough fallback
        intrinsic = max(0, (spot - strike) if option_type == "call" else (strike - spot))
        time_value = spot * iv * math.sqrt(T) * 0.4
        return max(0.5, round(intrinsic + time_value * 0.1, 2))


def generate_trade_card(pattern_result: dict, projected_open: float = None) -> dict:
    """
    Generate a complete trade card with entry, SL, target, and reasoning.
    
    Args:
        pattern_result: Output from pattern_matcher.generate_pattern_signal()
        projected_open: Gift Nifty projected opening price
    """
    settings = load_settings()
    capital = settings["capital"]
    max_risk = capital * settings["risk_per_trade"]
    
    direction = pattern_result.get("direction", "skip")
    confidence = pattern_result.get("confidence", 0)
    avg_move = pattern_result.get("avg_move", 0)
    conditions = pattern_result.get("conditions", {})
    
    # Skip if low confidence or neutral with no edge
    if direction == "skip" or confidence < 55:
        # Even with low confidence, we can suggest a non-directional strategy
        # Pro traders sell premium in low-confidence environments
        if projected_open and projected_open > 0:
            # Neutral / low confidence → Iron Condor (profit from time decay)
            direction = "neutral"
            confidence = max(confidence, 40)
        else:
            return {
                "action": "skip",
                "reason": "No data available to generate any trade",
                "conditions": conditions,
                "pattern_result": pattern_result,
            }
    
    # Determine projected opening price
    if projected_open is None or projected_open == 0:
        projected_open = 24500  # Default fallback
    
    spot = projected_open
    confidence_tier = get_confidence_tier(confidence)
    vix_change = conditions.get("vix_change_pct", 0)
    vol_regime = get_vol_regime(vix_change)
    
    # Look up strategy
    strategy_key = (direction, confidence_tier, vol_regime)
    strategy_type = STRATEGY_MATRIX.get(strategy_key, "skip")
    
    if strategy_type == "skip":
        return {
            "action": "skip",
            "reason": f"No suitable strategy for {direction}/{confidence_tier}/{vol_regime}",
            "conditions": conditions,
            "pattern_result": pattern_result,
        }
    
    # Calculate expected move in points
    expected_move_pts = abs(avg_move) * spot / 100
    
    # Days to expiry (current week = ~3 days avg, next week = ~7)
    days_to_expiry = 3 if "small" not in strategy_type else 5
    iv = 0.22 if vol_regime == "high" else 0.18  # Realistic NIFTY IV range
    
    # Calculate actual expiry date
    # NSE (NIFTY/Stock options): Weekly expiry = Tuesday
    # BSE (SENSEX): Weekly expiry = Thursday
    # Monthly: Last respective weekday of the month
    from datetime import date, timedelta
    today = date.today()
    # NSE NIFTY weekly = Tuesday (weekday 1)
    days_until_tuesday = (1 - today.weekday()) % 7
    if days_until_tuesday == 0:
        days_until_tuesday = 7  # If today is Tuesday, use next Tuesday
    expiry_date = today + timedelta(days=days_until_tuesday)
    if days_to_expiry > 4:
        expiry_date = expiry_date + timedelta(days=7)  # Next week expiry
    expiry_date_str = expiry_date.strftime("%d %b %Y") + " (Tue)"
    
    # Generate specific trade based on strategy type
    trade = _build_spread_trade(
        strategy_type, spot, expected_move_pts, days_to_expiry, iv, max_risk, capital
    )
    
    if trade:
        trade["expiry_date"] = expiry_date_str
    
    if trade is None:
        return {
            "action": "skip",
            "reason": "Could not construct viable trade within risk limits",
            "conditions": conditions,
            "pattern_result": pattern_result,
        }
    
    # Calculate trading charges (Zerodha)
    charges = _calculate_charges(trade)
    trade["charges"] = charges
    trade["net_max_profit"] = round(trade["max_profit"] - charges["total"], 2)
    trade["net_max_loss"] = round(trade["max_loss"] + charges["total"], 2)
    
    # Build the trade card
    trade_card = {
        "action": "trade",
        "timestamp": None,  # Set by orchestrator
        "direction": direction,
        "confidence": confidence,
        "strategy_type": strategy_type,
        "projected_open": spot,
        "trade": trade,
        "reasoning": _build_reasoning(direction, confidence, conditions, pattern_result),
        "conditions": conditions,
        "pattern_result": pattern_result,
        "risk_check": {
            "max_loss": trade["net_max_loss"],
            "max_loss_pct": round(trade["net_max_loss"] / capital * 100, 2),
            "within_2pct_cap": trade["net_max_loss"] <= max_risk,
            "capital": capital,
        }
    }
    
    return trade_card


def _calculate_charges(trade: dict) -> dict:
    """
    Calculate Zerodha trading charges for an options spread.
    Charges per leg: Brokerage + STT + Exchange + GST + SEBI + Stamp duty
    """
    legs = trade.get("legs", [])
    num_legs = len(legs)
    
    # Brokerage: Rs.20 per order (per leg, entry + exit = 2 orders per leg)
    brokerage = 20 * num_legs * 2  # Entry + Exit for each leg
    
    # GST: 18% on brokerage
    gst = round(brokerage * 0.18, 2)
    
    # STT: 0.0625% on sell-side premium × quantity (on exercise/expiry)
    # Approximate: on the net premium of the spread
    net_premium = trade.get("net_cost", 0) * LOT_SIZE
    stt = round(abs(net_premium) * 0.000625, 2)
    
    # Exchange transaction charges: ~Rs.3.5 per lakh of turnover
    turnover = sum(leg.get("premium_est", 0) for leg in legs) * LOT_SIZE * 2
    exchange_charges = round(turnover * 0.0000345, 2)
    
    # SEBI charges: Rs.10 per crore
    sebi = round(turnover * 0.000001, 2)
    
    # Stamp duty: 0.003% on buy side
    stamp = round(turnover * 0.5 * 0.00003, 2)
    
    total = round(brokerage + gst + stt + exchange_charges + sebi + stamp, 2)
    
    return {
        "brokerage": brokerage,
        "gst": gst,
        "stt": stt,
        "exchange": exchange_charges,
        "sebi": sebi,
        "stamp": stamp,
        "total": total,
        "description": f"Charges: Rs.{total} (Brokerage Rs.{brokerage} + GST + STT + Exchange)"
    }


def _build_spread_trade(strategy_type: str, spot: float, expected_move: float,
                        days_to_expiry: int, iv: float, max_risk: float, capital: float) -> dict:
    """Build a specific spread trade with calculated premiums."""
    
    if "bear_put" in strategy_type:
        # Bear Put Spread: Buy higher PE, Sell lower PE
        width = 200 if "wide" in strategy_type else 100 if "small" not in strategy_type else 50
        
        # Pick strikes that fit within risk budget
        # Start OTM and find affordable combination
        long_strike = round_to_strike(spot - expected_move * 0.5)
        short_strike = long_strike - width
        
        long_premium = estimate_premium(spot, long_strike, days_to_expiry, "put", iv)
        short_premium = estimate_premium(spot, short_strike, days_to_expiry, "put", iv)
        
        net_cost = long_premium - short_premium
        net_cost_total = net_cost * LOT_SIZE
        max_profit = (width - net_cost) * LOT_SIZE
        max_loss = net_cost_total
        
        # Check risk cap
        if max_loss > max_risk:
            # Try smaller width
            width = 50
            short_strike = long_strike - width
            short_premium = estimate_premium(spot, short_strike, days_to_expiry, "put", iv)
            net_cost = long_premium - short_premium
            net_cost_total = net_cost * LOT_SIZE
            max_profit = (width - net_cost) * LOT_SIZE
            max_loss = net_cost_total
            
            if max_loss > max_risk:
                return None
        
        sl_value = net_cost * 0.5  # SL at 50% of premium paid
        
        return {
            "type": "bear_put_spread",
            "legs": [
                {"action": "BUY", "option": "PE", "strike": long_strike, "premium_est": long_premium},
                {"action": "SELL", "option": "PE", "strike": short_strike, "premium_est": short_premium},
            ],
            "net_cost": round(net_cost, 2),
            "net_cost_total": round(net_cost_total, 2),
            "max_profit": round(max_profit, 2),
            "max_loss": round(max_loss, 2),
            "sl_value": round(sl_value * LOT_SIZE, 2),
            "risk_reward": round(max_profit / max_loss, 2) if max_loss > 0 else 0,
            "breakeven": long_strike - net_cost,
            "expiry_days": days_to_expiry,
            "width": width,
        }
    
    elif "bull_call" in strategy_type:
        # Bull Call Spread: Buy lower CE, Sell higher CE
        width = 200 if "wide" in strategy_type else 100 if "small" not in strategy_type else 50
        
        # Pick strikes that fit within risk budget — slightly OTM
        long_strike = round_to_strike(spot + expected_move * 0.5)
        short_strike = long_strike + width
        
        long_premium = estimate_premium(spot, long_strike, days_to_expiry, "call", iv)
        short_premium = estimate_premium(spot, short_strike, days_to_expiry, "call", iv)
        
        net_cost = long_premium - short_premium
        net_cost_total = net_cost * LOT_SIZE
        max_profit = (width - net_cost) * LOT_SIZE
        max_loss = net_cost_total
        
        if max_loss > max_risk:
            width = 50
            short_strike = long_strike + width
            short_premium = estimate_premium(spot, short_strike, days_to_expiry, "call", iv)
            net_cost = long_premium - short_premium
            net_cost_total = net_cost * LOT_SIZE
            max_profit = (width - net_cost) * LOT_SIZE
            max_loss = net_cost_total
            
            if max_loss > max_risk:
                return None
        
        sl_value = net_cost * 0.5
        
        return {
            "type": "bull_call_spread",
            "legs": [
                {"action": "BUY", "option": "CE", "strike": long_strike, "premium_est": long_premium},
                {"action": "SELL", "option": "CE", "strike": short_strike, "premium_est": short_premium},
            ],
            "net_cost": round(net_cost, 2),
            "net_cost_total": round(net_cost_total, 2),
            "max_profit": round(max_profit, 2),
            "max_loss": round(max_loss, 2),
            "sl_value": round(sl_value * LOT_SIZE, 2),
            "risk_reward": round(max_profit / max_loss, 2) if max_loss > 0 else 0,
            "breakeven": long_strike + net_cost,
            "expiry_days": days_to_expiry,
            "width": width,
        }
    
    elif "straddle" in strategy_type:
        # Long Straddle: Buy ATM CE + ATM PE
        atm_strike = round_to_strike(spot)
        
        call_premium = estimate_premium(spot, atm_strike, days_to_expiry, "call", iv)
        put_premium = estimate_premium(spot, atm_strike, days_to_expiry, "put", iv)
        
        total_cost = (call_premium + put_premium) * LOT_SIZE
        max_loss = total_cost  # if NIFTY stays exactly at ATM
        
        if max_loss > max_risk:
            return None
        
        # Breakevens
        upper_be = atm_strike + call_premium + put_premium
        lower_be = atm_strike - call_premium - put_premium
        
        return {
            "type": "long_straddle",
            "legs": [
                {"action": "BUY", "option": "CE", "strike": atm_strike, "premium_est": call_premium},
                {"action": "BUY", "option": "PE", "strike": atm_strike, "premium_est": put_premium},
            ],
            "net_cost": round(call_premium + put_premium, 2),
            "net_cost_total": round(total_cost, 2),
            "max_profit": "unlimited",
            "max_loss": round(max_loss, 2),
            "sl_value": round(max_loss * 0.5, 2),
            "risk_reward": "asymmetric",
            "breakeven": f"{int(lower_be)} / {int(upper_be)}",
            "expiry_days": days_to_expiry,
            "width": 0,
        }
    
    return None


def _build_reasoning(direction: str, confidence: int, conditions: dict, pattern: dict) -> str:
    """Build plain-English reasoning for the trade card."""
    us_change = conditions.get("us_change_pct", 0)
    vix_change = conditions.get("vix_change_pct", 0)
    matching = pattern.get("matching_days", 0)
    sample = pattern.get("sample_description", "")
    
    parts = []
    
    # Global context
    if us_change < -0.5:
        parts.append(f"US markets fell {abs(us_change):.1f}%")
    elif us_change > 0.5:
        parts.append(f"US markets rose {us_change:.1f}%")
    else:
        parts.append("US markets were flat")
    
    if vix_change > 5:
        parts.append(f"VIX spiked {vix_change:.1f}% (fear rising)")
    elif vix_change < -5:
        parts.append(f"VIX dropped {abs(vix_change):.1f}% (fear easing)")
    
    # Historical backing
    parts.append(f"Historical match: {sample}")
    parts.append(f"Confidence: {confidence}% ({matching} similar days found)")
    
    # Direction logic
    if direction == "bullish":
        parts.append("NIFTY historically recovers in these conditions")
    elif direction == "bearish":
        parts.append("NIFTY historically falls further in these conditions")
    
    return ". ".join(parts) + "."


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test with pattern matcher output
    from engine.signals.pattern_matcher import generate_pattern_signal
    
    global_data_path = Path("output/today_global_data.json")
    if global_data_path.exists():
        with open(global_data_path) as f:
            global_data = json.load(f)
        
        # Get pattern result
        pattern_result = generate_pattern_signal(global_data)
        
        # Get projected open
        nifty_data = global_data.get("data", {}).get("gift_nifty")
        projected_open = nifty_data["last_close"] if nifty_data else 24500
        
        # Generate trade card
        trade_card = generate_trade_card(pattern_result, projected_open)
        print(json.dumps(trade_card, indent=2, default=str))
    else:
        print("Run data_fetcher.py first")
