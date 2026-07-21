"""
Options Tycoon - Dashboard Routes

Provides upload history, score trends, and dashboard data for logged-in users.
"""

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.database import get_connection

router = APIRouter()


class SaveUploadRequest(BaseModel):
    """Request body for saving an upload to history."""
    user_id: int
    trades_count: int
    dna_score: Optional[int] = None
    behavioral_pct: Optional[float] = None
    total_pnl: Optional[float] = None
    persona: Optional[str] = None
    fix_one_thing: Optional[str] = None
    filename: Optional[str] = None
    report_json: Optional[str] = None


@router.post("/dashboard/save-upload")
async def save_upload(request: SaveUploadRequest):
    """
    Save an upload result to the user's history.
    Strict dedup: won't save if same user has same score + same trade count already.
    """
    conn = get_connection()
    try:
        # Strict dedup: don't save if identical score+trades already exists for this user
        existing = conn.execute(
            """SELECT id FROM upload_history 
               WHERE user_id = ? AND dna_score = ? AND trades_count = ?
               LIMIT 1""",
            (request.user_id, request.dna_score, request.trades_count)
        ).fetchone()
        
        if existing:
            return {"id": existing["id"], "status": "already_saved"}
        
        cursor = conn.execute(
            """INSERT INTO upload_history 
               (user_id, upload_date, filename, trades_count, dna_score, 
                behavioral_pct, total_pnl, persona, fix_one_thing, report_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                request.user_id,
                datetime.utcnow().isoformat(),
                request.filename,
                request.trades_count,
                request.dna_score,
                request.behavioral_pct,
                request.total_pnl,
                request.persona,
                request.fix_one_thing,
                request.report_json,
            )
        )
        conn.commit()
        return {"id": cursor.lastrowid, "status": "saved"}
    finally:
        conn.close()


@router.get("/dashboard/history/{user_id}")
async def get_upload_history(user_id: int, limit: int = Query(default=20)):
    """Get upload history for a user, ordered by most recent first."""
    conn = get_connection()
    try:
        # Verify user exists
        user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        rows = conn.execute(
            """SELECT id, upload_date, filename, trades_count, dna_score, 
                      behavioral_pct, total_pnl, persona, fix_one_thing
               FROM upload_history 
               WHERE user_id = ? 
               ORDER BY upload_date DESC 
               LIMIT ?""",
            (user_id, limit)
        ).fetchall()

        history = []
        for row in rows:
            history.append({
                "id": row["id"],
                "upload_date": row["upload_date"],
                "filename": row["filename"],
                "trades_count": row["trades_count"],
                "dna_score": row["dna_score"],
                "behavioral_pct": row["behavioral_pct"],
                "total_pnl": row["total_pnl"],
                "persona": row["persona"],
                "fix_one_thing": row["fix_one_thing"],
            })

        return {"user_id": user_id, "uploads": history, "total": len(history)}
    finally:
        conn.close()


@router.get("/dashboard/score-trend/{user_id}")
async def get_score_trend(user_id: int):
    """Get DNA Score progression over time for charting."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT upload_date, dna_score, behavioral_pct, trades_count, persona
               FROM upload_history 
               WHERE user_id = ? AND dna_score IS NOT NULL
               ORDER BY upload_date ASC""",
            (user_id,)
        ).fetchall()

        trend = []
        for row in rows:
            trend.append({
                "date": row["upload_date"],
                "score": row["dna_score"],
                "behavioral_pct": row["behavioral_pct"],
                "trades": row["trades_count"],
                "persona": row["persona"],
            })

        # Compute improvement stats
        improvement = None
        if len(trend) >= 2:
            first_score = trend[0]["score"]
            last_score = trend[-1]["score"]
            improvement = {
                "first_score": first_score,
                "current_score": last_score,
                "change": last_score - first_score,
                "direction": "improving" if last_score > first_score else ("declining" if last_score < first_score else "stable"),
                "uploads_count": len(trend),
            }

        return {"user_id": user_id, "trend": trend, "improvement": improvement}
    finally:
        conn.close()


@router.get("/dashboard/stats/{user_id}")
async def get_dashboard_stats(user_id: int):
    """Get summary stats for the dashboard cards."""
    conn = get_connection()
    try:
        # Latest upload
        latest = conn.execute(
            """SELECT dna_score, behavioral_pct, total_pnl, persona, fix_one_thing, trades_count, upload_date
               FROM upload_history 
               WHERE user_id = ? 
               ORDER BY upload_date DESC 
               LIMIT 1""",
            (user_id,)
        ).fetchone()

        if not latest:
            return {"has_data": False}

        # Previous upload (for comparison)
        previous = conn.execute(
            """SELECT dna_score, behavioral_pct
               FROM upload_history 
               WHERE user_id = ? 
               ORDER BY upload_date DESC 
               LIMIT 1 OFFSET 1""",
            (user_id,)
        ).fetchone()

        # Total uploads count
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM upload_history WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        score_change = None
        if previous and previous["dna_score"] is not None and latest["dna_score"] is not None:
            score_change = latest["dna_score"] - previous["dna_score"]

        return {
            "has_data": True,
            "current_score": latest["dna_score"],
            "behavioral_pct": latest["behavioral_pct"],
            "persona": latest["persona"],
            "fix_one_thing": latest["fix_one_thing"],
            "total_pnl": latest["total_pnl"],
            "trades_count": latest["trades_count"],
            "last_upload": latest["upload_date"],
            "score_change": score_change,
            "total_uploads": count["cnt"] if count else 0,
        }
    finally:
        conn.close()


@router.delete("/dashboard/delete-account/{user_id}")
async def delete_account(user_id: int):
    """
    Delete a user account and ALL associated data.
    GDPR/DPDPA compliance — right to erasure.
    """
    conn = get_connection()
    try:
        # Verify user exists
        user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Delete all user data
        conn.execute("DELETE FROM upload_history WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

        return {"status": "deleted", "message": "Account and all associated data have been permanently deleted."}
    finally:
        conn.close()


@router.post("/dashboard/send-reminders")
async def send_weekly_reminders():
    """
    Send weekly upload reminders to users who haven't uploaded in 7+ days.
    Call this from a cron job or manually.
    """
    from engine.email_service import send_weekly_reminder
    from datetime import datetime, timedelta

    conn = get_connection()
    try:
        # Get all users
        users = conn.execute("SELECT id, email, name FROM users").fetchall()
        
        sent = 0
        skipped = 0
        for user in users:
            # Check last upload date
            last_upload = conn.execute(
                "SELECT upload_date, dna_score FROM upload_history WHERE user_id = ? ORDER BY upload_date DESC LIMIT 1",
                (user["id"],)
            ).fetchone()
            
            if last_upload:
                # Calculate days since last upload
                try:
                    last_date = datetime.fromisoformat(last_upload["upload_date"])
                    days_ago = (datetime.utcnow() - last_date).days
                    if days_ago >= 7:
                        send_weekly_reminder(
                            user_name=user["name"] or "Trader",
                            user_email=user["email"],
                            dna_score=last_upload["dna_score"],
                            days_since_upload=days_ago
                        )
                        sent += 1
                    else:
                        skipped += 1
                except Exception:
                    skipped += 1
            else:
                # Never uploaded — send reminder
                send_weekly_reminder(
                    user_name=user["name"] or "Trader",
                    user_email=user["email"],
                    dna_score=None,
                    days_since_upload=7
                )
                sent += 1

        return {"sent": sent, "skipped": skipped, "total_users": len(users)}
    finally:
        conn.close()


@router.get("/dashboard/latest-report/{user_id}")
async def get_latest_report(user_id: int):
    """Get the full latest report JSON for a user (for restoring session after logout)."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT report_json FROM upload_history 
               WHERE user_id = ? AND report_json IS NOT NULL 
               ORDER BY upload_date DESC LIMIT 1""",
            (user_id,)
        ).fetchone()

        if row and row["report_json"]:
            import json
            return json.loads(row["report_json"])
        return {"error": "No report found"}
    finally:
        conn.close()


@router.delete("/dashboard/clear-history/{user_id}")
async def clear_history(user_id: int):
    """Clear all upload history for a user (keeps account active)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM upload_history WHERE user_id = ?", (user_id,))
        conn.commit()
        return {"status": "cleared", "message": "Upload history cleared."}
    finally:
        conn.close()


# --- Trader DNA Report (merged from routes/report.py) ---

@router.get("/report/{profile_id}")
def get_trader_dna_report(profile_id: int):
    """Generate the Devastating Report from trade history."""
    from engine.report_generator import generate_devastating_report

    conn = get_connection()
    try:
        trades = conn.execute(
            "SELECT * FROM trades WHERE profile_id = ? AND status IN ('closed', 'settled') ORDER BY opened_at",
            (profile_id,)
        ).fetchall()

        trade_list = []
        for t in trades:
            trade_list.append({
                'ticker': t['ticker'],
                'entry_time': t['opened_at'],
                'exit_time': t['closed_at'],
                'entry_price': t['entry_price'],
                'exit_price': t['exit_price'] if t['exit_price'] else t['entry_price'],
                'pnl': t['realized_pnl'] if t['realized_pnl'] else 0,
                'quantity': 1,
            })

        if len(trade_list) < 5:
            return {
                "error": "Need at least 5 closed trades to generate report",
                "trade_count": len(trade_list),
            }

        report = generate_devastating_report(trade_list)
        return report
    finally:
        conn.close()
