"""
Skipped days: a skip locks the Today tab for that date and logs the untaken ticket, so
Review can later show what skipped trades would have done and the rules can be judged on data.
"""

import json
from datetime import datetime, timezone


def skip_reason(ticket) -> str:
    """Why this ticket was skipped, in words: the failed rules, with a blocking event named first."""
    t = ticket or {}
    alert = t.get("event_alert")
    parts = [f"{alert['name']} event"] if alert else []
    parts += [f for f in (t.get("failed") or []) if not (alert and f == "No event before expiry")]
    if not parts:
        return "Chose to skip"
    return ("NO-GO: " if t.get("verdict") == "NO-GO" else "") + "; ".join(parts)


def _row(r):
    d = dict(r)
    try:
        d["ticket"] = json.loads(d.pop("ticket_json") or "null")
    except ValueError:
        d["ticket"] = None
    return d


def record_skip(user_id, day, ticket, next_entry, market="NIFTY"):
    """Log today's skip. Skipping twice in a day keeps the latest ticket and reason."""
    from db.database import get_connection
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO desk_skips (user_id, market, skip_date, reason, next_entry, ticket_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (user_id, market, skip_date) DO UPDATE SET reason = excluded.reason,
                   next_entry = excluded.next_entry, ticket_json = excluded.ticket_json""",
            (int(user_id), market, day.isoformat(), skip_reason(ticket), next_entry, json.dumps(ticket),
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()
    return get_skip(user_id, day, market)


def get_skip(user_id, day, market="NIFTY"):
    from db.database import get_connection
    conn = get_connection()
    try:
        r = conn.execute("SELECT * FROM desk_skips WHERE user_id = ? AND market = ? AND skip_date = ?",
                         (int(user_id), market, day.isoformat())).fetchone()
    finally:
        conn.close()
    return _row(r) if r else None


def undo_skip(user_id, day, market="NIFTY"):
    from db.database import get_connection
    conn = get_connection()
    try:
        conn.execute("DELETE FROM desk_skips WHERE user_id = ? AND market = ? AND skip_date = ?",
                     (int(user_id), market, day.isoformat()))
        conn.commit()
    finally:
        conn.close()


def list_skips(user_id, market="NIFTY", limit=50):
    """Most recent first, for the Review tab."""
    from db.database import get_connection
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM desk_skips WHERE user_id = ? AND market = ? ORDER BY skip_date DESC LIMIT ?",
                            (int(user_id), market, int(limit))).fetchall()
    finally:
        conn.close()
    return [_row(r) for r in rows]
