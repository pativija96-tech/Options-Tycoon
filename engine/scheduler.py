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
    TRADE_HOUR_UTC = 3   # 9:20 AM IST (5 min after open — gives time to login)
    TRADE_MINUTE_UTC = 50


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
    """
    Auto-generate signal + execute.
    
    QQQ mode: Fully automated (IBKR OAuth doesn't need daily login)
    NIFTY mode: Only executes if Kite is authenticated (user logged in today)
    """
    import httpx
    import os
    port = os.environ.get("PORT", "8000")

    if _TRADING_MODE == "nifty":
        logger.info("Auto-trade: checking Kite authentication before NIFTY execution...")
        # Check if user has logged into Kite today
        try:
            from engine.broker.kite_auth import is_authenticated
            if not is_authenticated():
                logger.warning("NIFTY auto-trade SKIPPED — Kite not authenticated. Login required.")
                _send_telegram_alert("⏭️ NIFTY trade skipped — Kite not authenticated. Login to Zerodha to enable auto-trade.")
                return
        except Exception as e:
            logger.error(f"Kite auth check failed: {e}")
            return
    
    logger.info(f"Auto-trade: generating {_TRADING_MODE.upper()} signal + executing...")
    try:
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
            _send_telegram_alert(f"⚠️ Signal generation failed: {gen_result.get('error', 'unknown')}")
            return
        
        # Step 2: Execute live
        resp2 = httpx.post(
            f"http://localhost:{port}/api/live/live-execute",
            headers={"X-User-Id": "1"},
            timeout=60,
        )
        exec_result = resp2.json()
        logger.info(f"Execution result: {exec_result}")
        
        # Notify on NIFTY execution result
        if _TRADING_MODE == "nifty":
            if exec_result.get("success"):
                placed = exec_result.get("placed", 4)
                _send_telegram_alert(f"✅ NIFTY IC placed — {placed} legs filled. Check Kite app for confirmation.")
            else:
                error = exec_result.get("error") or exec_result.get("message", "Unknown")
                _send_telegram_alert(f"❌ NIFTY IC execution failed: {error}")
        
    except Exception as e:
        logger.error(f"Auto-trade failed: {e}")
        _send_telegram_alert(f"🚨 Auto-trade error: {str(e)[:100]}")


def _send_telegram_alert(message: str):
    """Send a Telegram alert (best-effort, non-blocking)."""
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from scripts.telegram_bot import send_alert
        send_alert("error", message)
    except Exception as e:
        logger.debug(f"Telegram alert skipped: {e}")


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
        
        # --- Auto-trade (both modes — generate + execute at market open) ---
        is_trade_time = now.hour == TRADE_HOUR_UTC and now.minute == TRADE_MINUTE_UTC
        trade_not_run = last_trade_date != today
        
        if is_weekday and is_trade_time and trade_not_run:
            logger.info(f"Auto-trade trigger at {now.isoformat()} UTC ({_TRADING_MODE.upper()})")
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
