"""
Options Tycoon - Time Machine API Routes

Provides historical replay functionality, allowing traders to step through
past options chain data day-by-day and practice decision-making against
historical scenarios.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data.loader import load_mock_data, get_available_tickers
from engine.greeks import black_scholes_greeks, compute_iv_rank

router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory session storage (keyed by profile_id)
# ---------------------------------------------------------------------------

_sessions: dict[int, dict] = {}


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class TimeMachineStartRequest(BaseModel):
    """Request model for starting a time machine replay session."""
    profile_id: int
    ticker: str
    start_date: str  # ISO date string (YYYY-MM-DD)
    end_date: str    # ISO date string (YYYY-MM-DD)
    mode: str = "manual"  # "auto" or "manual"


# ---------------------------------------------------------------------------
# GET /timemachine/windows — List available historical data windows
# ---------------------------------------------------------------------------


@router.get("/timemachine/windows")
def list_windows():
    """
    List available historical data windows from mock data files.

    Scans each ticker's mock data to determine available expiration date ranges,
    which serve as replay windows.
    """
    tickers = get_available_tickers()
    windows = []

    for ticker in tickers:
        data = load_mock_data(ticker)
        if data is None or "expirations" not in data:
            continue

        expirations = data["expirations"]
        if not expirations:
            continue

        dates = sorted(exp["date"] for exp in expirations)
        windows.append({
            "ticker": ticker,
            "underlying_price": data.get("underlying_price"),
            "available_dates": dates,
            "start_date": dates[0],
            "end_date": dates[-1],
            "expiration_count": len(dates),
        })

    return {"windows": windows, "total_tickers": len(windows)}


# ---------------------------------------------------------------------------
# POST /timemachine/start — Start a replay session
# ---------------------------------------------------------------------------


@router.post("/timemachine/start")
def start_session(request: TimeMachineStartRequest):
    """
    Start a time machine replay session for a given ticker and date range.

    Loads the mock data and builds a list of trading days within the
    requested window. Stores session state in memory.
    """
    if request.mode not in ("auto", "manual"):
        raise HTTPException(
            status_code=400,
            detail="mode must be 'auto' or 'manual'"
        )

    # Load mock data for the ticker
    data = load_mock_data(request.ticker)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No mock data available for ticker '{request.ticker}'"
        )

    if "expirations" not in data or not data["expirations"]:
        raise HTTPException(
            status_code=404,
            detail=f"No expiration data available for ticker '{request.ticker}'"
        )

    # Parse date range
    try:
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD."
        )

    if start_date >= end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be before end_date"
        )

    # Build trading days (weekdays only) within the date range
    trading_days = _generate_trading_days(start_date, end_date)

    if not trading_days:
        raise HTTPException(
            status_code=400,
            detail="No trading days found in the specified date range"
        )

    # Find applicable expirations within or after the date range
    applicable_expirations = [
        exp for exp in data["expirations"]
        if exp["date"] >= request.start_date
    ]

    if not applicable_expirations:
        applicable_expirations = data["expirations"]

    # Build initial session state
    session = {
        "profile_id": request.profile_id,
        "ticker": request.ticker,
        "underlying_price": data.get("underlying_price"),
        "mode": request.mode,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "trading_days": [d.isoformat() for d in trading_days],
        "current_day_index": 0,
        "current_date": trading_days[0].isoformat(),
        "total_days": len(trading_days),
        "remaining_days": len(trading_days) - 1,
        "expirations": applicable_expirations,
        "started_at": datetime.utcnow().isoformat(),
        "status": "active",
    }

    # Store session keyed by profile_id
    _sessions[request.profile_id] = session

    # Get chain data for the initial day
    chain_data = _get_chain_for_day(session, trading_days[0])

    return {
        "session": {
            "profile_id": request.profile_id,
            "ticker": request.ticker,
            "mode": request.mode,
            "current_date": session["current_date"],
            "total_days": session["total_days"],
            "remaining_days": session["remaining_days"],
            "status": "active",
        },
        "chain_data": chain_data,
    }


# ---------------------------------------------------------------------------
# POST /timemachine/advance — Advance one day
# ---------------------------------------------------------------------------


@router.post("/timemachine/advance")
def advance_day(profile_id: int):
    """
    Advance the replay session by one trading day.

    Returns updated chain data for the new day.
    """
    if profile_id not in _sessions:
        raise HTTPException(
            status_code=404,
            detail="No active time machine session found for this profile"
        )

    session = _sessions[profile_id]

    if session["status"] != "active":
        raise HTTPException(
            status_code=400,
            detail="Session is not active (already completed)"
        )

    current_index = session["current_day_index"]
    total_days = session["total_days"]

    # Check if we can advance
    if current_index >= total_days - 1:
        session["status"] = "completed"
        return {
            "message": "Replay session completed — no more trading days",
            "session": {
                "profile_id": profile_id,
                "ticker": session["ticker"],
                "current_date": session["current_date"],
                "total_days": total_days,
                "remaining_days": 0,
                "status": "completed",
            },
            "chain_data": None,
        }

    # Advance to next day
    new_index = current_index + 1
    session["current_day_index"] = new_index
    session["current_date"] = session["trading_days"][new_index]
    session["remaining_days"] = total_days - new_index - 1

    # Get chain data for the new day
    current_date = datetime.strptime(
        session["current_date"], "%Y-%m-%d"
    ).date()
    chain_data = _get_chain_for_day(session, current_date)

    return {
        "session": {
            "profile_id": profile_id,
            "ticker": session["ticker"],
            "current_date": session["current_date"],
            "day_number": new_index + 1,
            "total_days": total_days,
            "remaining_days": session["remaining_days"],
            "progress_pct": round((new_index + 1) / total_days * 100, 1),
            "status": "active",
        },
        "chain_data": chain_data,
    }


# ---------------------------------------------------------------------------
# GET /timemachine/state — Get current replay state
# ---------------------------------------------------------------------------


@router.get("/timemachine/state")
def get_state(profile_id: int):
    """
    Return the current state of the time machine replay session.

    Includes current day, progress percentage, and remaining days.
    """
    if profile_id not in _sessions:
        raise HTTPException(
            status_code=404,
            detail="No active time machine session found for this profile"
        )

    session = _sessions[profile_id]
    current_index = session["current_day_index"]
    total_days = session["total_days"]

    return {
        "profile_id": session["profile_id"],
        "ticker": session["ticker"],
        "mode": session["mode"],
        "current_date": session["current_date"],
        "day_number": current_index + 1,
        "total_days": total_days,
        "remaining_days": session["remaining_days"],
        "progress_pct": round((current_index + 1) / total_days * 100, 1),
        "start_date": session["start_date"],
        "end_date": session["end_date"],
        "started_at": session["started_at"],
        "status": session["status"],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_trading_days(start_date, end_date) -> list:
    """Generate a list of weekday dates between start and end (inclusive)."""
    days = []
    current = start_date
    while current <= end_date:
        # Monday=0 ... Friday=4 are trading days
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _get_chain_for_day(session: dict, current_date) -> dict:
    """
    Get the options chain data applicable for a given trading day.

    Simulates time decay by adjusting Greeks based on days to expiration.
    Uses the nearest expiration that hasn't passed yet.
    """
    expirations = session["expirations"]
    underlying_price = session["underlying_price"]

    # Find the nearest expiration on or after current_date
    applicable_exp = None
    for exp in expirations:
        exp_date = datetime.strptime(exp["date"], "%Y-%m-%d").date()
        if exp_date >= current_date:
            applicable_exp = exp
            break

    # If none found, use the last available expiration
    if applicable_exp is None:
        applicable_exp = expirations[-1]

    exp_date = datetime.strptime(applicable_exp["date"], "%Y-%m-%d").date()
    days_to_expiry = (exp_date - current_date).days
    T = max(days_to_expiry / 365.0, 0.001)  # Time in years

    # Recompute Greeks for each strike based on current time to expiry
    chain_with_greeks = []
    for row in applicable_exp["chain"]:
        strike = row["strike"]
        call_iv = row["call"]["iv"]
        put_iv = row["put"]["iv"]

        # Compute fresh Greeks
        call_greeks = black_scholes_greeks(
            S=underlying_price, K=strike, T=T,
            sigma=call_iv, option_type="call"
        )
        put_greeks = black_scholes_greeks(
            S=underlying_price, K=strike, T=T,
            sigma=put_iv, option_type="put"
        )

        chain_with_greeks.append({
            "strike": strike,
            "days_to_expiry": days_to_expiry,
            "call": {
                "bid": row["call"]["bid"],
                "ask": row["call"]["ask"],
                "last": row["call"]["last"],
                "volume": row["call"]["volume"],
                "oi": row["call"]["oi"],
                "iv": call_iv,
                "delta": call_greeks["delta"],
                "gamma": call_greeks["gamma"],
                "theta": call_greeks["theta"],
                "vega": call_greeks["vega"],
            },
            "put": {
                "bid": row["put"]["bid"],
                "ask": row["put"]["ask"],
                "last": row["put"]["last"],
                "volume": row["put"]["volume"],
                "oi": row["put"]["oi"],
                "iv": put_iv,
                "delta": put_greeks["delta"],
                "gamma": put_greeks["gamma"],
                "theta": put_greeks["theta"],
                "vega": put_greeks["vega"],
            },
        })

    return {
        "ticker": session["ticker"],
        "underlying_price": underlying_price,
        "current_date": current_date.isoformat(),
        "expiration_date": applicable_exp["date"],
        "days_to_expiry": days_to_expiry,
        "chain": chain_with_greeks,
    }
