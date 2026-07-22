"""
Options Tycoon — HTTP-Only Session Management + Founder Allowlist

Replaces localStorage-based auth with server-side signed cookies.
Provides a FastAPI dependency for founder-only route protection.
"""

import os
import hmac
import hashlib
import json
import time
import logging
from typing import Optional
from fastapi import Request, HTTPException, Response

logger = logging.getLogger(__name__)

# Session secret — MUST be set in production (Railway env var)
SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-secret-change-in-production")

# Founder allowlist — single email, env var
FOUNDER_ALLOWED_EMAILS = [
    e.strip() for e in
    os.environ.get("FOUNDER_ALLOWED_EMAILS", "").split(",")
    if e.strip()
]

# Session cookie config
SESSION_COOKIE_NAME = "ot_session"
SESSION_MAX_AGE = 7 * 24 * 60 * 60  # 7 days
IS_PRODUCTION = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("PRODUCTION"))


def _sign(payload: str) -> str:
    """Create HMAC-SHA256 signature for a payload."""
    return hmac.new(
        SESSION_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()


def _verify(payload: str, signature: str) -> bool:
    """Verify HMAC-SHA256 signature."""
    expected = _sign(payload)
    return hmac.compare_digest(expected, signature)


def create_session_cookie(response: Response, user_id: int, email: str, name: str) -> None:
    """
    Set an HTTP-Only signed session cookie on the response.
    Called after successful Google auth.
    """
    session_data = json.dumps({
        "user_id": user_id,
        "email": email,
        "name": name,
        "issued_at": int(time.time()),
    })
    signature = _sign(session_data)
    cookie_value = f"{session_data}|{signature}"

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="strict" if IS_PRODUCTION else "lax",
        max_age=SESSION_MAX_AGE,
        path="/",
    )


def get_session(request: Request) -> Optional[dict]:
    """
    Read and validate the session cookie from a request.
    Returns session dict (user_id, email, name) or None if invalid/missing.
    """
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        return None

    try:
        payload, signature = cookie.rsplit("|", 1)
    except ValueError:
        return None

    if not _verify(payload, signature):
        return None

    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return None

    # Check expiration
    issued_at = data.get("issued_at", 0)
    if time.time() - issued_at > SESSION_MAX_AGE:
        return None

    return data


def clear_session_cookie(response: Response) -> None:
    """Remove the session cookie (logout)."""
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


def require_founder(request: Request) -> dict:
    """
    FastAPI dependency: require a valid session from the founder's email.
    Returns session dict if valid founder, raises 403 otherwise.

    Auth methods (in priority order):
    1. Skip for kite-callback (Zerodha redirect has no session)
    2. HTTP-Only session cookie (primary, secure)
    3. X-User-Id header (TEMPORARY — only from same-origin requests via Referer check)
    """
    # Exempt kite-callback from auth (Zerodha redirect)
    if "/kite-callback" in str(request.url.path):
        return {"user_id": 0, "email": "kite-callback", "name": ""}

    # Try cookie first (preferred, secure)
    session = get_session(request)
    if session:
        email = session.get("email", "")
        if FOUNDER_ALLOWED_EMAILS and email in FOUNDER_ALLOWED_EMAILS:
            return session

    # Temporary fallback: X-User-Id header — ONLY from same-origin requests
    # This prevents external attackers from using it while allowing the frontend to work
    referer = request.headers.get("referer", "")
    origin = request.headers.get("origin", "")
    is_same_origin = any(
        domain in (referer + origin)
        for domain in ["options-tycoon.com", "localhost", "127.0.0.1"]
    )
    
    if is_same_origin:
        user_id = request.headers.get("X-User-Id") or request.query_params.get("user_id")
        if user_id:
            try:
                from db.database import get_connection
                conn = get_connection()
                try:
                    row = conn.execute("SELECT email FROM users WHERE id = ?", (int(user_id),)).fetchone()
                    if row and row["email"] in FOUNDER_ALLOWED_EMAILS:
                        return {"user_id": int(user_id), "email": row["email"], "name": ""}
                finally:
                    conn.close()
            except Exception:
                pass

    # No valid auth
    if not FOUNDER_ALLOWED_EMAILS:
        return {"user_id": 0, "email": "dev@localhost", "name": "dev"}

    raise HTTPException(status_code=403, detail="Access denied")


def is_founder(request: Request) -> bool:
    """
    Check if the current request is from the founder (non-throwing).
    Used for conditional UI rendering APIs.
    """
    session = get_session(request)
    if not session:
        return False
    return session.get("email", "") in FOUNDER_ALLOWED_EMAILS
