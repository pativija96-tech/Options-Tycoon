"""
Black-Scholes Greeks calculator and IV Rank computation.

Provides analytical Greeks (Delta, Gamma, Theta, Vega) for European options
using the Black-Scholes pricing model, plus IV Rank as a percentile measure.
"""

import math
from scipy.stats import norm


def black_scholes_greeks(S, K, T, r=0.05, sigma=0.20, option_type='call'):
    """
    Compute Black-Scholes Greeks for a European option.

    Args:
        S: Current underlying price (must be > 0)
        K: Strike price (must be > 0)
        T: Time to expiration in years (e.g., 30/365 for 30 days)
        r: Risk-free interest rate (default 0.05 for 5%)
        sigma: Implied volatility (e.g., 0.20 for 20%)
        option_type: 'call' or 'put'

    Returns:
        dict with keys: delta, gamma, theta (per day), vega (per 1% IV change)
        All values rounded to 4 decimal places.
    """
    option_type = option_type.lower()

    # Edge case: at expiration (T=0) or no volatility (sigma=0)
    if T <= 0 or sigma <= 0:
        return _greeks_at_expiry(S, K, option_type)

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    # Delta
    if option_type == 'call':
        delta = norm.cdf(d1)
    else:
        delta = norm.cdf(d1) - 1

    # Gamma (same for calls and puts)
    gamma = norm.pdf(d1) / (S * sigma * sqrt_T)

    # Theta (annualized, then converted to per-day)
    if option_type == 'call':
        theta_annual = (
            -(S * norm.pdf(d1) * sigma) / (2 * sqrt_T)
            - r * K * math.exp(-r * T) * norm.cdf(d2)
        )
    else:
        theta_annual = (
            -(S * norm.pdf(d1) * sigma) / (2 * sqrt_T)
            + r * K * math.exp(-r * T) * norm.cdf(-d2)
        )
    theta = theta_annual / 365  # per-day theta

    # Vega (per 1% IV change, i.e., divide by 100)
    vega = S * norm.pdf(d1) * sqrt_T / 100

    return {
        'delta': round(delta, 4),
        'gamma': round(gamma, 4),
        'theta': round(theta, 4),
        'vega': round(vega, 4),
    }


def _greeks_at_expiry(S, K, option_type):
    """
    Return Greeks when T=0 or sigma=0 (no time value remaining).
    At expiry, delta is binary (1 or 0 for ITM/OTM), gamma and vega are 0,
    and theta is 0.
    """
    if option_type == 'call':
        delta = 1.0 if S > K else 0.0
    else:
        delta = -1.0 if S < K else 0.0

    return {
        'delta': round(delta, 4),
        'gamma': round(0.0, 4),
        'theta': round(0.0, 4),
        'vega': round(0.0, 4),
    }


def compute_iv_rank(current_iv, iv_history):
    """
    Compute IV Rank as the percentile of current IV relative to the
    historical IV range.

    Formula: (current_iv - min) / (max - min) * 100

    Args:
        current_iv: Current implied volatility value
        iv_history: List of historical IV values (52-week typically)

    Returns:
        float: IV Rank as percentage (0-100), rounded to 2 decimal places.
        None: If fewer than 20 data points in iv_history.
    """
    if iv_history is None or len(iv_history) < 20:
        return None

    iv_min = min(iv_history)
    iv_max = max(iv_history)

    # If min == max, IV has been flat — rank is 0 (or could be 50, but 0 is safer)
    if iv_max == iv_min:
        return 0.0

    rank = (current_iv - iv_min) / (iv_max - iv_min) * 100
    # Clamp to [0, 100] in case current_iv is outside historical range
    rank = max(0.0, min(100.0, rank))
    return round(rank, 2)
