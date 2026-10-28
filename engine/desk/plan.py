"""
Trading Plan — the user's own rules, stored per user, read by the Trade Ticket.

Every rule may be left unset (None / empty). An unset rule shows as "Not set in
your plan" on the ticket instead of the app inventing a threshold for you.
Defaults are only values that already existed in config/settings.json.
"""

import json
import logging
from datetime import date, datetime, timezone

logger = logging.getLogger("options_tycoon.desk.plan")

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

# key -> (type, description). Order here is the order on the Plan page.
PLAN_FIELDS = {
    "entry_days": ("days", "Days you enter a new trade"),
    "vix_min": ("number", "Lowest India VIX you trade"),
    "vix_max": ("number", "Highest India VIX you trade"),
    "min_credit": ("number", "Minimum credit for 1 lot (₹)"),
    "min_rr": ("number", "Minimum reward : risk (e.g. 0.60)"),
    "max_loss_per_trade": ("number", "Largest max loss you accept per trade (₹)"),
    "profit_target_pct": ("number", "Profit target as a share of credit (0.50 = 50%)"),
    "loss_exit_rupees": ("number", "Exit when the open loss reaches (₹)"),
    "exit_days_before_expiry": ("number", "Exit this many trading days before expiry"),
    "expiry_margin_buffer": ("number", "Extra funds kept for expiry-day margin (₹)"),
    "weekly_loss_limit": ("number", "Stop new trades after losing this much in a week (₹)"),
    "monthly_loss_limit": ("number", "Stop new trades after losing this much in a month (₹)"),
    "pause_after_losses": ("number", "Pause after this many losses in a row"),
    "events": ("events", "Event dates to avoid (RBI, Budget, elections…)"),
}


def default_plan() -> dict:
    """A plan with only the values the repo already had; everything else unset."""
    plan = {k: None for k in PLAN_FIELDS}
    plan["entry_days"] = []
    plan["events"] = []
    try:
        from pathlib import Path
        settings_path = Path(__file__).resolve().parent.parent.parent / "config" / "settings.json"
        with open(settings_path) as f:
            nifty = json.load(f).get("nifty", {})
        plan["profit_target_pct"] = nifty.get("profit_target_pct")
        plan["max_loss_per_trade"] = nifty.get("max_loss_per_trade")
    except Exception:
        pass
    return plan


class PlanError(ValueError):
    """Raised when a submitted plan has an invalid value."""


def _num(key, value):
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise PlanError(f"{key} must be a number")
    if n != n or n < 0:
        raise PlanError(f"{key} must be zero or more")
    return n


def validate_plan(raw: dict) -> dict:
    """Return a clean plan from user input, or raise PlanError. Unknown keys are dropped."""
    if not isinstance(raw, dict):
        raise PlanError("plan must be an object")
    plan = default_plan()
    for key, (kind, _) in PLAN_FIELDS.items():
        if key not in raw:
            continue
        value = raw[key]
        if kind == "number":
            plan[key] = _num(key, value)
        elif kind == "days":
            days = value or []
            if not isinstance(days, list) or any(d not in WEEKDAYS for d in days):
                raise PlanError(f"entry_days must be a list of {', '.join(WEEKDAYS)}")
            plan[key] = [d for d in WEEKDAYS if d in days]
        elif kind == "events":
            events = value or []
            if not isinstance(events, list):
                raise PlanError("events must be a list")
            clean = []
            for ev in events:
                if not isinstance(ev, dict):
                    raise PlanError("each event needs a date and a label")
                try:
                    d = date.fromisoformat(str(ev.get("date", "")).strip())
                except ValueError:
                    raise PlanError("event dates must be YYYY-MM-DD")
                label = str(ev.get("label", "")).strip()[:80] or "Event"
                clean.append({"date": d.isoformat(), "label": label})
            plan[key] = sorted(clean, key=lambda e: e["date"])

    if plan["profit_target_pct"] is not None and not (0 < plan["profit_target_pct"] <= 1):
        raise PlanError("profit_target_pct must be between 0 and 1")
    for key in ("exit_days_before_expiry", "pause_after_losses"):
        if plan[key] is not None:
            plan[key] = int(plan[key])
    if plan["vix_min"] is not None and plan["vix_max"] is not None and plan["vix_min"] > plan["vix_max"]:
        raise PlanError("vix_min cannot be above vix_max")
    return plan


def load_plan(user_id: int) -> dict:
    """The user's saved plan merged over the defaults (missing keys stay default)."""
    from db.database import get_connection
    conn = get_connection()
    try:
        row = conn.execute("SELECT plan_json FROM trading_plans WHERE user_id = ?", (int(user_id),)).fetchone()
    finally:
        conn.close()
    plan = default_plan()
    if row:
        try:
            saved = json.loads(row["plan_json"])
            plan.update({k: v for k, v in saved.items() if k in PLAN_FIELDS})
        except Exception:
            logger.warning(f"Unreadable trading plan for user {user_id}; using defaults")
    return plan


def save_plan(user_id: int, raw: dict) -> dict:
    """Validate and upsert the user's plan. Returns the stored plan."""
    plan = validate_plan(raw)
    from db.database import get_connection
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO trading_plans (user_id, plan_json, updated_at) VALUES (?, ?, ?)
               ON CONFLICT (user_id) DO UPDATE SET plan_json = excluded.plan_json, updated_at = excluded.updated_at""",
            (int(user_id), json.dumps(plan), datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()
    return plan
