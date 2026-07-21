"""
Live Signal Engine Routes — Localhost-only (127.0.0.1) FastAPI endpoints.
Serves trade signals, gate status, auth state, and execution triggers.
"""

import json
import logging
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live", tags=["live-signal-engine"])

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@router.get("/signal")
async def get_today_signal():
    """Return today's generated trade card."""
    signal_path = OUTPUT_DIR / "today_signal.json"
    if not signal_path.exists():
        return JSONResponse(
            status_code=404,
            content={"action": "skip", "reason": "No signal generated yet today"}
        )
    with open(signal_path) as f:
        return json.load(f)


@router.post("/generate-signal")
async def generate_signal():
    """Trigger signal generation on-demand."""
    import sys
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from engine.signals.signal_engine import run_morning_signal
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            result = await asyncio.wait_for(
                loop.run_in_executor(pool, run_morning_signal),
                timeout=120
            )
        if result:
            return {"success": True, "action": result.get("action"), "direction": result.get("direction"), "confidence": result.get("confidence")}
        return {"success": False, "error": "Signal engine returned None"}
    except asyncio.TimeoutError:
        return JSONResponse(status_code=504, content={"success": False, "error": "Timed out. Try again — data may be cached now."})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)[:200]})


@router.get("/gate-status")
async def get_gate_status(request: Request):
    """Return paper trading gate status for the logged-in user (computed from DB)."""
    user_id = request.headers.get("X-User-Id") or request.query_params.get("user_id") or "0"
    
    from db.database import get_connection
    conn = get_connection()
    try:
        # Get user's trades from DB (trailing 30)
        rows = conn.execute(
            "SELECT pnl, status FROM live_trades WHERE user_id = ? AND status IN ('win','loss') ORDER BY id DESC LIMIT 30",
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
        # Redirect back to live page with success
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/static/live.html?kite=connected")
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


@router.get("/trade-log")
async def get_trade_log():
    """Return the full trade log."""
    log_path = OUTPUT_DIR / "trade_log.json"
    if not log_path.exists():
        return {"trades": [], "total": 0}
    with open(log_path) as f:
        trades = json.load(f)
    return {"trades": trades, "total": len(trades)}


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


@router.get("/admin/all-trades")
async def admin_all_trades(request: Request):
    """Admin endpoint: view all users' trades. Protected by X-Admin-Key header only."""
    admin_key = request.headers.get("X-Admin-Key")
    import os
    expected_key = os.environ.get("OT_ADMIN_KEY", "change-me-in-railway-env-vars")
    if not admin_key or admin_key != expected_key:
        return JSONResponse(status_code=403, content={"error": "Unauthorized. X-Admin-Key header required."})
    
    from db.database import get_connection
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT lt.*, u.email, u.name as user_name 
               FROM live_trades lt 
               LEFT JOIN users u ON lt.user_id = u.id 
               ORDER BY lt.id DESC LIMIT 200"""
        ).fetchall()
        trades = [dict(r) for r in rows] if rows else []
        
        # Summary per user
        user_stats = conn.execute(
            """SELECT user_id, COUNT(*) as total, 
                      SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                      SUM(COALESCE(pnl, 0)) as total_pnl
               FROM live_trades GROUP BY user_id"""
        ).fetchall()
        stats = [dict(r) for r in user_stats] if user_stats else []
        
        return {"trades": trades, "user_stats": stats, "total_trades": len(trades)}
    except Exception as e:
        return {"error": str(e)[:200], "trades": [], "user_stats": []}
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


@router.post("/run-eod")
async def run_eod():
    """Trigger EOD resolution — resolves all open trades using actual NIFTY close."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from db.database import get_connection
    
    try:
        # Fetch today's NIFTY close
        import yfinance as yf
        data = yf.download("^NSEI", period="2d", progress=False, timeout=15)
        if data is None or len(data) < 1:
            return JSONResponse(status_code=500, content={"success": False, "error": "Could not fetch NIFTY close"})
        
        close_col = data["Close"]
        if hasattr(close_col, "columns"):
            close_col = close_col.iloc[:, 0]
        nifty_close = float(close_col.iloc[-1])
        
        # Resolve all open trades in DB
        conn = get_connection()
        open_trades = conn.execute("SELECT * FROM live_trades WHERE status = 'open'").fetchall()
        resolved_count = 0
        
        for trade in open_trades:
            trade_dict = dict(trade)
            projected_open = trade_dict.get("projected_open") or nifty_close
            strategy = trade_dict.get("strategy", "")
            max_profit = trade_dict.get("max_profit", 0)
            max_loss = trade_dict.get("max_loss", 0)
            entry_cost = trade_dict.get("entry_cost", 0)
            direction = trade_dict.get("direction", "bullish")
            legs_json = trade_dict.get("legs", "[]")
            
            try:
                import json as jmod
                legs = jmod.loads(legs_json) if isinstance(legs_json, str) else legs_json
            except Exception:
                legs = []
            
            nifty_move = nifty_close - projected_open
            
            # Resolve based on strategy
            if "bull_call" in strategy:
                long_strike = legs[0].get("strike", 0) if legs else 0
                if nifty_close > long_strike:
                    width = trade_dict.get("width", 200)
                    intrinsic = min(nifty_close - long_strike, width)
                    pnl = min((intrinsic * 65) - entry_cost, max_profit)
                else:
                    pnl = -entry_cost if entry_cost > 0 else -max_loss
            elif "bear_put" in strategy:
                long_strike = legs[0].get("strike", 0) if legs else 0
                if nifty_close < long_strike:
                    width = trade_dict.get("width", 200)
                    intrinsic = min(long_strike - nifty_close, width)
                    pnl = min((intrinsic * 65) - entry_cost, max_profit)
                else:
                    pnl = -entry_cost if entry_cost > 0 else -max_loss
            elif "iron_condor" in strategy:
                # Iron condor profits if NIFTY stays in range
                short_call = 0
                short_put = 0
                for leg in legs:
                    if leg.get("action") == "SELL" and leg.get("option") == "CE":
                        short_call = leg.get("strike", 0)
                    if leg.get("action") == "SELL" and leg.get("option") == "PE":
                        short_put = leg.get("strike", 0)
                if short_put < nifty_close < short_call:
                    pnl = max_profit  # Stayed in range — full profit
                else:
                    pnl = -max_loss  # Broke out of range
            else:
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
        
        return {"success": True, "resolved": resolved_count, "nifty_close": nifty_close}
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)[:200]})


@router.get("/settings")
async def get_settings():
    """Return current capital and risk settings (non-sensitive)."""
    settings_path = CONFIG_DIR / "settings.json"
    if not settings_path.exists():
        return {"capital": 1000000, "risk_per_trade": 0.02, "risk_per_day": 0.05}
    with open(settings_path) as f:
        settings = json.load(f)
    return {
        "capital": settings.get("capital"),
        "risk_per_trade": settings.get("risk_per_trade"),
        "risk_per_day": settings.get("risk_per_day"),
        "nifty_lot_size": settings.get("nifty_lot_size", 65),
    }


@router.get("/open-positions")
async def get_open_positions(request: Request):
    """Return all open (unresolved) trades for the user with current suggestions."""
    user_id = request.headers.get("X-User-Id") or request.query_params.get("user_id") or "0"
    from db.database import get_connection
    import yfinance as yf
    
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM live_trades WHERE user_id = ? AND status = 'open' ORDER BY id DESC",
            (int(user_id),)
        ).fetchall()
        
        if not rows:
            return {"positions": [], "nifty_current": None}
        
        # Fetch current NIFTY price
        nifty_current = None
        try:
            data = yf.download("^NSEI", period="1d", progress=False, timeout=10)
            if data is not None and len(data) >= 1:
                close_col = data["Close"]
                if hasattr(close_col, "columns"):
                    close_col = close_col.iloc[:, 0]
                nifty_current = float(close_col.iloc[-1])
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
