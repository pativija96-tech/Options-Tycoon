"""
Background Scheduler — Runs automated EOD check at 3:35 PM IST every weekday.

No manual action needed. The scheduler:
1. Checks if NIFTY breached short strikes (SL trigger)
2. On Tuesday (expiry): resolves the trade as win/loss
3. On other days: holds if safe, exits if breached

Uses APScheduler-free approach (threading + time check) to avoid
adding dependencies. Runs a simple loop in a background thread.
"""

import logging
import threading
import time
from datetime import datetime, timedelta

logger = logging.getLogger("options_tycoon.scheduler")

_scheduler_thread = None
_stop_event = threading.Event()

# EOD runs at 3:35 PM IST (10:05 AM UTC)
EOD_HOUR_UTC = 10
EOD_MINUTE_UTC = 5


def _run_eod_job():
    """Execute the EOD resolution logic."""
    logger.info("Scheduled EOD job triggered")
    try:
        import httpx
        import os
        port = os.environ.get("PORT", "8000")
        resp = httpx.post(
            f"http://localhost:{port}/api/live/run-eod",
            headers={"X-User-Id": "1"},
            timeout=60,
        )
        result = resp.json()
        logger.info(f"EOD result: {result}")
    except Exception as e:
        logger.error(f"Scheduled EOD failed: {e}")


def _scheduler_loop():
    """Background loop that checks time and triggers EOD."""
    logger.info("Scheduler loop started")
    last_run_date = None
    
    while not _stop_event.is_set():
        now = datetime.utcnow()
        today = now.date()
        
        # Only run on weekdays (Mon=0 through Fri=4)
        is_weekday = now.weekday() < 5
        
        # Check if it's time (3:35 PM IST = 10:05 UTC)
        is_time = now.hour == EOD_HOUR_UTC and now.minute == EOD_MINUTE_UTC
        
        # Haven't run today yet
        not_run_today = last_run_date != today
        
        if is_weekday and is_time and not_run_today:
            logger.info(f"EOD trigger at {now.isoformat()} UTC")
            _run_eod_job()
            last_run_date = today
        
        # Sleep 30 seconds between checks
        _stop_event.wait(30)
    
    logger.info("Scheduler loop stopped")


def start_scheduler():
    """Start the background scheduler thread."""
    global _scheduler_thread
    
    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.info("Scheduler already running")
        return
    
    _stop_event.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _scheduler_thread.start()
    logger.info("EOD scheduler started")


def stop_scheduler():
    """Stop the background scheduler."""
    _stop_event.set()
    if _scheduler_thread:
        _scheduler_thread.join(timeout=5)
    logger.info("EOD scheduler stopped")
