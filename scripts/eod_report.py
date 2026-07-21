"""
EOD Report — End-of-day P&L calculation and trade resolution.
Runs daily at 6:00 PM PHT (3:30 PM IST) via Task Scheduler.

In paper mode: simulates whether SL/target would have been hit based on NIFTY's actual daily range.
In live mode: fetches real positions from Kite API.
"""

import json
import logging
import sys
import random
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.gate_checker import check_gates

# Import telegram (may fail gracefully)
try:
    from scripts.telegram_bot import send_eod
except ImportError:
    def send_eod(data): print("[Telegram not available]", json.dumps(data, indent=2))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("eod_report")

OUTPUT_DIR = ROOT / "output"


def load_trade_log() -> list:
    """Load the trade log."""
    log_path = OUTPUT_DIR / "trade_log.json"
    if not log_path.exists():
        return []
    with open(log_path) as f:
        return json.load(f)


def save_trade_log(trades: list):
    """Save updated trade log."""
    log_path = OUTPUT_DIR / "trade_log.json"
    with open(log_path, "w") as f:
        json.dump(trades, f, indent=2)


def resolve_paper_trades(trades: list) -> list:
    """
    Resolve open paper trades using ACTUAL NIFTY closing data from yfinance.
    Checks if the trade's strikes would have been profitable based on real market movement.
    """
    today_str = date.today().isoformat()
    
    # Fetch today's actual NIFTY close
    nifty_close = _get_nifty_close_today()
    if nifty_close is None:
        logger.warning("Could not fetch NIFTY close — skipping resolution for today")
        return trades
    
    for trade in trades:
        if trade.get("status") != "open":
            continue
        
        trade_date = trade.get("date", "")
        if trade_date > today_str:
            continue
        
        # Determine outcome based on actual NIFTY movement
        strategy = trade.get("strategy", "")
        legs = trade.get("legs", [])
        max_profit = trade.get("max_profit", 0)
        max_loss = trade.get("max_loss", 0)
        entry_cost = trade.get("entry_cost", 0)
        
        if not legs:
            trade["pnl"] = 0
            trade["status"] = "closed"
            trade["exit_reason"] = "no_legs_data"
            continue
        
        # Get projected open from signal (or use a default)
        projected_open = trade.get("projected_open", nifty_close)
        nifty_move = nifty_close - projected_open
        nifty_move_pct = (nifty_move / projected_open) * 100 if projected_open else 0
        
        # Evaluate based on strategy type
        if "bull_call" in strategy:
            # Bull call spread profits when NIFTY goes UP
            long_strike = legs[0].get("strike", 0) if legs else 0
            if nifty_close > long_strike:
                # In profit — calculate how much
                intrinsic_gain = min(nifty_close - long_strike, trade.get("width", 200) if "width" in str(trade) else 200)
                pnl = min((intrinsic_gain * 25) - entry_cost, max_profit)
                trade["pnl"] = round(pnl)
                trade["status"] = "win" if pnl > 0 else "loss"
            else:
                # Out of money — lose entry cost
                trade["pnl"] = -entry_cost if entry_cost > 0 else -max_loss
                trade["status"] = "loss"
                
        elif "bear_put" in strategy:
            # Bear put spread profits when NIFTY goes DOWN
            long_strike = legs[0].get("strike", 0) if legs else 0
            if nifty_close < long_strike:
                intrinsic_gain = min(long_strike - nifty_close, 200)
                pnl = min((intrinsic_gain * 25) - entry_cost, max_profit)
                trade["pnl"] = round(pnl)
                trade["status"] = "win" if pnl > 0 else "loss"
            else:
                trade["pnl"] = -entry_cost if entry_cost > 0 else -max_loss
                trade["status"] = "loss"
                
        elif "straddle" in strategy:
            # Long straddle profits from big move in either direction
            atm_strike = legs[0].get("strike", 0) if legs else 0
            total_premium = entry_cost
            actual_move = abs(nifty_close - atm_strike) * 25
            pnl = actual_move - total_premium
            trade["pnl"] = round(pnl)
            trade["status"] = "win" if pnl > 0 else "loss"
        else:
            # Unknown strategy — use directional logic
            direction = trade.get("direction", "bullish")
            if direction == "bullish" and nifty_move > 0:
                trade["pnl"] = round(min(abs(nifty_move) * 25 * 0.5, max_profit))
                trade["status"] = "win"
            elif direction == "bearish" and nifty_move < 0:
                trade["pnl"] = round(min(abs(nifty_move) * 25 * 0.5, max_profit))
                trade["status"] = "win"
            else:
                trade["pnl"] = -max_loss if max_loss > 0 else round(-abs(nifty_move) * 25 * 0.3)
                trade["status"] = "loss"
        
        trade["exit_reason"] = "eod_resolution"
        trade["nifty_close"] = nifty_close
        trade["nifty_move_pct"] = round(nifty_move_pct, 2)
        trade["resolved_at"] = datetime.now().isoformat()
        logger.info(f"Trade #{trade['id']} resolved: {trade['status']} P&L=Rs.{trade['pnl']} (NIFTY close={nifty_close}, move={nifty_move_pct:+.2f}%)")
    
    return trades


def _get_nifty_close_today() -> float:
    """Fetch today's NIFTY closing price using yfinance (free)."""
    try:
        import yfinance as yf
        data = yf.download("^NSEI", period="2d", progress=False, timeout=10)
        if data is not None and len(data) >= 1:
            close_col = data["Close"]
            if hasattr(close_col, "columns"):
                close_col = close_col.iloc[:, 0]
            return float(close_col.iloc[-1])
    except Exception as e:
        logger.error(f"Failed to fetch NIFTY close: {e}")
    return None


def generate_eod_report(trades: list) -> dict:
    """Generate EOD report data."""
    today_str = date.today().isoformat()
    
    # Today's closed trades
    today_closed = [t for t in trades if t.get("date") == today_str and t.get("status") in ("win", "loss")]
    today_open = [t for t in trades if t.get("status") == "open"]
    
    # Today's P&L
    today_pnl = sum(t.get("pnl", 0) for t in today_closed)
    
    # All-time stats
    all_closed = [t for t in trades if t.get("status") in ("win", "loss")]
    total_pnl = sum(t.get("pnl", 0) for t in all_closed)
    total_trades = len(all_closed)
    wins = len([t for t in all_closed if t.get("pnl", 0) > 0])
    
    report = {
        "date": today_str,
        "today_pnl": today_pnl,
        "today_trades_resolved": len(today_closed),
        "today_wins": len([t for t in today_closed if t.get("pnl", 0) > 0]),
        "today_losses": len([t for t in today_closed if t.get("pnl", 0) < 0]),
        "open_positions": [
            {"id": t["id"], "strategy": t.get("strategy", "?"), "pnl": t.get("pnl")}
            for t in today_open
        ],
        "all_time": {
            "total_trades": total_trades,
            "total_pnl": total_pnl,
            "win_rate": f"{wins/total_trades*100:.1f}%" if total_trades > 0 else "—",
        },
        "gate_status": {},
        "generated_at": datetime.now().isoformat(),
    }
    
    return report


def run_eod():
    """
    Complete EOD pipeline:
    1. Resolve open paper trades
    2. Update trade log
    3. Run gate checker
    4. Generate EOD report
    5. Send via Telegram
    """
    logger.info("=" * 50)
    logger.info(f"EOD Report started at {datetime.now().isoformat()}")
    logger.info("=" * 50)
    
    # Step 1: Load and resolve trades
    trades = load_trade_log()
    if not trades:
        logger.info("No trades in log. Nothing to report.")
        return
    
    trades = resolve_paper_trades(trades)
    save_trade_log(trades)
    
    # Step 2: Run gate checker
    gate_status = check_gates()
    
    # Step 3: Generate report
    report = generate_eod_report(trades)
    report["gate_status"] = gate_status
    
    # Save report
    report_path = OUTPUT_DIR / "eod_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info(f"EOD report saved to {report_path}")
    
    # Step 4: Send Telegram
    try:
        send_eod(report)
        logger.info("EOD Telegram sent")
    except Exception as e:
        logger.warning(f"Telegram failed (non-fatal): {e}")
    
    # Summary
    logger.info(f"Today P&L: Rs.{report['today_pnl']:+,.0f} | "
                f"All-time: Rs.{report['all_time']['total_pnl']:+,.0f} | "
                f"Gates: {sum(1 for v in gate_status.get('metrics', {}).values() if v)}/7")
    logger.info("EOD complete.")


if __name__ == "__main__":
    run_eod()
