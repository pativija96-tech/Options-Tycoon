"""
Kite Executor — NIFTY Iron Condor auto-execution via Zerodha Kite API.

EXECUTION PIPELINE:
1. Validate Kite session is authenticated
2. Build 4-leg order list from signal card
3. Place BUY legs first (wings/hedges) — this activates hedge margin benefit
4. Place SELL legs after (shorts) — margin reduced because hedges are in place
5. If any BUY leg fails → abort all SELL legs (never naked short)
6. Return order results + Telegram notification

MARGIN LOGIC:
- Individual naked SELL = ~₹1.6L margin
- SELL with hedge already in position = ~₹35K margin (hedge benefit)
- BUY-first ordering ensures hedge benefit is always applied

PRODUCT TYPE:
- NRML (default): Positional, holds to Tuesday expiry
- MIS: Intraday, auto-squares off at 3:25 PM IST

PHASE MODEL:
- Phase 1: 1 lot (65 qty) — slippage discovery (5 trades)
- Phase 2: 1 lot (65 qty) — validation (10 trades)
- Phase 3: 2 lots (130 qty) — full size, ongoing
"""

import os
import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger("kite_executor")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

PHASES = {
    1: {"name": "Phase 1: Discovery", "lots": 1, "quantity": 65, "max_trades": 5},
    2: {"name": "Phase 2: Validation", "lots": 1, "quantity": 65, "max_trades": 10},
    3: {"name": "Phase 3: Full Size", "lots": 2, "quantity": 130, "max_trades": None},
}

CURRENT_PHASE = int(os.environ.get("TRADING_PHASE", "1"))


def get_phase_config() -> dict:
    """Get current phase configuration."""
    phase = PHASES.get(CURRENT_PHASE, PHASES[1]).copy()
    phase["current_phase"] = CURRENT_PHASE
    return phase


# ─────────────────────────────────────────────────────────────────────────────
# SYMBOL BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def get_expiry_symbol_format(strike: int, option_type: str) -> str:
    """
    Build Kite trading symbol for NIFTY weekly options.

    Format: NIFTY{YY}{MON}{Strike}{CE/PE}
    Example: NIFTY26AUG24850CE

    Uses the EXPIRY date's month (next Tuesday), not today's month.
    Critical for end-of-month trades where expiry falls in next month.
    """
    from datetime import datetime, timezone, timedelta as td

    ist = timezone(td(hours=5, minutes=30))
    today = datetime.now(ist).date()

    # Next Tuesday (NIFTY weekly expiry day)
    days_until_tuesday = (1 - today.weekday()) % 7
    if days_until_tuesday == 0:
        days_until_tuesday = 7
    expiry_date = today + td(days=days_until_tuesday)

    yy = str(expiry_date.year)[2:]  # "26"
    month_names = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                   "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    mon = month_names[expiry_date.month]

    return f"NIFTY{yy}{mon}{strike}{option_type}"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN EXECUTION FUNCTION (single entry point — no duplicates)
# ─────────────────────────────────────────────────────────────────────────────

def execute_iron_condor(signal: dict) -> dict:
    """
    Execute a 4-leg NIFTY Iron Condor on Zerodha via Kite Connect API.

    ORDER SEQUENCE (critical for margin):
    1. BUY 24250 PE  (long put wing)
    2. BUY 24950 CE  (long call wing)
    3. SELL 24350 PE  (short put — hedge already exists → reduced margin)
    4. SELL 24850 CE  (short call — hedge already exists → reduced margin)

    If any BUY fails → all SELL legs are skipped (no naked shorts ever).

    Args:
        signal: Trade card dict from simple_ic_engine.generate_daily_signal()

    Returns:
        dict with success, order details, and execution summary
    """
    from engine.broker.kite_auth import is_authenticated, get_kite_client

    # ── Pre-flight checks ──
    if not is_authenticated():
        return {"success": False, "error": "Kite not authenticated. Login to Zerodha first."}

    kite = get_kite_client()
    if not kite:
        return {"success": False, "error": "Could not get Kite client instance."}

    trade = signal.get("trade", {})
    legs = trade.get("legs", [])
    if len(legs) != 4:
        return {"success": False, "error": f"Expected 4 legs in signal, got {len(legs)}"}

    phase = get_phase_config()
    quantity = phase["quantity"]
    product = os.environ.get("KITE_PRODUCT_TYPE", "NRML")

    # ── Build order list ──
    orders = []
    for leg in legs:
        symbol = get_expiry_symbol_format(leg["strike"], leg["option"])
        orders.append({
            "tradingsymbol": symbol,
            "transaction_type": leg["action"],  # "BUY" or "SELL"
            "quantity": quantity,
            "product": product,
            "strike": leg["strike"],
            "option": leg["option"],
        })

    # ── Sort: BUY first, SELL second (hedge margin benefit) ──
    buy_legs = [o for o in orders if o["transaction_type"] == "BUY"]
    sell_legs = [o for o in orders if o["transaction_type"] == "SELL"]
    execution_order = buy_legs + sell_legs

    logger.info(
        f"NIFTY IC Execution | {quantity} qty | {product} | "
        f"BUY×{len(buy_legs)} then SELL×{len(sell_legs)}"
    )

    # ── Execute legs sequentially ──
    results = []
    buy_failed = False

    for order in execution_order:
        # Safety: if a BUY (hedge) failed, never place naked SELL
        if buy_failed and order["transaction_type"] == "SELL":
            results.append({
                "leg": f"{order['transaction_type']} {order['strike']} {order['option']}",
                "symbol": order["tradingsymbol"],
                "order_id": None,
                "status": "skipped",
                "error": "Aborted — hedge leg failed",
            })
            logger.warning(f"SKIP {order['tradingsymbol']} — hedge failed, no naked short")
            continue

        try:
            order_id = kite.place_order(
                variety="regular",
                exchange="NFO",
                tradingsymbol=order["tradingsymbol"],
                transaction_type=order["transaction_type"],
                quantity=order["quantity"],
                order_type="MARKET",
                product=order["product"],
            )
            results.append({
                "leg": f"{order['transaction_type']} {order['strike']} {order['option']}",
                "symbol": order["tradingsymbol"],
                "order_id": order_id,
                "status": "placed",
                "error": None,
            })
            logger.info(f"✓ {order['tradingsymbol']} {order['transaction_type']} → {order_id}")

        except Exception as e:
            error_msg = str(e)[:300]
            results.append({
                "leg": f"{order['transaction_type']} {order['strike']} {order['option']}",
                "symbol": order["tradingsymbol"],
                "order_id": None,
                "status": "failed",
                "error": error_msg,
            })
            logger.error(f"✗ {order['tradingsymbol']} — {error_msg}")
            if order["transaction_type"] == "BUY":
                buy_failed = True

    # ── Summary ──
    placed = sum(1 for r in results if r["status"] == "placed")
    failed = sum(1 for r in results if r["status"] == "failed")
    skipped = sum(1 for r in results if r["status"] == "skipped")

    success = failed == 0 and skipped == 0

    if failed > 0:
        logger.error(f"⚠️ PARTIAL FILL: {placed} placed, {failed} failed, {skipped} skipped")

    return {
        "success": success,
        "mode": "live",
        "product": product,
        "phase": phase["name"],
        "quantity": quantity,
        "placed": placed,
        "failed": failed,
        "skipped": skipped,
        "orders": results,
        "message": (
            f"All 4 legs placed successfully" if success
            else f"PARTIAL: {placed}/4 placed, {failed} failed, {skipped} skipped — check Kite app"
        ),
    }


# Keep old name as alias for backward compatibility with routes/live.py
execute_iron_condor_basket = execute_iron_condor


# ─────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def get_order_fills(order_ids: list) -> dict:
    """Get actual fill prices for placed orders (for slippage measurement)."""
    from engine.broker.kite_auth import is_authenticated, get_kite_client

    if not is_authenticated():
        return {"success": False, "error": "Not authenticated"}

    kite = get_kite_client()
    if not kite:
        return {"success": False, "error": "No Kite client"}

    try:
        all_orders = kite.orders()
        fills = {}
        for oid in order_ids:
            matching = [o for o in all_orders if str(o.get("order_id")) == str(oid)]
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
