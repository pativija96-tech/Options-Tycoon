"""
Phase 5 — replay the desk's iron condor on real NSE end-of-day option prices.

The rules are the desk's own (engine/signals/simple_ic_engine.py + the Trading Plan):
  strikes   NIFTY (put-call-parity level at entry) rounded to 50, short ±offset, wings
            `wing` beyond, `lot` quantity
  entry     "expiry_day": on each expiry day, sell next week's condor (how the desk trades
            today: enter Tuesday, the expiry day, into next Tuesday's contract); or a weekday
            number, entering the nearest expiry at least 2 days away (the engine's
            MIN_DAYS_TO_EXPIRY)
  exits     first of: profit target (share of credit), loss exit (₹), the exit-by day
            (N trading days before expiry), else expiry
  charges   engine.desk.trades.estimate_charges(8) — the same estimate the desk uses

Limits, stated in every report: only daily closes exist, so entries and exits are at the
day's close; a target or loss touched during the day and reversed by the close is not
seen; slippage is a parameter (default 0, i.e. optimistic).
"""

from collections import Counter

from engine.research.bhavcopy import as_date, build_days, parity_spot, price

LIMITS = ("End-of-day prices only: entry and every exit happen at that day's close. Intraday touches of the "
          "target or loss exit are not seen. Slippage per leg per order is {slip} points. Lot {lot} is applied to "
          "every year for comparability (NSE's lot size changed over time). Charges are the desk's estimate.")


def _round50(x):
    return int(round(x / 50.0) * 50)


def _pick_entries(days, entry, min_days=2):
    """[(entry_day, expiry)] in date order."""
    tdays = sorted(days)
    expiries = sorted({e for d in days.values() for e in d})
    out = []
    for d in tdays:
        dd = as_date(d)
        if entry == "expiry_day":
            if d not in expiries:
                continue
            later = [e for e in expiries if e > d]
        else:
            if dd.weekday() != int(entry):
                continue
            later = [e for e in expiries if (as_date(e) - dd).days >= min_days]
        if later:
            out.append((d, later[0]))
    return out


def replay(rows_or_days, *, offset=250, wing=100, lot=65, target_pct=0.5, loss_exit=None,
           exit_days_before_expiry=1, slippage_pts=0.0, charges=None, entry="expiry_day"):
    from engine.desk.trades import estimate_charges
    charges = estimate_charges(8) if charges is None else charges
    days = rows_or_days if isinstance(rows_or_days, dict) else build_days(rows_or_days)
    tdays = sorted(days)
    trades, skipped = [], []
    busy_until = None
    for d0, expiry in _pick_entries(days, entry):
        if busy_until and d0 < busy_until:
            continue                                   # one condor at a time; re-entry on the exit day is allowed
                                                       # (a hold-to-expiry trade closes at that day's close)
        chain = days[d0].get(expiry, {})
        spot = parity_spot(chain)
        if spot is None:
            skipped.append({"date": d0, "expiry": expiry, "reason": "no call/put pair to read NIFTY level"})
            continue
        sp, sc = _round50(spot) - offset, _round50(spot) + offset
        lp, lc = sp - wing, sc + wing
        legs = [("SELL", "PE", sp), ("SELL", "CE", sc), ("BUY", "PE", lp), ("BUY", "CE", lc)]
        entry_px = {k: price(chain.get((k[2], k[1]))) for k in legs}
        if any(v is None for v in entry_px.values()):
            missing = [f"{s} {o}" for (_, o, s), v in entry_px.items() if v is None]
            skipped.append({"date": d0, "expiry": expiry, "reason": "no price for " + ", ".join(missing)})
            continue
        credit = (entry_px[legs[0]] + entry_px[legs[1]] - entry_px[legs[2]] - entry_px[legs[3]]) - 4 * slippage_pts
        if credit <= 0:
            skipped.append({"date": d0, "expiry": expiry, "reason": f"credit {credit:.2f} not positive"})
            continue

        before_exp = [t for t in tdays if d0 < t < expiry]
        if exit_days_before_expiry and len(before_exp) >= exit_days_before_expiry:
            exit_by = before_exp[-exit_days_before_expiry]
        else:
            exit_by = expiry if expiry in days else (before_exp[-1] if before_exp else None)
        if exit_by is None:
            skipped.append({"date": d0, "expiry": expiry, "reason": "no trading day before expiry in the data"})
            continue

        last = dict(entry_px)
        gaps = 0
        exit_day, reason, close_cost = None, None, None
        for t in [x for x in tdays if d0 < x <= exit_by]:
            ch = days[t].get(expiry, {})
            for k in legs:
                v = price(ch.get((k[2], k[1])))
                if v is None:
                    gaps += 1
                else:
                    last[k] = v
            cost = last[legs[0]] + last[legs[1]] - last[legs[2]] - last[legs[3]]
            pnl = (credit - cost - 4 * slippage_pts) * lot
            if target_pct and pnl >= credit * target_pct * lot:
                exit_day, reason, close_cost = t, "target", cost
                break
            if loss_exit and pnl <= -loss_exit:
                exit_day, reason, close_cost = t, "loss_exit", cost
                break
            if t == exit_by:
                exit_day, reason, close_cost = t, ("expiry" if t == expiry else "exit_day"), cost
        if exit_day is None:
            skipped.append({"date": d0, "expiry": expiry, "reason": "no prices between entry and exit"})
            continue

        gross = round((credit - close_cost - 4 * slippage_pts) * lot, 2)
        max_loss = round((wing - credit) * lot, 2)
        trades.append({
            "opened_on": d0, "closed_on": exit_day, "expiry": expiry, "spot": spot,
            "strikes": f"{lp}/{sp} PE · {sc}/{lc} CE", "lot": lot, "status": "closed",
            "entry_credit": round(credit, 2), "credit_rupees": round(credit * lot, 2), "max_loss": max_loss,
            "exit_reason": reason, "pnl_gross": gross, "charges_est": charges,
            "pnl_net": round(gross - charges, 2), "price_gaps": gaps,
            "planned_risk": loss_exit if loss_exit else max_loss,
            "legs": [{"side": s, "option": o, "strike": k} for s, o, k in legs],
        })
        busy_until = exit_day
    return {"trades": trades, "skipped": skipped,
            "params": {"offset": offset, "wing": wing, "lot": lot, "target_pct": target_pct, "loss_exit": loss_exit,
                       "exit_days_before_expiry": exit_days_before_expiry, "slippage_pts": slippage_pts,
                       "charges": charges, "entry": entry},
            "limits": LIMITS.format(slip=slippage_pts, lot=lot)}


def summarize(result):
    """Desk-style scorecard (engine.desk.review.review_stats) plus replay-specific counts."""
    from engine.desk.review import review_stats
    trades = result["trades"]
    s = review_stats(trades)
    by_year = {}
    for t in trades:
        y = t["closed_on"][:4]
        by_year.setdefault(y, {"trades": 0, "net": 0.0})
        by_year[y]["trades"] += 1
        by_year[y]["net"] = round(by_year[y]["net"] + t["pnl_net"], 2)
    worst = min(trades, key=lambda t: t["pnl_net"]) if trades else None
    return {
        "params": result["params"], "limits": result["limits"],
        "trades": s["trades"], "skipped": len(result["skipped"]),
        "net": s.get("net"), "win_rate": s.get("win_rate"), "avg_win": s.get("avg_win"), "avg_loss": s.get("avg_loss"),
        "expectancy": s.get("expectancy"), "max_drawdown": s.get("max_drawdown"), "worst_week": s.get("worst_week"),
        "worst_trade": {k: worst[k] for k in ("opened_on", "closed_on", "strikes", "pnl_net", "exit_reason")} if worst else None,
        "avg_credit": round(sum(t["credit_rupees"] for t in trades) / len(trades), 2) if trades else None,
        "exit_reasons": dict(Counter(t["exit_reason"] for t in trades)),
        "by_year": by_year,
        "price_gaps": sum(t["price_gaps"] for t in trades),
        "skip_reasons": dict(Counter(x["reason"].split(" for ")[0] for x in result["skipped"])),
    }


def grid(rows_or_days, offsets=(200, 250, 300, 350, 400), loss_exits=(None, 1500), **kw):
    days = rows_or_days if isinstance(rows_or_days, dict) else build_days(rows_or_days)
    out = []
    for off in offsets:
        for le in loss_exits:
            out.append(summarize(replay(days, offset=off, loss_exit=le, **kw)))
    return out
