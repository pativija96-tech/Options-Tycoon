"""
Options Tycoon - Google Authentication Routes

Handles Google Sign-In verification, user creation, and session management.
Uses Google's client-side JWT token approach (ID token verification).
"""

import os
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response
from pydantic import BaseModel

from db.database import get_connection

router = APIRouter()

# Google OAuth Client ID — MUST be set via environment variable in production
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
if not GOOGLE_CLIENT_ID:
    # Allow fallback ONLY in local development
    import logging
    logging.warning("GOOGLE_CLIENT_ID not set. Using development fallback. DO NOT use in production.")
    GOOGLE_CLIENT_ID = "300392846336-ciu88fsr38tot4ong5va4m4r2mnmu6b3.apps.googleusercontent.com"


class GoogleTokenRequest(BaseModel):
    """Request body for Google Sign-In token verification."""
    credential: str  # The ID token from Google Sign-In


class AuthResponse(BaseModel):
    """Response after successful authentication."""
    user_id: int
    email: str
    name: str
    picture: str | None = None
    is_new_user: bool = False


@router.post("/auth/google")
async def google_sign_in(request: GoogleTokenRequest, response: Response):
    """
    Verify Google ID token and create/retrieve user.
    Sets HTTP-Only session cookie on success.
    """
    from engine.session import create_session_cookie
    token = request.credential
    
    # Verify the token with Google
    user_info = await _verify_google_token(token)
    
    if not user_info:
        raise HTTPException(status_code=401, detail="Invalid Google token")
    
    email = user_info.get("email")
    name = user_info.get("name", email.split("@")[0])
    picture = user_info.get("picture")
    google_id = user_info.get("sub")  # Unique Google user ID
    
    if not email:
        raise HTTPException(status_code=401, detail="Could not retrieve email from Google")
    
    # Check if user exists, or create new
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM users WHERE google_id = ? OR email = ?",
            (google_id, email)
        ).fetchone()
        
        if existing:
            # Update last login
            conn.execute(
                "UPDATE users SET last_login = ?, name = ?, picture = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), name, picture, existing["id"])
            )
            conn.commit()
            # Set HTTP-Only session cookie
            create_session_cookie(response, existing["id"], existing["email"], existing["name"] or name)
            return AuthResponse(
                user_id=existing["id"],
                email=existing["email"],
                name=existing["name"] or name,
                picture=picture,
                is_new_user=False,
            )
        else:
            # Create new user
            cursor = conn.execute(
                """INSERT INTO users (email, name, google_id, picture, created_at, last_login)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (email, name, google_id, picture, 
                 datetime.utcnow().isoformat(), datetime.utcnow().isoformat())
            )
            conn.commit()
            user_id = cursor.lastrowid
            
            # Send welcome email (non-blocking, don't fail if email fails)
            try:
                from engine.email_service import send_welcome_email
                send_welcome_email(name, email)
            except Exception:
                pass
            
            # Set HTTP-Only session cookie
            create_session_cookie(response, user_id, email, name)
            return AuthResponse(
                user_id=user_id,
                email=email,
                name=name,
                picture=picture,
                is_new_user=True,
            )
    finally:
        conn.close()


@router.get("/auth/me")
async def get_current_user(user_id: int):
    """Get user profile by ID (for session restoration)."""
    conn = get_connection()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "user_id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "picture": user["picture"],
            "created_at": user["created_at"],
            "last_login": user["last_login"],
        }
    finally:
        conn.close()


async def _verify_google_token(token: str) -> dict | None:
    """
    Verify Google ID token using Google's tokeninfo endpoint.
    
    Returns user info dict if valid, None if invalid.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
            )
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            # Verify the token was meant for our app
            if data.get("aud") != GOOGLE_CLIENT_ID:
                return None
            
            # Verify email is verified
            if data.get("email_verified") != "true":
                return None
            
            return {
                "sub": data.get("sub"),
                "email": data.get("email"),
                "name": data.get("name"),
                "picture": data.get("picture"),
            }
    except Exception:
        return None


@router.post("/auth/logout")
async def logout(response: Response):
    """Clear the session cookie."""
    from engine.session import clear_session_cookie
    clear_session_cookie(response)
    return {"success": True}


@router.get("/auth/session")
async def get_session_info(request: Request):
    """
    Get current session from HTTP-Only cookie.
    Used by frontend to check auth state without localStorage.
    """
    from engine.session import get_session, is_founder
    session = get_session(request)
    if not session:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "user_id": session.get("user_id"),
        "email": session.get("email"),
        "name": session.get("name"),
        "is_founder": is_founder(request),
    }
