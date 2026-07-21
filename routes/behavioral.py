"""
Options Tycoon - Behavioral Metrics API Routes

Exposes behavioral intelligence data for the frontend dashboard, leaderboard,
and sim-vs-real gap analysis.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException

from db.database import get_connection
from engine.behavioral import (
    compute_all_behavioral_metrics,
    compute_discipline_rating,
    compute_patience_score,
    compute_sizing_consistency,
    compute_emotional_reactivity,
    compute_streak,
    determine_phase,
    generate_diagnostic,
    compute_trader_dna_score,
    compute_strategy_vs_behavior_cost,
    get_fix_one_thing,
)
from engine.achievements import compute_xp, get_level, check_achievements

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /behavioral/{profile_id} — Full behavioral metrics
# ---------------------------------------------------------------------------


@router.get("/behavioral/{profile_id}")
def get_behavioral_metrics(profile_id: int):
    """Return all computed behavioral metrics for a profile."""
    _verify_profile_exists(profile_id)

    metrics = compute_all_behavioral_metrics(profile_id)

    # Also compute advanced metrics
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM trades WHERE profile_id = ? ORDER BY opened_at ASC", (profile_id,)).fetchall()
        trades = [dict(row) for row in rows]
    finally:
        conn.close()

    dna_score = compute_trader_dna_score(metrics)
    strategy_vs_behavior = compute_strategy_vs_behavior_cost(trades)
    fix_one_thing = get_fix_one_thing(trades)

    # Count behavioral flags from trade data
    revenge_count = sum(1 for t in trades if t.get('is_revenge_trade'))
    overconfidence_count = sum(1 for t in trades if t.get('is_overconfidence_trap'))
    impulse_count = sum(1 for t in trades if t.get('is_impulse_early_exit'))

    return {
        # existing fields
        "discipline_rating": metrics["discipline_rating"],
        "patience_score": metrics["patience_score"],
        "sizing_consistency": metrics["sizing_consistency"],
        "emotional_reactivity": metrics["emotional_reactivity"],
        "loss_disposition_ratio": metrics["loss_disposition_ratio"],
        "current_streak": metrics["current_streak"],
        "longest_streak": metrics["longest_streak"],
        "total_trades": metrics["total_trades"],
        "phase": metrics["phase"],
        "diagnostic_summary": metrics["diagnostic_summary"],
        # new fields
        "dna_score": dna_score,
        "strategy_vs_behavior": strategy_vs_behavior,
        "fix_one_thing": fix_one_thing,
        # flag counts
        "revenge_trade_count": revenge_count,
        "overconfidence_count": overconfidence_count,
        "impulse_exit_count": impulse_count,
        "disposition_bias": metrics["loss_disposition_ratio"] is not None and metrics["loss_disposition_ratio"] > 1.2,
    }


# ---------------------------------------------------------------------------
# GET /behavioral/{profile_id}/diagnostic — Diagnostic summary text
# ---------------------------------------------------------------------------


@router.get("/behavioral/{profile_id}/diagnostic")
def get_diagnostic(profile_id: int):
    """Return the diagnostic text summary, trade count, and phase."""
    _verify_profile_exists(profile_id)

    metrics = compute_all_behavioral_metrics(profile_id)

    return {
        "diagnostic": metrics["diagnostic_summary"],
        "total_trades": metrics["total_trades"],
        "phase": metrics["phase"],
    }


# ---------------------------------------------------------------------------
# GET /behavioral/{profile_id}/streak — Streak data
# ---------------------------------------------------------------------------


@router.get("/behavioral/{profile_id}/streak")
def get_streak(profile_id: int):
    """Return current and longest disciplined trade streaks."""
    _verify_profile_exists(profile_id)

    metrics = compute_all_behavioral_metrics(profile_id)

    return {
        "current_streak": metrics["current_streak"],
        "longest_streak": metrics["longest_streak"],
    }


# ---------------------------------------------------------------------------
# GET /behavioral/{profile_id}/monthly — Monthly P&L for leaderboard
# ---------------------------------------------------------------------------


@router.get("/behavioral/{profile_id}/monthly")
def get_monthly_pnl(profile_id: int):
    """Return monthly P&L records for self-competition leaderboard."""
    _verify_profile_exists(profile_id)

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT year_month, realized_pnl, trade_count "
            "FROM monthly_pnl WHERE profile_id = ? ORDER BY year_month ASC",
            (profile_id,),
        ).fetchall()

        months = [
            {
                "year_month": row["year_month"],
                "realized_pnl": row["realized_pnl"],
                "trade_count": row["trade_count"],
            }
            for row in rows
        ]

        # Determine best month and current month
        best_month = None
        current_month = None

        if months:
            best_month = max(months, key=lambda m: m["realized_pnl"])
            now_ym = datetime.utcnow().strftime("%Y-%m")
            current_month = next(
                (m for m in months if m["year_month"] == now_ym), None
            )

        return {
            "months": months,
            "best_month": best_month,
            "current_month": current_month,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /behavioral/{profile_id}/weekly-gap — Sim vs Real behavioral gap
# ---------------------------------------------------------------------------


@router.get("/behavioral/{profile_id}/weekly-gap")
def get_weekly_gap(profile_id: int):
    """
    Return side-by-side comparison of sim and real trading behavior
    from the last 7 days.
    """
    _verify_profile_exists(profile_id)

    conn = get_connection()
    try:
        seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()

        # Sim trades from last 7 days
        sim_rows = conn.execute(
            "SELECT * FROM trades WHERE profile_id = ? "
            "AND status IN ('closed', 'settled') "
            "AND opened_at >= ? ORDER BY opened_at ASC",
            (profile_id, seven_days_ago),
        ).fetchall()
        sim_trades = [dict(row) for row in sim_rows]

        # Real trades from last 7 days
        real_rows = conn.execute(
            "SELECT * FROM real_trades WHERE profile_id = ? "
            "AND entry_time >= ? ORDER BY entry_time ASC",
            (profile_id, seven_days_ago),
        ).fetchall()
        real_trades = [dict(row) for row in real_rows]

        # Compute sim metrics
        sim_discipline = compute_discipline_rating(sim_trades)
        sim_patience = compute_patience_score(sim_trades)
        sim_sizing = compute_sizing_consistency(sim_trades)
        sim_emotional = compute_emotional_reactivity(sim_trades)
        sim_current, sim_longest = compute_streak(sim_trades)

        # Compute real metrics (real_trades use position_size as pct proxy)
        real_metrics_trades = _normalize_real_trades(real_trades)
        real_discipline = compute_discipline_rating(real_metrics_trades)
        real_patience = None  # Real trades don't track chain timing
        real_sizing = compute_sizing_consistency(real_metrics_trades)
        real_emotional = None  # Real trades have limited emotional flags
        real_current, real_longest = compute_streak(real_metrics_trades)

        sim_summary = {
            "trade_count": len(sim_trades),
            "discipline_rating": sim_discipline,
            "patience_score": sim_patience,
            "sizing_consistency": sim_sizing,
            "emotional_reactivity": sim_emotional,
            "current_streak": sim_current,
            "longest_streak": sim_longest,
        }

        real_summary = {
            "trade_count": len(real_trades),
            "discipline_rating": real_discipline,
            "patience_score": real_patience,
            "sizing_consistency": real_sizing,
            "emotional_reactivity": real_emotional,
            "current_streak": real_current,
            "longest_streak": real_longest,
        }

        # Compute differences where both values exist
        differences = {}
        for key in ["discipline_rating", "sizing_consistency"]:
            sim_val = sim_summary.get(key)
            real_val = real_summary.get(key)
            if sim_val is not None and real_val is not None:
                differences[key] = round(real_val - sim_val, 2)

        return {
            "period": "last_7_days",
            "sim": sim_summary,
            "real": real_summary,
            "differences": differences,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /behavioral/{profile_id}/achievements — XP and achievements
# ---------------------------------------------------------------------------


@router.get("/behavioral/{profile_id}/achievements")
def get_achievements(profile_id: int):
    """Return XP, level, and unlocked achievements for a profile."""
    _verify_profile_exists(profile_id)

    conn = get_connection()
    try:
        # Fetch all trades for XP computation
        rows = conn.execute(
            "SELECT position_pct FROM trades WHERE profile_id = ?",
            (profile_id,),
        ).fetchall()
        trades = [dict(row) for row in rows]

        # Compute XP and level
        xp = compute_xp(trades)
        level = get_level(xp)

        # Compute behavioral stats for achievement checks
        metrics = compute_all_behavioral_metrics(profile_id)
        stats = {
            "total_trades": metrics["total_trades"],
            "longest_streak": metrics["longest_streak"],
            "days_since_revenge": metrics.get("days_since_revenge", 0),
        }

        unlocked = check_achievements(stats)

        return {
            "xp": xp,
            "level": level,
            "achievements": unlocked,
        }
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
