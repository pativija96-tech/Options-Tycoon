"""
Price Simulation API Router for Options Tycoon.

Provides endpoints to run market simulation sessions using pre-generated
intraday OHLC data. Advances simulated time tick-by-tick to drive the
trading game experience.
"""

import json
import uuid
import random
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(tags=["simulation"])

# --- In-memory session store ---
_sessions: dict[str, dict] = {}

# Path to intraday data directory
INTRADAY_DIR = Path(__file__).parent.parent / "data" / "mock" / "intraday"


class SimulationStartRequest(BaseModel):
    profile_id: int
    ticker: str


class SimulationStartResponse(BaseModel):
    session_id: str
    ticker: str
    current_time: str
    current_price: float
    session_end: str


class TickResponse(BaseModel):
    current_time: str
    current_price: float
    tick: dict
    session_active: bool
    message: Optional[str] = None


class SessionStateResponse(BaseModel):
    session_id: str
    ticker: str
    current_time: str
    current_price: float
    session_high: float
    session_low: float
    ticks_elapsed: int
    ticks_remaining: int
    session_active: bool


def _find_intraday_files(ticker: str) -> list[Path]:
    """Find all intraday data files for a given ticker."""
    if not INTRADAY_DIR.exists():
        return []
    pattern = f"{ticker.upper()}_day*.json"
    return sorted(INTRADAY_DIR.glob(pattern))


def _load_intraday_data(file_path: Path) -> dict:
    """Load and parse an intraday JSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.post("/simulation/start", response_model=SimulationStartResponse)
async def start_simulation(request: SimulationStartRequest):
    """
    Start a new market simulation session.

    Picks a random intraday file for the given ticker and initializes
    a new session at market open (09:15).
    """
    ticker = request.ticker.upper()

    # Find available intraday files for the ticker
    files = _find_intraday_files(ticker)
    if not files:
        raise HTTPException(
            status_code=404,
            detail=f"No intraday data available for ticker: {ticker}"
        )

    # Pick a random file
    chosen_file = random.choice(files)
    data = _load_intraday_data(chosen_file)

    session_id = str(uuid.uuid4())
    opening_price = data["opening_price"]

    # Initialize session state
    _sessions[session_id] = {
        "session_id": session_id,
        "profile_id": request.profile_id,
        "ticker": ticker,
        "data": data,
        "ticks": data["ticks"],
        "current_tick_index": 0,
        "current_price": opening_price,
        "session_high": opening_price,
        "session_low": opening_price,
        "session_active": True,
        "file_used": chosen_file.name,
    }

    return SimulationStartResponse(
        session_id=session_id,
        ticker=ticker,
        current_time=data["session_start"],
        current_price=opening_price,
        session_end=data["session_end"],
    )


@router.get("/simulation/tick")
async def get_next_tick(session_id: str = Query(..., description="Active session ID")):
    """
    Advance the simulation by 1-3 ticks and return the latest tick data.

    Returns the next tick(s) of price data, advancing simulated time.
    When the session reaches 15:30 (end), returns session_active=false.
    """
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session["session_active"]:
        return {
            "current_time": "15:30",
            "current_price": session["current_price"],
            "tick": None,
            "session_active": False,
            "message": "Market Closed",
        }

    ticks = session["ticks"]
    current_idx = session["current_tick_index"]
    total_ticks = len(ticks)

    # Advance 1-3 ticks (random for realistic feel)
    advance = random.randint(1, 3)
    advance = min(advance, total_ticks - current_idx)

    if advance <= 0:
        session["session_active"] = False
        return {
            "current_time": "15:30",
            "current_price": session["current_price"],
            "tick": None,
            "session_active": False,
            "message": "Market Closed",
        }

    # Process ticks
    last_tick = None
    for i in range(advance):
        tick_idx = current_idx + i
        if tick_idx >= total_ticks:
            break
        last_tick = ticks[tick_idx]
        session["current_price"] = last_tick["close"]
        session["session_high"] = max(session["session_high"], last_tick["high"])
        session["session_low"] = min(session["session_low"], last_tick["low"])

    session["current_tick_index"] = current_idx + advance

    # Check if session is over
    if session["current_tick_index"] >= total_ticks:
        session["session_active"] = False
        return {
            "current_time": "15:30",
            "current_price": session["current_price"],
            "tick": last_tick,
            "session_active": False,
            "message": "Market Closed",
        }

    return TickResponse(
        current_time=last_tick["time"],
        current_price=last_tick["close"],
        tick=last_tick,
        session_active=True,
    )


@router.get("/simulation/state", response_model=SessionStateResponse)
async def get_session_state(session_id: str = Query(..., description="Active session ID")):
    """
    Get the current state of a simulation session.

    Returns timing info, price stats, and session status.
    """
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    total_ticks = len(session["ticks"])
    ticks_elapsed = session["current_tick_index"]
    ticks_remaining = total_ticks - ticks_elapsed

    # Determine current time
    if ticks_elapsed == 0:
        current_time = "09:15"
    elif ticks_elapsed >= total_ticks:
        current_time = "15:30"
    else:
        current_time = session["ticks"][ticks_elapsed - 1]["time"]

    return SessionStateResponse(
        session_id=session["session_id"],
        ticker=session["ticker"],
        current_time=current_time,
        current_price=session["current_price"],
        session_high=session["session_high"],
        session_low=session["session_low"],
        ticks_elapsed=ticks_elapsed,
        ticks_remaining=ticks_remaining,
        session_active=session["session_active"],
    )


@router.get("/simulation/chart-data")
async def get_chart_data(session_id: str = Query(..., description="Active session ID")):
    """
    Get price history for charting (last 60 ticks of data).

    Returns the most recent 60 ticks of OHLC data that have been
    'played' in this session, suitable for rendering a price chart.
    """
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    ticks_elapsed = session["current_tick_index"]
    all_ticks = session["ticks"]

    # Return last 60 ticks (or fewer if not that many have elapsed)
    start_idx = max(0, ticks_elapsed - 60)
    end_idx = ticks_elapsed

    chart_ticks = all_ticks[start_idx:end_idx]

    return {
        "session_id": session["session_id"],
        "ticker": session["ticker"],
        "ticks_shown": len(chart_ticks),
        "ticks_elapsed": ticks_elapsed,
        "data": chart_ticks,
    }
