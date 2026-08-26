"""
Kite Auth — Zerodha OAuth token management.
Handles daily login redirect flow per SEBI guidelines.

Flow:
1. User clicks "Login to Zerodha" on live.html
2. Redirected to Kite login page
3. Kite redirects back with request_token
4. Backend exchanges for access_token
5. Token stored in memory (session-only)

NOTE: This module is scaffolded. Connect external Kite API when ready.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "kite_creds.json"

# In-memory token store (resets on restart)
_session = {
    "access_token": None,
    "authenticated": False,
    "user_name": None,
    "login_time": None,
}


def get_login_url() -> str:
    """Generate Kite OAuth login URL."""
    config = _load_config()
    api_key = config.get("api_key", "")
    if not api_key or "YOUR_" in api_key:
        return "NOT_CONFIGURED"
    return f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"


def handle_callback(request_token: str) -> dict:
    """
    Exchange request_token for access_token.
    Called when Kite redirects back to our callback URL.
    
    NOTE: Requires kiteconnect library and valid API secret.
    Scaffolded for now — will connect when Kite subscription is active.
    """
    config = _load_config()
    api_key = config.get("api_key", "")
    api_secret = config.get("api_secret", "")
    
    if not api_key or not api_secret or "YOUR_" in api_key:
        logger.warning("Kite credentials not configured")
        return {"success": False, "error": "Kite credentials not configured in config/kite_creds.json"}
    
    try:
        from kiteconnect import KiteConnect
        kite = KiteConnect(api_key=api_key)
        data = kite.generate_session(request_token, api_secret=api_secret)
        
        _session["access_token"] = data["access_token"]
        _session["authenticated"] = True
        _session["user_name"] = data.get("user_name", "Unknown")
        _session["login_time"] = data.get("login_time")
        
        logger.info(f"Kite authenticated: {_session['user_name']}")
        return {"success": True, "user": _session["user_name"]}
    
    except ImportError:
        logger.warning("kiteconnect not installed — running in offline mode")
        return {"success": False, "error": "kiteconnect library not installed (pip install kiteconnect)"}
    except Exception as e:
        logger.error(f"Kite auth failed: {e}")
        return {"success": False, "error": str(e)}


def is_authenticated() -> bool:
    """Check if we have a session flag set (in-memory).

    NOTE: This only reflects the in-memory flag — it does NOT prove the token
    is still valid with Kite (the token expires daily ~6 AM IST, and Railway
    restarts wipe this session). For a real check, use verify_token_live().
    """
    return _session.get("authenticated", False)


def verify_token_live() -> bool:
    """
    Make a lightweight live call to Kite to confirm the token actually works.
    Returns True only if Kite accepts the token right now. On any failure
    (expired token, restart, network), marks the session unauthenticated so
    the app falls back honestly instead of trusting a dead flag.
    """
    if not _session.get("authenticated") or not _session.get("access_token"):
        return False
    try:
        from kiteconnect import KiteConnect
        config = _load_config()
        kite = KiteConnect(api_key=config.get("api_key", ""))
        kite.set_access_token(_session["access_token"])
        profile = kite.profile()  # cheap authenticated call
        if profile:
            _session["user_name"] = profile.get("user_name", _session.get("user_name"))
            return True
        return False
    except Exception as e:
        # Token is dead/expired or lib missing — reset so we don't mislead.
        logger.warning(f"Kite token verification failed — marking unauthenticated: {str(e)[:120]}")
        _session["authenticated"] = False
        _session["access_token"] = None
        return False


def get_access_token() -> str:
    """Get current access token (None if not authenticated)."""
    return _session.get("access_token")


def get_session_info() -> dict:
    """Get non-sensitive session info for UI display.

    Includes 'token_live' — the result of an actual live Kite check — so the
    UI can show whether the connection is genuinely working, not just flagged.
    """
    live = verify_token_live()
    return {
        "authenticated": _session["authenticated"],
        "token_live": live,
        "user": _session.get("user_name"),
        "login_time": _session.get("login_time"),
    }


def get_kite_client():
    """Get an authenticated KiteConnect instance, or None."""
    if not _session.get("authenticated") or not _session.get("access_token"):
        return None
    try:
        from kiteconnect import KiteConnect
        config = _load_config()
        kite = KiteConnect(api_key=config.get("api_key", ""))
        kite.set_access_token(_session["access_token"])
        return kite
    except Exception:
        return None


def _load_config() -> dict:
    """Load Kite credentials from env vars (Railway) or config file (local dev)."""
    import os
    # Prefer environment variables (production on Railway)
    api_key = os.environ.get("KITE_API_KEY", "")
    api_secret = os.environ.get("KITE_API_SECRET", "")
    if api_key and api_secret and "YOUR_" not in api_key:
        return {"api_key": api_key, "api_secret": api_secret}
    
    # Fallback to config file (local development)
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        return json.load(f)
