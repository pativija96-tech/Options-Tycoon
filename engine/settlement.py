"""
Options Tycoon - Settlement Engine

Auto-settles expired options positions at intrinsic value.
ITM options settle at intrinsic value, OTM options settle at zero.
Updates portfolio balance with realized P&L on settlement.
"""

import json
from datetime import datetime, timezone, date

from db.database import get_connection
from data.loader import load_mock_data


def settle_position(trade_id: int, underlying_price: float, db_path: str | None = None) -> dict:
    """
    Settle a single trade position at expiration.

    Computes intrinsic value for each leg based on the underlying price:
      - Buy call: max(0, S - K) * qty
      - Buy put: max(0, K - S) * qty
      - Sell call: -max(0, S - K) * qty (liability)
      - Sell put: -max(0, K - S) * qty (liability)

    Updates the trade record with exit_price, realized_pnl, status='settled',
    and credits the exit_value back to the profile balance.

    Args:
        trade_id: ID of the trade to settle.
        underlying_price: Current price of the underlying asset.
        db_path: Optional database path override (for testing).

    Returns:
        dict of the settled trade record.

    Raises:
        ValueError: If trade not found or already settled/closed.
    """
    conn = get_connection(db_path)
    try:
        # Fetch the trade record
        trade = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()

        if trade is None:
            raise ValueError(f"Trade {trade_id} not found")

        if trade["status"] != "open":
            raise ValueError(f"Trade {trade_id} is not open (status: {trade['status']})")

        # Parse legs JSON
        legs = json.loads(trade["legs"])

        # Compute intrinsic value for each leg
        exit_value = 0.0
        for leg in legs:
            strike = leg["strike"]
            quantity = abs(leg["quantity"])
            contract_type = leg["contract_type"]
            action = leg["action"]

            if contract_type == "call":
                intrinsic = max(0.0, underlying_price - strike) * quantity
            else:  # put
                intrinsic = max(0.0, strike - underlying_price) * quantity

            # Sell legs represent a liability (negative value)
            if action == "sell":
                intrinsic = -intrinsic

            exit_value += intrinsic

        # Compute realized P&L
        entry_price = trade["entry_price"]
        realized_pnl = round(exit_value - entry_price, 2)
        exit_value = round(exit_value, 2)

        # Update trade record
        closed_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """UPDATE trades SET
                status = 'settled',
                exit_price = ?,
                realized_pnl = ?,
                closed_at = ?
            WHERE id = ?""",
            (exit_value, realized_pnl, closed_at, trade_id),
        )

        # Update profile balance: credit exit_value back
        conn.execute(
            "UPDATE profiles SET balance = balance + ? WHERE id = ?",
            (exit_value, trade["profile_id"]),
        )

        conn.commit()

        # Fetch and return the updated trade record
        updated_trade = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()

        return dict(updated_trade)

    finally:
        conn.close()


def settle_expired_positions(db_path: str | None = None) -> list[dict]:
    """
    Settle all open positions that have reached or passed their expiration date.

    Queries all trades with status='open' and expiration_date <= today,
    loads the underlying price from mock data, and settles each position.

    Args:
        db_path: Optional database path override (for testing).

    Returns:
        List of settled trade record dicts.
    """
    conn = get_connection(db_path)
    try:
        today_str = date.today().isoformat()

        # Find all expired open positions
        expired_trades = conn.execute(
            """SELECT * FROM trades
               WHERE status = 'open' AND expiration_date <= ?
               ORDER BY opened_at ASC""",
            (today_str,),
        ).fetchall()

    finally:
        conn.close()

    settled = []
    for trade in expired_trades:
        # Load underlying price from mock data
        ticker = trade["ticker"]
        mock_data = load_mock_data(ticker)

        if mock_data is None:
            # Skip if no market data available for this ticker
            continue

        underlying_price = mock_data.get("underlying_price")
        if underlying_price is None:
            continue

        # Settle the position
        settled_trade = settle_position(trade["id"], underlying_price, db_path)
        settled.append(settled_trade)

    return settled


def auto_settle_expired(db_path: str | None = None) -> None:
    """
    Find all open positions past expiration and settle them.

    Called on startup to clean up any expired positions that weren't
    settled during normal operation (e.g., server was down over expiry).

    Uses the existing settle_position() logic for proper intrinsic value
    calculation rather than random factors.
    """
    conn = get_connection(db_path)
    try:
        today_str = date.today().isoformat()

        expired = conn.execute(
            """SELECT * FROM trades
               WHERE status = 'open' AND expiration_date <= ?
               ORDER BY opened_at ASC""",
            (today_str,),
        ).fetchall()
    finally:
        conn.close()

    if not expired:
        return

    settled_count = 0
    for trade in expired:
        ticker = trade["ticker"]
        mock_data = load_mock_data(ticker)

        if mock_data is None:
            continue

        underlying_price = mock_data.get("underlying_price")
        if underlying_price is None:
            continue

        try:
            settle_position(trade["id"], underlying_price, db_path)
            settled_count += 1
        except ValueError:
            # Already settled or other issue, skip
            continue

    if settled_count:
        print(f"[SETTLEMENT] Settled {settled_count} expired position(s)")
