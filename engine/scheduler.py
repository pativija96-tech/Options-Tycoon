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

# EOD/Trade schedule times (UTC)
# NIFTY EOD: 3:35 PM IST = 10:05 UTC
# QQQ Trade: 9:35 AM EST = 13:35 UTC (5 min after open)
# QQQ EOD: 4:05 PM EST = 20:05 UTC (5 min after close)
import os as _sched_os
_TRADING_MODE = _sched_os.environ.get("TRADING_MODE", "qqq").lower()

if _TRADING_MODE == "qqq":
    EOD_HOUR_UTC = 20   # 4:05 PM EST (QQQ close)
    EOD_MINUTE_UTC = 5
    TRADE_HOUR_UTC = 13  # 9:35 AM EST (QQQ open)
    TRADE_MINUTE_UTC = 35
else:
    EOD_HOUR_UTC = 10   # 3:35 PM IST (NIFTY close)
    EOD_MINUTE_UTC = 5
    TRADE_HOUR_UTC = 3   # 9:15 AM IST (NIFTY open) — no auto-trade for NIFTY
    TRADE_MINUTE_UTC = 45


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


def _run_auto_trade():
    """Auto-generate signal + execute (QQQ mode). Runs at US market open."""
    logger.info("Auto-trade: generating QQQ signal + executing...")
    try:
        import httpx
        import os
        port = os.environ.get("PORT", "8000")
        
        # Step 1: Generate signal
        resp = httpx.post(
            f"http://localhost:{port}/api/live/generate-signal",
            headers={"X-User-Id": "1"},
            timeout=60,
        )
        gen_result = resp.json()
        logger.info(f"Signal generated: {gen_result}")
        
        if not gen_result.get("success"):
            logger.warning(f"Signal generation failed: {gen_result.get('error')}")
            return
        
        # Step 2: Execute live (if IBKR is configured)
        resp2 = httpx.post(
            f"http://localhost:{port}/api/live/live-execute",
            headers={"X-User-Id": "1"},
            timeout=60,
        )
        exec_result = resp2.json()
        logger.info(f"Execution result: {exec_result}")
        
    except Exception as e:
        logger.error(f"Auto-trade failed: {e}")


def _send_ibkr_heartbeat():
    """Send IBKR session heartbeat (tickle). Keeps REST session alive."""
    try:
        from engine.broker.ibkr_executor import get_ibkr_executor
        executor = get_ibkr_executor()
        if executor.is_configured and executor.access_token:
            ok = executor.send_heartbeat()
            if ok:
                logger.debug("IBKR heartbeat OK")
            else:
                logger.warning("IBKR heartbeat failed — session may expire")
    except Exception as e:
        logger.debug(f"IBKR heartbeat skipped: {e}")


def _ibkr_startup_auth():
    """
    Self-healing: Re-authenticate IBKR on scheduler startup.
    Handles Railway restarts — ensures session is ready before market open.
    """
    try:
        from engine.broker.ibkr_executor import get_ibkr_executor
        executor = get_ibkr_executor()
        if executor.is_configured:
            logger.info("Scheduler startup: authenticating IBKR session...")
            if executor.authenticate():
                logger.info("IBKR session ready (startup auth successful)")
            else:
                logger.warning("IBKR startup auth failed — will retry on next heartbeat cycle")
    except Exception as e:
        logger.warning(f"IBKR startup auth skipped: {e}")


def _scheduler_loop():
    """Background loop that checks time and triggers EOD + auto-trade + IBKR heartbeat."""
    logger.info("Scheduler loop started")
    last_eod_date = None
    last_trade_date = None
    last_heartbeat = 0.0  # epoch seconds
    startup_auth_done = False

    HEARTBEAT_INTERVAL = 55  # seconds (IBKR requires tickle every 60s)
    
    while not _stop_event.is_set():
        now = datetime.utcnow()
        today = now.date()
        
        # --- Self-healing: authenticate IBKR on first loop (handles Railway restarts) ---
        if not startup_auth_done and _TRADING_MODE == "qqq":
            _ibkr_startup_auth()
            startup_auth_done = True
            last_heartbeat = time.time()  # Reset heartbeat timer after auth
        
        # Only run on weekdays (Mon=0 through Fri=4)
        is_weekday = now.weekday() < 5
        
        # --- IBKR Heartbeat (every ~55 seconds, always) ---
        elapsed = time.time() - last_heartbeat
        if elapsed >= HEARTBEAT_INTERVAL:
            _send_ibkr_heartbeat()
            last_heartbeat = time.time()
        
        # --- EOD check ---
        is_eod_time = now.hour == EOD_HOUR_UTC and now.minute == EOD_MINUTE_UTC
        eod_not_run = last_eod_date != today
        
        if is_weekday and is_eod_time and eod_not_run:
            logger.info(f"EOD trigger at {now.isoformat()} UTC")
            _run_eod_job()
            last_eod_date = today
        
        # --- Auto-trade (QQQ mode only — generate + execute at market open) ---
        if _TRADING_MODE == "qqq":
            is_trade_time = now.hour == TRADE_HOUR_UTC and now.minute == TRADE_MINUTE_UTC
            trade_not_run = last_trade_date != today
            
            if is_weekday and is_trade_time and trade_not_run:
                logger.info(f"Auto-trade trigger at {now.isoformat()} UTC (QQQ)")
                _run_auto_trade()
                last_trade_date = today
        
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
