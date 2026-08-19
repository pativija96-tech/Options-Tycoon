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
    Auto-generate signal + send Telegram alert with strikes.
    
    NO auto-execution — user places orders manually via Kite web basket order
    (gets spread margin benefit that API individual legs don't get).
    
    Signal is generated and saved so the live-nifty page shows it.
    Telegram alert sent with exact strikes to place.
    """
    import httpx
    import os
    port = os.environ.get("PORT", "8000")

    if _TRADING_MODE == "nifty":
        logger.info("Auto-trade: checking Kite authentication before NIFTY signal generation...")
        try:
            from engine.broker.kite_auth import is_authenticated
            if not is_authenticated():
                logger.warning("NIFTY signal: Kite not authenticated — using yfinance for price data.")
        except Exception as e:
            logger.debug(f"Kite auth check: {e}")
    
    logger.info(f"Generating {_TRADING_MODE.upper()} signal (manual execution mode)...")
    try:
        # Generate signal only — NO execution
        resp = httpx.post(
            f"http://localhost:{port}/api/live/generate-signal",
            headers={"X-User-Id": "1"},
            timeout=120,
        )
        gen_result = resp.json()
        logger.info(f"Signal generated: {gen_result}")
        
        if not gen_result.get("success"):
            error_msg = gen_result.get('error') or gen_result.get('detail') or str(gen_result)[:200]
            logger.warning(f"Signal generation failed: {error_msg}")
            _send_telegram_alert(f"⚠️ Signal generation failed: {error_msg}")
            return
        
        # Load the full signal to get strikes for Telegram
        try:
            import json
            from pathlib import Path
            signal_path = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "output" / f"today_signal_{_TRADING_MODE}.json"
            if signal_path.exists():
                with open(signal_path) as f:
                    signal = json.load(f)
                
                if signal.get("action") == "trade":
                    trade = signal.get("trade", {})
                    legs = trade.get("legs", [])
                    projected = signal.get("projected_open", 0)
                    profit_target = trade.get("profit_target", {})
                    exec_seq = trade.get("execution_sequence", {})
                    
                    # Build SEQUENTIAL leg format (hedges first, then shorts — NOT basket)
                    basket_text = ""
                    if exec_seq:
                        basket_text = "\n\n⚙️ PLACE ONE ORDER AT A TIME (not basket):"
                        basket_text += "\n\nPHASE A — Buy hedges first, wait for COMPLETE:"
                        for b in exec_seq.get("phase_a_hedges_first", []):
                            basket_text += f"\n  {b['seq']}. {b['action']} {b['symbol']} × {b['qty']} (LIMIT/NRML)"
                        basket_text += "\n\nPHASE B — Then sell shorts:"
                        for b in exec_seq.get("phase_b_shorts_after_hedges_filled", []):
                            basket_text += f"\n  {b['seq']}. {b['action']} {b['symbol']} × {b['qty']} (LIMIT/NRML)"
                    else:
                        basket_text = "\n\nLegs (place ONE at a time, hedges/BUY first):"
                        for leg in legs:
                            basket_text += f"\n  {leg['action']} NIFTY {leg['strike']} {leg['option']} @ ~Rs.{leg.get('premium_est', 0):.1f}"
                    
                    # Profit target info
                    pt_text = ""
                    if profit_target:
                        pt_text = f"\n\n🎯 PROFIT TARGET: Exit at Rs.{profit_target.get('value', 0):.0f} profit ({profit_target.get('pct', 0.5)*100:.0f}% of max)"
                        pt_text += f"\n   Buy back all legs when total cost ≤ Rs.{profit_target.get('exit_premium_total', 0):.0f}"
                    
                    msg = (
                        f"📊 NIFTY IC Signal Ready\n\n"
                        f"NIFTY: {projected:.0f}\n"
                        f"Expiry: {trade.get('expiry_date', 'Tue')}\n"
                        f"{basket_text}\n"
                        f"\nReward: Rs.{trade.get('net_max_profit', trade.get('max_profit', 0)):.0f}"
                        f"\nRisk: Rs.{trade.get('net_max_loss', trade.get('max_loss', 0)):.0f}"
                        f"{pt_text}"
                        f"\n\n⚠️ Place each leg as an INDIVIDUAL order (NOT basket)."
                        f"\nBUY hedges first → wait COMPLETE → then SELL shorts."
                        f"\nLIMIT at LTP. Hedges must fill before shorts (spread margin)."
                    )
                    _send_telegram_alert(msg)
                else:
                    _send_telegram_alert(f"⏭️ No trade today: {signal.get('reason', 'skip')}")
        except Exception as e:
            logger.warning(f"Telegram signal alert failed: {e}")
            _send_telegram_alert(f"📊 Signal generated — check live-nifty page. (Detail error: {str(e)[:50]})")
        
    except Exception as e:
        logger.error(f"Signal generation failed: {e}")
        _send_telegram_alert(f"🚨 Signal generation error: {str(e)[:100]}")


def _send_telegram_alert(message: str):
    """Send alert via Telegram (if configured). Email disabled — user generates signals manually."""
    # Email disabled — user logs in and generates signals manually each week
    # Keeping Telegram as optional secondary alert (non-blocking)
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
