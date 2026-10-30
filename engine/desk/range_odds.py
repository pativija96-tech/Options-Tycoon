"""
Morning range check — how far NIFTY moved over a holding window that started on
mornings like today's. Data and counts only: no direction call, no recommendation.

Built from pieces that already exist in this repo:
  - move buckets              engine/signals/data_fetcher.py  bucket_us_move
  - 95% Wilson interval       engine/signals/pattern_matcher.py _wilson_ci
  - minimum 20 matches        config/settings.json min_historical_matches
  - lift vs all days          scripts/range_edge_validation.py (the "does bucketing add lift" test)
  - 3-year train / 6-month
    test walk-forward         scripts/range_walk_forward.py
  - distinct episodes         scripts/high_vol_validation.py
What is different from those scripts (on purpose):
  - the window is the real holding period (entry-day open → N trading days), not one day
  - "touched" uses each day's high and low, not only the close
  - conditions are real overnight world closes and India VIX, not NIFTY's own previous day
  - point widths are scaled to today's NIFTY level (250 pts at 15,000 ≠ 250 pts at 25,000)

All inputs are {symbol: [{"date","open","high","low","close"}, ...]} sorted by date.
"""

from datetime import date, timedelta

from engine.signals.data_fetcher import bucket_us_move
from engine.signals.pattern_matcher import _wilson_ci

WIDTHS = [150, 200, 250, 300, 350, 400]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
WORLD_SHOWN = ["sp500", "nasdaq", "vix", "dxy", "us_10y", "ftse", "dax", "nikkei", "hang_seng"]
DIMS = ["vix_band", "us_bucket", "trend_bucket"]   # dropped from the right when matches run short


def _d(s):
    return date.fromisoformat(s[:10])


def last_two_before(rows, day: date):
    """The last two closes dated before `day` → (change %, date of the last close), or (None, None)."""
    before = [r for r in rows if _d(r["date"]) < day]
    if len(before) < 2 or not before[-2]["close"]:
        return None, None
    a, b = before[-2]["close"], before[-1]["close"]
    return round((b - a) / a * 100, 2), before[-1]["date"]


def last_close_before(rows, day: date):
    before = [r for r in rows if _d(r["date"]) < day]
    return (before[-1]["close"], before[-1]["date"]) if before else (None, None)


def conditions_for(series, day: date, nifty_closes_before=None):
    """
    What was known on the morning of `day`, before India opened: the last world closes,
    India VIX's last close and NIFTY's 5-day move. Only rows dated before `day` are used,
    so a US close from the previous US session counts and nothing from `day` itself does.
    """
    world = {}
    for name in WORLD_SHOWN:
        chg, d = last_two_before(series.get(name) or [], day)
        world[name] = {"change_pct": chg, "date": d}
    vix, vix_date = last_close_before(series.get("india_vix") or [], day)
    closes = nifty_closes_before
    if closes is None:
        closes = [r["close"] for r in (series.get("nifty") or []) if _d(r["date"]) < day]
    trend = round((closes[-1] - closes[-6]) / closes[-6] * 100, 2) if len(closes) >= 6 else None
    return {"world": world, "india_vix": vix, "india_vix_date": vix_date, "nifty_5d_pct": trend}


def vix_terciles(values):
    v = sorted(x for x in values if x is not None)
    if len(v) < 3:
        return None
    return (v[len(v) // 3], v[(2 * len(v)) // 3])


def buckets(cond, terciles):
    vix = cond.get("india_vix")
    if vix is None or terciles is None:
        band = None
    else:
        band = "low" if vix < terciles[0] else ("high" if vix >= terciles[1] else "mid")
    us = (cond["world"].get("sp500") or {}).get("change_pct")
    trend = cond.get("nifty_5d_pct")
    return {"vix_band": band,
            "us_bucket": bucket_us_move(us) if us is not None else None,
            # same scaling the old matcher used for its multi-day trend (3-day sum / 3)
            "trend_bucket": bucket_us_move(trend / 5) if trend is not None else None}


def build_samples(series, before: date, horizon: int, weekday: int):
    """One sample per past entry day on `weekday` whose whole window ended before `before`."""
    nifty = series.get("nifty") or []
    days = [_d(r["date"]) for r in nifty]
    out = []
    for i, r in enumerate(nifty):
        d = days[i]
        if d.weekday() != weekday or i < 6 or i + horizon - 1 >= len(nifty):
            continue
        window = nifty[i:i + horizon]
        if _d(window[-1]["date"]) >= before:
            continue
        ref = r["open"] or nifty[i - 1]["close"]
        hi = max((w["high"] if w["high"] is not None else w["close"]) for w in window)
        lo = min((w["low"] if w["low"] is not None else w["close"]) for w in window)
        out.append({
            "date": d.isoformat(), "exit_date": window[-1]["date"], "ref": ref,
            "up_pct": (hi - ref) / ref * 100, "down_pct": (ref - lo) / ref * 100,
            "end_pct": (window[-1]["close"] - ref) / ref * 100,
            "cond": conditions_for(series, d, [x["close"] for x in nifty[:i]]),
        })
    return out


def _touch_stay(s, w_pct):
    return s["up_pct"] <= w_pct and s["down_pct"] <= w_pct


def _rate(samples, w_pct):
    n = len(samples)
    k = sum(1 for s in samples if _touch_stay(s, w_pct))
    return k, n


def match(samples, today_b, terciles, min_matches):
    """Samples in today's buckets, dropping dimensions from the right until there are enough."""
    labelled = [(s, buckets(s["cond"], terciles)) for s in samples]
    for k in range(len(DIMS), 0, -1):
        dims = [d for d in DIMS[:k] if today_b.get(d) is not None]
        if not dims:
            continue
        m = [s for s, b in labelled if all(b[d] == today_b[d] for d in dims)]
        if len(m) >= min_matches:
            return m, dims
    return [], []


def episodes(matched):
    """Back-to-back weeks count as one episode (they share the same market spell)."""
    ds = sorted(_d(s["date"]) for s in matched)
    n = 0
    for i, d in enumerate(ds):
        if i == 0 or (d - ds[i - 1]).days > 7:
            n += 1
    return n


def walk_forward(samples, w_pct, min_matches, train_years=3, test_months=6):
    """
    Would today's kind of matching have predicted 'stayed inside' better than plain history?
    Train on 3 years, score the next 6 months, roll forward 6 months (as range_walk_forward.py).
    Score = Brier (mean squared error of the probability; lower is better).
    """
    if not samples:
        return None
    start, end = _d(samples[0]["date"]), _d(samples[-1]["date"])
    train_d, test_d = timedelta(days=365 * train_years), timedelta(days=30 * test_months)
    w0, se_m, se_b, n = start, 0.0, 0.0, 0
    while w0 + train_d + test_d <= end + timedelta(days=1):
        t_end, x_end = w0 + train_d, w0 + train_d + test_d
        train = [s for s in samples if w0 <= _d(s["date"]) < t_end]
        test = [s for s in samples if t_end <= _d(s["date"]) < x_end]
        if len(train) >= min_matches and test:
            terc = vix_terciles([s["cond"]["india_vix"] for s in train])
            k, m = _rate(train, w_pct)
            p_base = k / m
            for s in test:
                matched, _ = match(train, buckets(s["cond"], terc), terc, min_matches)
                km, mm = _rate(matched, w_pct)
                p = km / mm if mm else p_base
                y = 1.0 if _touch_stay(s, w_pct) else 0.0
                se_m += (p - y) ** 2
                se_b += (p_base - y) ** 2
                n += 1
        w0 += test_d
    if not n:
        return None
    bm, bb = se_m / n, se_b / n
    return {"tested_weeks": n, "brier_matched": round(bm, 4), "brier_all_days": round(bb, 4),
            "verdict": ("Matching on today's conditions predicted better than plain history" if bm < bb
                        else "Matching on today's conditions did NOT predict better than plain history")}


def report(series, today: date, horizon: int = 5, weekday: int = None, min_matches: int = 20, widths=WIDTHS):
    weekday = today.weekday() if weekday is None else weekday
    notes = []
    nifty = series.get("nifty") or []
    if len(nifty) < 300:
        return {"ready": False, "reason": f"Only {len(nifty)} days of NIFTY history — press Load history first."}
    spot, spot_date = last_close_before(nifty, today)
    if spot is None:
        spot, spot_date = nifty[-1]["close"], nifty[-1]["date"]
    if not series.get("india_vix"):
        notes.append("No India VIX history — VIX level is not used for matching.")
    if not series.get("sp500"):
        notes.append("No S&P 500 history — the US close is not used for matching.")

    cond_today = conditions_for(series, today)
    samples = build_samples(series, today, horizon, weekday)
    if len(samples) < min_matches:
        return {"ready": False, "reason": f"Only {len(samples)} past {WEEKDAYS[weekday]} windows — not enough history."}
    terc = vix_terciles([s["cond"]["india_vix"] for s in samples])
    today_b = buckets(cond_today, terc)
    matched, dims = match(samples, today_b, terc, min_matches)
    if not matched:
        notes.append(f"Fewer than {min_matches} past mornings matched even on one condition — showing all days only.")

    rows = []
    for w in widths:
        w_pct = w / spot * 100
        kb, nb = _rate(samples, w_pct)
        row = {"width": w, "width_pct": round(w_pct, 2),
               "all": {"stayed": kb, "n": nb, "pct": round(kb / nb * 100, 1)}}
        if matched:
            km, nm = _rate(matched, w_pct)
            lo, hi = _wilson_ci(km, nm)
            row["matched"] = {"stayed": km, "n": nm, "pct": round(km / nm * 100, 1),
                              "ci95": [round(lo * 100, 1), round(hi * 100, 1)],
                              "closed_inside": sum(1 for s in matched if abs(s["end_pct"]) <= w_pct)}
            row["lift"] = round(row["matched"]["pct"] - row["all"]["pct"], 1)
        rows.append(row)

    pool = matched or samples
    worst = sorted(pool, key=lambda s: -max(s["up_pct"], s["down_pct"]))[:5]
    worst = [{"date": s["date"], "exit_date": s["exit_date"],
              "direction": "up" if s["up_pct"] >= s["down_pct"] else "down",
              "move_pct": round(max(s["up_pct"], s["down_pct"]), 2),
              "move_pts_today": round(max(s["up_pct"], s["down_pct"]) * spot / 100)} for s in worst]

    world = [{"symbol": k, "change_pct": v["change_pct"], "date": v["date"],
              "bucket": bucket_us_move(v["change_pct"]) if v["change_pct"] is not None else None}
             for k, v in cond_today["world"].items()]
    stale = [w["symbol"] for w in world if w["date"] and (today - _d(w["date"])).days > 4]
    if stale:
        notes.append("Some world closes are more than 4 days old (holiday, or history not reloaded): " + ", ".join(stale))

    return {
        "ready": True, "as_of": today.isoformat(), "weekday": WEEKDAYS[weekday], "horizon_days": horizon,
        "spot": spot, "spot_date": spot_date,
        "conditions": {"world": world, "india_vix": cond_today["india_vix"], "india_vix_date": cond_today["india_vix_date"],
                       "nifty_5d_pct": cond_today["nifty_5d_pct"], "buckets": today_b,
                       "vix_terciles": [round(t, 2) for t in terc] if terc else None},
        "matched_on": dims, "matches": len(matched), "episodes": episodes(matched) if matched else 0,
        "all_windows": len(samples), "history_from": samples[0]["date"], "history_to": samples[-1]["date"],
        "min_matches": min_matches, "rows": rows, "worst": worst,
        "walk_forward": walk_forward(samples, 250 / spot * 100, min_matches),
        "notes": notes,
        "method": (f"Each past {WEEKDAYS[weekday]}: NIFTY's open, then the highest high and lowest low over "
                   f"{horizon} trading days. 'Stayed' means it never went beyond ±width; widths are scaled "
                   f"to today's NIFTY level. Conditions use only closes from before that morning."),
    }
