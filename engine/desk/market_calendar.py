"""
NSE trading days and the market-event calendar (data/historical/nse_holidays.json and
nifty_events.json, both hand-kept with their sources inside).

An event's impact date is the session it first hits: "india" events hit their own day (or the
next session if that day is shut), "overnight" events (after NSE's close) hit the next session.
"""

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent.parent / "data" / "historical"
STALE_AFTER_DAYS = 14       # from the 3 Nov action list
LOOKAHEAD_DAYS = 30         # a calendar with nothing in the next 30 days is stale


@lru_cache(maxsize=1)
def _holiday_file():
    try:
        with open(DATA / "nse_holidays.json", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"holidays": [], "covers_through": None}


def holidays():
    """{date: name} of NSE weekday and weekend holidays on file."""
    return {date.fromisoformat(h["date"]): h["name"] for h in _holiday_file().get("holidays", [])}


def covers_through():
    d = _holiday_file().get("covers_through")
    return date.fromisoformat(d) if d else None


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in holidays()


def next_trading_day(d: date) -> date:
    """The first trading day after d."""
    d += timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def previous_trading_day(d: date) -> date:
    """The last trading day before d."""
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def on_or_before(d: date) -> date:
    return d if is_trading_day(d) else previous_trading_day(d)


def on_or_after(d: date) -> date:
    return d if is_trading_day(d) else next_trading_day(d)


def load_events() -> dict:
    """{"last_updated", "events", ...} from the event calendar; empty if it can't be read."""
    try:
        with open(DATA / "nifty_events.json", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"last_updated": None, "events": []}


def impact_date(event) -> date:
    d = date.fromisoformat(event["date"])
    return next_trading_day(d) if event.get("session") == "overnight" else on_or_after(d)


def event_hits(events, start: date, end: date):
    """Events whose impact date falls from start through end, each with its impact date and tier."""
    hits = []
    for e in events or []:
        try:
            when = impact_date(e)
        except (KeyError, ValueError):
            continue
        if start <= when <= end:
            hits.append({"name": e.get("name") or e.get("label") or "Event", "date": e["date"],
                         "impact_date": when.isoformat(), "tier": e.get("tier") or "high",
                         "overnight": e.get("session") == "overnight"})
    return sorted(hits, key=lambda h: (h["tier"] != "high", h["impact_date"]))


def calendar_stale(calendar, today: date) -> bool:
    """True if the calendar is old, or lists nothing in the next 30 days."""
    updated = (calendar or {}).get("last_updated")
    if not updated or (today - date.fromisoformat(updated)).days > STALE_AFTER_DAYS:
        return True
    limit = today + timedelta(days=LOOKAHEAD_DAYS)
    return not any(today <= date.fromisoformat(e["date"]) <= limit for e in calendar.get("events", []))


def plan_events(plan):
    """The plan's own event dates, treated as high tier, in the calendar's shape."""
    return [{"date": e["date"], "name": e.get("label") or "Event", "tier": "high", "session": "india"}
            for e in (plan.get("events") or []) if e.get("date")]


def next_clear_entry(plan, today: date, events, hold_days: int = 7):
    """
    The next entry day after today with no high-tier event from that day through the next week's
    hold (hold_days is an estimate: the real expiry isn't known yet). None within 60 days.
    """
    days = plan.get("entry_days") or []
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for i in range(1, 61):
        d = today + timedelta(days=i)
        if not is_trading_day(d) or (days and names[d.weekday()] not in days):
            continue
        if not any(h["tier"] == "high" for h in event_hits(events, d, d + timedelta(days=hold_days))):
            return d
    return None
