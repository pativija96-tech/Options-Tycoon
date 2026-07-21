"""
Kite Ticker — WebSocket connection for live quotes at execution time.
Connects ONLY when user is on live.html and authenticated.
Disconnects immediately after order placement.

NOTE: Scaffolded. Will connect when Kite subscription is active.
"""

import logging

logger = logging.getLogger(__name__)

# In-memory live quotes cache
_live_quotes = {}


def get_live_quotes(instrument_tokens: list) -> dict:
    """
    Fetch live bid/ask for given instrument tokens.
    
    In production: connects KiteTicker WebSocket, subscribes, 
    waits for first tick, returns prices.
    
    For now: returns None (signals to UI that live data unavailable).
    """
    from engine.broker.kite_auth import is_authenticated, get_access_token
    
    if not is_authenticated():
        return {"available": False, "reason": "Not authenticated"}
    
    # Scaffolded — real implementation:
    # from kiteconnect import KiteTicker
    # kws = KiteTicker(api_key, access_token)
    # kws.on_ticks = on_ticks_handler
    # kws.subscribe(instrument_tokens)
    # ... wait for data ...
    # kws.close()
    
    logger.info(f"Live quotes requested for {len(instrument_tokens)} instruments (not connected)")
    return {
        "available": False,
        "reason": "Kite Ticker not connected. Using estimated prices.",
        "tokens_requested": instrument_tokens,
    }


def lookup_instrument_token(strike: int, option_type: str, expiry: str = None) -> int:
    """
    Look up Kite instrument token for a given NIFTY strike.
    
    In production: downloads instrument list from Kite, 
    maps strike+type+expiry to token.
    
    For now: returns placeholder.
    """
    # Real: kite.instruments("NFO") → filter by tradingsymbol
    logger.debug(f"Instrument lookup: NIFTY {strike} {option_type} (not connected)")
    return 0  # Placeholder
