"""
Options Tycoon - Portfolio & Profile Management Routes

Handles profile CRUD, game-over detection, and strategy sub-profiles.
"""

from fastapi import APIRouter, HTTPException
from db.database import get_connection
from db.models import (
    ProfileCreate,
    ProfileResponse,
    StrategyProfileCreate,
    StrategyProfileResponse,
    ErrorResponse,
)

router = APIRouter()

INITIAL_BALANCE = 10000.0
MAX_STRATEGY_PROFILES = 5


def _determine_phase(total_trades: int) -> str:
    """
    Determine behavioral profile phase based on trade count.
    Phase A: 0-5 trades (raw data only)
    Phase B: 6-14 trades (discipline + sizing)
    Phase C: 15-24 trades (patience + initial emotional)
    Phase D: 25+ trades (full profile)
    """
    if total_trades >= 25:
        return "D"
    elif total_trades >= 15:
        return "C"
    elif total_trades >= 6:
        return "B"
    return "A"


def check_game_over(profile_id: int) -> bool:
    """
    Check if a profile's balance has reached $0 and lock it if so.
    Returns True if the profile is now locked (game over).
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, balance, is_locked FROM profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        if row is None:
            return False
        if row["is_locked"]:
            return True
        if row["balance"] <= 0:
            conn.execute(
                "UPDATE profiles SET is_locked = 1 WHERE id = ?",
                (profile_id,),
            )
            conn.commit()
            return True
        return False
    finally:
        conn.close()


def _get_total_trades(conn, profile_id: int) -> int:
    """Get the total number of trades (all statuses) for a profile."""
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM trades WHERE profile_id = ?",
        (profile_id,),
    ).fetchone()
    return row["cnt"] if row else 0


# --- Profile Endpoints ---


@router.post("/profiles", response_model=ProfileResponse, status_code=201)
def create_profile(body: ProfileCreate):
    """Create a new trading profile with $10,000 starting balance."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO profiles (name, balance, mode, is_locked) VALUES (?, ?, 'sim_only', 0)",
            (body.name, INITIAL_BALANCE),
        )
        conn.commit()
        profile_id = cursor.lastrowid

        return ProfileResponse(
            id=profile_id,
            name=body.name,
            balance=INITIAL_BALANCE,
            mode="sim_only",
            is_locked=False,
            phase="A",
            total_trades=0,
        )
    finally:
        conn.close()


@router.get("/profiles", response_model=list[ProfileResponse])
def list_profiles():
    """List all trading profiles."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM profiles").fetchall()
        profiles = []
        for row in rows:
            total_trades = _get_total_trades(conn, row["id"])
            profiles.append(
                ProfileResponse(
                    id=row["id"],
                    name=row["name"],
                    balance=row["balance"],
                    mode=row["mode"],
                    is_locked=bool(row["is_locked"]),
                    phase=_determine_phase(total_trades),
                    total_trades=total_trades,
                )
            )
        return profiles
    finally:
        conn.close()


@router.get("/profiles/{profile_id}", response_model=ProfileResponse)
def get_profile(profile_id: int):
    """Get a single profile with current balance, phase, and trade count."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Profile not found")

        total_trades = _get_total_trades(conn, profile_id)

        return ProfileResponse(
            id=row["id"],
            name=row["name"],
            balance=row["balance"],
            mode=row["mode"],
            is_locked=bool(row["is_locked"]),
            phase=_determine_phase(total_trades),
            total_trades=total_trades,
        )
    finally:
        conn.close()


@router.put("/profiles/{profile_id}", response_model=ProfileResponse)
def update_profile(profile_id: int, body: dict):
    """Update profile fields (mode, name)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Profile not found")

        # Update mode if provided
        mode = body.get("mode", row["mode"])
        if mode not in ("sim_only", "sim_and_real"):
            raise HTTPException(status_code=400, detail="mode must be 'sim_only' or 'sim_and_real'")

        conn.execute(
            "UPDATE profiles SET mode = ? WHERE id = ?",
            (mode, profile_id),
        )
        conn.commit()

        total_trades = _get_total_trades(conn, profile_id)

        return ProfileResponse(
            id=row["id"],
            name=row["name"],
            balance=row["balance"],
            mode=mode,
            is_locked=bool(row["is_locked"]),
            phase=_determine_phase(total_trades),
            total_trades=total_trades,
        )
    finally:
        conn.close()
@router.delete("/profiles/{profile_id}", status_code=204)
def delete_profile(profile_id: int):
    """Delete a profile and all related data."""
    conn = get_connection()
    try:
        # Verify profile exists
        row = conn.execute(
            "SELECT id FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Profile not found")

        # Delete all related data (order matters for foreign keys)
        conn.execute("DELETE FROM telemetry WHERE profile_id = ?", (profile_id,))
        conn.execute("DELETE FROM behavioral_metrics WHERE profile_id = ?", (profile_id,))
        conn.execute("DELETE FROM real_trades WHERE profile_id = ?", (profile_id,))
        conn.execute("DELETE FROM monthly_pnl WHERE profile_id = ?", (profile_id,))
        conn.execute("DELETE FROM trades WHERE profile_id = ?", (profile_id,))
        conn.execute("DELETE FROM strategy_profiles WHERE profile_id = ?", (profile_id,))
        conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        conn.commit()
    finally:
        conn.close()


# --- Strategy Sub-Profile Endpoints ---


@router.post(
    "/profiles/{profile_id}/strategy-profiles",
    response_model=StrategyProfileResponse,
    status_code=201,
)
def create_strategy_profile(profile_id: int, body: StrategyProfileCreate):
    """Create a strategy sub-profile (max 5 per profile)."""
    conn = get_connection()
    try:
        # Verify parent profile exists and is not locked
        profile = conn.execute(
            "SELECT id, is_locked FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        if profile["is_locked"]:
            raise HTTPException(
                status_code=403,
                detail="Profile is locked (Game Over). Cannot create strategy profiles.",
            )

        # Check max 5 constraint
        count_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM strategy_profiles WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        if count_row["cnt"] >= MAX_STRATEGY_PROFILES:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum of {MAX_STRATEGY_PROFILES} strategy profiles per profile reached.",
            )

        cursor = conn.execute(
            "INSERT INTO strategy_profiles (profile_id, name, balance, is_locked) VALUES (?, ?, ?, 0)",
            (profile_id, body.name, INITIAL_BALANCE),
        )
        conn.commit()

        # Fetch the created row to get the created_at timestamp
        new_row = conn.execute(
            "SELECT * FROM strategy_profiles WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()

        return StrategyProfileResponse(
            id=new_row["id"],
            profile_id=new_row["profile_id"],
            name=new_row["name"],
            balance=new_row["balance"],
            is_locked=bool(new_row["is_locked"]),
            created_at=new_row["created_at"],
        )
    finally:
        conn.close()


@router.get(
    "/profiles/{profile_id}/strategy-profiles",
    response_model=list[StrategyProfileResponse],
)
def list_strategy_profiles(profile_id: int):
    """List all strategy sub-profiles for a given profile."""
    conn = get_connection()
    try:
        # Verify parent profile exists
        profile = conn.execute(
            "SELECT id FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")

        rows = conn.execute(
            "SELECT * FROM strategy_profiles WHERE profile_id = ?", (profile_id,)
        ).fetchall()

        return [
            StrategyProfileResponse(
                id=row["id"],
                profile_id=row["profile_id"],
                name=row["name"],
                balance=row["balance"],
                is_locked=bool(row["is_locked"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]
    finally:
        conn.close()
