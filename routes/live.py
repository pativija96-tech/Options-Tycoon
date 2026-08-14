"""
Live Signal Engine Routes — Localhost-only (127.0.0.1) FastAPI endpoints.
Serves trade signals, gate status, auth state, and execution triggers.
"""

import json
import logging
from pathlib import Path
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from engine.session import require_founder

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live", tags=["live-signal-engine"], dependencies=[Depends(require_founder)])

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@router.get("/signal")
async def get_today_signal(request: Request, mode: str = None):
    """
    Return today's generated trade card.
    Accepts ?mode=nifty or ?mode=qqq to get mode-specific signal.
    Falls back to signal_history DB if file is missing (Railway redeploy).
    """
    import os
    requested_mode = (mode or request.query_params.get("mode", "")).lower()
    trading_mode = requested_mode if requested_mode in ("qqq", "nifty") else os.environ.get("TRADING_MODE", "qqq").lower()
    
    # Try mode-specific file first
    mode_signal_path = OUTPUT_DIR / f"today_signal_{trading_mode}.json"
    if mode_signal_path.exists():
        with open(mode_signal_path) as f:
            return json.load(f)
    
    # Fallback to generic file
    signal_path = OUTPUT_DIR / "today_signal.json"
    if signal_path.exists():
        with open(signal_path) as f:
            return json.load(f)
    
    # Fallback: load today's signal from DB (survives Railway redeploys)
    from datetime import date
    from db.signal_history import get_signal_history
    today = date.today().strftime("%Y-%m-%d")
    history = get_signal_history(days=1, limit=1)
    if history and history[0].get("signal_date") == today:
        full_json = history[0].get("full_signal_json")
        if full_json:
            try:
                return json.loads(full_json)
            except (json.JSONDecodeError, TypeError):
                pass
    
    return JSONResponse(
        status_code=404,
        content={"action": "skip", "reason": "No signal generated yet today"}
    )


@router.post("/generate-signal")
async def generate_signal(request: Request, mode: str = None):
    """
    Trigger signal generation.
    Accepts ?mode=nifty or ?mode=qqq to force a specific engine.
    Falls back to TRADING_MODE env var if not specified.
    """
    import sys
    import os
    import asyncio
    import json as json_mod
    from concurrent.futures import ThreadPoolExecutor
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    
    # Allow explicit mode override via query param (for page-specific requests)
    requested_mode = (mode or request.query_params.get("mode", "")).lower()
    trading_mode = requested_mode if requested_mode in ("qqq", "nifty") else os.environ.get("TRADING_MODE", "qqq").lower()
    
    logger.info(f"generate-signal called: requested_mode={requested_mode}, resolved={trading_mode}")
    
    try:
        if trading_mode == "qqq":
            from engine.signals.qqq_ic_engine import generate_qqq_signal
            gen_func = generate_qqq_signal
        else:
            from engine.signals.simple_ic_engine import generate_daily_signal
            gen_func = generate_daily_signal
        
        from db.signal_history import save_signal
        
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            result = await asyncio.wait_for(
                loop.run_in_executor(pool, gen_func),
                timeout=90
            )
        
        if not result:
            return {"success": False, "error": "Signal engine returned None"}
        
        # Save to separate files per mode (so each page reads its own signal)
        signal_filename = f"today_signal_{trading_mode}.json"
        signal_path = OUTPUT_DIR / signal_filename
        with open(signal_path, "w") as f:
            json_mod.dump(result, f, indent=2, default=str)
        
        # Also save as generic (for backward compatibility)
        generic_path = OUTPUT_DIR / "today_signal.json"
        with open(generic_path, "w") as f:
            json_mod.dump(result, f, indent=2, default=str)
        
        # Save to DB (survives redeploys)
        try:
            save_signal(result)
        except Exception:
            pass
        
        # Send Telegram notification (non-fatal)
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
            from telegram_bot import send_signal as tg_send
            tg_send(result)
        except Exception:
            pass
        
        return {"success": True, "mode": trading_mode, "action": result.get("action"), "direction": result.get("direction"), "market": result.get("market", "NIFTY")}
    except asyncio.TimeoutError:
        return JSONResponse(status_code=504, content={"success": False, "error": "Timed out."})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)[:200]})


@router.get("/gate-status")
async def get_gate_status(request: Request):
    """Return paper trading gate status for the logged-in user (computed from DB)."""
    user_id = request.headers.get("X-User-Id") or request.query_params.get("user_id") or "0"
    
    from db.database import get_connection
    conn = get_connection()
    try:
        # Get user's LIVE trades from DB (exclude paper trades)
        rows = conn.execute(
            "SELECT pnl, status FROM live_trades WHERE user_id = ? AND status IN ('win','loss') AND mode = 'live' ORDER BY id DESC LIMIT 30",
            (int(user_id),)
        ).fetchall()
        trades = [dict(r) for r in rows] if rows else []
        total = len(trades)
        
        if total == 0:
            return {
                "locked": True,
                "metrics": {"trade_count": False, "win_rate": False, "profit_factor": False, "avg_win_loss": False, "max_drawdown": False, "max_consec_losses": False, "expectancy": False},
                "metrics_detail": {"trade_count": "0/30", "win_rate": "--", "profit_factor": "--", "avg_win_loss": "--", "max_drawdown": "--", "max_consec_losses": "--", "expectancy": "--"},
                "total_trades": 0,
                "message": "No resolved trades yet. Execute signals and wait for EOD resolution."
            }
        
        # Compute 7 metrics from DB data
        wins = [t for t in trades if t["pnl"] and t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] and t["pnl"] < 0]
        win_count = len(wins)
        loss_count = len(losses)
        
        win_rate = win_count / total if total > 0 else 0
        total_wins = sum(t["pnl"] for t in wins) if wins else 0
        total_losses = abs(sum(t["pnl"] for t in losses)) if losses else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else (999 if total_wins > 0 else 0)
        avg_win = total_wins / win_count if win_count > 0 else 0
        avg_loss = total_losses / loss_count if loss_count > 0 else 1
        avg_win_loss = avg_win / avg_loss if avg_loss > 0 else 999
        
        # Drawdown
        import json as json_mod
        settings_path = Path(__file__).resolve().parent.parent / "config" / "settings.json"
        capital = 1000000
        if settings_path.exists():
            with open(settings_path) as f:
                capital = json_mod.load(f).get("capital", 1000000)
        
        equity = 0
        peak = 0
        max_dd = 0
        max_consec = 0
        current_streak = 0
        for t in reversed(trades):
            pnl = t["pnl"] or 0
            equity += pnl
            if equity > peak:
                peak = equity
            dd = (peak - equity) / capital if capital > 0 else 0
            if dd > max_dd:
                max_dd = dd
            if pnl < 0:
                current_streak += 1
                max_consec = max(max_consec, current_streak)
            else:
                current_streak = 0
        
        # Expectancy
        win_pct = win_rate
        loss_pct = 1 - win_pct
        expectancy = (win_pct * avg_win) - (loss_pct * avg_loss)
        
        # Check thresholds
        metrics = {
            "trade_count": total >= 30,
            "win_rate": win_rate > 0.50,
            "profit_factor": profit_factor > 1.5,
            "avg_win_loss": avg_win_loss > 1.0,
            "max_drawdown": max_dd < 0.15,
            "max_consec_losses": max_consec < 5,
            "expectancy": expectancy > 0,
        }
        metrics_detail = {
            "trade_count": f"{total}/30",
            "win_rate": f"{win_rate*100:.1f}%",
            "profit_factor": f"{profit_factor:.2f}",
            "avg_win_loss": f"{avg_win_loss:.2f}",
            "max_drawdown": f"{max_dd*100:.1f}%",
            "max_consec_losses": str(max_consec),
            "expectancy": f"Rs.{expectancy:.0f}",
        }
        
        all_pass = all(metrics.values())
        
        return {
            "locked": not all_pass,
            "metrics": metrics,
            "metrics_detail": metrics_detail,
            "total_trades": total,
            "all_pass": all_pass,
            "user_id": user_id,
        }
    except Exception as e:
        return {"locked": True, "metrics": {}, "metrics_detail": {}, "total_trades": 0, "error": str(e)[:100]}
    finally:
        conn.close()


@router.get("/auth-status")
async def get_auth_status():
    """Return Kite authentication state."""
    from engine.broker.kite_auth import get_session_info
    return get_session_info()


@router.get("/kite-login")
async def kite_login():
    """Redirect user to Kite OAuth login page."""
    from engine.broker.kite_auth import get_login_url
    url = get_login_url()
    if url == "NOT_CONFIGURED":
        return JSONResponse(status_code=500, content={"error": "Kite API key not configured in Railway env vars"})
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=url)


@router.get("/kite-callback")
async def kite_callback(request: Request):
    """Handle Kite OAuth callback — exchange request_token for access_token."""
    request_token = request.query_params.get("request_token")
    if not request_token:
        return JSONResponse(status_code=400, content={"error": "No request_token received from Kite"})
    
    from engine.broker.kite_auth import handle_callback
    result = handle_callback(request_token)
    
    if result.get("success"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/static/live-nifty.html?kite=connected")
    else:
        return JSONResponse(status_code=400, content=result)


@router.get("/live-prices")
async def get_live_prices(request: Request):
    """Fetch live LTP prices for given strikes using Kite API."""
    from engine.broker.kite_auth import is_authenticated, get_kite_client
    
    if not is_authenticated():
        return {"available": False, "reason": "Not authenticated. Login to Zerodha first."}
    
    kite = get_kite_client()
    if not kite:
        return {"available": False, "reason": "Kite client not available"}
    
    # Get strikes from today's signal
    signal_path = OUTPUT_DIR / "today_signal.json"
    if not signal_path.exists():
        return {"available": False, "reason": "No signal generated today"}
    
    with open(signal_path) as f:
        signal = json.load(f)
    
    trade = signal.get("trade", {})
    legs = trade.get("legs", [])
    if not legs:
        return {"available": False, "reason": "No legs in trade card"}
    
    # Build instrument symbols and fetch LTP
    try:
        # Get next expiry date for correct symbol format
        from datetime import date, timedelta
        today = date.today()
        # Next Tuesday (weekly expiry)
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        expiry_date = today + timedelta(days=days_until_tuesday)
        # Kite format: NIFTY + YY + M(short) + DD + Strike + CE/PE
        # Monthly format: NIFTY + YY + MON + Strike + CE/PE  
        # Weekly format: NIFTY + YY + M + DD + Strike + CE/PE (single digit month, 2 digit day)
        # Actually Kite uses: NIFTY2572224400CE = NIFTY + YY + 7(month) + 22(day) + strike + type
        yy = expiry_date.strftime("%y")  # 26
        mon = str(expiry_date.month)  # 7 (single digit for months 1-9, or O/N/D)
        if expiry_date.month == 10: mon = "O"
        elif expiry_date.month == 11: mon = "N" 
        elif expiry_date.month == 12: mon = "D"
        dd = expiry_date.strftime("%d")  # 22
        
        instruments = []
        for leg in legs:
            strike = leg.get("strike", 0)
            option_type = leg.get("option", "CE")
            # Format: NFO:NIFTY26722{strike}{type}
            symbol = f"NFO:NIFTY{yy}{mon}{dd}{strike}{option_type}"
            instruments.append(symbol)
        
        # Fetch LTP from Kite
        ltp_data = kite.ltp(instruments)
        
        prices = {}
        for inst, data in ltp_data.items():
            prices[inst] = data.get("last_price", 0)
        
        return {"available": True, "prices": prices, "instruments": instruments, "expiry": expiry_date.isoformat()}
    except Exception as e:
        return {"available": False, "reason": f"Kite LTP fetch failed: {str(e)[:200]}", "instruments": instruments if 'instruments' in dir() else []}


@router.post("/paper-execute")
async def paper_execute(request: Request):
    """Log today's signal as a paper trade for the logged-in user. One trade per user per day."""
    signal_path = OUTPUT_DIR / "today_signal.json"
    if not signal_path.exists():
        return JSONResponse(status_code=400, content={"error": "No signal to execute"})

    with open(signal_path) as f:
        signal = json.load(f)

    if signal.get("action") not in ("trade",):
        return JSONResponse(status_code=400, content={"error": "Signal is not a trade"})

    # Get user from request
    user_id = request.headers.get("X-User-Id") or request.query_params.get("user_id")
    if not user_id:
        user_id = "0"

    today = signal.get("date", "")

    # Check if user already executed today
    from db.database import get_connection
    import json as json_mod
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM live_trades WHERE user_id = ? AND date = ?",
            (int(user_id), today)
        ).fetchone()
        
        if existing:
            return JSONResponse(status_code=409, content={"error": "Already executed today. One trade per day.", "success": False})

        trade_data = signal.get("trade", {})
        conn.execute(
            """INSERT INTO live_trades (user_id, date, direction, confidence, strategy, legs, 
               entry_cost, max_loss, max_profit, sl_value, projected_open, width, status, mode)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', 'paper')""",
            (
                int(user_id),
                today,
                signal.get("direction", ""),
                signal.get("confidence", 0),
                trade_data.get("type", ""),
                json_mod.dumps(trade_data.get("legs", [])),
                trade_data.get("net_cost_total", 0),
                trade_data.get("max_loss", 0),
                trade_data.get("max_profit", 0),
                trade_data.get("sl_value", 0),
                signal.get("projected_open", 0),
                trade_data.get("width", 0),
            )
        )
        conn.commit()
        logger.info(f"Paper trade logged for user {user_id}: {trade_data.get('type')}")
        return {"success": True, "user_id": user_id, "message": "Paper trade logged"}
    except Exception as e:
        logger.error(f"DB insert failed: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)[:100]})
    finally:
        conn.close()


@router.get("/my-trades")
async def get_my_trades(request: Request):
    """Return trades for the logged-in user."""
    user_id = request.headers.get("X-User-Id") or request.query_params.get("user_id") or "0"
    from db.database import get_connection
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM live_trades WHERE user_id = ? ORDER BY id DESC LIMIT 50",
            (int(user_id),)
        ).fetchall()
        trades = [dict(r) for r in rows] if rows else []
        total = conn.execute("SELECT COUNT(*) as cnt FROM live_trades WHERE user_id = ?", (int(user_id),)).fetchone()
        wins = conn.execute("SELECT COUNT(*) as cnt FROM live_trades WHERE user_id = ? AND pnl > 0", (int(user_id),)).fetchone()
        return {
            "trades": trades,
            "total": total["cnt"] if total else 0,
            "wins": wins["cnt"] if wins else 0,
            "user_id": user_id,
        }
    except Exception as e:
        return {"trades": [], "total": 0, "wins": 0, "error": str(e)[:100]}
    finally:
        conn.close()


@router.get("/eod-report")
async def get_eod_report():
    """Return today's EOD report if available."""
    eod_path = OUTPUT_DIR / "eod_report.json"
    if not eod_path.exists():
        return {"available": False, "message": "No EOD report yet"}
    with open(eod_path) as f:
        return json.load(f)


@router.delete("/cleanup-old-trades")
async def cleanup_old_trades(request: Request):
    """Delete test/paper trades before a cutoff date. Keeps only real live trades."""
    from db.database import get_connection
    cutoff = request.query_params.get("before", "2026-08-05")
    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) as cnt FROM live_trades WHERE date < ?", (cutoff,)).fetchone()
        deleted_count = count["cnt"] if count else 0
        conn.execute("DELETE FROM live_trades WHERE date < ?", (cutoff,))
        conn.commit()
        return {"success": True, "deleted": deleted_count, "cutoff": cutoff}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)[:200]})
    finally:
        conn.close()


@router.post("/run-eod")
async def run_eod():
    """
    Smart EOD Resolution:
    - Iron Condors: check if NIFTY breached short strikes (SL trigger) OR if it's expiry day
    - Check profit target: if position can be closed at 50% profit, flag PROFIT_TARGET_MET
    - If breached → resolve as loss (max loss)
    - If expiry day (Tuesday) and in range → resolve as win (full premium)
    - If not expiry and in range → leave open (hold to expiry)
    """
    from db.database import get_connection
    from datetime import date
    
    # Load profit target config
    profit_target_pct = 0.50
    try:
        config_path = Path(__file__).resolve().parent.parent / "config" / "settings.json"
        if config_path.exists():
            with open(config_path) as f:
                _cfg = json.load(f)
            profit_target_pct = _cfg.get("nifty", {}).get("profit_target_pct", 0.50)
    except Exception:
        pass
    
    try:
        # Fetch NIFTY data — Kite REQUIRED for accurate resolution
        nifty_close = None
        nifty_high = None
        nifty_low = None
        data_source = None
        
        # Try Kite (real-time, accurate)
        try:
            from engine.broker.kite_auth import is_authenticated, get_kite_client
            if is_authenticated():
                kite = get_kite_client()
                if kite:
                    ohlc = kite.ohlc(["NSE:NIFTY 50"])
                    if "NSE:NIFTY 50" in ohlc:
                        nd = ohlc["NSE:NIFTY 50"]["ohlc"]
                        nifty_close = ohlc["NSE:NIFTY 50"]["last_price"]
                        nifty_high = nd.get("high")
                        nifty_low = nd.get("low")
                        data_source = "kite"
        except Exception:
            pass
        
        # If Kite unavailable — try yfinance as fallback (for after-hours when Kite token may have expired)
        if not nifty_close:
            import yfinance as yf
            data = yf.download("^NSEI", period="2d", progress=False, timeout=15)
            if data is not None and len(data) >= 1:
                close_col = data["Close"]
                if hasattr(close_col, "columns"):
                    close_col = close_col.iloc[:, 0]
                nifty_close = float(close_col.iloc[-1])
                try:
                    high_col = data["High"]
                    low_col = data["Low"]
                    if hasattr(high_col, "columns"):
                        high_col = high_col.iloc[:, 0]
                        low_col = low_col.iloc[:, 0]
                    nifty_high = float(high_col.iloc[-1])
                    nifty_low = float(low_col.iloc[-1])
                except Exception:
                    pass
                data_source = "yfinance"
        
        if not nifty_close:
            return JSONResponse(status_code=500, content={"success": False, "error": "Could not fetch NIFTY data. Login to Zerodha first or try after market hours."})
        
        today = date.today()
        is_expiry_day = today.weekday() == 1  # Tuesday = 1
        
        conn = get_connection()
        open_trades = conn.execute("SELECT * FROM live_trades WHERE status IN ('open', 'PROFIT_TARGET_MET')").fetchall()
        
        resolved_count = 0
        held_count = 0
        profit_target_count = 0
        results = []
        
        for trade in open_trades:
            trade_dict = dict(trade)
            strategy = trade_dict.get("strategy", "")
            max_profit = trade_dict.get("max_profit", 0) or 0
            max_loss = trade_dict.get("max_loss", 0) or 0
            legs_json = trade_dict.get("legs", "[]")
            
            try:
                import json as jmod
                legs = jmod.loads(legs_json) if isinstance(legs_json, str) else legs_json
            except Exception:
                legs = []
            
            if "iron_condor" in strategy:
                # Get short strikes
                short_call = 0
                short_put = 0
                for leg in legs:
                    if leg.get("action") == "SELL" and leg.get("option") == "CE":
                        short_call = leg.get("strike", 0)
                    if leg.get("action") == "SELL" and leg.get("option") == "PE":
                        short_put = leg.get("strike", 0)
                
                # Check SL breach (using high/low if available, else close)
                check_high = nifty_high or nifty_close
                check_low = nifty_low or nifty_close
                
                breached = check_high >= short_call or check_low <= short_put
                in_range = short_put < nifty_close < short_call
                
                if breached:
                    # SL triggered — resolve as loss immediately
                    pnl = -max_loss
                    status = "loss"
                    exit_reason = "sl_breach"
                    conn.execute(
                        "UPDATE live_trades SET status=?, pnl=?, nifty_close=?, exit_reason=?, resolved_at=datetime('now') WHERE id=?",
                        (status, round(pnl, 2), nifty_close, exit_reason, trade_dict["id"])
                    )
                    resolved_count += 1
                    results.append({"id": trade_dict["id"], "action": "SL_TRIGGERED", "pnl": pnl})
                    
                elif is_expiry_day:
                    # Expiry day — resolve based on close position
                    if in_range:
                        pnl = max_profit
                        status = "win"
                    else:
                        pnl = -max_loss
                        status = "loss"
                    exit_reason = "expiry"
                    conn.execute(
                        "UPDATE live_trades SET status=?, pnl=?, nifty_close=?, exit_reason=?, resolved_at=datetime('now') WHERE id=?",
                        (status, round(pnl, 2), nifty_close, exit_reason, trade_dict["id"])
                    )
                    resolved_count += 1
                    results.append({"id": trade_dict["id"], "action": "EXPIRED", "pnl": pnl})
                    
                elif in_range and max_profit > 0:
                    # Check profit target: NIFTY well within range suggests premium has decayed
                    # Distance from nearest short strike as % of total range
                    range_width = short_call - short_put
                    dist_to_call = short_call - nifty_close
                    dist_to_put = nifty_close - short_put
                    min_dist = min(dist_to_call, dist_to_put)
                    cushion_pct = min_dist / (range_width / 2) if range_width > 0 else 0
                    
                    # If NIFTY is comfortably in the middle (>60% cushion on both sides)
                    # and we're past 50% of time to expiry, flag profit target
                    trade_date_str = trade_dict.get("date", "")
                    days_held = 0
                    if trade_date_str:
                        try:
                            from datetime import datetime as dt
                            trade_dt = dt.strptime(trade_date_str, "%Y-%m-%d").date()
                            days_held = (today - trade_dt).days
                        except:
                            pass
                    
                    # Profit target logic: if held 2+ days AND well in range, mark for exit
                    if days_held >= 2 and cushion_pct >= 0.40 and trade_dict.get("status") != "PROFIT_TARGET_MET":
                        profit_target_value = round(max_profit * profit_target_pct, 2)
                        conn.execute(
                            "UPDATE live_trades SET status='PROFIT_TARGET_MET' WHERE id=?",
                            (trade_dict["id"],)
                        )
                        profit_target_count += 1
                        results.append({
                            "id": trade_dict["id"], 
                            "action": "PROFIT_TARGET_MET",
                            "target_profit": profit_target_value,
                            "cushion_pct": round(cushion_pct * 100, 1),
                            "days_held": days_held,
                            "instruction": f"EXIT NOW — close all 4 legs. Target profit Rs.{profit_target_value:.0f} ({profit_target_pct*100:.0f}% of max). NIFTY at {nifty_close:.0f}, {cushion_pct*100:.0f}% cushion to nearest strike.",
                        })
                    else:
                        held_count += 1
                        results.append({"id": trade_dict["id"], "action": "HOLDING", "in_range": in_range, "nifty": nifty_close, "cushion_pct": round(cushion_pct * 100, 1)})
                else:
                    # Not expiry, not breached — hold position
                    held_count += 1
                    results.append({"id": trade_dict["id"], "action": "HOLDING", "in_range": in_range, "nifty": nifty_close})
            
            else:
                # Non-IC strategies — resolve at close (legacy behavior)
                projected_open = trade_dict.get("projected_open") or nifty_close
                direction = trade_dict.get("direction", "bullish")
                nifty_move = nifty_close - projected_open
                
                if direction == "bullish" and nifty_move > 0:
                    pnl = min(abs(nifty_move) * 65 * 0.3, max_profit)
                elif direction == "bearish" and nifty_move < 0:
                    pnl = min(abs(nifty_move) * 65 * 0.3, max_profit)
                else:
                    pnl = -max_loss
                
                status = "win" if pnl > 0 else "loss"
                conn.execute(
                    "UPDATE live_trades SET status=?, pnl=?, nifty_close=?, exit_reason='eod_resolution', resolved_at=datetime('now') WHERE id=?",
                    (status, round(pnl, 2), nifty_close, trade_dict["id"])
                )
                resolved_count += 1
        
        conn.commit()
        conn.close()
        
        # Send Telegram alert if profit target hit
        if profit_target_count > 0:
            try:
                from engine.scheduler import _send_telegram_alert
                for r in results:
                    if r.get("action") == "PROFIT_TARGET_MET":
                        _send_telegram_alert(f"🎯 PROFIT TARGET: {r['instruction']}")
            except Exception:
                pass
        
        return {
            "success": True,
            "resolved": resolved_count,
            "held": held_count,
            "profit_target_hit": profit_target_count,
            "nifty_close": nifty_close,
            "nifty_high": nifty_high,
            "nifty_low": nifty_low,
            "is_expiry_day": is_expiry_day,
            "data_source": data_source,
            "results": results,
        }
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)[:200]})


@router.get("/settings")
async def get_settings():
    """Return current capital and risk settings (non-sensitive)."""
    import os
    settings_path = CONFIG_DIR / "settings.json"
    if not settings_path.exists():
        return {"capital": 1000, "risk_per_trade": 0.70, "risk_per_day": 0.70, "trading_mode": "qqq"}
    with open(settings_path) as f:
        settings = json.load(f)
    trading_mode = settings.get("trading_mode", os.environ.get("TRADING_MODE", "qqq"))
    # Return mode-specific capital
    if trading_mode == "nifty":
        capital = settings.get("nifty", {}).get("capital", settings.get("capital", 75000))
    else:
        capital = settings.get("qqq", {}).get("capital", settings.get("capital", 1000))
    return {
        "trading_mode": trading_mode,
        "capital": capital,
        "risk_per_trade": settings.get("risk_per_trade"),
        "risk_per_day": settings.get("risk_per_day"),
    }


@router.get("/open-positions")
async def get_open_positions(request: Request):
    """Return all open (unresolved) trades for the user with current suggestions."""
    user_id = request.headers.get("X-User-Id") or request.query_params.get("user_id") or "0"
    from db.database import get_connection
    
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM live_trades WHERE user_id = ? AND status = 'open' AND mode = 'live' ORDER BY id DESC",
            (int(user_id),)
        ).fetchall()
        
        if not rows:
            return {"positions": [], "nifty_current": None}
        
        # Fetch current NIFTY price — Kite first, yfinance fallback
        nifty_current = None
        data_source = None
        
        try:
            from engine.broker.kite_auth import is_authenticated, get_kite_client
            if is_authenticated():
                kite = get_kite_client()
                if kite:
                    ltp = kite.ltp(["NSE:NIFTY 50"])
                    if "NSE:NIFTY 50" in ltp:
                        nifty_current = ltp["NSE:NIFTY 50"]["last_price"]
                        data_source = "kite"
        except Exception:
            pass
        
        if not nifty_current:
            try:
                import yfinance as yf
                data = yf.download("^NSEI", period="1d", progress=False, timeout=10)
                if data is not None and len(data) >= 1:
                    close_col = data["Close"]
                    if hasattr(close_col, "columns"):
                        close_col = close_col.iloc[:, 0]
                    nifty_current = float(close_col.iloc[-1])
                    data_source = "yfinance"
            except:
                pass
        
        positions = []
        for row in rows:
            trade = dict(row)
            entry_cost = trade.get("entry_cost", 0) or 0
            max_profit = trade.get("max_profit", 0) or 0
            max_loss = trade.get("max_loss", 0) or 0
            sl_value = trade.get("sl_value", 0) or 0
            projected_open = trade.get("projected_open", 0) or 0
            
            # Estimate current P&L if we have NIFTY price
            current_pnl = None
            suggestion = "Hold — no action needed"
            suggestion_type = "hold"
            
            if nifty_current and projected_open:
                strategy = trade.get("strategy", "")
                direction = trade.get("direction", "")
                width = trade.get("width", 200) or 200
                
                if "bull_call" in strategy:
                    try:
                        import json as jm
                        legs = jm.loads(trade.get("legs", "[]"))
                        long_strike = legs[0].get("strike", projected_open) if legs else projected_open
                    except:
                        long_strike = projected_open
                    
                    if nifty_current > long_strike:
                        intrinsic = min(nifty_current - long_strike, width)
                        current_pnl = round((intrinsic * 65) - abs(entry_cost))
                    else:
                        current_pnl = round(-abs(entry_cost))
                        
                elif "bear_put" in strategy:
                    try:
                        import json as jm
                        legs = jm.loads(trade.get("legs", "[]"))
                        long_strike = legs[0].get("strike", projected_open) if legs else projected_open
                    except:
                        long_strike = projected_open
                    
                    if nifty_current < long_strike:
                        intrinsic = min(long_strike - nifty_current, width)
                        current_pnl = round((intrinsic * 65) - abs(entry_cost))
                    else:
                        current_pnl = round(-abs(entry_cost))
                        
                elif "iron_condor" in strategy:
                    try:
                        import json as jm
                        legs = jm.loads(trade.get("legs", "[]"))
                        short_call = legs[0].get("strike", projected_open + 200) if len(legs) > 0 else projected_open + 200
                        short_put = legs[2].get("strike", projected_open - 200) if len(legs) > 2 else projected_open - 200
                    except:
                        short_call = projected_open + 200
                        short_put = projected_open - 200
                    
                    if short_put <= nifty_current <= short_call:
                        current_pnl = round(max_profit * 0.8)  # Approximate
                    else:
                        breach = max(nifty_current - short_call, short_put - nifty_current, 0)
                        current_pnl = round(max_profit - (breach * 65))
                
                # Generate suggestion
                if current_pnl is not None:
                    pnl_pct = current_pnl / max_profit if max_profit > 0 else 0
                    
                    if current_pnl > 0 and pnl_pct >= 0.7:
                        suggestion = "EXIT NOW — 70%+ of max profit reached. Lock gains."
                        suggestion_type = "exit"
                    elif current_pnl > 0 and pnl_pct >= 0.4:
                        suggestion = "TRAIL SL — Move SL to breakeven. Profit protected."
                        suggestion_type = "trail"
                    elif current_pnl > 0:
                        suggestion = "Hold — in profit, let it run."
                        suggestion_type = "hold"
                    elif abs(current_pnl) >= sl_value and sl_value > 0:
                        suggestion = "SL TRIGGERED — Exit immediately."
                        suggestion_type = "exit_loss"
                    else:
                        suggestion = "Hold — within acceptable loss range."
                        suggestion_type = "hold"
            
            trade["current_pnl"] = current_pnl
            trade["suggestion"] = suggestion
            trade["suggestion_type"] = suggestion_type
            trade["nifty_current"] = nifty_current
            positions.append(trade)
        
        return {"positions": positions, "nifty_current": nifty_current}
    except Exception as e:
        return {"positions": [], "error": str(e)[:200]}
    finally:
        conn.close()


@router.post("/exit-trade")
async def exit_trade(request: Request):
    """Manually exit/close a trade at current estimated P&L."""
    body = await request.json()
    trade_id = body.get("trade_id")
    exit_pnl = body.get("pnl", 0)
    
    if not trade_id:
        return JSONResponse(status_code=400, content={"error": "trade_id required"})
    
    from db.database import get_connection
    from datetime import datetime
    conn = get_connection()
    try:
        status = "win" if exit_pnl > 0 else "loss"
        conn.execute(
            "UPDATE live_trades SET status = ?, pnl = ?, exit_reason = 'manual_exit', resolved_at = ? WHERE id = ?",
            (status, exit_pnl, datetime.now().isoformat(), trade_id)
        )
        conn.commit()
        return {"success": True, "trade_id": trade_id, "status": status, "pnl": exit_pnl}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)[:100]})
    finally:
        conn.close()


@router.post("/trail-sl")
async def trail_sl(request: Request):
    """Update stop-loss for an open trade (trail to breakeven or lock profit)."""
    body = await request.json()
    trade_id = body.get("trade_id")
    new_sl = body.get("new_sl", 0)
    
    if not trade_id:
        return JSONResponse(status_code=400, content={"error": "trade_id required"})
    
    from db.database import get_connection
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE live_trades SET sl_value = ? WHERE id = ? AND status = 'open'",
            (new_sl, trade_id)
        )
        conn.commit()
        return {"success": True, "trade_id": trade_id, "new_sl": new_sl}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)[:100]})
    finally:
        conn.close()


# --- Upload Kite Tradebook CSV ---

@router.post("/upload-tradebook")
async def upload_tradebook(request: Request):
    """Parse uploaded Kite Tradebook CSV and import NIFTY F&O trades into live_trades.
    
    Kite Tradebook CSV columns:
    symbol, isin, trade_date, exchange, segment, series, trade_type, auction, quantity, price, trade_id, order_id, order_execution_time, expiry_date
    
    Handles:
    - Round-trips (buy+sell same symbol same day = realized P&L)
    - Open positions (net long/short at end of day)
    - Groups by date for trade history
    """
    from db.database import get_connection
    import csv
    import io
    
    user_id = request.headers.get("X-User-Id") or "1"
    
    # Parse multipart form data
    form = await request.form()
    file = form.get("file")
    if not file:
        return JSONResponse(status_code=400, content={"success": False, "error": "No file uploaded"})
    
    try:
        content = await file.read()
        filename = (file.filename or "").lower()
        
        # Helper: extract strike and option type from symbol
        def _parse_symbol(symbol):
            option_type = ""
            strike = ""
            sym_upper = symbol.upper()
            if "CE" in sym_upper:
                option_type = "CE"
                idx = sym_upper.rindex("CE")
                digits = ""
                for ch in reversed(symbol[:idx]):
                    if ch.isdigit():
                        digits = ch + digits
                    else:
                        break
                strike = digits
            elif "PE" in sym_upper:
                option_type = "PE"
                idx = sym_upper.rindex("PE")
                digits = ""
                for ch in reversed(symbol[:idx]):
                    if ch.isdigit():
                        digits = ch + digits
                    else:
                        break
                strike = digits
            return option_type, strike
        
        all_orders = []
        
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            # Excel file
            import openpyxl
            from io import BytesIO
            wb = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            headers_raw = next(rows_iter)
            headers = [str(h).strip().lower().replace(" ", "_") if h else f"col{i}" for i, h in enumerate(headers_raw)]
            
            for row_values in rows_iter:
                if not row_values:
                    continue
                row = dict(zip(headers, [v if v is not None else "" for v in row_values]))
                symbol = str(row.get("symbol", "") or row.get("tradingsymbol", "") or "").strip()
                
                if "NIFTY" not in symbol.upper():
                    continue
                if "CE" not in symbol.upper() and "PE" not in symbol.upper():
                    continue
                
                trade_date = str(row.get("trade_date", "") or "").strip()
                if not trade_date:
                    continue
                # Handle datetime objects from Excel
                if hasattr(row.get("trade_date"), "strftime"):
                    trade_date = row["trade_date"].strftime("%Y-%m-%d")
                else:
                    trade_date = trade_date.split("T")[0].split(" ")[0]
                
                trade_type = str(row.get("trade_type", "") or "").upper().strip()
                try:
                    quantity = abs(int(float(row.get("quantity", 0) or 0)))
                    price = float(row.get("price", 0) or 0)
                except (ValueError, TypeError):
                    continue
                
                if trade_type in ("BUY", "B"):
                    action = "BUY"
                elif trade_type in ("SELL", "S"):
                    action = "SELL"
                else:
                    continue
                
                option_type, strike = _parse_symbol(symbol)
                all_orders.append({
                    "date": trade_date, "symbol": symbol, "action": action,
                    "quantity": quantity, "price": price, "option_type": option_type, "strike": strike,
                })
            wb.close()
        else:
            # CSV file
            text = content.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            if reader.fieldnames:
                reader.fieldnames = [f.strip().lower().replace(" ", "_") for f in reader.fieldnames]
            
            for row in reader:
                symbol = (row.get("symbol", "") or row.get("tradingsymbol", "") or "").strip()
                if "NIFTY" not in symbol.upper():
                    continue
                if "CE" not in symbol.upper() and "PE" not in symbol.upper():
                    continue
                
                trade_date = (row.get("trade_date", "") or "").strip()
                if not trade_date:
                    continue
                trade_date = trade_date.split("T")[0]
                
                trade_type = (row.get("trade_type", "") or "").upper().strip()
                quantity = abs(int(float(row.get("quantity", 0) or 0)))
                price = float(row.get("price", 0) or 0)
                
                if trade_type in ("BUY", "B"):
                    action = "BUY"
                elif trade_type in ("SELL", "S"):
                    action = "SELL"
                else:
                    continue
                
                option_type, strike = _parse_symbol(symbol)
                all_orders.append({
                    "date": trade_date, "symbol": symbol, "action": action,
                    "quantity": quantity, "price": price, "option_type": option_type, "strike": strike,
                })
        
        if not all_orders:
            return JSONResponse(status_code=400, content={
                "success": False, 
                "error": "No NIFTY F&O trades found in the CSV. Make sure you're uploading the Tradebook from Console → Reports → Tradebook."
            })
        
        # Group by date
        from collections import defaultdict
        trades_by_date = defaultdict(list)
        for order in all_orders:
            trades_by_date[order["date"]].append(order)
        
        # Process each date: match round-trips and compute P&L
        conn = get_connection()
        imported_trades = []
        try:
            for trade_date, orders in sorted(trades_by_date.items()):
                # Check if already imported
                existing = conn.execute(
                    "SELECT id FROM live_trades WHERE user_id = ? AND date = ? AND mode = 'live'",
                    (int(user_id), trade_date)
                ).fetchone()
                if existing:
                    continue
                
                # Match round-trips: same symbol buy+sell = closed trade
                # Track by symbol
                symbol_ledger = defaultdict(list)
                for o in orders:
                    symbol_ledger[o["symbol"]].append(o)
                
                total_realized_pnl = 0
                legs_detail = []
                has_open_positions = False
                
                for sym, sym_orders in symbol_ledger.items():
                    buys = [o for o in sym_orders if o["action"] == "BUY"]
                    sells = [o for o in sym_orders if o["action"] == "SELL"]
                    
                    buy_qty = sum(o["quantity"] for o in buys)
                    sell_qty = sum(o["quantity"] for o in sells)
                    buy_avg = sum(o["price"] * o["quantity"] for o in buys) / buy_qty if buy_qty > 0 else 0
                    sell_avg = sum(o["price"] * o["quantity"] for o in sells) / sell_qty if sell_qty > 0 else 0
                    
                    matched_qty = min(buy_qty, sell_qty)
                    
                    if matched_qty > 0:
                        # Realized P&L on matched quantity
                        pnl = (sell_avg - buy_avg) * matched_qty
                        total_realized_pnl += pnl
                    
                    if buy_qty != sell_qty:
                        has_open_positions = True
                    
                    # Record leg detail
                    net_action = "BUY" if buy_qty > sell_qty else "SELL" if sell_qty > buy_qty else "CLOSED"
                    legs_detail.append({
                        "symbol": sym,
                        "action": net_action,
                        "strike": sym_orders[0]["strike"],
                        "option": sym_orders[0]["option_type"],
                        "buy_qty": buy_qty,
                        "sell_qty": sell_qty,
                        "buy_avg": round(buy_avg, 2),
                        "sell_avg": round(sell_avg, 2),
                        "pnl": round((sell_avg - buy_avg) * matched_qty, 2) if matched_qty > 0 else 0,
                    })
                
                total_realized_pnl = round(total_realized_pnl, 2)
                
                # Determine strategy and status
                unique_strikes = set(l["strike"] for l in legs_detail)
                unique_options = set(l["option"] for l in legs_detail)
                num_symbols = len(legs_detail)
                
                strategy = "nifty_options"
                if num_symbols >= 4 and len(unique_options) == 2:
                    strategy = "iron_condor"
                elif num_symbols == 2 and len(unique_options) == 1:
                    strategy = "call_spread" if "CE" in unique_options else "put_spread"
                elif num_symbols <= 3:
                    strategy = "scalp"
                
                # Status: if all positions closed (no open), mark as resolved
                if not has_open_positions:
                    status = "win" if total_realized_pnl > 0 else "loss"
                    pnl_value = total_realized_pnl
                else:
                    status = "open"
                    pnl_value = None
                
                conn.execute(
                    """INSERT INTO live_trades (user_id, date, direction, confidence, strategy, legs,
                       entry_cost, max_loss, max_profit, sl_value, projected_open, width, status, pnl, mode, exit_reason)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'live', ?)""",
                    (
                        int(user_id),
                        trade_date,
                        "neutral",
                        100,
                        strategy,
                        json.dumps(legs_detail),
                        0,
                        0,
                        abs(total_realized_pnl) if total_realized_pnl > 0 else 0,
                        0,
                        0,
                        100,
                        status,
                        pnl_value,
                        f"Imported from Kite Tradebook ({len(orders)} fills, {num_symbols} symbols)",
                    )
                )
                imported_trades.append({
                    "date": trade_date,
                    "strategy": strategy,
                    "net_credit": total_realized_pnl,
                    "leg_count": num_symbols,
                    "status": status,
                    "pnl": total_realized_pnl,
                })
            
            conn.commit()
        finally:
            conn.close()
        
        if not imported_trades:
            return {"success": True, "message": "All trades in this CSV were already imported.", "trades": []}
        
        return {
            "success": True,
            "message": f"Imported {len(imported_trades)} trading day(s) from Kite Tradebook",
            "trades": imported_trades,
            "total_orders_parsed": len(all_orders),
        }
    
    except Exception as e:
        logger.error(f"Tradebook upload failed: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": f"Parse error: {str(e)[:200]}"})


# --- Fetch Trades from Kite API ---

@router.get("/fetch-kite-orders")
async def fetch_kite_orders(request: Request):
    """Fetch today's executed orders from Kite and return them for review before logging.
    Returns NIFTY F&O orders only, grouped by trade date.
    """
    from engine.broker.kite_auth import is_authenticated, get_kite_client
    
    if not is_authenticated():
        return JSONResponse(status_code=401, content={
            "success": False, 
            "error": "Not connected to Zerodha. Click 'Login to Zerodha' first."
        })
    
    kite = get_kite_client()
    if not kite:
        return JSONResponse(status_code=500, content={
            "success": False,
            "error": "Could not create Kite client. Try re-login."
        })
    
    try:
        # Fetch today's orders
        orders = kite.orders()
        
        # Filter: only COMPLETE orders, only NFO segment (options), only NIFTY
        nifty_orders = []
        for o in orders:
            if (o.get("status") == "COMPLETE" and 
                o.get("exchange") == "NFO" and
                "NIFTY" in (o.get("tradingsymbol") or "")):
                nifty_orders.append({
                    "order_id": o.get("order_id"),
                    "tradingsymbol": o.get("tradingsymbol"),
                    "transaction_type": o.get("transaction_type"),  # BUY or SELL
                    "quantity": o.get("quantity"),
                    "average_price": o.get("average_price"),
                    "product": o.get("product"),  # NRML or MIS
                    "order_timestamp": str(o.get("order_timestamp", "")),
                    "instrument_token": o.get("instrument_token"),
                    "exchange": o.get("exchange"),
                })
        
        if not nifty_orders:
            return {"success": True, "orders": [], "message": "No NIFTY F&O orders found today."}
        
        # Group into legs and compute trade summary
        total_credit = 0
        total_debit = 0
        legs = []
        for o in nifty_orders:
            symbol = o["tradingsymbol"]
            # Parse strike and option type from tradingsymbol like "NIFTY2481424500CE"
            strike = ""
            option_type = ""
            if "CE" in symbol:
                option_type = "CE"
                parts = symbol.split("CE")[0]
                # Extract last digits as strike
                strike = ''.join(filter(str.isdigit, parts[-5:]))
            elif "PE" in symbol:
                option_type = "PE"
                parts = symbol.split("PE")[0]
                strike = ''.join(filter(str.isdigit, parts[-5:]))
            
            premium_total = (o["average_price"] or 0) * (o["quantity"] or 0)
            if o["transaction_type"] == "SELL":
                total_credit += premium_total
            else:
                total_debit += premium_total
            
            legs.append({
                "action": o["transaction_type"],
                "strike": strike,
                "option": option_type,
                "premium": round(o["average_price"] or 0, 2),
                "quantity": o["quantity"],
                "symbol": symbol,
                "order_id": o["order_id"],
            })
        
        net_credit = round(total_credit - total_debit, 2)
        
        # Determine strategy type from legs
        strategy = "unknown"
        buy_count = len([l for l in legs if l["action"] == "BUY"])
        sell_count = len([l for l in legs if l["action"] == "SELL"])
        ce_count = len([l for l in legs if l["option"] == "CE"])
        pe_count = len([l for l in legs if l["option"] == "PE"])
        
        if buy_count == 2 and sell_count == 2 and ce_count == 2 and pe_count == 2:
            strategy = "iron_condor"
        elif buy_count == 1 and sell_count == 1 and ce_count == 2:
            strategy = "bull_call_spread" if legs[0]["action"] == "BUY" else "bear_call_spread"
        elif buy_count == 1 and sell_count == 1 and pe_count == 2:
            strategy = "bear_put_spread" if legs[0]["action"] == "BUY" else "bull_put_spread"
        elif len(legs) == 2 and buy_count == 2:
            strategy = "straddle" if ce_count == 1 and pe_count == 1 else "unknown"
        
        # Get current NIFTY price for reference
        nifty_price = None
        try:
            ltp = kite.ltp(["NSE:NIFTY 50"])
            if "NSE:NIFTY 50" in ltp:
                nifty_price = ltp["NSE:NIFTY 50"]["last_price"]
        except:
            pass
        
        from datetime import date as dt_date
        return {
            "success": True,
            "orders": nifty_orders,
            "summary": {
                "date": dt_date.today().strftime("%Y-%m-%d"),
                "strategy": strategy,
                "legs": legs,
                "total_legs": len(legs),
                "net_credit": net_credit,
                "total_credit": round(total_credit, 2),
                "total_debit": round(total_debit, 2),
                "nifty_price": nifty_price,
            }
        }
        
    except Exception as e:
        logger.error(f"Kite orders fetch failed: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "error": f"Failed to fetch orders: {str(e)[:200]}"
        })


@router.post("/import-kite-orders")
async def import_kite_orders(request: Request):
    """Import fetched Kite orders into the trade log.
    Called after user reviews the fetch-kite-orders result and confirms.
    """
    from db.database import get_connection
    body = await request.json()
    
    user_id = request.headers.get("X-User-Id") or body.get("user_id") or "1"
    summary = body.get("summary", {})
    
    date = summary.get("date", "")
    strategy = summary.get("strategy", "iron_condor")
    legs = summary.get("legs", [])
    net_credit = summary.get("net_credit", 0)
    nifty_price = summary.get("nifty_price", 0)
    
    if not date:
        from datetime import date as dt_date
        date = dt_date.today().strftime("%Y-%m-%d")
    
    # For IC: max_loss = (wing_width * lot_size) - net_credit
    # Default: wing_width=100pts, lot_size=65
    lot_size = 65
    wing_width = 100
    max_loss = (wing_width * lot_size) - net_credit
    
    conn = get_connection()
    try:
        # Check if already imported today
        existing = conn.execute(
            "SELECT id FROM live_trades WHERE user_id = ? AND date = ? AND mode = 'live'",
            (int(user_id), date)
        ).fetchone()
        
        if existing:
            return JSONResponse(status_code=409, content={
                "success": False,
                "error": f"Trade already logged for {date} (ID: {existing['id']}). Use Resolve to update it."
            })
        
        conn.execute(
            """INSERT INTO live_trades (user_id, date, direction, confidence, strategy, legs,
               entry_cost, max_loss, max_profit, sl_value, projected_open, width, status, mode, exit_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', 'live', ?)""",
            (
                int(user_id),
                date,
                "neutral",  # IC is neutral
                100,
                strategy,
                json.dumps(legs),
                -net_credit,  # credit received = negative entry cost
                max_loss,
                net_credit,
                max_loss,
                nifty_price or 0,
                wing_width,
                f"Imported from Kite ({len(legs)} legs)",
            )
        )
        conn.commit()
        logger.info(f"Kite orders imported for user {user_id}: {strategy} on {date}, credit: {net_credit}")
        return {"success": True, "message": f"Trade imported: {strategy} on {date}, net credit ₹{net_credit}"}
    except Exception as e:
        logger.error(f"Kite import failed: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)[:200]})
    finally:
        conn.close()


# --- Manual Trade Logging (for trades executed manually on Kite) ---

@router.post("/log-manual-trade")
async def log_manual_trade(request: Request):
    """Log a trade that was executed manually on Kite (not via API).
    
    Body JSON:
      - date: trade date (YYYY-MM-DD)
      - strategy: e.g. "iron_condor", "bull_call_spread", "bear_put_spread"
      - direction: "bullish", "bearish", or "neutral"
      - legs: array of leg objects [{action, strike, option, premium}]
      - entry_cost: total premium paid/received (negative = credit received)
      - max_profit: maximum possible profit
      - max_loss: maximum possible loss
      - pnl: realized P&L (optional, fill in later when resolved)
      - status: "open" or "win" or "loss" (default "open")
      - notes: free-text notes about the trade
    """
    from db.database import get_connection
    body = await request.json()
    
    user_id = request.headers.get("X-User-Id") or body.get("user_id") or "1"
    date = body.get("date", "")
    strategy = body.get("strategy", "iron_condor")
    direction = body.get("direction", "neutral")
    legs = body.get("legs", [])
    entry_cost = body.get("entry_cost", 0)
    max_profit = body.get("max_profit", 0)
    max_loss = body.get("max_loss", 0)
    pnl = body.get("pnl")
    status = body.get("status", "open")
    notes = body.get("notes", "")
    nifty_at_entry = body.get("nifty_at_entry", 0)
    
    if not date:
        from datetime import date as dt_date
        date = dt_date.today().strftime("%Y-%m-%d")
    
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO live_trades (user_id, date, direction, confidence, strategy, legs,
               entry_cost, max_loss, max_profit, sl_value, projected_open, width, status, pnl, mode, exit_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'live', ?)""",
            (
                int(user_id),
                date,
                direction,
                100,  # confidence = 100 for manual trades (you decided to take it)
                strategy,
                json.dumps(legs),
                entry_cost,
                max_loss,
                max_profit,
                max_loss,  # SL = max loss for IC
                nifty_at_entry,
                100,  # width placeholder
                status,
                pnl,
                notes,
            )
        )
        conn.commit()
        logger.info(f"Manual trade logged for user {user_id}: {strategy} on {date}, P&L: {pnl}")
        return {"success": True, "message": f"Trade logged: {strategy} on {date}"}
    except Exception as e:
        logger.error(f"Manual trade log failed: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)[:200]})
    finally:
        conn.close()


@router.put("/update-trade/{trade_id}")
async def update_trade(trade_id: int, request: Request):
    """Update an existing trade's P&L and status (for resolving manual trades)."""
    from db.database import get_connection
    body = await request.json()
    
    pnl = body.get("pnl")
    status = body.get("status")  # "win" or "loss"
    nifty_close = body.get("nifty_close")
    exit_reason = body.get("exit_reason", "")
    
    conn = get_connection()
    try:
        updates = []
        params = []
        if pnl is not None:
            updates.append("pnl = ?")
            params.append(pnl)
        if status:
            updates.append("status = ?")
            params.append(status)
        if nifty_close is not None:
            updates.append("nifty_close = ?")
            params.append(nifty_close)
        if exit_reason:
            updates.append("exit_reason = ?")
            params.append(exit_reason)
        updates.append("resolved_at = datetime('now')")
        
        if not updates:
            return JSONResponse(status_code=400, content={"error": "Nothing to update"})
        
        params.append(trade_id)
        conn.execute(f"UPDATE live_trades SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        return {"success": True, "message": f"Trade #{trade_id} updated"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)[:200]})
    finally:
        conn.close()


# --- Signal History Endpoints (DB-backed, works on Railway) ---

@router.get("/signal-history")
async def get_signal_history_endpoint(
    days: int = None,
    direction: str = None,
    action: str = None,
    limit: int = 100,
):
    """Return historical signal records from the database."""
    from db.signal_history import get_signal_history
    history = get_signal_history(days=days, direction=direction, action=action, limit=limit)
    return {"signals": history, "total": len(history)}


@router.get("/signal-stats")
async def get_signal_stats_endpoint(
    days: int = 30,
):
    """Return aggregate statistics over signal history for performance review."""
    from db.signal_history import get_signal_stats
    stats = get_signal_stats(days=days)
    return stats


@router.post("/run-backup")
async def run_backup():
    """Trigger a database backup. Exports critical tables to JSON."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.backup_db import run_backup as do_backup
    result = do_backup()
    return result


@router.post("/live-execute")
async def live_execute(request: Request, mode: str = None):
    """
    Execute Iron Condor with REAL money.
    Accepts ?mode=nifty or ?mode=qqq to force broker routing.
    Falls back to TRADING_MODE env var if not specified.
    """
    import os
    requested_mode = (mode or request.query_params.get("mode", "")).lower()
    trading_mode = requested_mode if requested_mode in ("qqq", "nifty") else os.environ.get("TRADING_MODE", "qqq").lower()
    
    logger.info(f"live-execute called: mode={trading_mode}")
    
    # Get today's signal (mode-specific file first)
    signal = None
    mode_signal_path = OUTPUT_DIR / f"today_signal_{trading_mode}.json"
    generic_signal_path = OUTPUT_DIR / "today_signal.json"
    
    if mode_signal_path.exists():
        with open(mode_signal_path) as f:
            signal = json.load(f)
    elif generic_signal_path.exists():
        with open(generic_signal_path) as f:
            signal = json.load(f)
    else:
        from datetime import date
        from db.signal_history import get_signal_history
        today = date.today().strftime("%Y-%m-%d")
        history = get_signal_history(days=1, limit=1)
        if history and history[0].get("signal_date") == today:
            full_json = history[0].get("full_signal_json")
            if full_json:
                signal = json.loads(full_json)
    
    if not signal:
        return JSONResponse(status_code=400, content={"success": False, "error": "No signal generated today"})
    
    if signal.get("action") != "trade":
        return JSONResponse(status_code=400, content={"success": False, "error": "Signal is not a trade"})
    
    # SAFETY CHECK: Verify signal matches requested mode
    signal_strategy = signal.get("strategy_type", "")
    if trading_mode == "nifty" and "qqq" in signal_strategy.lower():
        return JSONResponse(status_code=400, content={
            "success": False, 
            "error": "SAFETY BLOCK: NIFTY page tried to execute a QQQ signal. Regenerate the NIFTY signal first."
        })
    if trading_mode == "qqq" and "250" in signal_strategy:
        return JSONResponse(status_code=400, content={
            "success": False,
            "error": "SAFETY BLOCK: QQQ page tried to execute a NIFTY signal. Regenerate the QQQ signal first."
        })
    
    # Execute based on mode
    if trading_mode == "qqq":
        from engine.broker.ibkr_executor import execute_qqq_sync
        spot = signal.get("projected_open") or signal.get("conditions", {}).get("qqq_price")
        result = execute_qqq_sync(spot_price=spot)
    else:
        from engine.broker.kite_executor import execute_iron_condor
        result = execute_iron_condor(signal)
    
    # Also log as a paper trade in DB for tracking
    if result.get("success"):
        user_id = request.headers.get("X-User-Id") or "1"
        from db.database import get_connection
        trade_data = signal.get("trade", {})
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO live_trades (user_id, date, direction, confidence, strategy, legs,
                   entry_cost, max_loss, max_profit, sl_value, projected_open, width, status, mode)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', 'live')""",
                (
                    int(user_id),
                    signal.get("date", ""),
                    signal.get("direction", ""),
                    signal.get("confidence", 0),
                    trade_data.get("type", ""),
                    json.dumps(trade_data.get("legs", [])),
                    trade_data.get("net_cost_total", 0),
                    trade_data.get("max_loss", 0),
                    trade_data.get("max_profit", 0),
                    trade_data.get("sl_value", 0),
                    signal.get("projected_open", 0),
                    trade_data.get("width", 0),
                )
            )
            conn.commit()
        except Exception as e:
            logger.error(f"DB log failed (non-fatal): {e}")
        finally:
            conn.close()
    
    return result


@router.get("/phase-status")
async def get_phase_status():
    """Get current trading phase info and trade count."""
    from engine.broker.kite_executor import get_phase_config
    from db.database import get_connection
    
    phase = get_phase_config()
    
    conn = get_connection()
    try:
        live_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM live_trades WHERE mode = 'live'"
        ).fetchone()
        live_wins = conn.execute(
            "SELECT COUNT(*) as cnt FROM live_trades WHERE mode = 'live' AND status = 'win'"
        ).fetchone()
        
        count = live_count["cnt"] if live_count else 0
        wins = live_wins["cnt"] if live_wins else 0
        
        return {
            "phase": phase,
            "live_trades_total": count,
            "live_wins": wins,
            "live_win_rate": f"{wins/count*100:.0f}%" if count > 0 else "--",
            "trades_remaining_in_phase": (phase["max_trades"] - count) if phase["max_trades"] else "unlimited",
        }
    except Exception as e:
        return {"phase": phase, "error": str(e)[:100]}
    finally:
        conn.close()
