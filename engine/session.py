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

    Usage:
        @router.get("/signal")
        async def get_signal(session: dict = Depends(require_founder)):
            ...
    """
    session = get_session(request)

    if not session:
        raise HTTPException(status_code=403, detail="Access denied")

    email = session.get("email", "")
    if not FOUNDER_ALLOWED_EMAILS or email not in FOUNDER_ALLOWED_EMAILS:
        raise HTTPException(status_code=403, detail="Access denied")

    return session


def is_founder(request: Request) -> bool:
    """
    Check if the current request is from the founder (non-throwing).
    Used for conditional UI rendering APIs.
    """
    session = get_session(request)
    if not session:
        return False
    return session.get("email", "") in FOUNDER_ALLOWED_EMAILS
