"""
"Book rules" preset for the Trading Plan — values the Plan page can fill in for the
user to review and save. Nothing here saves a plan.

Every value has a source shown next to its field. Only rules that a source states are
filled; a field with no reliable book number stays as the user had it.
  Elder, The New Trading for a Living — 2% rule (risk per trade), 6% rule (monthly stop)
  tastylive iron condor studies       — collect ⅓ of the wing width; manage winners at 50%
  This repo's signal engine          — VIX above 40 skip, expiry-day ELM estimate, 1-day-early exit
  The user's own practice            — Tuesday entry
  data/historical/event_calendar.json — upcoming NIFTY / ALL high-impact events
"""

import json
from datetime import date
from pathlib import Path

from engine.signals.simple_ic_engine import ELM_FACTOR, LOT_SIZE, VIX_MAX, WING_WIDTH

ROOT = Path(__file__).resolve().parent.parent.parent
ELDER_RISK_PER_TRADE = 0.02
ELDER_MONTHLY_STOP = 0.06
TASTY_CREDIT_SHARE_OF_WIDTH = 1 / 3

ELDER = "Elder, The New Trading for a Living"
TASTY = "tastylive iron condor studies"


def _nifty_settings():
    try:
        with open(ROOT / "config" / "settings.json") as f:
            return json.load(f).get("nifty", {})
    except Exception:
        return {}


def _events(today: date):
    try:
        with open(ROOT / "data" / "historical" / "event_calendar.json") as f:
            rows = json.load(f)
    except Exception:
        return [], ["Event calendar not found"]
    out, notes = [], []
    for e in rows:
        try:
            d = date.fromisoformat(e["date"])
        except (KeyError, ValueError):
            continue
        if d < today or e.get("market") not in ("NIFTY", "ALL") or e.get("impact") != "high":
            continue
        out.append({"date": d.isoformat(), "label": str(e.get("name", "Event"))[:80]})
        if d.weekday() >= 5:
            notes.append(f"{e.get('name')} on {d.isoformat()} falls on a {d.strftime('%A')} — check the official date")
    return sorted(out, key=lambda e: e["date"]), notes


def book_preset(today: date) -> dict:
    nifty = _nifty_settings()
    capital = nifty.get("capital")
    margin = nifty.get("margin_per_lot")
    min_credit_ps = WING_WIDTH * TASTY_CREDIT_SHARE_OF_WIDTH
    events, notes = _events(today)

    values, sources = {}, {}

    def put(key, value, source):
        values[key] = value
        sources[key] = source

    put("entry_days", ["Tue"], "Your own practice: entry was always on Tuesday (not a book rule)")
    put("vix_max", VIX_MAX, f"Your signal engine skips when India VIX is above {VIX_MAX}")
    put("min_credit", round(min_credit_ps * LOT_SIZE),
        f"{TASTY}: collect ⅓ of the wing width — {WING_WIDTH} ÷ 3 = {min_credit_ps:.2f}/share × {LOT_SIZE}")
    put("min_rr", 0.5, f"{TASTY}: a ⅓-width credit against a ⅔-width max loss = 0.50")
    put("profit_target_pct", nifty.get("profit_target_pct", 0.5),
        f"{TASTY}: manage winners at 50% of max profit; also your settings")
    put("exit_days_before_expiry", 1, "Your signal engine: exit before expiry morning (expiry-day margin spike)")
    if margin:
        put("expiry_margin_buffer", round(margin * ELM_FACTOR),
            f"Your signal engine's expiry-day margin estimate: ₹{margin:,} × {ELM_FACTOR} (seen on 24 Aug 2026)")
    if capital:
        put("loss_exit_rupees", round(capital * ELDER_RISK_PER_TRADE),
            f"{ELDER}: 2% rule — {ELDER_RISK_PER_TRADE:.0%} of ₹{capital:,} capital. A gap can still go past it, up to the full max loss")
        put("monthly_loss_limit", round(capital * ELDER_MONTHLY_STOP),
            f"{ELDER}: 6% rule — stop for the month at {ELDER_MONTHLY_STOP:.0%} of ₹{capital:,} capital")
    else:
        notes.append("No NIFTY capital in settings — loss exit and monthly limit not filled")
    put("events", events, "Upcoming high-impact NIFTY / all-market events from your event calendar")

    unsourced = {
        "vix_min": "No book gives an India VIX level (tastylive uses IV rank, which the app doesn't have)",
        "max_loss_per_trade": ("Left as is: the 2% rule is applied as the loss exit. As a max-loss limit it would "
                               "block every condor (structural max loss ≈ ₹4,700); your engine's 25%-of-capital cap still applies"),
        "weekly_loss_limit": "No book number found — Elder's rule is monthly",
        "pause_after_losses": "No book number found",
    }
    return {"values": values, "sources": sources, "not_filled": unsourced, "capital": capital, "notes": notes}
