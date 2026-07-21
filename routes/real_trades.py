"""
Options Tycoon - Real Trades API Routes

Handles logging of real trades in parallel mode and provides
sim-vs-real comparison analysis.
"""

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException

from db.database import get_connection
from db.models import RealTradeEntry
from engine.behavioral import (
    compute_all_behavioral_metrics,
    compute_discipline_rating,
    compute_patience_score,
    compute_sizing_consistency,
    compute_emotional_reactivity,
    compute_streak,
    detect_revenge_trade,
    detect_overconfidence_trap,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /real-trades/{profile_id} — Log a real trade
# ---------------------------------------------------------------------------


@router.post("/real-trades/{profile_id}")
def log_real_trade(profile_id: int, entry: RealTradeEntry):
    """
    Log a real trade entry with behavioral state snapshot.

    Runs revenge trade and overconfidence detection on the entry,
    storing behavioral flags alongside the trade data.
    """
    _verify_profile_exists(profile_id)

    # Get current behavioral metrics as a snapshot
    metrics = compute_all_behavioral_metrics(profile_id)

    # Fetch recent real trades for pattern detection
    conn = get_connection()
    try:
        recent_rows = conn.execute(
            """SELECT * FROM real_trades
               WHERE profile_id = ?
               ORDER BY created_at DESC LIMIT 10""",
            (profile_id,),
        ).fetchall()
        recent_trades = [dict(row) for row in recent_rows]

        # Compute average position size from recent trades
        if recent_trades:
            avg_position_size = sum(
                t["position_size"] for t in recent_trades
            ) / len(recent_trades)
        else:
            avg_position_size = entry.position_size

        # Detect revenge trade
        # Map real_trades fields for the detection function
        recent_for_revenge = [
            {
                "closed_at": t.get("exit_time"),
                "realized_pnl": t.get("outcome_amount"),
            }
            for t in recent_trades
        ]
        is_revenge = detect_revenge_trade(
            trade_position_size=entry.position_size,
            avg_position_size=avg_position_size,
            recent_trades=recent_for_revenge,
            trade_opened_at=entry.entry_time,
        )

        # Detect overconfidence trap
        recent_for_overconf = [
            {"realized_pnl": t.get("outcome_amount")}
            for t in recent_trades
        ]
        is_overconfidence = detect_overconfidence_trap(
            trade_position_size=entry.position_size,
            avg_position_size=avg_position_size,
            recent_closed_trades=recent_for_overconf,
        )

        # Build behavioral state JSON
        behavioral_state = json.dumps({
            "discipline_rating": metrics["discipline_rating"],
            "patience_score": metrics["patience_score"],
            "sizing_consistency": metrics["sizing_consistency"],
            "emotional_reactivity": metrics["emotional_reactivity"],
            "phase": metrics["phase"],
        })

        # Insert the real trade
        cursor = conn.execute(
            """INSERT INTO real_trades
               (profile_id, ticker, option_type, strike_price, position_size,
                entry_time, exit_time, outcome_amount, behavioral_state,
                is_revenge_trade, is_overconfidence_trap)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile_id,
                entry.ticker,
                entry.option_type,
                entry.strike_price,
                entry.position_size,
                entry.entry_time,
                entry.exit_time,
                entry.outcome_amount,
                behavioral_state,
                1 if is_revenge else 0,
                1 if is_overconfidence else 0,
            ),
        )
        conn.commit()
        trade_id = cursor.lastrowid
    finally:
        conn.close()

    return {
        "id": trade_id,
        "profile_id": profile_id,
        "ticker": entry.ticker,
        "is_revenge_trade": is_revenge,
        "is_overconfidence_trap": is_overconfidence,
        "behavioral_state": json.loads(behavioral_state),
    }


# ---------------------------------------------------------------------------
# GET /real-trades/{profile_id} — Get real trade history
# ---------------------------------------------------------------------------


@router.get("/real-trades/{profile_id}")
def get_real_trades(profile_id: int):
    """Return all real trade records for a profile."""
    _verify_profile_exists(profile_id)

    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, profile_id, ticker, option_type, strike_price,
                      position_size, entry_time, exit_time, outcome_amount,
                      behavioral_state, is_revenge_trade, is_overconfidence_trap,
                      created_at
               FROM real_trades
               WHERE profile_id = ?
               ORDER BY created_at DESC""",
            (profile_id,),
        ).fetchall()

        trades = []
        for row in rows:
            trade = {
                "id": row["id"],
                "profile_id": row["profile_id"],
                "ticker": row["ticker"],
                "option_type": row["option_type"],
                "strike_price": row["strike_price"],
                "position_size": row["position_size"],
                "entry_time": row["entry_time"],
                "exit_time": row["exit_time"],
                "outcome_amount": row["outcome_amount"],
                "behavioral_state": json.loads(row["behavioral_state"])
                if row["behavioral_state"]
                else None,
                "is_revenge_trade": bool(row["is_revenge_trade"]),
                "is_overconfidence_trap": bool(row["is_overconfidence_trap"]),
                "created_at": row["created_at"],
            }
            trades.append(trade)

        return {"trades": trades, "count": len(trades)}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /compare/{profile_id} — Compare Mode (sim vs real)
# ---------------------------------------------------------------------------


@router.get("/compare/{profile_id}")
def compare_sim_vs_real(profile_id: int):
    """
    Compare simulated trading metrics vs real trading metrics side-by-side.

    Returns behavioral metrics computed from sim trades and real trades
    independently, plus the differences for each comparable metric.
    """
    _verify_profile_exists(profile_id)

    conn = get_connection()
    try:
        # Fetch all sim trades
        sim_rows = conn.execute(
            """SELECT * FROM trades
               WHERE profile_id = ? AND status IN ('closed', 'settled')
               ORDER BY opened_at ASC""",
            (profile_id,),
        ).fetchall()
        sim_trades = [dict(row) for row in sim_rows]

        # Fetch all real trades
        real_rows = conn.execute(
            """SELECT * FROM real_trades
               WHERE profile_id = ?
               ORDER BY entry_time ASC""",
            (profile_id,),
        ).fetchall()
        real_trades = [dict(row) for row in real_rows]
    finally:
        conn.close()

    # Compute sim metrics
    sim_discipline = compute_discipline_rating(sim_trades)
    sim_patience = compute_patience_score(sim_trades)
    sim_sizing = compute_sizing_consistency(sim_trades)
    sim_emotional = compute_emotional_reactivity(sim_trades)
    sim_current_streak, sim_longest_streak = compute_streak(sim_trades)

    # Normalize real trades for metric computation
    real_normalized = _normalize_real_trades(real_trades)
    real_discipline = compute_discipline_rating(real_normalized)
    real_patience = compute_patience_score(real_normalized)
    real_sizing = compute_sizing_consistency(real_normalized)
    real_emotional = compute_emotional_reactivity(real_normalized)
    real_current_streak, real_longest_streak = compute_streak(real_normalized)

    # Compute total P&L for each
    sim_total_pnl = sum(
        t.get("realized_pnl", 0) or 0 for t in sim_trades
    )
    real_total_pnl = sum(
        t.get("outcome_amount", 0) or 0 for t in real_trades
    )

    sim_metrics = {
        "trade_count": len(sim_trades),
        "discipline_rating": sim_discipline,
        "patience_score": sim_patience,
        "sizing_consistency": sim_sizing,
        "emotional_reactivity": sim_emotional,
        "current_streak": sim_current_streak,
        "longest_streak": sim_longest_streak,
        "total_pnl": round(sim_total_pnl, 2),
    }

    real_metrics = {
        "trade_count": len(real_trades),
        "discipline_rating": real_discipline,
        "patience_score": real_patience,
        "sizing_consistency": real_sizing,
        "emotional_reactivity": real_emotional,
        "current_streak": real_current_streak,
        "longest_streak": real_longest_streak,
        "total_pnl": round(real_total_pnl, 2),
    }

    # Compute differences for each metric where both values exist
    differences = {}
    for key in [
        "discipline_rating",
        "patience_score",
        "sizing_consistency",
        "emotional_reactivity",
        "total_pnl",
    ]:
        sim_val = sim_metrics.get(key)
        real_val = real_metrics.get(key)
        if sim_val is not None and real_val is not None:
            differences[key] = round(real_val - sim_val, 2)

    differences["streak_gap"] = real_current_streak - sim_current_streak
    differences["trade_count_gap"] = len(real_trades) - len(sim_trades)

    return {
        "profile_id": profile_id,
        "sim": sim_metrics,
        "real": real_metrics,
        "differences": differences,
    }


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


def _normalize_real_trades(real_trades: list[dict]) -> list[dict]:
    """
    Normalize real_trades rows to look like sim trades for metric computation.

    Maps position_size to position_pct and entry_time to opened_at so the
    core behavioral functions can operate on them.
    """
    normalized = []
    for t in real_trades:
        normalized.append({
            "position_pct": t.get("position_size", 0),
            "opened_at": t.get("entry_time"),
            "closed_at": t.get("exit_time"),
            "realized_pnl": t.get("outcome_amount"),
            "chain_opened_at": None,
            "trade_executed_at": None,
            "is_revenge_trade": t.get("is_revenge_trade", 0),
            "is_overconfidence_trap": t.get("is_overconfidence_trap", 0),
            "is_impulse_early_exit": 0,
            "max_unrealized_pnl": None,
        })
    return normalized
