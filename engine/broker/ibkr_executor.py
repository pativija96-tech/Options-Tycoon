"""
IBKR Executor — Places QQQ Iron Condor orders via Interactive Brokers API.

Uses ib_insync library for async IBKR TWS/Gateway connection.
Places a 4-leg combo (BAG) order as a single limit order at midpoint.

Requirements:
  - pip install ib_insync
  - IBKR TWS or Gateway running (or IBKR Cloud Gateway)
  - Account with options trading permissions

Usage:
    from engine.broker.ibkr_executor import execute_qqq_iron_condor
    result = await execute_qqq_iron_condor(spot_price=500.0)
"""

import os
import logging
from datetime import datetime, date, timedelta
from typing import Optional

logger = logging.getLogger("ibkr_executor")

# IBKR connection settings (env vars)
IBKR_HOST = os.environ.get("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.environ.get("IBKR_PORT", "7497"))  # 7497=TWS paper, 7496=TWS live, 4001=Gateway
IBKR_CLIENT_ID = int(os.environ.get("IBKR_CLIENT_ID", "1"))

# QQQ strategy parameters
QQQ_OFFSET = 15      # ±$15 from current price
QQQ_WING = 7         # $7 wing width
QQQ_MULTIPLIER = 100  # Standard US options multiplier


def get_next_expiry() -> str:
    """Get today's date formatted for 0DTE options (YYYYMMDD)."""
    today = date.today()
    return today.strftime("%Y%m%d")


def get_qqq_strikes(spot_price: float) -> dict:
    """Calculate Iron Condor strikes from current QQQ price."""
    # Round to nearest $1
    spot = round(spot_price)
    
    short_call = spot + QQQ_OFFSET
    long_call = short_call + QQQ_WING
    short_put = spot - QQQ_OFFSET
    long_put = short_put - QQQ_WING
    
    return {
        "short_call": short_call,
        "long_call": long_call,
        "short_put": short_put,
        "long_put": long_put,
        "spot": spot,
    }


async def connect_ibkr():
    """Connect to IBKR TWS/Gateway."""
    try:
        from ib_insync import IB
        ib = IB()
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
        logger.info(f"Connected to IBKR at {IBKR_HOST}:{IBKR_PORT}")
        return ib
    except Exception as e:
        logger.error(f"IBKR connection failed: {e}")
        return None


async def get_qqq_price(ib) -> Optional[float]:
    """Get current QQQ price from IBKR."""
    try:
        from ib_insync import Stock
        contract = Stock("QQQ", "SMART", "USD")
        ib.qualifyContracts(contract)
        ticker = ib.reqMktData(contract)
        await ib.sleep(2)  # Wait for data
        price = ticker.marketPrice()
        ib.cancelMktData(contract)
        if price and price > 0:
            return float(price)
        # Fallback to last close
        return float(ticker.close) if ticker.close else None
    except Exception as e:
        logger.error(f"QQQ price fetch failed: {e}")
        return None


async def execute_qqq_iron_condor(spot_price: float = None) -> dict:
    """
    Execute a QQQ Iron Condor via IBKR.
    
    Places a 4-leg combo order as a single BAG order at net credit midpoint.
    
    Returns dict with order status, fill prices, etc.
    """
    from ib_insync import IB, Option, ComboLeg, Contract, LimitOrder
    
    ib = await connect_ibkr()
    if not ib:
        return {"success": False, "error": "Could not connect to IBKR"}
    
    try:
        # Get QQQ price if not provided
        if not spot_price:
            spot_price = await get_qqq_price(ib)
            if not spot_price:
                return {"success": False, "error": "Could not get QQQ price"}
        
        strikes = get_qqq_strikes(spot_price)
        expiry = get_next_expiry()
        
        logger.info(f"QQQ IC: spot=${spot_price}, strikes={strikes}, expiry={expiry}")
        
        # Define the 4 option contracts
        short_call = Option("QQQ", expiry, strikes["short_call"], "C", "SMART")
        long_call = Option("QQQ", expiry, strikes["long_call"], "C", "SMART")
        short_put = Option("QQQ", expiry, strikes["short_put"], "P", "SMART")
        long_put = Option("QQQ", expiry, strikes["long_put"], "P", "SMART")
        
        # Qualify contracts (verify they exist)
        contracts = [short_call, long_call, short_put, long_put]
        qualified = ib.qualifyContracts(*contracts)
        
        if len(qualified) != 4:
            return {"success": False, "error": f"Only {len(qualified)}/4 contracts qualified. Check expiry/strikes."}
        
        # Build combo (BAG) order
        combo = Contract()
        combo.symbol = "QQQ"
        combo.secType = "BAG"
        combo.currency = "USD"
        combo.exchange = "SMART"
        
        combo.comboLegs = [
            ComboLeg(conId=short_call.conId, ratio=1, action="SELL", exchange="SMART"),
            ComboLeg(conId=long_call.conId, ratio=1, action="BUY", exchange="SMART"),
            ComboLeg(conId=short_put.conId, ratio=1, action="SELL", exchange="SMART"),
            ComboLeg(conId=long_put.conId, ratio=1, action="BUY", exchange="SMART"),
        ]
        
        # Get midpoint price for the combo
        ticker = ib.reqMktData(combo)
        await ib.sleep(3)
        
        # Net credit = we receive money (negative price for sell combo)
        bid = ticker.bid if ticker.bid and ticker.bid > 0 else 0
        ask = ticker.ask if ticker.ask and ticker.ask > 0 else 0
        mid = (bid + ask) / 2 if bid and ask else 0.30  # Default ~$0.30 credit
        
        # Place limit order at midpoint (net credit)
        order = LimitOrder("SELL", 1, round(mid, 2))  # SELL combo = collect credit
        
        trade = ib.placeOrder(combo, order)
        await ib.sleep(5)  # Wait for fill
        
        # Check fill status
        if trade.orderStatus.status == "Filled":
            fill_price = trade.orderStatus.avgFillPrice
            result = {
                "success": True,
                "mode": "live",
                "order_id": trade.order.orderId,
                "status": "filled",
                "fill_price": fill_price,
                "credit_received": fill_price * QQQ_MULTIPLIER,
                "strikes": strikes,
                "expiry": expiry,
                "message": f"QQQ IC filled at ${fill_price:.2f} credit (${fill_price*100:.0f} total)",
            }
        elif trade.orderStatus.status in ("Submitted", "PreSubmitted"):
            result = {
                "success": True,
                "mode": "live",
                "order_id": trade.order.orderId,
                "status": "pending",
                "limit_price": mid,
                "strikes": strikes,
                "expiry": expiry,
                "message": f"Order submitted at ${mid:.2f}. Waiting for fill...",
            }
        else:
            result = {
                "success": False,
                "order_id": trade.order.orderId if trade.order else None,
                "status": trade.orderStatus.status,
                "error": f"Order status: {trade.orderStatus.status}",
            }
        
        return result
        
    except Exception as e:
        logger.error(f"IBKR execution failed: {e}")
        return {"success": False, "error": str(e)[:300]}
    
    finally:
        ib.disconnect()


def execute_qqq_sync(spot_price: float = None) -> dict:
    """Synchronous wrapper for use from scheduler/signal engine."""
    import asyncio
    try:
        return asyncio.run(execute_qqq_iron_condor(spot_price))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(execute_qqq_iron_condor(spot_price))
        finally:
            loop.close()
