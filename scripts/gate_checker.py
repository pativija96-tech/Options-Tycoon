"""
Gate Checker — Computes 7 paper trading metrics over trailing 30 trades.
Determines lock/unlock state for live trading promotion.

Metrics (all must pass for live unlock):
1. Trade count >= 30
2. Win rate > 50%
3. Profit factor > 1.5
4. Average win / Average loss ratio > 1.0
5. Max drawdown < 15%
6. Max consecutive losses < 5
7. Expectancy > 0

State Machine:
- Re-lock: IMMEDIATE on any breach (no debounce)
- Re-unlock: Full trading day debounce + manual user confirmation
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_settings() -> dict:
    """Load gate thresholds from config."""
    config_path = CONFIG_DIR / "settings.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {
        "capital": 10000,
        "gate_thresholds": {
            "min_trades": 30,
            "min_win_rate": 0.50,
            "min_profit_factor": 1.5,
            "min_avg_win_loss_ratio": 1.0,
            "max_drawdown": 0.15,
            "max_consec_losses": 5,
            "min_expectancy": 0,
        }
    }


def load_trade_log() -> list:
    """Load trade log from JSON file."""
    log_path = OUTPUT_DIR / "trade_log.json"
    if not log_path.exists():
        return []
    with open(log_path) as f:
        return json.load(f)


def load_gate_status() -> dict:
    """Load current gate status."""
    gate_path = OUTPUT_DIR / "gate_status.json"
    if gate_path.exists():
        with open(gate_path) as f:
            return json.load(f)
    return {"locked": True, "last_breach": None, "eligible_since": None, "confirmed": False}


def save_gate_status(status: dict):
    """Save gate status to JSON."""
    gate_path = OUTPUT_DIR / "gate_status.json"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(gate_path, "w") as f:
        json.dump(status, f, indent=2)


def compute_metrics(trades: list, settings: dict) -> dict:
    """
    Compute all 7 gate metrics over the provided trades.
    Only considers closed trades (status != 'open').
    """
    thresholds = settings.get("gate_thresholds", {})
    capital = settings.get("capital", 10000)
    
    # Filter to closed trades only (those with P&L resolved)
    closed = [t for t in trades if t.get("status") in ("win", "loss", "closed") and t.get("pnl") is not None]
    
    # Use trailing 30 trades
    trailing = closed[-30:] if len(closed) > 30 else closed
    
    total = len(trailing)
    
    if total == 0:
        return _empty_metrics(thresholds)
    
    wins = [t for t in trailing if t["pnl"] > 0]
    losses = [t for t in trailing if t["pnl"] < 0]
    
    win_count = len(wins)
    loss_count = len(losses)
    
    # 1. Trade count
    trade_count_pass = total >= thresholds.get("min_trades", 30)
    
    # 2. Win rate
    win_rate = win_count / total if total > 0 else 0
    win_rate_pass = win_rate > thresholds.get("min_win_rate", 0.50)
    
    # 3. Profit factor (total wins / total losses)
    total_wins = sum(t["pnl"] for t in wins)
    total_losses = abs(sum(t["pnl"] for t in losses))
    profit_factor = total_wins / total_losses if total_losses > 0 else (999 if total_wins > 0 else 0)
    profit_factor_pass = profit_factor > thresholds.get("min_profit_factor", 1.5)
    
    # 4. Average win / Average loss ratio
    avg_win = total_wins / win_count if win_count > 0 else 0
    avg_loss = total_losses / loss_count if loss_count > 0 else 1
    avg_win_loss = avg_win / avg_loss if avg_loss > 0 else 999
    avg_win_loss_pass = avg_win_loss > thresholds.get("min_avg_win_loss_ratio", 1.0)
    
    # 5. Max drawdown (from peak equity)
    equity_curve = []
    running_equity = 0
    for t in trailing:
        running_equity += t["pnl"]
        equity_curve.append(running_equity)
    
    peak = 0
    max_dd = 0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / capital if capital > 0 else 0
        if dd > max_dd:
            max_dd = dd
    
    max_dd_pass = max_dd < thresholds.get("max_drawdown", 0.15)
    
    # 6. Max consecutive losses
    max_consec = 0
    current_streak = 0
    for t in trailing:
        if t["pnl"] < 0:
            current_streak += 1
            max_consec = max(max_consec, current_streak)
        else:
            current_streak = 0
    
    max_consec_pass = max_consec < thresholds.get("max_consec_losses", 5)
    
    # 7. Expectancy
    win_pct = win_rate
    loss_pct = 1 - win_pct
    expectancy = (win_pct * avg_win) - (loss_pct * avg_loss)
    expectancy_pass = expectancy > thresholds.get("min_expectancy", 0)
    
    # Sharpe-like (informational only, not a gate)
    returns = [t["pnl"] for t in trailing]
    import numpy as np
    mean_return = np.mean(returns) if returns else 0
    std_return = np.std(returns) if len(returns) > 1 else 1
    sharpe = mean_return / std_return if std_return > 0 else 0
    
    return {
        "total_trades": total,
        "trailing_window": len(trailing),
        "metrics": {
            "trade_count": trade_count_pass,
            "win_rate": win_rate_pass,
            "profit_factor": profit_factor_pass,
            "avg_win_loss": avg_win_loss_pass,
            "max_drawdown": max_dd_pass,
            "max_consec_losses": max_consec_pass,
            "expectancy": expectancy_pass,
        },
        "metrics_detail": {
            "trade_count": f"{total}/{thresholds.get('min_trades', 30)}",
            "win_rate": f"{win_rate*100:.1f}%",
            "profit_factor": f"{profit_factor:.2f}",
            "avg_win_loss": f"{avg_win_loss:.2f}",
            "max_drawdown": f"{max_dd*100:.1f}%",
            "max_consec_losses": str(max_consec),
            "expectancy": f"Rs.{expectancy:.0f}",
            "sharpe": f"{sharpe:.2f} (info only)",
        },
        "all_pass": all([
            trade_count_pass, win_rate_pass, profit_factor_pass,
            avg_win_loss_pass, max_dd_pass, max_consec_pass, expectancy_pass
        ]),
    }


def _empty_metrics(thresholds: dict) -> dict:
    """Return empty metrics when no trades exist."""
    return {
        "total_trades": 0,
        "trailing_window": 0,
        "metrics": {k: False for k in ["trade_count", "win_rate", "profit_factor", "avg_win_loss", "max_drawdown", "max_consec_losses", "expectancy"]},
        "metrics_detail": {k: "—" for k in ["trade_count", "win_rate", "profit_factor", "avg_win_loss", "max_drawdown", "max_consec_losses", "expectancy", "sharpe"]},
        "all_pass": False,
    }


def check_gates() -> dict:
    """
    Main entry point: compute metrics and update gate lock state.
    
    State transitions:
    - Re-lock: IMMEDIATE on any breach
    - Re-unlock: Requires full trading day debounce + manual confirmation
    """
    settings = load_settings()
    trades = load_trade_log()
    current_status = load_gate_status()
    
    metrics = compute_metrics(trades, settings)
    all_pass = metrics["all_pass"]
    
    today = date.today().isoformat()
    was_locked = current_status.get("locked", True)
    
    # State machine logic
    if not all_pass:
        # IMMEDIATE re-lock on any breach (no debounce)
        new_status = {
            "locked": True,
            "last_breach": today,
            "eligible_since": None,
            "confirmed": False,
            "metrics": metrics["metrics"],
            "metrics_detail": metrics["metrics_detail"],
            "total_trades": metrics["total_trades"],
            "updated_at": datetime.now().isoformat(),
        }
    elif all_pass and was_locked:
        # All gates pass — mark eligible (but requires full day debounce + manual confirm)
        eligible_since = current_status.get("eligible_since")
        if eligible_since is None:
            # First time all pass — start debounce clock
            new_status = {
                "locked": True,  # Still locked until debounce + confirmation
                "last_breach": current_status.get("last_breach"),
                "eligible_since": today,
                "confirmed": False,
                "metrics": metrics["metrics"],
                "metrics_detail": metrics["metrics_detail"],
                "total_trades": metrics["total_trades"],
                "message": "All gates pass! Sustained for 1 full day + manual confirmation required to unlock.",
                "updated_at": datetime.now().isoformat(),
            }
        elif eligible_since != today:
            # Gates passed for more than 1 day — eligible for manual unlock
            new_status = {
                "locked": True,  # Still locked — awaiting manual confirmation
                "last_breach": current_status.get("last_breach"),
                "eligible_since": eligible_since,
                "confirmed": False,
                "eligible_for_unlock": True,
                "metrics": metrics["metrics"],
                "metrics_detail": metrics["metrics_detail"],
                "total_trades": metrics["total_trades"],
                "message": "ELIGIBLE for live unlock! Confirm via Telegram or UI.",
                "updated_at": datetime.now().isoformat(),
            }
        else:
            # Same day — debounce not yet complete
            new_status = {
                "locked": True,
                "last_breach": current_status.get("last_breach"),
                "eligible_since": eligible_since,
                "confirmed": False,
                "metrics": metrics["metrics"],
                "metrics_detail": metrics["metrics_detail"],
                "total_trades": metrics["total_trades"],
                "message": "All gates pass. Debounce: wait until tomorrow to confirm unlock.",
                "updated_at": datetime.now().isoformat(),
            }
    else:
        # Already unlocked and still passing — keep unlocked
        new_status = {
            "locked": False,
            "last_breach": current_status.get("last_breach"),
            "eligible_since": current_status.get("eligible_since"),
            "confirmed": True,
            "metrics": metrics["metrics"],
            "metrics_detail": metrics["metrics_detail"],
            "total_trades": metrics["total_trades"],
            "updated_at": datetime.now().isoformat(),
        }
    
    save_gate_status(new_status)
    logger.info(f"Gate check: locked={new_status['locked']}, "
                f"gates_passed={sum(1 for v in metrics['metrics'].values() if v)}/7")
    
    return new_status


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    status = check_gates()
    print(json.dumps(status, indent=2))
