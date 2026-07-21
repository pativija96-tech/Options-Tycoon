"""
Live Signal Engine Routes — Localhost-only (127.0.0.1) FastAPI endpoints.
Serves trade signals, gate status, auth state, and execution triggers.
"""

import json
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse

from db.signal_history import get_signal_history, get_signal_stats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live", tags=["live-signal-engine"])

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# In-memory auth state (resets on server restart — by design)
_auth_state = {"authenticated": False, "access_token": None, "user": None}


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


@router.get("/gate-status")
async def get_gate_status():
    """Return current paper trading gate status."""
    gate_path = OUTPUT_DIR / "gate_status.json"
    if not gate_path.exists():
        # Default: locked with no data
        return {
            "locked": True,
            "metrics": {},
            "metrics_detail": {
                "trade_count": False,
                "win_rate": False,
                "profit_factor": False,
                "avg_win_loss": False,
                "max_drawdown": False,
                "max_consec_losses": False,
                "expectancy": False,
            },
            "total_trades": 0,
            "message": "No trades logged yet. Run paper signals to build history."
        }
    with open(gate_path) as f:
        return json.load(f)


@router.get("/auth-status")
async def get_auth_status():
    """Return Kite authentication state."""
    return {
        "authenticated": _auth_state["authenticated"],
        "user": _auth_state.get("user"),
    }


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
    """Log today's signal as a paper trade (no real execution)."""
    signal_path = OUTPUT_DIR / "today_signal.json"
    if not signal_path.exists():
        return JSONResponse(status_code=400, content={"error": "No signal to execute"})

    with open(signal_path) as f:
        signal = json.load(f)

    if signal.get("action") != "trade":
        return JSONResponse(status_code=400, content={"error": "Signal is not a trade"})

    # Log as paper trade
    log_path = OUTPUT_DIR / "trade_log.json"
    trades = []
    if log_path.exists():
        with open(log_path) as f:
            trades = json.load(f)

    trade_entry = {
        "id": len(trades) + 1,
        "date": signal.get("date"),
        "direction": signal.get("direction"),
        "confidence": signal.get("confidence"),
        "strategy": signal.get("trade", {}).get("type"),
        "legs": signal.get("trade", {}).get("legs", []),
        "entry_cost": signal.get("trade", {}).get("net_cost_total", 0),
        "max_loss": signal.get("trade", {}).get("max_loss", 0),
        "max_profit": signal.get("trade", {}).get("max_profit", 0),
        "sl_value": signal.get("trade", {}).get("sl_value", 0),
        "projected_open": signal.get("projected_open", 0),
        "width": signal.get("trade", {}).get("width", 200),
        "status": "open",
        "pnl": None,
        "mode": "paper",
        "executed_at": signal.get("timestamp"),
    }

    trades.append(trade_entry)
    with open(log_path, "w") as f:
        json.dump(trades, f, indent=2)

    logger.info(f"Paper trade logged: #{trade_entry['id']} {trade_entry['strategy']}")
    return {"success": True, "trade_id": trade_entry["id"], "message": "Paper trade logged"}


@router.get("/eod-report")
async def get_eod_report():
    """Return today's EOD report if available."""
    eod_path = OUTPUT_DIR / "eod_report.json"
    if not eod_path.exists():
        return {"available": False, "message": "No EOD report yet"}
    with open(eod_path) as f:
        return json.load(f)


@router.get("/settings")
async def get_settings():
    """Return current capital and risk settings (non-sensitive)."""
    settings_path = CONFIG_DIR / "settings.json"
    if not settings_path.exists():
        return {"capital": 10000, "risk_per_trade": 0.02, "risk_per_day": 0.05}
    with open(settings_path) as f:
        settings = json.load(f)
    # Only expose non-sensitive fields
    return {
        "capital": settings.get("capital"),
        "risk_per_trade": settings.get("risk_per_trade"),
        "risk_per_day": settings.get("risk_per_day"),
        "nifty_lot_size": settings.get("nifty_lot_size", 25),
    }



@router.get("/signal-history")
async def get_signal_history_endpoint(
    days: Optional[int] = Query(None, description="Filter to last N days"),
    direction: Optional[str] = Query(None, description="Filter by direction: bullish, bearish, neutral"),
    action: Optional[str] = Query(None, description="Filter by action: trade, skip"),
    limit: int = Query(100, le=500, description="Max results"),
):
    """Return historical signal records from the database."""
    history = get_signal_history(days=days, direction=direction, action=action, limit=limit)
    return {"signals": history, "total": len(history)}


@router.get("/signal-stats")
async def get_signal_stats_endpoint(
    days: int = Query(30, description="Period in days for stats computation"),
):
    """Return aggregate statistics over signal history for performance review."""
    stats = get_signal_stats(days=days)
    return stats
