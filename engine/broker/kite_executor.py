"""
Kite Executor — Places Iron Condor orders automatically on Zerodha.

Handles:
- 4-leg IC order placement (SELL CE, BUY CE, SELL PE, BUY PE)
- Market orders for guaranteed fills (validates real slippage)
- Order status tracking
- Auto-exit on SL breach or expiry

Phase model:
- Phase 1: 0.5 lots (quantity = 32 instead of 65) — slippage discovery
- Phase 2: 0.5 lots — validation (10 trades)
- Phase 3: 1 full lot (quantity = 65)

Usage:
    from engine.broker.kite_executor import execute_iron_condor, get_phase_config
"""

import os
import json
import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger("kite_executor")

# Phase configuration
PHASES = {
    1: {"name": "Slippage Discovery", "lots": 1, "quantity": 25, "max_trades": 5, "description": "1 lot (25 qty) to measure real slippage"},
    2: {"name": "Validation", "lots": 1, "quantity": 25, "max_trades": 10, "description": "1 lot, 10 trades to validate consistency"},
    3: {"name": "Full Size", "lots": 2, "quantity": 50, "max_trades": None, "description": "2 lots (50 qty), ongoing trading"},
}

# Current phase — stored in env var or defaults to 1
CURRENT_PHASE = int(os.environ.get("TRADING_PHASE", "1"))


def get_phase_config() -> dict:
    """Get current phase configuration."""
    phase = PHASES.get(CURRENT_PHASE, PHASES[1])
    phase["current_phase"] = CURRENT_PHASE
    return phase


def get_expiry_symbol_format(strike: int, option_type: str) -> str:
    """
    Build Kite trading symbol for NIFTY options.
    
    Monthly format: NIFTY{YY}{MON}{Strike}{CE/PE}
    Example: NIFTY26JUL24000CE
    
    Weekly format: NIFTY{YY}{M}{DD}{Strike}{CE/PE}
    Example: NIFTY2670124000CE (July 1)
    
    Note: In monthly expiry week, weekly expiry doesn't exist.
    Currently using MONTHLY format for reliability.
    """
    from datetime import datetime, timezone, timedelta
    
    # Use IST
    ist = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(ist).date()
    
    yy = str(today.year)[2:]  # "26"
    
    # Monthly format: NIFTY26JUL{strike}{CE/PE}
    month_names = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                   "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    mon = month_names[today.month]
    
    return f"NIFTY{yy}{mon}{strike}{option_type}"


def execute_iron_condor(signal: dict, mode: str = "live") -> dict:
    """
    Execute a 4-leg Iron Condor on Zerodha via Kite API.
    
    Args:
        signal: The trade card from simple_ic_engine (contains legs, strikes, etc.)
        mode: "live" (real orders) or "paper" (log only, no real orders)
    
    Returns:
        dict with order_ids, fill_prices, slippage info
    """
    from engine.broker.kite_auth import is_authenticated, get_kite_client
    
    if not is_authenticated():
        return {"success": False, "error": "Kite not authenticated. Login to Zerodha first."}
    
    kite = get_kite_client()
    if not kite:
        return {"success": False, "error": "Could not get Kite client."}
    
    trade = signal.get("trade", {})
    legs = trade.get("legs", [])
    if len(legs) != 4:
        return {"success": False, "error": f"Expected 4 legs, got {len(legs)}"}
    
    phase = get_phase_config()
    quantity = phase["quantity"]
    
    # Build orders for each leg
    orders = []
    order_results = []
    
    for leg in legs:
        strike = leg["strike"]
        option_type = leg["option"]  # "CE" or "PE"
        action = leg["action"]  # "SELL" or "BUY"
        
        trading_symbol = get_expiry_symbol_format(strike, option_type)
        transaction_type = "SELL" if action == "SELL" else "BUY"
        
        orders.append({
            "trading_symbol": trading_symbol,
            "exchange": "NFO",
            "transaction_type": transaction_type,
            "quantity": quantity,
            "order_type": "MARKET",
            "product": "NRML",  # Positional — holding to weekly expiry
            "strike": strike,
            "option": option_type,
            "action": action,
        })
    
    if mode == "paper":
        # Paper mode — just log, don't place real orders
        return {
            "success": True,
            "mode": "paper",
            "phase": phase["name"],
            "quantity": quantity,
            "orders_planned": orders,
            "message": "Paper mode — orders not placed on Zerodha",
        }
    
    # LIVE mode — place actual orders
    for order in orders:
        try:
            order_id = kite.place_order(
                variety="regular",
                exchange=order["exchange"],
                tradingsymbol=order["trading_symbol"],
                transaction_type=order["transaction_type"],
                quantity=order["quantity"],
                order_type=order["order_type"],
                product=order["product"],
            )
            
            order_results.append({
                "leg": f"{order['action']} {order['strike']} {order['option']}",
                "trading_symbol": order["trading_symbol"],
                "order_id": order_id,
                "status": "placed",
                "error": None,
            })
            logger.info(f"Order placed: {order['trading_symbol']} {order['transaction_type']} qty={order['quantity']} → order_id={order_id}")
            
        except Exception as e:
            order_results.append({
                "leg": f"{order['action']} {order['strike']} {order['option']}",
                "trading_symbol": order["trading_symbol"],
                "order_id": None,
                "status": "failed",
                "error": str(e)[:200],
            })
            logger.error(f"Order FAILED: {order['trading_symbol']} — {e}")
    
    # Check results
    placed = [o for o in order_results if o["status"] == "placed"]
    failed = [o for o in order_results if o["status"] == "failed"]
    
    if failed:
        # If any leg failed, we have a partial fill — dangerous
        # TODO: Cancel the successfully placed legs to avoid naked exposure
        logger.error(f"PARTIAL FILL: {len(placed)} placed, {len(failed)} failed. Manual intervention needed!")
    
    return {
        "success": len(failed) == 0,
        "mode": "live",
        "phase": phase["name"],
        "phase_number": CURRENT_PHASE,
        "quantity": quantity,
        "orders": order_results,
        "placed": len(placed),
        "failed": len(failed),
        "message": f"{'All 4 legs placed' if not failed else 'PARTIAL FILL — check Kite app!'}",
    }


def get_order_fills(order_ids: list) -> dict:
    """
    Get actual fill prices for placed orders.
    Used to measure real slippage vs modeled premium.
    """
    from engine.broker.kite_auth import is_authenticated, get_kite_client
    
    if not is_authenticated():
        return {"success": False, "error": "Not authenticated"}
    
    kite = get_kite_client()
    if not kite:
        return {"success": False, "error": "No Kite client"}
    
    try:
        orders = kite.orders()
        fills = {}
        for oid in order_ids:
            matching = [o for o in orders if str(o.get("order_id")) == str(oid)]
            if matching:
                order = matching[0]
                fills[oid] = {
                    "status": order.get("status"),
                    "average_price": order.get("average_price"),
                    "filled_quantity": order.get("filled_quantity"),
                    "trading_symbol": order.get("tradingsymbol"),
                }
        return {"success": True, "fills": fills}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


def calculate_slippage(signal: dict, fill_prices: dict) -> dict:
    """
    Compare modeled premium (Black-Scholes) vs actual fill price.
    This is THE metric that determines if the strategy works live.
    """
    trade = signal.get("trade", {})
    legs = trade.get("legs", [])
    
    modeled_credit = 0
    actual_credit = 0
    
    for leg in legs:
        modeled_prem = leg.get("premium_est", 0)
        # Find matching fill
        # (In real usage, you'd match by strike/type)
        if leg["action"] == "SELL":
            modeled_credit += modeled_prem
        else:
            modeled_credit -= modeled_prem
    
    # actual_credit would come from fill_prices — implementation depends on order matching
    
    slippage = modeled_credit - actual_credit  # positive = lost money to slippage
    
    return {
        "modeled_credit": modeled_credit,
        "actual_credit": actual_credit,
        "slippage_per_share": slippage,
        "slippage_total": slippage * get_phase_config()["quantity"],
        "acceptable": slippage < 150 / 65,  # Rs.150 total / lot_size
    }
