"""
Trade Ticket — turns today's signal + the user's Trading Plan (+ live Kite data
when available) into one ticket: GO / NO-GO checks, the 4 entry orders in
sequence, credit / max loss / reward : risk, margin, and the exit plan.

build_ticket() is pure (no I/O) so it can be tested without Kite.
Statuses per check: "pass", "fail", "warn" (does not block the trade), "unset" (rule not in
your plan), "unknown" (data needed for the check is unavailable).
"""

from datetime import date, timedelta

from engine.desk.market_calendar import (calendar_stale, event_hits, hold_info, is_trading_day, next_clear_entry,
                                         on_or_after, plan_events, weekly_expiry_after)
from engine.desk.leg_prices import (VOL_RATIO_MAX, VOL_RATIO_MIN, has_depth, leg_quality, mid, open_price, vol_ratio)
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
    """d minus n NSE trading days (weekends and listed holidays are skipped)."""
    while n > 0:
        d -= timedelta(days=1)
        if is_trading_day(d):
            n -= 1
    return d


def _legs_from_signal(signal):
    """(long_put, short_put, short_call, long_call) strikes from the signal's legs."""
    legs = (signal.get("trade") or {}).get("legs") or []
    get = lambda action, opt: next((int(l["strike"]) for l in legs if l.get("action") == action and l.get("option") == opt), None)
    return get("BUY", "PE"), get("SELL", "PE"), get("SELL", "CE"), get("BUY", "CE")


def build_ticket(signal, plan, today, *, lot=65, expiry=None, symbols=None, quotes=None,
                 margin_required=None, funds_available=None, kite_errors=None, kite_connected=False, risk=None,
                 calendar=None):
    """
    signal:  dict from generate_daily_signal() (action "trade" or "skip").
    plan:    dict from engine.desk.plan (unset rules are None / []).
    today:   IST date.
    symbols: {(strike, "CE"|"PE"): tradingsymbol} from Kite, or None.
    quotes:  {tradingsymbol: {"ltp","bid","ask","last_trade_time","quote_time"}} from Kite, or None.
    calendar: market_calendar.load_events() — the event calendar — or None for the plan's events only.
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
    # without it, assume the next Tuesday (moved for holidays) and say it is unconfirmed.
    expiry_confirmed = expiry is not None
    if expiry is None:
        expiry = weekly_expiry_after(today)

    # Prices: live Kite best bid (sells) / best ask (buys) when every leg has a quote, else the
    # signal's model estimates. See leg_prices.py for why not the last traded price.
    est = {(l["strike"], l["option"]): float(l.get("premium_est") or 0) for l in trade.get("legs", [])}
    live = bool(symbols and quotes and all(symbols.get(k) in quotes for k in [(lp, "PE"), (sp, "PE"), (sc, "CE"), (lc, "CE")]))

    def price(side, strike, opt):
        if live:
            return open_price(side, quotes[symbols[(strike, opt)]])
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
        order = {"step": i, "side": side, "strike": strike, "option": opt, "symbol": symbol(strike, opt),
                 "qty": lot, "product": "NRML", "price": round(price(side, strike, opt), 2), "bid": bid, "ask": ask,
                 "note": note}
        if live:
            q = quotes[symbols[(strike, opt)]]
            order.update(ltp=q.get("ltp"), has_depth=has_depth(side, q), **leg_quality(q, today))
        orders.append(order)

    credit_ps = round(price("SELL", sp, "PE") + price("SELL", sc, "CE") - price("BUY", lp, "PE") - price("BUY", lc, "CE"), 2)
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

    # Window: today through expiry, in case the position is still held. Overnight events count on
    # the Indian session they hit. High tier blocks, medium warns.
    events = plan_events(plan) + list((calendar or {}).get("events") or [])
    hits = event_hits(events, today, expiry)
    high = [h for h in hits if h["tier"] == "high"]
    medium = [h for h in hits if h["tier"] != "high"]

    def describe(h):
        hit = f", hits the {h['impact_date']} session" if h["impact_date"] != h["date"] else ""
        return f"{h['name']} on {h['date']}{hit} ({h['tier']})"

    event_label = "No event before expiry"
    if high:
        add("events", event_label, "fail", "; ".join(describe(h) for h in hits))
    elif medium:
        add("events", event_label, "warn", "; ".join(describe(h) for h in medium))
    elif calendar is not None and calendar_stale(calendar, today):
        add("events", event_label, "unset", "Not set — calendar stale: refresh data/historical/nifty_events.json")
    elif not events:
        add("events", event_label, "unset", "No event dates in your plan")
    else:
        add("events", event_label, "pass", f"No listed event hits a session from {today.isoformat()} to expiry {expiry.isoformat()}")
    clear = next_clear_entry(plan, today, events) if high else None

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

    n_before = plan.get("exit_days_before_expiry")
    exit_by_d = subtract_trading_days(expiry, int(n_before)) if n_before is not None else None

    buffer = plan.get("expiry_margin_buffer") or 0
    cushion = plan.get("margin_cushion_pct") or 0
    reserve = plan.get("topup_reserve") or 0
    margin_label = "Margin available (cushion and expiry buffer)"
    if margin_required is None or funds_available is None:
        add("margin", margin_label, "unknown",
            "Needs Kite login" if not kite_connected else "Kite margin or funds not available")
    else:
        entry_need = margin_required * (1 + cushion / 100)
        full_need = entry_need + buffer
        have = f"{_inr(funds_available)} available"
        if funds_available < entry_need:
            add("margin", margin_label, "fail",
                f"Entry needs {_inr(margin_required)} + {_fmt_num(cushion)}% cushion = {_inr(entry_need)}; {have}. "
                f"Short by {_inr(entry_need - funds_available)}")
        elif funds_available >= full_need:
            add("margin", margin_label, "pass",
                f"{_inr(entry_need)} entry with cushion + {_inr(buffer)} expiry buffer; {have}")
        else:
            add_now = full_need - funds_available
            exits_early = exit_by_d is not None and exit_by_d < expiry
            if funds_available + reserve >= full_need:
                add("margin", margin_label, "warn",
                    f"Entry is covered. You may need to add {_inr(add_now)} from your reserve if still holding on expiry morning")
            elif exits_early:
                add("margin", margin_label, "warn",
                    f"Entry is covered. The {_inr(buffer)} expiry buffer is short by {_inr(add_now)} with {_inr(reserve)} reserve; "
                    f"your plan exits by {exit_by_d.isoformat()}, before it applies")
            else:
                add("margin", margin_label, "fail",
                    f"Exit-by is not before expiry and the {_inr(buffer)} expiry buffer is short by {_inr(add_now)}, "
                    f"even with {_inr(reserve)} reserve")

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
        add("prices_live", "Leg prices from Kite", "pass", "Live best bid (sells) and best ask (buys)")
    else:
        add("prices_live", "Leg prices from Kite", "unknown", "Model estimates — Kite quotes not available")

    # Quotes must be real prices for this session and fit one NIFTY level.
    unreliable = []
    ratio = None
    if live:
        no_depth = [o["symbol"] for o in orders if not o["has_depth"]]
        if no_depth:
            unreliable.append("no " + "bid/ask" + " for " + ", ".join(no_depth))
        old = [o["symbol"] for o in orders if o["previous_session"]]
        if old:
            unreliable.append("no trade yet this session for " + ", ".join(old))
        ratio = vol_ratio([(o["strike"], o["option"], mid(quotes[o["symbol"]])) for o in orders],
                          market["spot"], (expiry - today).days)
        if ratio is not None and not VOL_RATIO_MIN <= ratio <= VOL_RATIO_MAX:
            unreliable.append(f"put/call volatility ratio {ratio:.2f} is outside the normal "
                              f"{VOL_RATIO_MIN}–{VOL_RATIO_MAX}, so the legs don't fit NIFTY at {market['spot']:,.0f}")
        if unreliable:
            add("legs_consistent", "Leg prices consistent with spot", "fail",
                "Prices unreliable — rebuild: " + "; ".join(unreliable))
        elif ratio is None:
            add("legs_consistent", "Leg prices consistent with spot", "unknown", "Could not compare the legs with NIFTY")
        else:
            add("legs_consistent", "Leg prices consistent with spot", "pass",
                f"Put/call volatility ratio {ratio:.2f} (normal {VOL_RATIO_MIN}–{VOL_RATIO_MAX})")
        wide = [f"{o['symbol']} {o['spread_pct']:.1f}%" for o in orders if o["wide"]]
        stale = [o["symbol"] for o in orders if o["stale"] and not o["previous_session"]]
        notes = ([f"Wide spread: {', '.join(wide)}"] if wide else []) + ([f"Last trade over 2 min ago: {', '.join(stale)}"] if stale else [])
        if any(o["previous_session"] for o in orders):
            notes.append("Some legs have no trade yet this session")
        if notes:
            add("leg_quality", "Leg spreads and freshness", "warn", " · ".join(notes))
        else:
            add("leg_quality", "Leg spreads and freshness", "pass", "All spreads within 5% and last trades within 2 minutes")
    else:
        add("legs_consistent", "Leg prices consistent with spot", "unknown", "Needs live Kite quotes")

    # Time to hold: the next session you could enter in must come before the exit-by day.
    session = on_or_after(today)
    if exit_by_d is None:
        add("time_to_hold", "Time to hold before exit-by", "unset", "No exit-before-expiry rule in your plan")
    elif exit_by_d <= session:
        add("time_to_hold", "Time to hold before exit-by", "fail",
            f"No time to hold: exit-by is {DAY_NAMES[exit_by_d.weekday()]} {exit_by_d.isoformat()}, the next session is "
            f"{DAY_NAMES[session.weekday()]} {session.isoformat()}. This is the {expiry.isoformat()} contract — "
            "prepare again on expiry day for next week's")
    else:
        add("time_to_hold", "Time to hold before exit-by", "pass",
            f"Enter {DAY_NAMES[session.weekday()]} {session.isoformat()}, exit by {DAY_NAMES[exit_by_d.weekday()]} {exit_by_d.isoformat()}")

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
    exit_by = exit_by_d.isoformat() if exit_by_d else None

    return {**base,
            "action": "trade", "verdict": verdict,
            "failed": [c["label"] for c in fails], "unset_count": len(unset),
            "pricing": "kite_live" if live else "estimate",
            "prices_unreliable": bool(unreliable), "vol_ratio": ratio,
            "hold": hold_info(session, exit_by_d, expiry),
            "event_alert": high[0] if high else None, "next_clear_entry": clear.isoformat() if clear else None,
            "expiry": expiry.isoformat(), "expiry_confirmed": expiry_confirmed,
            "strikes": {"long_put": lp, "short_put": sp, "short_call": sc, "long_call": lc, "wing": wing},
            "lot": lot, "orders": orders,
            "credit_per_share": credit_ps, "credit": credit, "max_loss": max_loss, "reward_risk": rr,
            "charges_est": charges,
            "margin": {"required": margin_required, "buffer": buffer, "cushion_pct": cushion, "reserve": reserve,
                       "funds": funds_available},
            "elm_estimate": trade.get("elm_estimate"),
            "risk": risk,
            "checks": checks,
            "exit_plan": {"target": target, "loss_exit": loss_exit, "exit_by": exit_by,
                          "order": "Buy back both shorts first, then sell the hedges"}}
