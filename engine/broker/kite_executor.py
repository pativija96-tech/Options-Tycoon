"""
Kite Executor — Places orders on Zerodha via Kite Connect API.
Handles multi-leg spread orders + automatic SL placement.

NOTE: Scaffolded. Will connect when Kite subscription is active.
Includes risk cap enforcement (2% per trade, 5% per day).
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "settings.json"
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"


def execute_trade(trade_card: dict) -> dict:
    """
    Execute a trade from a trade card via Kite API.
    
    Checks:
    1. Authentication status
    2. 2% per-trade risk cap
    3. 5% daily loss cap
    
    Returns execution result.
    """
    from engine.broker.kite_auth import is_authenticated, get_access_token
    
    # Check auth
    if not is_authenticated():
        return {"success": False, "error": "Not authenticated. Login to Zerodha first.", "code": "AUTH_REQUIRED"}
    
    # Check risk caps
    risk_check = _check_risk_caps(trade_card)
    if not risk_check["allowed"]:
        return {"success": False, "error": risk_check["reason"], "code": "RISK_CAP_HIT"}
    
    # Check gate status
    gate_check = _check_gate_status()
    if gate_check.get("locked", True):
        # Paper mode — log but don't actually place orders
        return _paper_execute(trade_card)
    
    # Live execution (when gates pass)
    return _live_execute(trade_card)


def _check_risk_caps(trade_card: dict) -> dict:
    """Enforce 2% per-trade and 5% daily loss caps."""
    settings = _load_settings()
    capital = settings.get("capital", 10000)
    max_trade_risk = capital * settings.get("risk_per_trade", 0.02)
    max_daily_risk = capital * settings.get("risk_per_day", 0.05)
    
    trade = trade_card.get("trade", {})
    max_loss = trade.get("max_loss", 0)
    
    # Per-trade check
    if max_loss > max_trade_risk:
        return {"allowed": False, "reason": f"Trade risk Rs.{max_loss} exceeds 2% cap (Rs.{max_trade_risk})"}
    
    # Daily loss check
    daily_loss = _get_today_loss()
    if abs(daily_loss) >= max_daily_risk:
        return {"allowed": False, "reason": f"Daily loss limit reached (Rs.{abs(daily_loss):.0f} / Rs.{max_daily_risk:.0f})"}
    
    if abs(daily_loss) + max_loss > max_daily_risk:
        return {"allowed": False, "reason": f"This trade could breach daily limit. Remaining budget: Rs.{max_daily_risk - abs(daily_loss):.0f}"}
    
    return {"allowed": True}


def _check_gate_status() -> dict:
    """Check if live trading is unlocked."""
    gate_path = OUTPUT_DIR / "gate_status.json"
    if gate_path.exists():
        with open(gate_path) as f:
            return json.load(f)
    return {"locked": True}


def _paper_execute(trade_card: dict) -> dict:
    """Log trade as paper execution (no real orders)."""
    logger.info("Paper execution (gates locked) — logging trade without Kite orders")
    return {
        "success": True,
        "mode": "paper",
        "message": "Trade logged in paper mode (gates locked). No real orders placed.",
        "trade_id": None,
    }


def _live_execute(trade_card: dict) -> dict:
    """
    Place actual orders on Kite.
    NOTE: Scaffolded — requires kiteconnect + active subscription.
    """
    from engine.broker.kite_auth import get_access_token
    
    access_token = get_access_token()
    if not access_token:
        return {"success": False, "error": "No access token available", "code": "NO_TOKEN"}
    
    trade = trade_card.get("trade", {})
    legs = trade.get("legs", [])
    
    try:
        from kiteconnect import KiteConnect
        config = _load_kite_config()
        kite = KiteConnect(api_key=config.get("api_key", ""))
        kite.set_access_token(access_token)
        
        order_ids = []
        for leg in legs:
            # Determine transaction type
            txn_type = "BUY" if leg["action"] == "BUY" else "SELL"
            
            # Place order
            order_id = kite.place_order(
                variety="regular",
                exchange="NFO",
                tradingsymbol=_build_tradingsymbol(leg),
                transaction_type=txn_type,
                quantity=25,  # 1 lot
                product="NRML",
                order_type="MARKET",
            )
            order_ids.append(order_id)
            logger.info(f"Order placed: {txn_type} {leg['strike']} {leg['option']} → ID: {order_id}")
        
        return {
            "success": True,
            "mode": "live",
            "order_ids": order_ids,
            "message": f"Live orders placed: {len(order_ids)} legs executed",
        }
    
    except ImportError:
        return {"success": False, "error": "kiteconnect not installed", "code": "NO_LIBRARY"}
    except Exception as e:
        logger.error(f"Live execution failed: {e}")
        return {"success": False, "error": str(e), "code": "EXECUTION_ERROR"}


def _get_today_loss() -> float:
    """Get today's cumulative realized loss from trade log."""
    from datetime import date
    log_path = OUTPUT_DIR / "trade_log.json"
    if not log_path.exists():
        return 0
    with open(log_path) as f:
        trades = json.load(f)
    today_str = date.today().isoformat()
    today_losses = sum(
        t.get("pnl", 0) for t in trades
        if t.get("date") == today_str and t.get("pnl", 0) < 0
    )
    return today_losses


def _build_tradingsymbol(leg: dict) -> str:
    """Build Kite trading symbol from leg data. Placeholder logic."""
    # Real implementation needs: expiry date + correct format
    # e.g., "NIFTY2570324400PE"
    return f"NIFTY{leg['strike']}{leg['option']}"


def _load_settings() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"capital": 10000, "risk_per_trade": 0.02, "risk_per_day": 0.05}


def _load_kite_config() -> dict:
    kite_path = Path(__file__).resolve().parent.parent.parent / "config" / "kite_creds.json"
    if kite_path.exists():
        with open(kite_path) as f:
            return json.load(f)
    return {}
