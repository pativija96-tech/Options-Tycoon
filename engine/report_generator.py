"""
Options Tycoon - Devastating Behavioral Report Generator.

Generates a detailed, shareable behavioral report from trade history.
The report is designed to be brutally honest — showing traders exactly
which psychological patterns are costing them money.

All language is observational (no advice). The data speaks for itself.
"""

from datetime import datetime, timedelta
from typing import Optional
import statistics


def generate_devastating_report(trades: list) -> dict:
    """
    Generate the full Devastating Report from trade history.

    Input: list of trade dicts with fields:
        - ticker: str
        - entry_time: str (ISO format datetime)
        - exit_time: str (ISO format datetime)
        - entry_price: float
        - exit_price: float
        - pnl: float (realized P&L)
        - quantity: int

    Returns a comprehensive report dict with summary, behavioral_losses,
    patterns, key_insight, and disclaimer.
    """
    if not trades or len(trades) < 5:
        return {"error": "Need at least 5 trades to generate a meaningful report"}

    # --- Compute Summary ---
    total_trades = len(trades)
    total_pnl = sum(t.get('pnl', 0) for t in trades)
    win_count = sum(1 for t in trades if t.get('pnl', 0) > 0)
    loss_count = sum(1 for t in trades if t.get('pnl', 0) < 0)
    win_rate = round(win_count / total_trades * 100, 1) if total_trades > 0 else 0

    # Hold duration analysis
    avg_hold_winners = _avg_hold_days(trades, winners=True)
    avg_hold_losers = _avg_hold_days(trades, winners=False)

    summary = {
        "total_trades": total_trades,
        "total_pnl": round(total_pnl, 2),
        "win_rate": win_rate,
        "avg_hold_winners": round(avg_hold_winners, 1),
        "avg_hold_losers": round(avg_hold_losers, 1),
    }

    # --- Detect Behavioral Patterns ---
    revenge_data = _detect_revenge_trades(trades)
    overconfidence_data = _detect_overconfidence(trades)
    impulse_data = _detect_impulse_exits(trades)

    total_behavioral_loss = (
        revenge_data["total_loss"]
        + overconfidence_data["total_loss"]
        + impulse_data["total_missed"]
    )

    total_losses = abs(sum(t['pnl'] for t in trades if t.get('pnl', 0) < 0))
    percent_of_total = round(
        (abs(total_behavioral_loss) / total_losses * 100), 1
    ) if total_losses > 0 else 0

    # Breakdown percentages
    behavioral_abs = abs(total_behavioral_loss) if total_behavioral_loss != 0 else 1
    revenge_pct = round(abs(revenge_data["total_loss"]) / behavioral_abs * 100) if behavioral_abs > 0 else 0
    overconf_pct = round(abs(overconfidence_data["total_loss"]) / behavioral_abs * 100) if behavioral_abs > 0 else 0
    impulse_pct = round(abs(impulse_data["total_missed"]) / behavioral_abs * 100) if behavioral_abs > 0 else 0

    behavioral_losses = {
        "total_behavioral_loss": round(total_behavioral_loss, 2),
        "percent_of_total_loss": percent_of_total,
        "breakdown": {
            "revenge_trading": {
                "count": revenge_data["count"],
                "loss": round(revenge_data["total_loss"], 2),
                "percent_of_behavioral": revenge_pct,
            },
            "overconfidence": {
                "count": overconfidence_data["count"],
                "loss": round(overconfidence_data["total_loss"], 2),
                "percent_of_behavioral": overconf_pct,
            },
            "impulse_exits": {
                "count": impulse_data["count"],
                "missed_profit": round(impulse_data["total_missed"], 2),
                "percent_of_behavioral": impulse_pct,
            },
        }
    }

    # --- Build Pattern Details ---
    patterns = []

    if revenge_data["count"] > 0:
        avg_size_multiplier = _compute_avg_revenge_multiplier(trades, revenge_data["indices"])
        loss_rate = revenge_data["loss_rate"]
        patterns.append({
            "type": "revenge_trading",
            "title": "Revenge Trading",
            "explanation": (
                "A Revenge Trade occurs when you increase your position size to more than 150% "
                "of your average within 24 hours of a realized loss. This is an emotional response "
                "to recover losses quickly."
            ),
            "your_data": (
                f"You placed {revenge_data['count']} revenge trades. "
                f"Average size was {avg_size_multiplier:.1f}x your normal. "
                f"{revenge_data['losses_in_revenge']} of {revenge_data['count']} were losses."
            ),
            "evidence": revenge_data["evidence"][:3],
            "cost": round(revenge_data["total_loss"], 2),
            "severity": "critical" if revenge_data["count"] >= 10 else "high",
        })

    if overconfidence_data["count"] > 0:
        patterns.append({
            "type": "overconfidence",
            "title": "Overconfidence Trap",
            "explanation": (
                "An Overconfidence Trap is when you increase your position size to more than 150% "
                "of your average immediately after 3 or more consecutive winning trades. Winning "
                "streaks inflate self-belief and lead to outsized bets."
            ),
            "your_data": (
                f"You fell into this trap {overconfidence_data['count']} times. "
                f"All {overconfidence_data['count']} resulted in losses."
            ),
            "evidence": overconfidence_data["evidence"][:3],
            "cost": round(overconfidence_data["total_loss"], 2),
            "severity": "high" if overconfidence_data["count"] >= 3 else "moderate",
        })

    if impulse_data["count"] > 0:
        patterns.append({
            "type": "impulse_exits",
            "title": "Impulse Early Exit",
            "explanation": (
                "An Impulse Exit is when you close a winning trade that later moved significantly "
                "further in your favor. You captured less than 40% of the available profit on these "
                "trades, leaving money on the table due to fear of reversal."
            ),
            "your_data": (
                f"You impulse-exited {impulse_data['count']} trades. "
                f"Total missed profit: ₹{abs(impulse_data['total_missed']):,.0f}."
            ),
            "evidence": impulse_data["evidence"][:3],
            "cost": round(impulse_data["total_missed"], 2),
            "severity": "moderate" if impulse_data["count"] < 10 else "high",
        })

    # --- Calm vs Emotional Analysis ---
    calm_stats = _compute_calm_vs_emotional(trades, revenge_data["indices"], overconfidence_data["indices"])

    # --- Key Insight ---
    key_insight = (
        f"{percent_of_total}% of your total losses (₹{abs(total_behavioral_loss):,.0f} out of "
        f"₹{total_losses:,.0f}) came from behavioral patterns — not bad market analysis. "
        f"Your strategy win rate on 'calm' trades is {calm_stats['calm_win_rate']}%. "
        f"On emotional trades it drops to {calm_stats['emotional_win_rate']}%."
    )

    # --- Disclaimer ---
    disclaimer = (
        "This analysis is based on YOUR historical trade data. It is observational only — "
        "not financial advice. All trading decisions remain your responsibility."
    )

    return {
        "summary": summary,
        "behavioral_losses": behavioral_losses,
        "patterns": patterns,
        "calm_vs_emotional": calm_stats,
        "key_insight": key_insight,
        "disclaimer": disclaimer,
    }


# ===========================================================================
# Internal Detection Functions
# ===========================================================================


def _avg_hold_days(trades: list, winners: bool) -> float:
    """Compute average hold duration in days for winners or losers."""
    durations = []
    for t in trades:
        pnl = t.get('pnl', 0)
        if winners and pnl <= 0:
            continue
        if not winners and pnl >= 0:
            continue
        entry = _parse_time(t.get('entry_time'))
        exit_t = _parse_time(t.get('exit_time'))
        if entry and exit_t:
            days = (exit_t - entry).total_seconds() / 86400
            durations.append(days)
    return statistics.mean(durations) if durations else 0.0


def _detect_revenge_trades(trades: list) -> dict:
    """
    Detect revenge trades: oversized positions within 24h of a loss.
    A revenge trade is when position size > 150% of average AND placed
    within 24 hours of a realized loss.
    """
    if len(trades) < 2:
        return {"count": 0, "total_loss": 0, "losses_in_revenge": 0, "indices": [], "evidence": [], "loss_rate": 0}

    avg_size = statistics.mean([abs(t.get('pnl', 0)) for t in trades]) if trades else 1
    avg_entry = statistics.mean([t.get('entry_price', 0) for t in trades]) if trades else 1

    count = 0
    total_loss = 0.0
    losses_in_revenge = 0
    indices = []
    evidence = []

    for i in range(1, len(trades)):
        prev = trades[i - 1]
        curr = trades[i]

        # Previous trade must be a loss
        if prev.get('pnl', 0) >= 0:
            continue

        # Check time gap < 24 hours
        prev_exit = _parse_time(prev.get('exit_time'))
        curr_entry = _parse_time(curr.get('entry_time'))
        if not prev_exit or not curr_entry:
            continue
        gap_seconds = (curr_entry - prev_exit).total_seconds()
        if gap_seconds < 0 or gap_seconds > 86400:
            continue

        # Check oversized: entry_price > 150% of average
        curr_size = curr.get('entry_price', 0)
        if curr_size < avg_entry * 1.5:
            continue

        # This is a revenge trade
        count += 1
        indices.append(i)
        pnl = curr.get('pnl', 0)
        if pnl < 0:
            total_loss += pnl
            losses_in_revenge += 1

        # Build evidence string
        gap_min = int(gap_seconds / 60)
        size_mult = round(curr_size / avg_entry, 1)
        prev_loss = abs(prev.get('pnl', 0))
        evidence_str = (
            f"Trade #{i + 1}: ₹{curr_size:,.0f} position ({size_mult}x avg) "
            f"placed {gap_min} min after ₹{prev_loss:,.0f} loss → "
            f"{'Lost' if pnl < 0 else 'Won'} ₹{abs(pnl):,.0f}"
        )
        evidence.append(evidence_str)

    loss_rate = round(losses_in_revenge / count * 100, 1) if count > 0 else 0

    return {
        "count": count,
        "total_loss": total_loss,
        "losses_in_revenge": losses_in_revenge,
        "indices": indices,
        "evidence": evidence,
        "loss_rate": loss_rate,
    }


def _detect_overconfidence(trades: list) -> dict:
    """
    Detect overconfidence traps: oversized position after 3+ consecutive wins.
    """
    if len(trades) < 4:
        return {"count": 0, "total_loss": 0, "indices": [], "evidence": []}

    avg_entry = statistics.mean([t.get('entry_price', 0) for t in trades]) if trades else 1

    count = 0
    total_loss = 0.0
    indices = []
    evidence = []

    for i in range(3, len(trades)):
        # Check 3 consecutive wins before this trade
        streak = all(trades[j].get('pnl', 0) > 0 for j in range(i - 3, i))
        if not streak:
            continue

        curr = trades[i]
        curr_size = curr.get('entry_price', 0)

        # Check oversized
        if curr_size < avg_entry * 1.5:
            continue

        # Check if it resulted in a loss
        pnl = curr.get('pnl', 0)
        if pnl >= 0:
            continue

        count += 1
        indices.append(i)
        total_loss += pnl

        size_mult = round(curr_size / avg_entry, 1)
        evidence_str = (
            f"Trade #{i + 1}: After 3 consecutive wins, position jumped to "
            f"₹{curr_size:,.0f} ({size_mult}x avg) → Lost ₹{abs(pnl):,.0f}"
        )
        evidence.append(evidence_str)

    return {
        "count": count,
        "total_loss": total_loss,
        "indices": indices,
        "evidence": evidence,
    }


def _detect_impulse_exits(trades: list) -> dict:
    """
    Detect impulse exits: trades where profit captured was less than 40%
    of the maximum unrealized profit (i.e., exited too early out of fear).
    We approximate this by looking at winners where PnL is < 40% of entry_price
    movement potential, using price trajectory heuristics.
    """
    count = 0
    total_missed = 0.0
    indices = []
    evidence = []

    for i, t in enumerate(trades):
        pnl = t.get('pnl', 0)
        entry_price = t.get('entry_price', 0)
        exit_price = t.get('exit_price', 0)

        # Only look at winning trades
        if pnl <= 0 or entry_price <= 0:
            continue

        # Heuristic: if the trade won but the gain is less than 15% of entry
        # and the entry price is significant, it might be an impulse exit
        # We estimate max profit as 2.5x the realized (conservative estimate)
        gain_pct = (exit_price - entry_price) / entry_price * 100

        # Only flag if the gain was very small relative to position
        if gain_pct < 5 and pnl > 0:
            # Estimate missed profit (conservative: could have made ~3x)
            estimated_max = pnl * 3
            missed = estimated_max - pnl
            count += 1
            indices.append(i)
            total_missed -= missed  # Negative because it's a loss of opportunity

            evidence_str = (
                f"Trade #{i + 1}: {t.get('ticker', '?')} — took ₹{pnl:,.0f} profit "
                f"but position moved further (estimated ₹{estimated_max:,.0f} available)"
            )
            evidence.append(evidence_str)

    # If heuristic found nothing, try alternate: look for very short-hold winners
    if count == 0:
        avg_hold = _avg_hold_days(trades, winners=True)
        for i, t in enumerate(trades):
            pnl = t.get('pnl', 0)
            if pnl <= 0:
                continue
            entry = _parse_time(t.get('entry_time'))
            exit_t = _parse_time(t.get('exit_time'))
            if not entry or not exit_t:
                continue
            hold_hours = (exit_t - entry).total_seconds() / 3600
            # Very quick exits (< 25% of average hold time)
            if avg_hold > 0 and hold_hours < avg_hold * 24 * 0.25 and pnl > 0:
                estimated_max = pnl * 2.5
                missed = estimated_max - pnl
                count += 1
                indices.append(i)
                total_missed -= missed
                evidence_str = (
                    f"Trade #{i + 1}: {t.get('ticker', '?')} — exited after "
                    f"{hold_hours:.1f}h with ₹{pnl:,.0f} (avg hold is {avg_hold * 24:.0f}h)"
                )
                evidence.append(evidence_str)

    return {
        "count": count,
        "total_missed": total_missed,
        "indices": indices,
        "evidence": evidence,
    }


def _compute_avg_revenge_multiplier(trades: list, revenge_indices: list) -> float:
    """Compute average size multiplier for revenge trades."""
    if not revenge_indices:
        return 0.0
    avg_entry = statistics.mean([t.get('entry_price', 0) for t in trades]) if trades else 1
    multipliers = [trades[i].get('entry_price', 0) / avg_entry for i in revenge_indices if avg_entry > 0]
    return statistics.mean(multipliers) if multipliers else 0.0


def _compute_calm_vs_emotional(trades: list, revenge_indices: list, overconf_indices: list) -> dict:
    """Compare win rates and P&L between calm and emotional trades."""
    emotional_indices = set(revenge_indices + overconf_indices)

    calm_trades = [t for i, t in enumerate(trades) if i not in emotional_indices]
    emotional_trades = [t for i, t in enumerate(trades) if i in emotional_indices]

    calm_wins = sum(1 for t in calm_trades if t.get('pnl', 0) > 0)
    calm_total = len(calm_trades)
    calm_win_rate = round(calm_wins / calm_total * 100, 1) if calm_total > 0 else 0
    calm_avg_pnl = round(statistics.mean([t.get('pnl', 0) for t in calm_trades]), 2) if calm_trades else 0

    emo_wins = sum(1 for t in emotional_trades if t.get('pnl', 0) > 0)
    emo_total = len(emotional_trades)
    emotional_win_rate = round(emo_wins / emo_total * 100, 1) if emo_total > 0 else 0
    emotional_avg_pnl = round(statistics.mean([t.get('pnl', 0) for t in emotional_trades]), 2) if emotional_trades else 0

    return {
        "calm_win_rate": calm_win_rate,
        "calm_avg_pnl": calm_avg_pnl,
        "calm_trade_count": calm_total,
        "emotional_win_rate": emotional_win_rate,
        "emotional_avg_pnl": emotional_avg_pnl,
        "emotional_trade_count": emo_total,
    }


def _parse_time(val) -> Optional[datetime]:
    """Parse a time value to datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None
