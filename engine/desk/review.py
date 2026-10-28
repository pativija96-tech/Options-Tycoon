"""
Weekly review + risk budget (Phase 4). Pure functions over closed desk trades.

R-multiple = net P&L ÷ the risk planned at entry (your loss exit if set, else the
trade's max loss). Weeks run Monday–Sunday; dates are the trade's close date.
"""

from datetime import date, timedelta


def _planned_risk(t):
    if t.get("planned_risk"):
        return float(t["planned_risk"])
    legs = t.get("legs") or []
    sp = next((l["strike"] for l in legs if l["side"] == "SELL" and l["option"] == "PE"), None)
    lp = next((l["strike"] for l in legs if l["side"] == "BUY" and l["option"] == "PE"), None)
    if sp and lp and t.get("entry_credit") is not None:
        return round((sp - lp - t["entry_credit"]) * t["lot"], 2)
    return None


def _closed(trades):
    return sorted([t for t in trades if t.get("status") == "closed" and t.get("pnl_net") is not None],
                  key=lambda t: (t.get("closed_on") or t.get("opened_on"), t.get("id") or 0))


def review_stats(trades):
    closed = _closed(trades)
    n = len(closed)
    out = {"trades": n, "open_trades": len([t for t in trades if t.get("status") == "open"])}
    if not n:
        return {**out, "net": 0, "rows": [], "equity": []}
    pnls = [t["pnl_net"] for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    equity, peak, max_dd, run = [], 0.0, 0.0, 0.0
    rows = []
    for t in closed:
        run += t["pnl_net"]
        peak = max(peak, run)
        max_dd = min(max_dd, run - peak)
        risk = _planned_risk(t)
        r = round(t["pnl_net"] / risk, 2) if risk else None
        equity.append({"date": t.get("closed_on") or t.get("opened_on"), "equity": round(run, 2)})
        rows.append({"id": t.get("id"), "opened_on": t.get("opened_on"), "closed_on": t.get("closed_on"),
                     "strikes": t.get("strikes"), "credit": round((t.get("entry_credit") or 0) * t["lot"], 2),
                     "pnl_gross": t.get("pnl_gross"), "charges_est": t.get("charges_est"), "pnl_net": t["pnl_net"],
                     "r": r, "followed_plan": t.get("followed_plan"), "note": t.get("note"),
                     "exit_reason": t.get("exit_reason"), "source": t.get("source")})
    weekly = weekly_totals(closed)
    rs = [row["r"] for row in rows if row["r"] is not None]

    def split(flag):
        ps = [t["pnl_net"] for t in closed if t.get("followed_plan") == flag]
        return {"trades": len(ps), "net": round(sum(ps), 2), "avg": round(sum(ps) / len(ps), 2) if ps else None}

    return {**out,
            "net": round(sum(pnls), 2),
            "win_rate": round(len(wins) / n * 100, 1),
            "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
            "expectancy": round(sum(pnls) / n, 2),
            "expectancy_r": round(sum(rs) / len(rs), 2) if rs else None,
            "max_drawdown": round(max_dd, 2),
            "worst_week": min((w["net"] for w in weekly), default=None),
            "weeks": weekly,
            "followed": split("yes"), "deviated": split("no"),
            "unreviewed": len([t for t in closed if not t.get("followed_plan")]),
            "rows": list(reversed(rows)), "equity": equity}


def weekly_totals(closed):
    by = {}
    for t in closed:
        d = date.fromisoformat((t.get("closed_on") or t.get("opened_on"))[:10])
        wk = d - timedelta(days=d.weekday())
        by[wk] = round(by.get(wk, 0.0) + t["pnl_net"], 2)
    return [{"week_of": k.isoformat(), "net": v} for k, v in sorted(by.items())]


def risk_budget(trades, plan, today: date):
    """
    Net P&L this week and this month (by close date), the current losing streak,
    and whether any plan limit is hit. Limits are positive rupee amounts.
    """
    closed = _closed(trades)
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    def net_since(start):
        return round(sum(t["pnl_net"] for t in closed
                         if date.fromisoformat((t.get("closed_on") or t["opened_on"])[:10]) >= start), 2)

    week_net, month_net = net_since(week_start), net_since(month_start)
    streak = 0
    for t in reversed(closed):
        if t["pnl_net"] < 0:
            streak += 1
        else:
            break
    wl, ml, pause = plan.get("weekly_loss_limit"), plan.get("monthly_loss_limit"), plan.get("pause_after_losses")
    breaches = []
    if wl is not None and week_net <= -wl:
        breaches.append(f"Weekly loss limit hit: {week_net:,.0f} vs −{wl:,.0f}")
    if ml is not None and month_net <= -ml:
        breaches.append(f"Monthly loss limit hit: {month_net:,.0f} vs −{ml:,.0f}")
    if pause and streak >= pause:
        breaches.append(f"{streak} losses in a row — your plan pauses after {int(pause)}")
    return {"week_net": week_net, "month_net": month_net, "losing_streak": streak,
            "week_left": round(wl + week_net, 2) if wl is not None else None,
            "month_left": round(ml + month_net, 2) if ml is not None else None,
            "configured": any(v is not None for v in (wl, ml, pause)), "breaches": breaches}
