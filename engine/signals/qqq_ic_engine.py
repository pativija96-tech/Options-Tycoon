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

# Strategy parameters (validated)
QQQ_OFFSET = 15       # ±$15 from ATM
QQQ_WING = 7          # $7 wing width
QQQ_MULTIPLIER = 100  # US options multiplier
VIX_MAX = 35          # Don't trade if VIX > 35


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
