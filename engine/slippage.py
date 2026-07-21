"""
Slippage cost calculation for options trades.

Computes realistic friction cost as 50% of the bid-ask spread for each leg,
deducted at trade entry to simulate market impact.
"""


def compute_slippage(legs: list, chain_data: dict) -> float:
    """
    Compute slippage cost as 50% of bid-ask spread for each leg.

    Args:
        legs: list of TradeLeg-like dicts/objects with keys:
              contract_type ('call'/'put'), strike, expiration, quantity, action
        chain_data: dict with 'expirations' list, each containing 'date' and 'chain'
                    rows with nested 'call'/'put' dicts holding 'bid' and 'ask' prices.

    Returns:
        Total slippage cost (float, always >= 0), rounded to 2 decimal places.
    """
    total_slippage = 0.0

    for leg in legs:
        # Support both dict-like and object-like access
        contract_type = _get_attr(leg, "contract_type")
        strike = _get_attr(leg, "strike")
        expiration = _get_attr(leg, "expiration")
        quantity = _get_attr(leg, "quantity")

        contract = _find_contract(chain_data, strike, expiration, contract_type)
        if contract is None:
            # No matching contract found — use 0 spread (no slippage penalty)
            continue

        bid = contract.get("bid", 0)
        ask = contract.get("ask", 0)
        spread = ask - bid

        # Slippage = 50% of spread × absolute quantity
        total_slippage += 0.5 * spread * abs(quantity)

    return round(total_slippage, 2)


def _find_contract(chain_data: dict, strike: float, expiration: str, contract_type: str) -> dict | None:
    """
    Find a contract in chain_data matching strike, expiration, and contract_type.

    Args:
        chain_data: dict with 'expirations' list
        strike: strike price to match
        expiration: expiration date string (ISO format)
        contract_type: 'call' or 'put'

    Returns:
        dict with 'bid' and 'ask' keys, or None if not found.
    """
    expirations = chain_data.get("expirations", [])

    for exp in expirations:
        if exp.get("date") != expiration:
            continue
        for row in exp.get("chain", []):
            if row.get("strike") == strike:
                # Return the call or put sub-dict
                return row.get(contract_type)

    return None


def _get_attr(obj, key):
    """Get attribute from dict-like or object-like source."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)
