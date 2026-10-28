"""
Position monitor + exit ticket (Phase 3).

monitor_position() is pure: given an open desk trade, live leg prices and NIFTY spot,
it returns live P&L, progress to the profit target and loss exit, distance to the
short strikes, the exit-by countdown, an alert status, and the 4 closing orders
(shorts bought back first). Without prices it returns the same shape with the live
fields set to None, so the page can say "log in to Kite".
"""

from datetime import date


def _strike(legs, side, option):
    return next((l["strike"] for l in legs if l["side"] == side and l["option"] == option), None)


def monitor_position(trade, today: date, quotes=None, spot=None, plan=None):
    plan = plan or {}
    legs = trade["legs"]
    lot = trade["lot"]
    credit_ps = trade["entry_credit"]
    credit = round(credit_ps * lot, 2)
    sp, lp = _strike(legs, "SELL", "PE"), _strike(legs, "BUY", "PE")
    sc, lc = _strike(legs, "SELL", "CE"), _strike(legs, "BUY", "CE")
    wing = (sp - lp) if (sp and lp) else ((lc - sc) if (sc and lc) else None)
    max_loss = round((wing - credit_ps) * lot, 2) if wing else None

    exit_plan = trade.get("exit_plan") or {}
    pt = exit_plan.get("profit_target_pct", plan.get("profit_target_pct"))
    loss_exit = exit_plan.get("loss_exit", plan.get("loss_exit_rupees"))
    exit_by = exit_plan.get("exit_by")
    target_profit = round(credit * pt, 2) if pt else None

    live = bool(quotes) and all(l["symbol"] in quotes for l in legs)
    close_cost_ps = None
    pnl = None
    if live:
        close_cost_ps = round(sum(quotes[l["symbol"]] if l["side"] == "SELL" else -quotes[l["symbol"]] for l in legs), 2)
        pnl = round((credit_ps - close_cost_ps) * lot, 2)

    def pct(v, whole):
        if v is None or not whole:
            return None
        return max(0.0, min(100.0, round(v / whole * 100, 1)))

    target_progress = pct(pnl, target_profit) if pnl is not None else None
    loss_progress = pct(-pnl if pnl is not None else None, loss_exit) if pnl is not None else None

    days_to_exit = None
    if exit_by:
        days_to_exit = (date.fromisoformat(exit_by) - today).days

    if pnl is not None and target_profit and pnl >= target_profit:
        status, message = "target", "Profit target reached — prepare exit"
    elif pnl is not None and loss_exit and pnl <= -loss_exit:
        status, message = "loss_exit", "Loss exit reached — prepare exit"
    elif days_to_exit is not None and days_to_exit <= 0:
        status, message = "exit_day", "Exit-by day — prepare exit"
    elif pnl is None:
        status, message = "no_data", "Log in to Kite for live P&L"
    else:
        status, message = "hold", "Holding — within plan"

    exit_orders = []
    ordered = sorted(legs, key=lambda l: (0 if l["side"] == "SELL" else 1, l["option"] != "PE"))
    for i, l in enumerate(ordered, 1):
        exit_orders.append({"step": i, "side": "BUY" if l["side"] == "SELL" else "SELL", "symbol": l["symbol"],
                            "strike": l["strike"], "option": l["option"], "qty": l["qty"], "product": "NRML",
                            "price": round(quotes[l["symbol"]], 2) if live else None})

    return {
        "trade_id": trade.get("id"), "opened_on": trade.get("opened_on"), "expiry": trade.get("expiry"),
        "strikes": {"long_put": lp, "short_put": sp, "short_call": sc, "long_call": lc, "wing": wing},
        "lot": lot, "entry_credit_per_share": credit_ps, "credit": credit, "max_loss": max_loss,
        "live": live, "spot": spot, "close_cost": round(close_cost_ps * lot, 2) if close_cost_ps is not None else None,
        "pnl": pnl, "target_profit": target_profit, "target_progress": target_progress,
        "loss_exit": loss_exit, "loss_progress": loss_progress,
        "distance_to_short_call": round(sc - spot, 1) if (spot and sc) else None,
        "distance_to_short_put": round(spot - sp, 1) if (spot and sp) else None,
        "exit_by": exit_by, "days_to_exit_by": days_to_exit,
        "status": status, "message": message,
        "exit_orders": exit_orders,
        "exit_rule": "Buy back both shorts first (wait for COMPLETE), then sell the hedges. Fresh opposite orders, exact quantity.",
    }
