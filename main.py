"""
Options Tycoon — Main Application Entry Point

Behavioral intelligence platform for options traders.
FastAPI server serving vanilla HTML/JS/CSS frontend, backed by SQLite/PostgreSQL.
"""

import os
import sys
import logging
from pathlib import Path

# Ensure the app directory is in Python path (needed for Railway/cloud deployment)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from db.database import init_db

# --- Configuration ---
IS_PRODUCTION = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("PRODUCTION"))
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

# --- Logging ---
logging.basicConfig(level=logging.INFO if IS_PRODUCTION else logging.DEBUG)
logger = logging.getLogger("options_tycoon")

# --- Rate Limiter (P0-10: Per-user for authenticated, per-IP for unauthenticated) ---
limiter = Limiter(key_func=get_remote_address)

# --- App Initialization ---
app = FastAPI(
    title="Options Tycoon",
    description="Behavioral intelligence platform for options traders",
    version="0.1.0",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)
app.state.limiter = limiter


# --- Rate Limit Error Handler ---
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": True, "detail": "Too many requests. Please wait a moment and try again."},
    )


# --- Global Error Handler (P0-7: No stack traces in production) ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions. Return generic error. Log details server-side."""
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {type(exc).__name__}: {exc}")
    if not IS_PRODUCTION:
        # In dev, include error details for debugging
        import traceback
        return JSONResponse(
            status_code=500,
            content={"error": True, "detail": str(exc), "traceback": traceback.format_exc()},
        )
    # In production, generic message only
    return JSONResponse(
        status_code=500,
        content={"error": True, "detail": "An internal error occurred. Please try again or contact support."},
    )


# --- Startup & Shutdown ---
@app.on_event("startup")
def startup():
    """Initialize the database schema, run migrations, and settle expired positions."""
    init_db()
    # Run pending migrations (safe to call every startup)
    from db.migrations import run_migrations
    run_migrations()
    _settle_expired_positions()


@app.on_event("shutdown")
def shutdown():
    """Graceful shutdown — log and clean up."""
    logger.info("Application shutting down gracefully.")


def _settle_expired_positions():
    """Check for and settle any positions past their expiration date."""
    try:
        from engine.settlement import auto_settle_expired
        auto_settle_expired()
    except Exception as e:
        logger.warning(f"Settlement check skipped: {e}")


# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Route Includes ---
from routes.portfolio import router as portfolio_router
from routes.trading import router as trading_router
from routes.data import router as data_router
from routes.behavioral import router as behavioral_router
from routes.telemetry import router as telemetry_router
from routes.real_trades import router as real_trades_router
from routes.timemachine import router as timemachine_router
from routes.simulation import router as simulation_router
from routes.report import router as report_router
from routes.feedback import router as feedback_router
from routes.auth import router as auth_router
from routes.dashboard import router as dashboard_router
from routes.live import router as live_router

app.include_router(portfolio_router, prefix="/api")
app.include_router(trading_router, prefix="/api")
app.include_router(data_router, prefix="/api")
app.include_router(behavioral_router, prefix="/api")
app.include_router(telemetry_router, prefix="/api")
app.include_router(real_trades_router, prefix="/api")
app.include_router(timemachine_router, prefix="/api")
app.include_router(simulation_router, prefix="/api")
app.include_router(report_router, prefix="/api")
app.include_router(feedback_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(live_router)


# --- Static File Serving ---
# Ensure output directory exists (gitignored, but needed at runtime for signal engine)
Path("output").mkdir(exist_ok=True)
app.mount("/output", StaticFiles(directory="output"), name="output")
app.mount("/static", StaticFiles(directory="static"), name="static")


# --- Root & Health ---
@app.get("/")
async def root():
    """Redirect root to the marketing landing page."""
    return RedirectResponse(url="/static/landing.html")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "app": "Options Tycoon", "version": "0.1.0"}


@app.get("/admin/stats")
async def admin_stats():
    """Quick admin stats — user count, upload count. Not protected (low risk for beta)."""
    from db.database import get_connection
    conn = get_connection()
    try:
        users = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()
        uploads = conn.execute("SELECT COUNT(*) as cnt FROM upload_history").fetchone()
        return {
            "total_users": users["cnt"] if users else 0,
            "total_uploads": uploads["cnt"] if uploads else 0,
        }
    except Exception:
        return {"total_users": "unknown", "total_uploads": "unknown"}
    finally:
        conn.close()


@app.get("/admin/test-email")
async def test_email():
    """Send a test email to verify the email system works."""
    from engine.email_service import RESEND_API_KEY
    import httpx as hx
    
    has_key = bool(RESEND_API_KEY)
    key_preview = RESEND_API_KEY[:10] + "..." if RESEND_API_KEY else "EMPTY"
    
    if not has_key:
        return {"sent": False, "error": "RESEND_API_KEY not set", "key_preview": key_preview}
    
    # Direct API call with full error capture
    try:
        response = hx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={
                "from": "Options Tycoon <onboarding@resend.dev>",
                "to": ["buyai.support@gmail.com"],
                "subject": "Test from Options Tycoon",
                "html": "<h1>It works!</h1><p>Email system is live.</p>",
            },
            timeout=10,
        )
        return {
            "sent": response.status_code == 200,
            "status_code": response.status_code,
            "response": response.text[:200],
            "key_preview": key_preview,
        }
    except Exception as e:
        return {"sent": False, "error": str(e), "key_preview": key_preview}
