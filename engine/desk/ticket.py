"""
Trade Ticket — turns today's signal + the user's Trading Plan (+ live Kite data
when available) into one ticket: GO / NO-GO checks, the 4 entry orders in
sequence, credit / max loss / reward : risk, margin, and the exit plan.

build_ticket() is pure (no I/O) so it can be tested without Kite.
Statuses per check: "pass", "fail", "unset" (rule not in your plan),
"unknown" (data needed for the check is unavailable).
"""

from datetime import date, timedelta

from engine.signals.simple_ic_engine import RISK_CAP_PCT

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _inr(n):
    if n is None:
        return "—"
    s = f"{abs(round(n)):,}"
    return ("−₹" if n < 0 else "₹") + s


def _fmt_num(n, places=2):
    return f"{n:.{places}f}".rstrip("0").rstrip(".") if n is not None else "—"


def subtract_trading_days(d: date, n: int) -> date:
    """d minus n weekdays (NSE holidays are not known here)."""
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _legs_from_signal(signal):
    """(long_put, short_put, short_call, long_call) strikes from the signal's legs."""
    legs = (signal.get("trade") or {}).get("legs") or []
    get = lambda action, opt: next((int(l["strike"]) for l in legs if l.get("action") == action and l.get("option") == opt), None)
    return get("BUY", "PE"), get("SELL", "PE"), get("SELL", "CE"), get("BUY", "CE")


def build_ticket(signal, plan, today, *, lot=65, expiry=None, symbols=None, quotes=None,
                 margin_required=None, funds_available=None, kite_errors=None, kite_connected=False, risk=None):
    """
    signal:  dict from generate_daily_signal() (action "trade" or "skip").
    plan:    dict from engine.desk.plan (unset rules are None / []).
    today:   IST date.
    symbols: {(strike, "CE"|"PE"): tradingsymbol} from Kite, or None.
    quotes:  {tradingsymbol: {"ltp","bid","ask"}} from Kite, or None.
    """
    kite_errors = list(kite_errors or [])
    cond = signal.get("conditions") or {}
    market = {
        "spot": cond.get("nifty_price") or cond.get("nifty"),
        "vix": cond.get("vix_level") or cond.get("vix"),
        "data_source": cond.get("data_source") or "unknown",
        "data_is_live": bool(cond.get("data_is_live")),
    }
    base = {"date": today.isoformat(), "weekday": DAY_NAMES[today.weekday()], "market": market,
            "kite_connected": kite_connected, "kite_notes": kite_errors}

    if signal.get("action") != "trade":
        return {**base, "action": "skip", "verdict": "NO TRADE",
                "skip_reason": signal.get("reason") or "The signal engine found no trade today."}

    lp, sp, sc, lc = _legs_from_signal(signal)
    if None in (lp, sp, sc, lc):
        return {**base, "action": "skip", "verdict": "NO TRADE", "skip_reason": "Signal is missing one of its four legs."}
    trade = signal.get("trade") or {}
    wing = trade.get("width") or (sp - lp)
    # Kite's instrument list confirms the real expiry (holiday shifts included);
    # without it, assume the next Tuesday after today and say it is unconfirmed.
    expiry_confirmed = expiry is not None
    if expiry is None:
        days = (1 - today.weekday()) % 7 or 7
        expiry = today + timedelta(days=days)

    # Prices: live Kite quotes when every leg has one, else the signal's model estimates.
    est = {(l["strike"], l["option"]): float(l.get("premium_est") or 0) for l in trade.get("legs", [])}
    live = bool(symbols and quotes and all(symbols.get(k) in quotes for k in [(lp, "PE"), (sp, "PE"), (sc, "CE"), (lc, "CE")]))

    def price(strike, opt):
        if live:
            return quotes[symbols[(strike, opt)]]["ltp"]
        return est.get((strike, opt), 0.0)

    def symbol(strike, opt):
        if symbols and symbols.get((strike, opt)):
            return symbols[(strike, opt)]
        return f"NIFTY {strike} {opt}"

    def bidask(strike, opt):
        if live:
            q = quotes[symbols[(strike, opt)]]
            return q.get("bid"), q.get("ask")
        return None, None

    order_defs = [("BUY", lp, "PE", "Put hedge — place first, wait for COMPLETE"),
                  ("BUY", lc, "CE", "Call hedge — wait for COMPLETE"),
                  ("SELL", sp, "PE", "Short put — only after both hedges are COMPLETE"),
                  ("SELL", sc, "CE", "Short call — closes the entry")]
    orders = []
    for i, (side, strike, opt, note) in enumerate(order_defs, 1):
        bid, ask = bidask(strike, opt)
        orders.append({"step": i, "side": side, "strike": strike, "option": opt, "symbol": symbol(strike, opt),
                       "qty": lot, "product": "NRML", "price": round(price(strike, opt), 2), "bid": bid, "ask": ask,
                       "note": note})

    credit_ps = round(price(sp, "PE") + price(sc, "CE") - price(lp, "PE") - price(lc, "CE"), 2)
    credit = round(credit_ps * lot, 2)
    max_loss = round((wing - credit_ps) * lot, 2)
    rr = round(credit / max_loss, 2) if max_loss > 0 else None
    charges = (trade.get("charges") or {}).get("total")
    capital = (signal.get("risk_check") or {}).get("capital")

    # ---- checks -------------------------------------------------------------
    checks = []

    def add(key, label, status, detail):
        checks.append({"key": key, "label": label, "status": status, "detail": detail})

    # The signal engine's own skip rules, re-checked here because live Kite prices
    # can differ from the model estimates the engine checked them on.
    if capital:
        cap = round(capital * RISK_CAP_PCT, 2)
        add("risk_cap", f"Max loss within {RISK_CAP_PCT:.0%} of capital (signal engine rule)",
            "pass" if max_loss <= cap else "fail",
            f"{_inr(max_loss)} vs {_inr(cap)} ({RISK_CAP_PCT:.0%} of {_inr(capital)})")
    else:
        add("risk_cap", f"Max loss within {RISK_CAP_PCT:.0%} of capital (signal engine rule)", "unknown",
            "Capital not in the signal")
    if charges is not None:
        add("covers_charges", "Credit covers charges (signal engine rule)",
            "pass" if credit - charges > 0 else "fail",
            f"{_inr(credit)} credit vs {_inr(charges)} charges")
    else:
        add("covers_charges", "Credit covers charges (signal engine rule)", "unknown", "Charges not in the signal")

    days = plan.get("entry_days") or []
    if not days:
        add("entry_day", "Entry day", "unset", "No entry days in your plan")
    elif base["weekday"] in days:
        add("entry_day", "Entry day", "pass", f"{base['weekday']} is one of your entry days ({', '.join(days)})")
    else:
        add("entry_day", "Entry day", "fail", f"{base['weekday']} is not an entry day in your plan ({', '.join(days)})")

    vmin, vmax, vix = plan.get("vix_min"), plan.get("vix_max"), market["vix"]
    if vmin is None and vmax is None:
        add("vix", "India VIX in your band", "unset", "No VIX band in your plan")
    elif vix is None:
        add("vix", "India VIX in your band", "unknown", "VIX not available")
    else:
        lo_ok = vmin is None or vix >= vmin
        hi_ok = vmax is None or vix <= vmax
        band = f"{_fmt_num(vmin) if vmin is not None else '—'}–{_fmt_num(vmax) if vmax is not None else '—'}"
        add("vix", "India VIX in your band", "pass" if lo_ok and hi_ok else "fail",
            f"{vix:.1f} {'within' if lo_ok and hi_ok else 'outside'} {band}")

    events = plan.get("events") or []
    if not events:
        add("events", "No event before expiry", "unset", "No event dates in your plan")
    else:
        hits = [e for e in events if today <= date.fromisoformat(e["date"]) <= expiry]
        if hits:
            add("events", "No event before expiry", "fail", "; ".join(f"{e['label']} on {e['date']}" for e in hits))
        else:
            add("events", "No event before expiry", "pass", f"None of your {len(events)} listed events fall before {expiry.isoformat()}")

    def threshold(key, label, value, limit, ok, fmt):
        if limit is None:
            add(key, label, "unset", "Not set in your plan")
        elif value is None:
            add(key, label, "unknown", "Not available")
        else:
            add(key, label, "pass" if ok(value, limit) else "fail",
                f"{fmt(value)} {'meets' if ok(value, limit) else 'misses'} your limit {fmt(limit)}")

    threshold("min_credit", "Credit at or above your minimum", credit, plan.get("min_credit"), lambda v, l: v >= l, _inr)
    threshold("min_rr", "Reward : risk at or above your minimum", rr, plan.get("min_rr"), lambda v, l: v >= l, lambda v: _fmt_num(v))
    threshold("max_loss", "Max loss within your per-trade limit", max_loss, plan.get("max_loss_per_trade"), lambda v, l: v <= l, _inr)

    buffer = plan.get("expiry_margin_buffer") or 0
    if margin_required is None or funds_available is None:
        add("margin", "Margin plus expiry buffer available", "unknown",
            "Needs Kite login" if not kite_connected else "Kite margin or funds not available")
    else:
        need = margin_required + buffer
        add("margin", "Margin plus expiry buffer available", "pass" if need <= funds_available else "fail",
            f"{_inr(margin_required)} + {_inr(buffer)} buffer vs {_inr(funds_available)} available")

    if not risk or not risk.get("configured"):
        add("risk_budget", "Loss limits and losing streak", "unset", "No weekly / monthly loss limit or pause rule in your plan")
    elif risk["breaches"]:
        add("risk_budget", "Loss limits and losing streak", "fail", "; ".join(risk["breaches"]))
    else:
        parts = []
        if risk.get("week_left") is not None:
            parts.append(f"week {_inr(risk['week_left'])} left")
        if risk.get("month_left") is not None:
            parts.append(f"month {_inr(risk['month_left'])} left")
        parts.append(f"losing streak {risk['losing_streak']}")
        add("risk_budget", "Loss limits and losing streak", "pass", " · ".join(parts))

    if market["data_is_live"]:
        add("data_live", "Signal built on live Kite data", "pass", "NIFTY and VIX from Kite")
    else:
        # A warning, as on the live-nifty page — not a NO-GO.
        add("data_live", "Signal built on live Kite data", "unknown",
            f"Delayed data ({market['data_source']}) — log in to Kite and prepare again for live prices")

    if live:
        add("prices_live", "Leg prices from Kite", "pass", "Live last-traded prices")
    else:
        add("prices_live", "Leg prices from Kite", "unknown", "Model estimates — Kite quotes not available")

    fails = [c for c in checks if c["status"] == "fail"]
    unset = [c for c in checks if c["status"] == "unset"]
    verdict = "NO-GO" if fails else "GO"

    # ---- exit plan ----------------------------------------------------------
    pt = plan.get("profit_target_pct")
    target = None
    if pt:
        target = {"pct": pt, "profit": round(credit * pt, 2), "buyback_total": round(credit * (1 - pt), 2),
                  "buyback_per_share": round(credit_ps * (1 - pt), 2),
                  # Charges are paid on all 8 orders, so the net is the gross profit minus all of them.
                  "profit_net": round(credit * pt - charges, 2) if charges is not None else None}
    loss_exit = plan.get("loss_exit_rupees")
    n_before = plan.get("exit_days_before_expiry")
    exit_by = subtract_trading_days(expiry, int(n_before)).isoformat() if n_before is not None else None

    return {**base,
            "action": "trade", "verdict": verdict,
            "failed": [c["label"] for c in fails], "unset_count": len(unset),
            "pricing": "kite_live" if live else "estimate",
            "expiry": expiry.isoformat(), "expiry_confirmed": expiry_confirmed,
            "strikes": {"long_put": lp, "short_put": sp, "short_call": sc, "long_call": lc, "wing": wing},
            "lot": lot, "orders": orders,
            "credit_per_share": credit_ps, "credit": credit, "max_loss": max_loss, "reward_risk": rr,
            "charges_est": charges,
            "margin": {"required": margin_required, "buffer": buffer, "funds": funds_available},
            "elm_estimate": trade.get("elm_estimate"),
            "risk": risk,
            "checks": checks,
            "exit_plan": {"target": target, "loss_exit": loss_exit, "exit_by": exit_by,
                          "order": "Buy back both shorts first, then sell the hedges"}}
