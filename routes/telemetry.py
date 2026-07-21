"""
Options Tycoon - Telemetry API Routes

Records trader decisions at risk gates and behavioral snapshots.
Also writes entries to feedback_loop.json for offline analysis.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.database import get_connection
from engine.behavioral import compute_all_behavioral_metrics

router = APIRouter()

# Path to the feedback loop JSON file (project root)
FEEDBACK_LOOP_PATH = Path(__file__).parent.parent / "feedback_loop.json"


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class TelemetryEntry(BaseModel):
    """Request model for logging a telemetry entry."""
    trade_id: Optional[int] = None
    risk_gate_warnings: list[str] = []
    trader_decision: str  # "proceeded" or "cancelled"


# ---------------------------------------------------------------------------
# POST /telemetry/{profile_id} — Log a telemetry entry
# ---------------------------------------------------------------------------


@router.post("/telemetry/{profile_id}")
def log_telemetry(profile_id: int, entry: TelemetryEntry):
    """
    Log a telemetry entry recording a trader's decision at a risk gate.

    Stores the entry in the telemetry table and appends to feedback_loop.json.
    Also captures a snapshot of current behavioral metrics.
    """
    _verify_profile_exists(profile_id)

    # Validate trader_decision
    if entry.trader_decision not in ("proceeded", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail="trader_decision must be 'proceeded' or 'cancelled'"
        )

    # Get current behavioral metrics snapshot
    metrics = compute_all_behavioral_metrics(profile_id)

    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO telemetry
               (profile_id, trade_id, discipline_rating, patience_score,
                sizing_consistency, emotional_reactivity,
                risk_gate_warnings, trader_decision)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile_id,
                entry.trade_id,
                metrics["discipline_rating"],
                metrics["patience_score"],
                metrics["sizing_consistency"],
                metrics["emotional_reactivity"],
                json.dumps(entry.risk_gate_warnings),
                entry.trader_decision,
            ),
        )
        conn.commit()
        telemetry_id = cursor.lastrowid
    finally:
        conn.close()

    # Append to feedback_loop.json
    feedback_entry = {
        "id": telemetry_id,
        "profile_id": profile_id,
        "trade_id": entry.trade_id,
        "timestamp": datetime.utcnow().isoformat(),
        "discipline_rating": metrics["discipline_rating"],
        "patience_score": metrics["patience_score"],
        "sizing_consistency": metrics["sizing_consistency"],
        "emotional_reactivity": metrics["emotional_reactivity"],
        "risk_gate_warnings": entry.risk_gate_warnings,
        "trader_decision": entry.trader_decision,
    }
    _append_to_feedback_loop(feedback_entry)

    return {
        "id": telemetry_id,
        "profile_id": profile_id,
        "trader_decision": entry.trader_decision,
        "behavioral_snapshot": {
            "discipline_rating": metrics["discipline_rating"],
            "patience_score": metrics["patience_score"],
            "sizing_consistency": metrics["sizing_consistency"],
            "emotional_reactivity": metrics["emotional_reactivity"],
        },
    }


# ---------------------------------------------------------------------------
# GET /telemetry/{profile_id} — Get telemetry log entries
# ---------------------------------------------------------------------------


@router.get("/telemetry/{profile_id}")
def get_telemetry(profile_id: int):
    """Return all telemetry log entries for a profile, ordered by timestamp DESC."""
    _verify_profile_exists(profile_id)

    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, profile_id, trade_id, timestamp,
                      discipline_rating, patience_score,
                      sizing_consistency, emotional_reactivity,
                      risk_gate_warnings, trader_decision
               FROM telemetry
               WHERE profile_id = ?
               ORDER BY timestamp DESC""",
            (profile_id,),
        ).fetchall()

        entries = []
        for row in rows:
            entries.append({
                "id": row["id"],
                "profile_id": row["profile_id"],
                "trade_id": row["trade_id"],
                "timestamp": row["timestamp"],
                "discipline_rating": row["discipline_rating"],
                "patience_score": row["patience_score"],
                "sizing_consistency": row["sizing_consistency"],
                "emotional_reactivity": row["emotional_reactivity"],
                "risk_gate_warnings": json.loads(row["risk_gate_warnings"])
                if row["risk_gate_warnings"]
                else [],
                "trader_decision": row["trader_decision"],
            })

        return {"entries": entries, "count": len(entries)}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _verify_profile_exists(profile_id: int) -> None:
    """Raise 404 if the profile does not exist."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Profile not found")
    finally:
        conn.close()


def _append_to_feedback_loop(entry: dict) -> None:
    """Append a telemetry entry to feedback_loop.json."""
    entries = []

    if FEEDBACK_LOOP_PATH.exists():
        try:
            with open(FEEDBACK_LOOP_PATH, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, IOError):
            entries = []

    entries.append(entry)

    with open(FEEDBACK_LOOP_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
