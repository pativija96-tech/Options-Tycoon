"""
Options Tycoon - Risk Guard System

Helper functions called during trade execution to surface observational
warnings. These are NOT API endpoints — they are invoked by the trading
route before a trade is confirmed.

All messaging uses OBSERVATIONAL language only:
- "Your data shows..."
- "This position risks X%..."
- NEVER uses directive language (buy, sell, proceed, stop, recommend).
"""

from datetime import datetime, timedelta
from typing import Optional

from data.loader import load_earnings_calendar
from db.database import get_connection
from engine.behavioral import compute_all_behavioral_metrics


# ---------------------------------------------------------------------------
# Risk Gate: Position size vs portfolio balance
# ---------------------------------------------------------------------------


def check_risk_gate(
    position_pct: float,
    portfolio_balance: float,
    max_loss: float,
) -> Optional[dict]:
    """
    Check if a trade's maximum potential loss exceeds 5% of portfolio balance.

    Uses observational language only — surfaces the data, never directs.

    Args:
        position_pct: The position size as percentage of portfolio.
        portfolio_balance: Current portfolio balance.
        max_loss: Maximum potential loss for this trade.

    Returns:
        Warning dict if max_loss > 5% of portfolio, otherwise None.
    """
    if portfolio_balance <= 0:
        return None

    risk_pct = round((max_loss / portfolio_balance) * 100, 2)

    if risk_pct > 5.0:
        return {
            "type": "risk_gate",
            "message": f"This position risks {risk_pct}% of your portfolio",
            "position_pct": risk_pct,
        }

    return None


# ---------------------------------------------------------------------------
# IV Crush Warning: Earnings proximity check
# ---------------------------------------------------------------------------


def check_iv_crush(ticker: str, trade_expiration: str) -> Optional[dict]:
    """
    Check if an earnings event falls within 48 hours of a trade's expiration.

    IV crush occurs when implied volatility collapses after an earnings
    announcement, dramatically reducing option premiums.

    Args:
        ticker: The underlying ticker symbol (e.g., "INFY").
        trade_expiration: The option expiration date as ISO string (e.g., "2025-02-15").

    Returns:
        Warning dict if earnings fall within 48h of expiration, otherwise None.
    """
    earnings_data = load_earnings_calendar()
    if not earnings_data:
        return None

    try:
        expiration_dt = datetime.fromisoformat(trade_expiration)
    except (ValueError, TypeError):
        return None

    # Window: 48 hours before expiration through expiration
    window_start = expiration_dt - timedelta(hours=48)
    window_end = expiration_dt

    ticker_upper = ticker.upper()

    for entry in earnings_data:
        if entry.get("ticker", "").upper() != ticker_upper:
            continue

        earnings_date_str = entry.get("earnings_date") or entry.get("date")
        if not earnings_date_str:
            continue

        try:
            earnings_dt = datetime.fromisoformat(earnings_date_str)
        except (ValueError, TypeError):
            continue

        if window_start <= earnings_dt <= window_end:
            return {
                "type": "iv_crush",
                "message": f"Earnings event within 48 hours for {ticker_upper}",
                "earnings_date": earnings_date_str,
            }

    return None


# ---------------------------------------------------------------------------
# Penalty Check: Reduced allocation limit
# ---------------------------------------------------------------------------


def check_penalty_active(profile_id: int) -> Optional[dict]:
    """
    Check if a profile currently has an active penalty (reduced limit).

    When a trader repeatedly exceeds the 5% risk threshold, a 24-hour
    penalty period is imposed, reducing the max allocation to 3%.

    Args:
        profile_id: The profile to check.

    Returns:
        Warning dict if penalty is active, otherwise None.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT penalty_until FROM profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()

        if row is None:
            return None

        penalty_until = row["penalty_until"]
        if penalty_until is None:
            return None

        try:
            penalty_dt = datetime.fromisoformat(penalty_until)
        except (ValueError, TypeError):
            return None

        if penalty_dt > datetime.utcnow():
            return {
                "type": "penalty",
                "reduced_limit_pct": 3.0,
                "expires_at": penalty_until,
                "message": "Allocation limit reduced to 3% (penalty active)",
            }

        return None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Apply Penalty: Set 24-hour reduced limit
# ---------------------------------------------------------------------------


def apply_penalty(profile_id: int) -> None:
    """
    Apply a 24-hour penalty to a profile for exceeding the 5% threshold.

    Sets penalty_until = now + 24 hours. During this window, the maximum
    allowed position size is reduced from 5% to 3%.

    Args:
        profile_id: The profile to penalize.
    """
    conn = get_connection()
    try:
        penalty_until = (datetime.utcnow() + timedelta(hours=24)).isoformat()
        conn.execute(
            "UPDATE profiles SET penalty_until = ? WHERE id = ?",
            (penalty_until, profile_id),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pre-Trade State: Behavioral snapshot for display
# ---------------------------------------------------------------------------


def build_pre_trade_state(profile_id: int) -> dict:
    """
    Build a behavioral metrics snapshot for display before trade execution.

    This data is shown to the trader so they can see their current behavioral
    profile before making a decision. Includes the mandatory disclaimer.

    Args:
        profile_id: The profile to build state for.

    Returns:
        Dict with current metrics and disclaimer text.
    """
    metrics = compute_all_behavioral_metrics(profile_id)

    return {
        "discipline_rating": metrics["discipline_rating"],
        "patience_score": metrics["patience_score"],
        "sizing_consistency": metrics["sizing_consistency"],
        "emotional_reactivity": metrics["emotional_reactivity"],
        "current_streak": metrics["current_streak"],
        "longest_streak": metrics["longest_streak"],
        "total_trades": metrics["total_trades"],
        "phase": metrics["phase"],
        "disclaimer": (
            "This is YOUR data. Not advice. All decisions are yours alone."
        ),
    }
