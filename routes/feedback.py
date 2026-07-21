"""
Options Tycoon - Tester Feedback Routes

Allows testers to submit bug reports, feature feedback, and test results
directly from the app. Stores in SQLite for review.
"""

import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.database import get_connection

router = APIRouter()


class FeedbackEntry(BaseModel):
    """A feedback entry from a tester."""
    tester_name: str
    category: str  # 'bug', 'suggestion', 'confusion', 'positive', 'test_result'
    page: str  # which page they were on
    description: str
    severity: str = "medium"  # 'low', 'medium', 'high', 'critical'
    test_script_id: str = ""  # if following a test script


# Create feedback table on import
def _ensure_feedback_table():
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tester_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tester_name TEXT NOT NULL,
                category TEXT NOT NULL,
                page TEXT NOT NULL,
                description TEXT NOT NULL,
                severity TEXT DEFAULT 'medium',
                test_script_id TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    finally:
        conn.close()

_ensure_feedback_table()


@router.post("/feedback")
def submit_feedback(entry: FeedbackEntry):
    """Submit tester feedback."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO tester_feedback (tester_name, category, page, description, severity, test_script_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (entry.tester_name, entry.category, entry.page, entry.description, entry.severity, entry.test_script_id),
        )
        conn.commit()
        return {"id": cursor.lastrowid, "message": "Feedback recorded. Thank you!"}
    finally:
        conn.close()


@router.get("/feedback")
def get_all_feedback():
    """Get all tester feedback (for review)."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM tester_feedback ORDER BY created_at DESC").fetchall()
        return {"feedback": [dict(row) for row in rows], "count": len(rows)}
    finally:
        conn.close()


@router.get("/feedback/summary")
def get_feedback_summary():
    """Get summary of feedback by category."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT category, COUNT(*) as count FROM tester_feedback GROUP BY category"
        ).fetchall()
        return {"summary": {row["category"]: row["count"] for row in rows}}
    finally:
        conn.close()
