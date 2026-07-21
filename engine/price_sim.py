"""
Live Price Simulation Engine for Options Tycoon.

Computes dynamic option chain prices based on underlying price movement
using delta approximation. This module bridges the static mock chain data
with the real-time simulation engine, producing realistic bid/ask/last
values that move with the underlying.
"""

import random
from typing import Optional


def _estimate_delta(strike: float, underlying: float, option_type: str, iv: float = 0.20) -> float:
    """
    Estimate option delta based on moneyness.

    Uses a simplified approximation based on the relationship between
    strike and underlying price. More accurate than a fixed delta but
    avoids full Black-Scholes computation for speed.

    Args:
        strike: Option strike price
        underlying: Current underlying price
        option_type: 'call' or 'put'
        iv: Implied volatility (used for ATM width estimation)

    Returns:
        Estimated delta value (-1 to 1)
    """
    # Moneyness ratio
    moneyness = (underlying - strike) / underlying

    # ATM band width (roughly 1 standard deviation)
    atm_width = iv * 0.15  # approximate for short-dated options

    if option_type == "call":
        if moneyness > atm_width * 2:
            # Deep ITM call
            return 0.95
        elif moneyness > atm_width:
            # ITM call
            return 0.70 + 0.25 * (moneyness / (atm_width * 2))
        elif moneyness > -atm_width:
            # ATM call
            return 0.45 + 0.25 * ((moneyness + atm_width) / (2 * atm_width))
        elif moneyness > -atm_width * 2:
            # OTM call
            return 0.15 + 0.30 * ((moneyness + atm_width * 2) / (atm_width * 2))
        else:
            # Deep OTM call
            return 0.05
    else:
        # Put delta is call_delta - 1 (for European options)
        call_delta = _estimate_delta(strike, underlying, "call", iv)
        return call_delta - 1.0


def _apply_spread_noise(price: float, spread_pct: float = 0.01) -> tuple[float, float, float]:
    """
    Generate realistic bid/ask/last from a theoretical mid price.

    Args:
        price: Theoretical option price (mid)
        spread_pct: Bid-ask spread as percentage of price

    Returns:
        Tuple of (bid, ask, last) prices
    """
    if price <= 0:
        return (0.05, 0.10, 0.05)

    # Spread widens for cheaper options
    if price < 10:
        spread = max(0.5, price * 0.05)
    elif price < 50:
        spread = max(1.0, price * 0.02)
    elif price < 200:
        spread = max(2.0, price * 0.015)
    else:
        spread = max(3.0, price * 0.01)

    half_spread = spread / 2
    bid = round(max(0.05, price - half_spread), 2)
    ask = round(price + half_spread, 2)

    # Last traded price is between bid and ask with slight randomness
    last = round(bid + random.uniform(0.3, 0.7) * (ask - bid), 2)

    return (bid, ask, last)


def compute_live_chain(base_chain: dict, current_price: float, original_price: float) -> list:
    """
    Compute a live options chain with prices adjusted for underlying movement.

    Uses delta approximation to shift option prices based on how far the
    underlying has moved from its original (opening) price.

    Args:
        base_chain: The static mock chain data (one expiration's chain list).
                    Each entry: {"strike": N, "call": {...}, "put": {...}}
        current_price: Current simulated underlying price
        original_price: Original underlying price when chain was created

    Returns:
        List of chain rows with updated bid/ask/last values reflecting
        the underlying price movement.

    Example:
        >>> chain = load_mock_data("NIFTY")["expirations"][0]["chain"]
        >>> updated = compute_live_chain(chain, 22550.0, 22450.0)
    """
    price_change = current_price - original_price
    updated_chain = []

    for row in base_chain:
        strike = row["strike"]
        new_row = {"strike": strike, "call": {}, "put": {}}

        # Process call side
        call_data = row["call"]
        call_iv = call_data.get("iv", 0.20)
        call_delta = _estimate_delta(strike, current_price, "call", call_iv)

        # Delta-adjusted price change
        call_price_change = call_delta * price_change

        # Base mid price from original bid/ask
        call_base_mid = (call_data["bid"] + call_data["ask"]) / 2
        new_call_mid = max(0.05, call_base_mid + call_price_change)

        call_bid, call_ask, call_last = _apply_spread_noise(new_call_mid)

        new_row["call"] = {
            "bid": call_bid,
            "ask": call_ask,
            "last": call_last,
            "volume": call_data.get("volume", 0),
            "oi": call_data.get("oi", 0),
            "iv": call_iv,
            "delta": round(call_delta, 4),
        }

        # Process put side
        put_data = row["put"]
        put_iv = put_data.get("iv", 0.20)
        put_delta = _estimate_delta(strike, current_price, "put", put_iv)

        # Delta-adjusted price change (put delta is negative, so price goes up when underlying drops)
        put_price_change = put_delta * price_change

        put_base_mid = (put_data["bid"] + put_data["ask"]) / 2
        new_put_mid = max(0.05, put_base_mid + put_price_change)

        put_bid, put_ask, put_last = _apply_spread_noise(new_put_mid)

        new_row["put"] = {
            "bid": put_bid,
            "ask": put_ask,
            "last": put_last,
            "volume": put_data.get("volume", 0),
            "oi": put_data.get("oi", 0),
            "iv": put_iv,
            "delta": round(put_delta, 4),
        }

        updated_chain.append(new_row)

    return updated_chain


def compute_single_option_price(
    base_price: float,
    strike: float,
    option_type: str,
    current_underlying: float,
    original_underlying: float,
    iv: float = 0.20,
) -> dict:
    """
    Compute updated price for a single option position.

    Useful for P&L calculations on individual positions held in portfolio.

    Args:
        base_price: Original option price when position was opened
        strike: Option strike price
        option_type: 'call' or 'put'
        current_underlying: Current simulated underlying price
        original_underlying: Underlying price when option was purchased
        iv: Implied volatility

    Returns:
        Dict with current_price, bid, ask, last, delta, pnl_per_lot
    """
    price_change = current_underlying - original_underlying
    delta = _estimate_delta(strike, current_underlying, option_type, iv)

    # Delta-adjusted new price
    new_price = max(0.05, base_price + delta * price_change)

    bid, ask, last = _apply_spread_noise(new_price)

    return {
        "current_price": round(new_price, 2),
        "bid": bid,
        "ask": ask,
        "last": last,
        "delta": round(delta, 4),
        "price_change": round(new_price - base_price, 2),
        "pnl_per_lot": round((new_price - base_price), 2),
    }
