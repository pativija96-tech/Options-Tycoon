"""
Options Tycoon - Trading Routes

Handles trade execution, position management, and trade journal.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from db.database import get_connection
from db.models import JournalUpdate, TradeCloseRequest, TradeRequest
from data.loader import load_mock_data
from engine.slippage import compute_slippage
from engine.risk_guards import check_risk_gate, check_iv_crush, check_penalty_active

router = APIRouter()


# --- Risk Check Endpoint ---


@router.get("/risk-check/{profile_id}")
def check_risk_gates(profile_id: int, position_pct: float = 0, ticker: str = "", expiry: str = ""):
    """
    Pre-trade risk check: returns observational warnings for the frontend.
    
    Checks:
    1. Position size vs portfolio balance (risk gate)
    2. Earnings proximity (IV crush)
    3. Active penalty (reduced allocation)
    
    Returns list of warning objects. Does NOT block the trade.
    """
    conn = get_connection()
    try:
        # Verify profile exists
        profile = conn.execute(
            "SELECT * FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")

        balance = profile["balance"]
        warnings = []

        # Check risk gate (position > 5%)
        if position_pct > 0 and balance > 0:
            max_loss = (position_pct / 100.0) * balance
            rg = check_risk_gate(position_pct, balance, max_loss)
            if rg:
                warnings.append(rg)

        # Check IV crush (earnings within 48h of expiry)
        if ticker and expiry:
            iv = check_iv_crush(ticker, expiry)
            if iv:
                warnings.append(iv)

        # Check penalty (reduced allocation limit)
        pen = check_penalty_active(profile_id)
        if pen:
            warnings.append(pen)

        return {"warnings": warnings}
    finally:
        conn.close()


# --- Trade Execution ---


@router.post("/trades")
def execute_trade(body: TradeRequest):
    """
    Execute a simulated trade (Deploy Credits).

    Validates funds, computes slippage, deducts cost from balance,
    and records the trade with full behavioral state timestamps.
    """
    conn = get_connection()
    try:
        # 1. Verify profile exists and is not locked
        profile = conn.execute(
            "SELECT * FROM profiles WHERE id = ?", (body.profile_id,)
        ).fetchone()
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        if profile["is_locked"]:
            raise HTTPException(
                status_code=400,
                detail={"error": True, "code": "GAME_OVER", "message": "Profile is locked (game over)"},
            )

        # 2. Load options chain for the ticker
        chain_data = load_mock_data(body.ticker.upper())
        if chain_data is None:
            raise HTTPException(
                status_code=404,
                detail=f"No chain data available for {body.ticker.upper()}",
            )

        # 3. Compute slippage
        legs_dicts = [leg.model_dump() for leg in body.legs]
        slippage_cost = compute_slippage(legs_dicts, chain_data)

        # 4. Compute total trade cost
        # Buy legs: pay the ask price; Sell legs: receive the bid price
        trade_cost = 0.0
        for leg in legs_dicts:
            contract = _find_contract_price(
                chain_data, leg["strike"], leg["expiration"], leg["contract_type"]
            )
            if contract is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Contract not found: {leg['contract_type']} {leg['strike']} {leg['expiration']}",
                )
            if leg["action"] == "buy":
                trade_cost += contract["ask"] * abs(leg["quantity"])
            else:  # sell
                trade_cost -= contract["bid"] * abs(leg["quantity"])

        total_cost = trade_cost + slippage_cost

        # 5. Validate sufficient funds
        balance = profile["balance"]
        if total_cost > balance:
            raise HTTPException(
                status_code=400,
                detail={"error": True, "code": "INSUFFICIENT_FUNDS", "message": "Insufficient funds for this trade"},
            )

        # 6. Compute position percentage
        position_pct = round((total_cost / balance) * 100, 2) if balance > 0 else 0

        # 7. Deduct cost from balance
        new_balance = round(balance - total_cost, 2)
        conn.execute(
            "UPDATE profiles SET balance = ? WHERE id = ?",
            (new_balance, body.profile_id),
        )

        # 8. Insert trade record
        trade_executed_at = datetime.now(timezone.utc).isoformat()
        expiration_date = body.legs[0].expiration  # Use first leg's expiration

        cursor = conn.execute(
            """INSERT INTO trades (
                profile_id, ticker, strategy_type, legs, entry_price,
                slippage_cost, position_size, position_pct, status,
                expiration_date, chain_opened_at, trade_executed_at,
                confirmation_proceeded
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)""",
            (
                body.profile_id,
                body.ticker.upper(),
                body.strategy_type,
                json.dumps(legs_dicts),
                total_cost,
                slippage_cost,
                total_cost,
                position_pct,
                expiration_date,
                body.chain_opened_at,
                trade_executed_at,
                1 if body.confirmation_proceeded else 0,
            ),
        )
        trade_id = cursor.lastrowid

        # 9. If balance reaches 0, lock the profile (game over)
        if new_balance <= 0:
            conn.execute(
                "UPDATE profiles SET is_locked = 1 WHERE id = ?",
                (body.profile_id,),
            )

        conn.commit()

        # 10. Return created trade with updated balance
        trade = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()

        result = dict(trade)
        result["updated_balance"] = new_balance

        return result

    finally:
        conn.close()


def _find_contract_price(chain_data: dict, strike: float, expiration: str, contract_type: str) -> dict | None:
    """Find a contract's bid/ask in chain_data matching strike, expiration, and type.
    
    If the exact expiration isn't found, uses the nearest available expiration.
    Uses approximate strike matching (within 0.5) to handle float precision.
    """
    expirations = chain_data.get("expirations", [])
    if not expirations:
        return None

    # Try exact expiration match first
    target_exp = None
    for exp in expirations:
        if exp.get("date") == expiration:
            target_exp = exp
            break

    # If no exact match, use the first (nearest) expiration
    if target_exp is None:
        target_exp = expirations[0]

    # Search for strike with approximate matching
    for row in target_exp.get("chain", []):
        row_strike = row.get("strike", 0)
        if abs(row_strike - strike) < 0.5:
            return row.get(contract_type)

    return None


# --- Trade Journal ---


@router.put("/trades/{trade_id}/journal")
def update_trade_journal(trade_id: int, body: JournalUpdate):
    """
    Update or set the journal note for a trade.
    Accepts notes up to 1000 characters (enforced by Pydantic model).
    Returns the updated trade record.
    """
    conn = get_connection()
    try:
        # Check trade exists
        row = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Trade not found")

        # Update journal note
        conn.execute(
            "UPDATE trades SET journal_note = ? WHERE id = ?",
            (body.note, trade_id),
        )
        conn.commit()

        # Fetch updated record
        updated = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()

        return dict(updated)
    finally:
        conn.close()


# --- Trade Listing ---


@router.get("/trades/{profile_id}")
def get_trades(profile_id: int):
    """
    Get all trade records for a given profile.
    Returns 404 if the profile doesn't exist.
    """
    conn = get_connection()
    try:
        # Verify profile exists
        profile = conn.execute(
            "SELECT id FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")

        rows = conn.execute(
            "SELECT * FROM trades WHERE profile_id = ? ORDER BY opened_at DESC",
            (profile_id,),
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        conn.close()


# --- Position Tracker ---


def _compute_leg_current_value(leg: dict, chain_data: dict) -> float | None:
    """
    Compute the current mid-price value of a single leg based on mock data.

    For buy legs: value is how much we could sell them for (mid-price * quantity).
    For sell legs: value is the liability (negative mid-price * quantity).

    Returns None if the contract cannot be found in chain data.
    """
    contract_type = leg.get("contract_type")
    strike = leg.get("strike")
    expiration = leg.get("expiration")
    quantity = leg.get("quantity", 1)
    action = leg.get("action")

    expirations = chain_data.get("expirations", [])
    for exp in expirations:
        if exp.get("date") != expiration:
            continue
        for row in exp.get("chain", []):
            if row.get("strike") == strike:
                contract = row.get(contract_type)
                if contract is None:
                    return None
                bid = contract.get("bid", 0)
                ask = contract.get("ask", 0)
                mid_price = (bid + ask) / 2

                # Buy legs have positive value (we own them)
                # Sell legs have negative value (we owe them)
                if action == "buy":
                    return mid_price * abs(quantity)
                else:
                    return -mid_price * abs(quantity)
    return None


def _compute_position_current_value(trade: dict, chain_data: dict) -> dict:
    """
    Compute the current estimated value of a position from mock mid-prices.

    Returns a dict with:
    - current_value: total current value of all legs
    - leg_breakdown: list of per-leg values
    """
    legs = json.loads(trade["legs"]) if isinstance(trade["legs"], str) else trade["legs"]
    leg_breakdown = []
    total_value = 0.0

    for leg in legs:
        leg_value = _compute_leg_current_value(leg, chain_data)
        if leg_value is not None:
            total_value += leg_value
        leg_breakdown.append({
            "contract_type": leg.get("contract_type"),
            "strike": leg.get("strike"),
            "expiration": leg.get("expiration"),
            "quantity": leg.get("quantity"),
            "action": leg.get("action"),
            "current_mid_value": round(leg_value, 2) if leg_value is not None else None,
        })

    return {
        "current_value": round(total_value, 2),
        "leg_breakdown": leg_breakdown,
    }


@router.get("/positions/{profile_id}")
def get_positions(profile_id: int):
    """
    Get all open positions for a profile with unrealized P&L.

    Returns entry_price, current estimated value (from mock mid-prices),
    unrealized P&L per position, and total unrealized P&L across all positions.
    Returns 404 if the profile doesn't exist.
    """
    conn = get_connection()
    try:
        # Verify profile exists
        profile = conn.execute(
            "SELECT id FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")

        # Fetch all open trades for this profile
        rows = conn.execute(
            "SELECT * FROM trades WHERE profile_id = ? AND status = 'open' ORDER BY opened_at DESC",
            (profile_id,),
        ).fetchall()

        positions = []
        total_unrealized_pnl = 0.0

        for row in rows:
            trade = dict(row)
            ticker = trade["ticker"]
            entry_price = trade["entry_price"]

            # Load current chain data for the ticker
            chain_data = load_mock_data(ticker)
            if chain_data is None:
                # No chain data available — cannot compute current value
                positions.append({
                    **trade,
                    "current_value": None,
                    "unrealized_pnl": None,
                    "leg_breakdown": [],
                })
                continue

            # Compute current value from mid-prices
            valuation = _compute_position_current_value(trade, chain_data)
            current_value = valuation["current_value"]
            unrealized_pnl = round(current_value - entry_price, 2)
            total_unrealized_pnl += unrealized_pnl

            # Update max_unrealized_pnl if current unrealized P&L is higher
            max_unrealized_pnl = trade.get("max_unrealized_pnl") or 0.0
            if unrealized_pnl > max_unrealized_pnl:
                max_unrealized_pnl = unrealized_pnl
                conn.execute(
                    "UPDATE trades SET max_unrealized_pnl = ? WHERE id = ?",
                    (max_unrealized_pnl, trade["id"]),
                )

            positions.append({
                **trade,
                "current_value": current_value,
                "unrealized_pnl": unrealized_pnl,
                "max_unrealized_pnl": max_unrealized_pnl,
                "leg_breakdown": valuation["leg_breakdown"],
            })

        conn.commit()

        return {
            "profile_id": profile_id,
            "positions": positions,
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
        }
    finally:
        conn.close()


@router.post("/positions/{trade_id}/close")
def close_position(trade_id: int, body: TradeCloseRequest):
    """
    Manually close a position with outcome tagging.

    Computes exit value from current mock mid-prices, sets realized P&L,
    updates portfolio balance, and flags impulse early exit if applicable.

    Returns 404 if trade not found, 400 if already closed.
    """
    conn = get_connection()
    try:
        # 1. Find the trade
        trade_row = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        if trade_row is None:
            raise HTTPException(status_code=404, detail="Trade not found")

        trade = dict(trade_row)

        # 2. Check if already closed
        if trade["status"] == "closed":
            raise HTTPException(status_code=400, detail="Position is already closed")

        # 3. Load chain data for exit value computation
        ticker = trade["ticker"]
        chain_data = load_mock_data(ticker)
        if chain_data is None:
            raise HTTPException(
                status_code=400,
                detail=f"No chain data available for {ticker} to compute exit value",
            )

        # 4. Compute exit value from current mid-prices
        valuation = _compute_position_current_value(trade, chain_data)
        exit_value = valuation["current_value"]
        entry_price = trade["entry_price"]
        realized_pnl = round(exit_value - entry_price, 2)

        # 5. Check for impulse early exit
        max_unrealized_pnl = trade.get("max_unrealized_pnl") or 0.0
        is_impulse_early_exit = 0
        if realized_pnl > 0 and max_unrealized_pnl > 0:
            if realized_pnl < 0.25 * max_unrealized_pnl:
                is_impulse_early_exit = 1

        # 6. Update portfolio balance (release capital back: balance += exit_value)
        profile = conn.execute(
            "SELECT * FROM profiles WHERE id = ?", (trade["profile_id"],)
        ).fetchone()
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")

        new_balance = round(profile["balance"] + exit_value, 2)
        conn.execute(
            "UPDATE profiles SET balance = ? WHERE id = ?",
            (new_balance, trade["profile_id"]),
        )

        # 7. Update trade record
        closed_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """UPDATE trades SET
                status = 'closed',
                exit_price = ?,
                realized_pnl = ?,
                closed_at = ?,
                outcome_tag = ?,
                is_impulse_early_exit = ?
            WHERE id = ?""",
            (exit_value, realized_pnl, closed_at, body.outcome_tag, is_impulse_early_exit, trade_id),
        )
        conn.commit()

        # 8. Return the updated trade with close details
        updated_trade = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()

        result = dict(updated_trade)
        result["updated_balance"] = new_balance
        result["is_impulse_early_exit"] = bool(is_impulse_early_exit)
        result["leg_breakdown"] = valuation["leg_breakdown"]

        return result
    finally:
        conn.close()
