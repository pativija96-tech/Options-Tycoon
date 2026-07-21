"""
Strategy card templates and strategy builder logic for Options Tycoon.

Provides predefined multi-leg strategy templates (Iron Condor, Bull Call Spread,
Bear Put Spread, Straddle, Strangle), auto-populates legs from current chain data,
and computes combined max profit, max loss, breakeven points, and net debit/credit.
"""

from typing import Optional


# ---------------------------------------------------------------------------
# Strategy Templates
# ---------------------------------------------------------------------------

STRATEGY_TEMPLATES = {
    "iron_condor": {
        "name": "Iron Condor",
        "description": "Sell OTM put + buy further OTM put + sell OTM call + buy further OTM call. Profits from low volatility within a range.",
        "legs": [
            {"contract_type": "put", "action": "buy", "offset": "far_otm_put"},
            {"contract_type": "put", "action": "sell", "offset": "otm_put"},
            {"contract_type": "call", "action": "sell", "offset": "otm_call"},
            {"contract_type": "call", "action": "buy", "offset": "far_otm_call"},
        ],
        "leg_count": 4,
    },
    "bull_call_spread": {
        "name": "Bull Call Spread",
        "description": "Buy call at lower strike, sell call at higher strike. Profits from moderate upward move.",
        "legs": [
            {"contract_type": "call", "action": "buy", "offset": "atm"},
            {"contract_type": "call", "action": "sell", "offset": "otm_call"},
        ],
        "leg_count": 2,
    },
    "bear_put_spread": {
        "name": "Bear Put Spread",
        "description": "Buy put at higher strike, sell put at lower strike. Profits from moderate downward move.",
        "legs": [
            {"contract_type": "put", "action": "buy", "offset": "atm"},
            {"contract_type": "put", "action": "sell", "offset": "otm_put"},
        ],
        "leg_count": 2,
    },
    "straddle": {
        "name": "Straddle",
        "description": "Buy call + buy put at the same ATM strike. Profits from large move in either direction.",
        "legs": [
            {"contract_type": "call", "action": "buy", "offset": "atm"},
            {"contract_type": "put", "action": "buy", "offset": "atm"},
        ],
        "leg_count": 2,
    },
    "strangle": {
        "name": "Strangle",
        "description": "Buy OTM call + buy OTM put at different strikes. Profits from large move, cheaper than straddle.",
        "legs": [
            {"contract_type": "put", "action": "buy", "offset": "otm_put"},
            {"contract_type": "call", "action": "buy", "offset": "otm_call"},
        ],
        "leg_count": 2,
    },
}


# ---------------------------------------------------------------------------
# Leg Generation
# ---------------------------------------------------------------------------

def _find_atm_strike(underlying_price: float, strikes: list[float]) -> float:
    """Find the strike closest to the underlying price (ATM)."""
    return min(strikes, key=lambda s: abs(s - underlying_price))


def _find_otm_call_strike(underlying_price: float, strikes: list[float]) -> float:
    """Find the first OTM call strike (one step above ATM)."""
    otm_strikes = sorted([s for s in strikes if s > underlying_price])
    if otm_strikes:
        return otm_strikes[0]
    # Fallback: use ATM
    return _find_atm_strike(underlying_price, strikes)


def _find_otm_put_strike(underlying_price: float, strikes: list[float]) -> float:
    """Find the first OTM put strike (one step below ATM)."""
    otm_strikes = sorted([s for s in strikes if s < underlying_price], reverse=True)
    if otm_strikes:
        return otm_strikes[0]
    # Fallback: use ATM
    return _find_atm_strike(underlying_price, strikes)


def _find_far_otm_call_strike(underlying_price: float, strikes: list[float]) -> float:
    """Find the second OTM call strike (two steps above ATM)."""
    otm_strikes = sorted([s for s in strikes if s > underlying_price])
    if len(otm_strikes) >= 2:
        return otm_strikes[1]
    if otm_strikes:
        return otm_strikes[0]
    return _find_atm_strike(underlying_price, strikes)


def _find_far_otm_put_strike(underlying_price: float, strikes: list[float]) -> float:
    """Find the second OTM put strike (two steps below ATM)."""
    otm_strikes = sorted([s for s in strikes if s < underlying_price], reverse=True)
    if len(otm_strikes) >= 2:
        return otm_strikes[1]
    if otm_strikes:
        return otm_strikes[0]
    return _find_atm_strike(underlying_price, strikes)


def _resolve_strike(offset: str, underlying_price: float, strikes: list[float]) -> float:
    """Resolve a template offset label to an actual strike price."""
    if offset == "atm":
        return _find_atm_strike(underlying_price, strikes)
    elif offset == "otm_call":
        return _find_otm_call_strike(underlying_price, strikes)
    elif offset == "otm_put":
        return _find_otm_put_strike(underlying_price, strikes)
    elif offset == "far_otm_call":
        return _find_far_otm_call_strike(underlying_price, strikes)
    elif offset == "far_otm_put":
        return _find_far_otm_put_strike(underlying_price, strikes)
    else:
        return _find_atm_strike(underlying_price, strikes)


def generate_strategy_legs(
    strategy_type: str,
    underlying_price: float,
    chain_data: dict,
    expiration: Optional[str] = None,
    quantity: int = 1,
) -> list[dict]:
    """
    Generate strategy legs for a given strategy type using current chain data.

    Args:
        strategy_type: Key from STRATEGY_TEMPLATES (e.g., 'iron_condor', 'straddle')
        underlying_price: Current price of the underlying asset
        chain_data: Chain data dict with 'expirations' list, each containing
                    'date' and 'chain' (list of rows with 'strike', 'call', 'put')
        expiration: Optional specific expiry date string. Uses first available if None.
        quantity: Number of contracts per leg (default 1)

    Returns:
        List of leg dicts with keys: contract_type, action, strike, expiration, quantity,
        bid, ask, mid_price
    """
    template = STRATEGY_TEMPLATES.get(strategy_type)
    if template is None:
        raise ValueError(f"Unknown strategy type: {strategy_type}. "
                         f"Available: {list(STRATEGY_TEMPLATES.keys())}")

    expirations = chain_data.get("expirations", [])
    if not expirations:
        raise ValueError("No expiration data available in chain_data")

    # Select expiration
    if expiration:
        exp_data = next(
            (e for e in expirations if e["date"] == expiration), None
        )
        if exp_data is None:
            raise ValueError(f"Expiration {expiration} not found in chain data")
    else:
        exp_data = expirations[0]

    exp_date = exp_data["date"]
    chain = exp_data.get("chain", [])
    if not chain:
        raise ValueError("No chain rows available for selected expiration")

    # Extract available strikes
    strikes = [row["strike"] for row in chain]

    # Build a lookup: strike -> row
    strike_lookup = {row["strike"]: row for row in chain}

    legs = []
    for leg_template in template["legs"]:
        contract_type = leg_template["contract_type"]
        action = leg_template["action"]
        offset = leg_template["offset"]

        strike = _resolve_strike(offset, underlying_price, strikes)
        row = strike_lookup[strike]

        # Get bid/ask for the specific contract type
        contract_data = row[contract_type]
        bid = contract_data["bid"]
        ask = contract_data["ask"]
        mid_price = round((bid + ask) / 2, 2)

        legs.append({
            "contract_type": contract_type,
            "action": action,
            "strike": strike,
            "expiration": exp_date,
            "quantity": quantity,
            "bid": bid,
            "ask": ask,
            "mid_price": mid_price,
        })

    return legs


# ---------------------------------------------------------------------------
# Strategy Metrics Computation
# ---------------------------------------------------------------------------

def _get_leg_cost(leg: dict) -> float:
    """
    Compute the cost of a single leg from the trader's perspective.

    Buy legs cost the ask price (trader pays).
    Sell legs receive the bid price (trader receives).

    Returns positive for credits (sell), negative for debits (buy).
    """
    if leg["action"] == "buy":
        return -leg["ask"] * leg["quantity"]
    else:  # sell
        return leg["bid"] * leg["quantity"]


def compute_strategy_metrics(legs: list[dict], chain_data: Optional[dict] = None) -> dict:
    """
    Compute combined strategy metrics for multi-leg positions.

    Args:
        legs: List of leg dicts (as returned by generate_strategy_legs),
              each with: contract_type, action, strike, quantity, bid, ask
        chain_data: Optional chain data (reserved for future use with more
                    complex P&L modeling)

    Returns:
        dict with:
            - net_debit_or_credit: Positive = net credit, negative = net debit
            - max_profit: Maximum profit achievable
            - max_loss: Maximum loss (as positive number representing risk)
            - breakeven_points: List of breakeven price points
            - strategy_type_detected: Detected strategy pattern (if recognized)
    """
    if not legs:
        return {
            "net_debit_or_credit": 0.0,
            "max_profit": 0.0,
            "max_loss": 0.0,
            "breakeven_points": [],
            "strategy_type_detected": "empty",
        }

    # Compute net debit/credit
    net = sum(_get_leg_cost(leg) for leg in legs)
    net = round(net, 2)

    # Detect strategy pattern and compute metrics
    strategy_info = _detect_and_compute(legs, net)

    return {
        "net_debit_or_credit": net,
        "max_profit": round(strategy_info["max_profit"], 2),
        "max_loss": round(strategy_info["max_loss"], 2),
        "breakeven_points": [round(bp, 2) for bp in strategy_info["breakeven_points"]],
        "strategy_type_detected": strategy_info["type"],
    }


def _detect_and_compute(legs: list[dict], net: float) -> dict:
    """
    Detect the strategy pattern from legs and compute max profit, max loss,
    and breakeven points.
    """
    # Categorize legs
    buy_calls = [l for l in legs if l["contract_type"] == "call" and l["action"] == "buy"]
    sell_calls = [l for l in legs if l["contract_type"] == "call" and l["action"] == "sell"]
    buy_puts = [l for l in legs if l["contract_type"] == "put" and l["action"] == "buy"]
    sell_puts = [l for l in legs if l["contract_type"] == "put" and l["action"] == "sell"]

    # Iron Condor: sell put + buy put (lower) + sell call + buy call (higher)
    if (len(sell_puts) == 1 and len(buy_puts) == 1 and
            len(sell_calls) == 1 and len(buy_calls) == 1):
        return _compute_iron_condor(buy_puts[0], sell_puts[0], sell_calls[0], buy_calls[0], net)

    # Bull Call Spread: buy call (lower) + sell call (higher)
    if len(buy_calls) == 1 and len(sell_calls) == 1 and not buy_puts and not sell_puts:
        return _compute_bull_call_spread(buy_calls[0], sell_calls[0], net)

    # Bear Put Spread: buy put (higher) + sell put (lower)
    if len(buy_puts) == 1 and len(sell_puts) == 1 and not buy_calls and not sell_calls:
        return _compute_bear_put_spread(buy_puts[0], sell_puts[0], net)

    # Straddle: buy call + buy put at same strike
    if (len(buy_calls) == 1 and len(buy_puts) == 1 and
            not sell_calls and not sell_puts and
            buy_calls[0]["strike"] == buy_puts[0]["strike"]):
        return _compute_straddle(buy_calls[0], buy_puts[0], net)

    # Strangle: buy call + buy put at different strikes
    if (len(buy_calls) == 1 and len(buy_puts) == 1 and
            not sell_calls and not sell_puts and
            buy_calls[0]["strike"] != buy_puts[0]["strike"]):
        return _compute_strangle(buy_calls[0], buy_puts[0], net)

    # Generic/custom: use simple net debit/credit analysis
    return _compute_generic(legs, net)


def _compute_iron_condor(buy_put: dict, sell_put: dict, sell_call: dict, buy_call: dict, net: float) -> dict:
    """
    Iron Condor metrics:
    - Max profit = net credit received
    - Max loss = width of wider spread - net credit
    - Breakevens: sell_put_strike - net_credit, sell_call_strike + net_credit
    """
    net_credit = net  # Should be positive for a properly constructed iron condor

    # Width is the distance between strikes on either side
    put_width = abs(sell_put["strike"] - buy_put["strike"])
    call_width = abs(buy_call["strike"] - sell_call["strike"])
    width = max(put_width, call_width)

    max_profit = max(net_credit, 0.0)
    max_loss = max(width - net_credit, 0.0)

    # Breakeven points
    breakevens = []
    if net_credit > 0:
        breakevens.append(sell_put["strike"] - net_credit)
        breakevens.append(sell_call["strike"] + net_credit)
    else:
        breakevens.append(sell_put["strike"])
        breakevens.append(sell_call["strike"])

    return {
        "type": "iron_condor",
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven_points": sorted(breakevens),
    }


def _compute_bull_call_spread(buy_call: dict, sell_call: dict, net: float) -> dict:
    """
    Bull Call Spread metrics:
    - Net debit = ask of lower strike call - bid of higher strike call
    - Max profit = width - net debit
    - Max loss = net debit
    - Breakeven = lower strike + net debit
    """
    width = abs(sell_call["strike"] - buy_call["strike"])
    net_debit = abs(net)  # net is negative (debit)

    max_profit = max(width - net_debit, 0.0)
    max_loss = net_debit

    breakeven = buy_call["strike"] + net_debit

    return {
        "type": "bull_call_spread",
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven_points": [breakeven],
    }


def _compute_bear_put_spread(buy_put: dict, sell_put: dict, net: float) -> dict:
    """
    Bear Put Spread metrics:
    - Net debit = ask of higher strike put - bid of lower strike put
    - Max profit = width - net debit
    - Max loss = net debit
    - Breakeven = higher strike - net debit
    """
    width = abs(buy_put["strike"] - sell_put["strike"])
    net_debit = abs(net)  # net is negative (debit)

    max_profit = max(width - net_debit, 0.0)
    max_loss = net_debit

    breakeven = buy_put["strike"] - net_debit

    return {
        "type": "bear_put_spread",
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven_points": [breakeven],
    }


def _compute_straddle(buy_call: dict, buy_put: dict, net: float) -> dict:
    """
    Straddle metrics:
    - Net debit = call ask + put ask (both bought)
    - Max profit = unlimited (theoretically)
    - Max loss = net debit (total premium paid)
    - Breakevens = strike ± net debit
    """
    net_debit = abs(net)
    strike = buy_call["strike"]

    # Unlimited upside, so we represent as a very large number
    max_profit = float("inf")
    max_loss = net_debit

    breakevens = [
        strike - net_debit,
        strike + net_debit,
    ]

    return {
        "type": "straddle",
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven_points": sorted(breakevens),
    }


def _compute_strangle(buy_call: dict, buy_put: dict, net: float) -> dict:
    """
    Strangle metrics:
    - Net debit = call ask + put ask (both bought at different strikes)
    - Max profit = unlimited (theoretically)
    - Max loss = net debit (total premium paid)
    - Breakevens = put_strike - net_debit, call_strike + net_debit
    """
    net_debit = abs(net)

    max_profit = float("inf")
    max_loss = net_debit

    breakevens = [
        buy_put["strike"] - net_debit,
        buy_call["strike"] + net_debit,
    ]

    return {
        "type": "strangle",
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven_points": sorted(breakevens),
    }


def _compute_generic(legs: list[dict], net: float) -> dict:
    """
    Generic strategy metrics for unrecognized leg combinations.
    Uses simple net debit/credit as the basis.
    """
    if net >= 0:
        # Net credit position
        max_profit = net
        max_loss = 0.0  # Unknown without full P&L modeling
    else:
        # Net debit position
        max_profit = 0.0  # Unknown without full P&L modeling
        max_loss = abs(net)

    return {
        "type": "custom",
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven_points": [],
    }
