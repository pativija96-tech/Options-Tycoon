"""Achievements and XP tracking for Options Tycoon."""

ACHIEVEMENTS = [
    {
        "id": "first_trade",
        "name": "First Trade",
        "desc": "Executed your first trade",
        "condition": lambda stats: stats["total_trades"] >= 1,
    },
    {
        "id": "streak_5",
        "name": "5-Trade Streak",
        "desc": "5 consecutive disciplined trades",
        "condition": lambda stats: stats["longest_streak"] >= 5,
    },
    {
        "id": "streak_10",
        "name": "10-Trade Streak",
        "desc": "10 consecutive disciplined trades",
        "condition": lambda stats: stats["longest_streak"] >= 10,
    },
    {
        "id": "phase_b",
        "name": "Phase B Unlocked",
        "desc": "Completed 6 trades",
        "condition": lambda stats: stats["total_trades"] >= 6,
    },
    {
        "id": "phase_c",
        "name": "Phase C Unlocked",
        "desc": "Completed 15 trades",
        "condition": lambda stats: stats["total_trades"] >= 15,
    },
    {
        "id": "phase_d",
        "name": "Phase D Unlocked",
        "desc": "Completed 25 trades — full profile",
        "condition": lambda stats: stats["total_trades"] >= 25,
    },
    {
        "id": "revenge_free",
        "name": "Revenge-Free Week",
        "desc": "7 days without a revenge trade",
        "condition": lambda stats: stats.get("days_since_revenge", 0) >= 7,
    },
]


def compute_xp(trades: list) -> int:
    """Compute total XP: +10 per disciplined trade, +5 per undisciplined."""
    xp = 0
    for t in trades:
        if t.get("position_pct", 100) <= 5.0:
            xp += 10
        else:
            xp += 5
    return xp


def get_level(xp: int) -> int:
    """XP to level: every 100 XP = 1 level."""
    return xp // 100 + 1


def check_achievements(stats: dict) -> list:
    """Return list of unlocked achievement dicts."""
    unlocked = []
    for ach in ACHIEVEMENTS:
        if ach["condition"](stats):
            unlocked.append({
                "id": ach["id"],
                "name": ach["name"],
                "desc": ach["desc"],
            })
    return unlocked
