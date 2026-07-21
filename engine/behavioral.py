"""
Options Tycoon - Behavioral Intelligence Engine.

Core behavioral analysis module that computes discipline metrics, detects
emotional trading patterns, and generates diagnostic summaries. All functions
operate on dictionaries (sqlite3.Row-compatible) rather than Pydantic models.

Metrics computed:
- Discipline Rating: percentage of trades within 5% risk cap
- Patience Score: average deliberation time before execution
- Sizing Consistency: standard deviation of position percentages
- Emotional Reactivity: composite score from revenge, overconfidence, impulse, disposition
- Streak Tracking: consecutive disciplined trades
- Phase Determination: progressive unlock based on trade count
"""

import statistics
from datetime import datetime, timedelta
from typing import Optional


# ---------------------------------------------------------------------------
# Helper: parse datetime strings from SQLite
# ---------------------------------------------------------------------------

def _parse_dt(value) -> Optional[datetime]:
    """Parse a datetime string from SQLite into a datetime object."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Core Metric Functions
# ---------------------------------------------------------------------------

def compute_discipline_rating(trades: list) -> Optional[float]:
    """
    Compute the percentage of trades that stayed within the 5% risk cap.

    Args:
        trades: List of trade dicts, each with 'position_pct' field.

    Returns:
        Float 0-100 representing discipline percentage, or None if no trades.
    """
    if not trades:
        return None

    disciplined = sum(1 for t in trades if t['position_pct'] <= 5.0)
    return round((disciplined / len(trades)) * 100, 1)


def compute_patience_score(trades: list) -> Optional[float]:
    """
    Compute the average seconds between chain open and trade execution.

    Measures deliberation time — how long a trader observes the chain
    before pulling the trigger.

    Args:
        trades: List of trade dicts with 'chain_opened_at' and 'trade_executed_at'.

    Returns:
        Average seconds as float, or None if no valid timing data exists.
    """
    times: list[float] = []

    for t in trades:
        chain_opened = _parse_dt(t.get('chain_opened_at'))
        trade_executed = _parse_dt(t.get('trade_executed_at'))

        if chain_opened and trade_executed:
            delta = (trade_executed - chain_opened).total_seconds()
            if delta > 0:
                times.append(delta)

    if not times:
        return None

    return round(sum(times) / len(times), 1)


def compute_sizing_consistency(trades: list) -> Optional[float]:
    """
    Compute the standard deviation of position sizes as portfolio percentage.

    Lower values indicate more consistent sizing decisions.

    Args:
        trades: List of trade dicts with 'position_pct' field.

    Returns:
        Standard deviation as float, or None if fewer than 2 trades.
    """
    if len(trades) < 2:
        return None

    pcts = [t['position_pct'] for t in trades]
    return round(statistics.stdev(pcts), 2)


# ---------------------------------------------------------------------------
# Emotional Pattern Detection
# ---------------------------------------------------------------------------

def detect_revenge_trade(
    trade_position_size: float,
    avg_position_size: float,
    recent_trades: list,
    trade_opened_at
) -> bool:
    """
    Detect revenge trading: oversized position taken shortly after a loss.

    A revenge trade is flagged when:
    1. Position size exceeds 150% of the average, AND
    2. There is a realized loss within 24 hours before the trade was opened.

    Args:
        trade_position_size: The position size of the current trade.
        avg_position_size: Average position size across recent trades.
        recent_trades: List of recent trade dicts with 'closed_at' and 'realized_pnl'.
        trade_opened_at: Datetime or string of when the current trade was opened.

    Returns:
        True if the trade exhibits revenge trading characteristics.
    """
    if not recent_trades or avg_position_size <= 0:
        return False

    if trade_position_size <= avg_position_size * 1.5:
        return False

    opened_at = _parse_dt(trade_opened_at)
    if opened_at is None:
        return False

    cutoff = opened_at - timedelta(hours=24)

    for t in recent_trades:
        closed_at = _parse_dt(t.get('closed_at'))
        realized_pnl = t.get('realized_pnl')

        if (closed_at is not None
                and closed_at >= cutoff
                and realized_pnl is not None
                and realized_pnl < 0):
            return True

    return False


def detect_overconfidence_trap(
    trade_position_size: float,
    avg_position_size: float,
    recent_closed_trades: list
) -> bool:
    """
    Detect overconfidence trap: oversized position after a winning streak.

    Flagged when:
    1. Position size exceeds 150% of the average, AND
    2. The last 3 closed trades are all winners (realized_pnl > 0).

    Args:
        trade_position_size: The position size of the current trade.
        avg_position_size: Average position size across recent trades.
        recent_closed_trades: List of recently closed trade dicts, ordered
            most recent first, with 'realized_pnl' field.

    Returns:
        True if the trade exhibits overconfidence characteristics.
    """
    if not recent_closed_trades or avg_position_size <= 0:
        return False

    if trade_position_size <= avg_position_size * 1.5:
        return False

    # Filter to trades that have realized P&L
    closed_with_pnl = [
        t for t in recent_closed_trades
        if t.get('realized_pnl') is not None
    ]

    if len(closed_with_pnl) < 3:
        return False

    # Check last 3 are all wins
    return all(t['realized_pnl'] > 0 for t in closed_with_pnl[:3])


def detect_loss_disposition(trades: list) -> tuple[Optional[float], bool]:
    """
    Detect loss disposition bias: holding losers longer than winners.

    Computes the ratio of average losing hold time to average winning hold time.
    A ratio > 1.2 means losers are held 20%+ longer, indicating disposition bias.

    Args:
        trades: List of trade dicts with 'realized_pnl', 'opened_at', 'closed_at'.

    Returns:
        Tuple of (ratio, is_flagged):
        - ratio: avg_losing_hold_hours / avg_winning_hold_hours, or None
        - is_flagged: True if ratio > 1.2
    """
    winners: list[dict] = []
    losers: list[dict] = []

    for t in trades:
        realized_pnl = t.get('realized_pnl')
        closed_at = _parse_dt(t.get('closed_at'))
        opened_at = _parse_dt(t.get('opened_at'))

        if realized_pnl is None or closed_at is None or opened_at is None:
            continue

        if realized_pnl > 0:
            winners.append(t)
        elif realized_pnl < 0:
            losers.append(t)

    if not winners or not losers:
        return (None, False)

    # Calculate average hold hours for winners
    total_win_hours = 0.0
    for t in winners:
        opened = _parse_dt(t['opened_at'])
        closed = _parse_dt(t['closed_at'])
        total_win_hours += (closed - opened).total_seconds() / 3600

    avg_win_hold = total_win_hours / len(winners)

    # Calculate average hold hours for losers
    total_loss_hours = 0.0
    for t in losers:
        opened = _parse_dt(t['opened_at'])
        closed = _parse_dt(t['closed_at'])
        total_loss_hours += (closed - opened).total_seconds() / 3600

    avg_loss_hold = total_loss_hours / len(losers)

    if avg_win_hold == 0:
        return (None, False)

    ratio = round(avg_loss_hold / avg_win_hold, 2)
    return (ratio, ratio > 1.2)


def detect_impulse_early_exit(
    realized_pnl: float,
    max_unrealized_pnl: float
) -> bool:
    """
    Detect impulse early exit: closing a winning trade far below its peak profit.

    Flagged when a trade is closed profitably but captured less than 25% of
    the maximum unrealized profit that was available during the trade.

    Args:
        realized_pnl: The actual P&L when the trade was closed.
        max_unrealized_pnl: The peak unrealized P&L during the trade's lifetime.

    Returns:
        True if the trade was closed prematurely relative to its potential.
    """
    if realized_pnl <= 0:
        return False
    if max_unrealized_pnl <= 0:
        return False

    return realized_pnl < (max_unrealized_pnl * 0.25)


# ---------------------------------------------------------------------------
# Composite Scoring
# ---------------------------------------------------------------------------

def compute_emotional_reactivity(trades: list) -> Optional[float]:
    """
    Compute composite Emotional Reactivity score (0-100).

    Aggregates frequency of four emotional trading events:
    - Revenge trades (max 25 points)
    - Overconfidence traps (max 25 points)
    - Impulse early exits (max 25 points)
    - Loss disposition bias (max 25 points)

    Each component = min(25, (event_count / total_trades) * 100)

    Args:
        trades: List of trade dicts with behavioral flags.

    Returns:
        Composite score 0-100, or None if no trades.
    """
    if not trades:
        return None

    total = len(trades)

    # Count flagged events from stored trade data
    revenge_count = sum(1 for t in trades if t.get('is_revenge_trade'))
    overconf_count = sum(1 for t in trades if t.get('is_overconfidence_trap'))
    impulse_count = sum(1 for t in trades if t.get('is_impulse_early_exit'))

    # Frequency-based scoring, each capped at 25
    revenge_score = min(25, (revenge_count / total) * 100)
    overconf_score = min(25, (overconf_count / total) * 100)
    impulse_score = min(25, (impulse_count / total) * 100)

    # Loss disposition component
    loss_disp_score = _compute_loss_disposition_component(trades)

    return round(revenge_score + overconf_score + impulse_score + loss_disp_score, 1)


def _compute_loss_disposition_component(trades: list) -> float:
    """
    Compute the loss disposition contribution to emotional reactivity (0-25).

    Based on how severe the disposition ratio is:
    - ratio <= 1.0: 0 points (no bias)
    - ratio 1.0-1.2: proportional 0-12.5 points (mild bias)
    - ratio > 1.2: proportional 12.5-25 points (flagged bias)
    - Capped at 25
    """
    ratio, is_flagged = detect_loss_disposition(trades)

    if ratio is None:
        return 0.0

    if ratio <= 1.0:
        return 0.0
    elif ratio <= 1.2:
        # Mild bias: scale 0-12.5
        return min(12.5, (ratio - 1.0) / 0.2 * 12.5)
    else:
        # Flagged bias: scale 12.5-25
        # Cap at ratio = 2.0 for max score
        severity = min(1.0, (ratio - 1.2) / 0.8)
        return min(25, 12.5 + severity * 12.5)


# ---------------------------------------------------------------------------
# Streak Tracking
# ---------------------------------------------------------------------------

def compute_streak(trades: list) -> tuple[int, int]:
    """
    Compute disciplined trade streaks.

    A streak is defined as consecutive trades where position_pct <= 5.0.
    Trades are ordered by opened_at.

    Args:
        trades: List of trade dicts with 'position_pct' and 'opened_at'.

    Returns:
        Tuple of (current_streak, longest_streak).
    """
    if not trades:
        return (0, 0)

    # Sort by opened_at
    sorted_trades = sorted(
        trades,
        key=lambda t: _parse_dt(t.get('opened_at')) or datetime.min
    )

    current_streak = 0
    longest_streak = 0
    running_streak = 0

    for t in sorted_trades:
        if t['position_pct'] <= 5.0:
            running_streak += 1
            longest_streak = max(longest_streak, running_streak)
        else:
            running_streak = 0

    # Current streak is the trailing streak from the last trade
    current_streak = 0
    for t in reversed(sorted_trades):
        if t['position_pct'] <= 5.0:
            current_streak += 1
        else:
            break

    return (current_streak, longest_streak)


# ---------------------------------------------------------------------------
# Phase Determination
# ---------------------------------------------------------------------------

def determine_phase(total_trades: int, has_trader_dna: bool = False) -> str:
    """
    Determine the progressive disclosure phase based on trade count.

    Phases control which metrics and features are visible:
    - Phase A (0-5 trades): Raw data only, no behavioral metrics shown
    - Phase B (6-14 trades): Discipline + sizing metrics visible
    - Phase C (15-24 trades): Patience + initial emotional metrics added
    - Phase D (25+ trades or Trader DNA): Full profile with diagnostics

    Args:
        total_trades: Total number of trades for the profile.
        has_trader_dna: Whether the trader has imported historical DNA data.

    Returns:
        Phase letter: 'A', 'B', 'C', or 'D'.
    """
    if has_trader_dna:
        return 'D'
    if total_trades >= 25:
        return 'D'
    elif total_trades >= 15:
        return 'C'
    elif total_trades >= 6:
        return 'B'
    else:
        return 'A'


# ---------------------------------------------------------------------------
# Diagnostic Summary Generation
# ---------------------------------------------------------------------------

def generate_diagnostic(metrics: dict, trades: list) -> str:
    """
    Generate an observational text summary of behavioral patterns.

    Uses ONLY observational language ("Your data shows...", "The pattern indicates...").
    NEVER uses directive language (buy, sell, proceed, stop, recommend).

    Args:
        metrics: Dict with keys: discipline_rating, patience_score,
                 sizing_consistency, emotional_reactivity, total_trades.
        trades: List of trade dicts (used for additional context).

    Returns:
        Multi-paragraph diagnostic text string.
    """
    total_trades = metrics.get('total_trades', len(trades))
    parts: list[str] = []

    parts.append(
        f"After {total_trades} trades, Mirror observes the following patterns:"
    )

    # Discipline Rating
    discipline = metrics.get('discipline_rating')
    if discipline is not None:
        if discipline >= 80:
            parts.append(
                f"Your Discipline Rating is {discipline}%. "
                "The majority of your trades stayed within the 5% risk cap."
            )
        elif discipline >= 50:
            parts.append(
                f"Your Discipline Rating is {discipline}%. "
                "A mixed pattern is visible — some trades respect the 5% threshold "
                "while others exceed it."
            )
        else:
            parts.append(
                f"Your Discipline Rating is {discipline}%. "
                "A notable portion of trades exceeded the 5% risk threshold."
            )

    # Patience Score
    patience = metrics.get('patience_score')
    if patience is not None:
        parts.append(
            f"Your average deliberation time is {patience} seconds "
            "between opening the options chain and executing a trade."
        )

    # Sizing Consistency
    sizing = metrics.get('sizing_consistency')
    if sizing is not None:
        if sizing < 2.0:
            descriptor = "This indicates relatively stable allocation decisions."
        elif sizing < 4.0:
            descriptor = "This indicates moderate variation in position sizing across trades."
        else:
            descriptor = "This indicates variable position sizing across trades."

        parts.append(
            f"Your Sizing Consistency (std dev) is {sizing}%. {descriptor}"
        )

    # Emotional Reactivity
    emotional = metrics.get('emotional_reactivity')
    if emotional is not None:
        parts.append(
            f"Your Emotional Reactivity score is {emotional}/100."
        )
        if emotional > 50:
            parts.append(
                "The pattern indicates frequent emotional trading events "
                "appearing in your trade history."
            )
        elif emotional > 25:
            parts.append(
                "Some emotional trading patterns are present but not dominant "
                "in the overall data."
            )

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Trader DNA Score (Phase 10 — Req 73)
# ---------------------------------------------------------------------------

def compute_trader_dna_score(metrics: dict) -> int:
    """
    Compute a single 0-100 Trader DNA Score combining all behavioral metrics.
    
    Weights:
    - Discipline Rating: 30% (higher is better)
    - Patience: 20% (normalized 0-100 from seconds, 120s = 100)
    - Sizing Consistency: 20% (inverted — lower stdev = better)
    - Emotional Control: 30% (inverted — lower reactivity = better)
    
    Returns integer 0-100.
    """
    discipline = metrics.get('discipline_rating') or 0
    patience_raw = metrics.get('patience_score') or 0
    patience = min(100, (patience_raw / 120) * 100)
    sizing_raw = metrics.get('sizing_consistency') or 0
    sizing = max(0, 100 - sizing_raw * 10)  # Lower stdev = better
    emotional_raw = metrics.get('emotional_reactivity') or 0
    emotional = 100 - emotional_raw  # Lower reactivity = better
    
    score = (discipline * 0.30) + (patience * 0.20) + (sizing * 0.20) + (emotional * 0.30)
    return max(0, min(100, round(score)))


# ---------------------------------------------------------------------------
# Strategy P&L vs Behavioral Cost (Phase 10 — Req 74)
# ---------------------------------------------------------------------------

def compute_strategy_vs_behavior_cost(trades: list) -> dict:
    """
    Separate strategy P&L from behavioral cost.
    
    - Strategy P&L: P&L from trades WITHOUT behavioral flags (clean trades)
    - Behavioral Cost: P&L from trades WITH behavioral flags (revenge, overconfidence, impulse)
    - Potential: What you'd have if all trades were clean
    
    Returns: {
        "strategy_pnl": float,  # P&L from clean trades
        "behavioral_cost": float,  # P&L lost to flagged trades
        "potential_pnl": float,  # strategy_pnl - behavioral_cost (what you'd have)
        "behavioral_pct": float,  # % of total loss attributable to behavior
    }
    """
    clean_pnl = 0
    flagged_pnl = 0
    
    for t in trades:
        pnl = t.get('realized_pnl') or 0
        is_flagged = (t.get('is_revenge_trade') or t.get('is_overconfidence_trap') or t.get('is_impulse_early_exit'))
        if is_flagged:
            flagged_pnl += pnl
        else:
            clean_pnl += pnl
    
    total_losses = sum(t.get('realized_pnl', 0) for t in trades if (t.get('realized_pnl') or 0) < 0)
    behavioral_pct = round(abs(flagged_pnl) / abs(total_losses) * 100, 1) if total_losses < 0 else 0
    
    return {
        "strategy_pnl": round(clean_pnl, 2),
        "behavioral_cost": round(flagged_pnl, 2),
        "potential_pnl": round(clean_pnl - flagged_pnl, 2),
        "behavioral_pct": behavioral_pct,
    }


# ---------------------------------------------------------------------------
# Fix One Thing First (Phase 10 — Req 75)
# ---------------------------------------------------------------------------

def get_fix_one_thing(trades: list) -> dict:
    """
    Identify the single behavioral pattern causing the most damage.
    
    Returns: {
        "pattern": "Revenge Trading",
        "cost": -2340.0,
        "count": 5,
        "recommendation": "Your revenge trades cost ₹2,340. They occur within 1 hour of losses and are 2.5x your normal size."
    }
    """
    patterns = {
        "Revenge Trading": {"cost": 0, "count": 0},
        "Overconfidence": {"cost": 0, "count": 0},
        "Impulse Exit": {"cost": 0, "count": 0},
    }
    
    for t in trades:
        pnl = t.get('realized_pnl') or 0
        if t.get('is_revenge_trade'):
            patterns["Revenge Trading"]["cost"] += pnl
            patterns["Revenge Trading"]["count"] += 1
        if t.get('is_overconfidence_trap'):
            patterns["Overconfidence"]["cost"] += pnl
            patterns["Overconfidence"]["count"] += 1
        if t.get('is_impulse_early_exit'):
            patterns["Impulse Exit"]["cost"] += pnl
            patterns["Impulse Exit"]["count"] += 1
    
    # Find worst pattern (most negative cost)
    worst = min(patterns.items(), key=lambda x: x[1]["cost"])
    pattern_name = worst[0]
    data = worst[1]
    
    if data["count"] == 0:
        return {"pattern": None, "cost": 0, "count": 0, "recommendation": "No major behavioral patterns detected yet."}
    
    return {
        "pattern": pattern_name,
        "cost": round(data["cost"], 2),
        "count": data["count"],
        "recommendation": f"Your {pattern_name.lower()} pattern cost \u20b9{abs(data['cost']):,.0f} across {data['count']} trades. Fix this ONE thing to see the biggest improvement."
    }


# ---------------------------------------------------------------------------
# Aggregate Computation (DB Integration)
# ---------------------------------------------------------------------------

def compute_all_behavioral_metrics(profile_id: int) -> dict:
    """
    Fetch all trades for a profile from the database and compute the
    complete behavioral metrics suite.

    Returns a dict with all values ready to INSERT/UPDATE into the
    behavioral_metrics table.

    Args:
        profile_id: The profile ID to compute metrics for.

    Returns:
        Dict with keys matching behavioral_metrics columns:
        - profile_id, source, discipline_rating, patience_score,
          sizing_consistency, emotional_reactivity, loss_disposition_ratio,
          loss_disposition_flagged, current_streak, longest_streak,
          total_trades, phase, diagnostic_summary, updated_at
    """
    from db.database import get_connection

    conn = get_connection()
    try:
        # Fetch all trades for this profile, ordered by opened_at
        rows = conn.execute(
            "SELECT * FROM trades WHERE profile_id = ? ORDER BY opened_at ASC",
            (profile_id,)
        ).fetchall()

        # Convert sqlite3.Row objects to dicts
        trades = [dict(row) for row in rows]
    finally:
        conn.close()

    total_trades = len(trades)

    # Compute core metrics
    discipline = compute_discipline_rating(trades)
    patience = compute_patience_score(trades)
    sizing = compute_sizing_consistency(trades)
    emotional = compute_emotional_reactivity(trades)

    # Loss disposition
    loss_ratio, loss_flagged = detect_loss_disposition(trades)

    # Streaks
    current_streak, longest_streak = compute_streak(trades)

    # Phase
    phase = determine_phase(total_trades)

    # Build metrics dict for diagnostic generation
    metrics_for_diag = {
        'discipline_rating': discipline,
        'patience_score': patience,
        'sizing_consistency': sizing,
        'emotional_reactivity': emotional,
        'total_trades': total_trades,
    }

    # Diagnostic (only generated in Phase D)
    diagnostic = None
    if phase == 'D' and total_trades > 0:
        diagnostic = generate_diagnostic(metrics_for_diag, trades)

    # Compute new competitive features
    dna_score = compute_trader_dna_score(metrics_for_diag)
    strategy_vs_behavior = compute_strategy_vs_behavior_cost(trades)
    fix_one_thing = get_fix_one_thing(trades)

    return {
        'profile_id': profile_id,
        'source': 'sim',
        'discipline_rating': discipline,
        'patience_score': patience,
        'sizing_consistency': sizing,
        'emotional_reactivity': emotional,
        'loss_disposition_ratio': loss_ratio,
        'loss_disposition_flagged': 1 if loss_flagged else 0,
        'current_streak': current_streak,
        'longest_streak': longest_streak,
        'total_trades': total_trades,
        'phase': phase,
        'diagnostic_summary': diagnostic,
        'dna_score': dna_score,
        'strategy_vs_behavior': strategy_vs_behavior,
        'fix_one_thing': fix_one_thing,
        'updated_at': datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Trader DNA Score (Single 0-100 number)
# ---------------------------------------------------------------------------

def compute_trader_dna_score(metrics: dict) -> int:
    """
    Compute a single 0-100 Trader DNA Score combining all behavioral metrics.
    
    Weights: Discipline 30%, Patience 20%, Sizing 20%, Emotional Control 30%
    """
    discipline = metrics.get('discipline_rating') or 0
    patience_raw = metrics.get('patience_score') or 0
    patience = min(100, (patience_raw / 120) * 100)
    sizing_raw = metrics.get('sizing_consistency') or 0
    sizing = max(0, 100 - sizing_raw * 10)
    emotional_raw = metrics.get('emotional_reactivity') or 0
    emotional = 100 - emotional_raw

    score = (discipline * 0.30) + (patience * 0.20) + (sizing * 0.20) + (emotional * 0.30)
    return max(0, min(100, round(score)))


# ---------------------------------------------------------------------------
# Strategy vs Behavior Cost Split
# ---------------------------------------------------------------------------

def compute_strategy_vs_behavior_cost(trades: list) -> dict:
    """
    Separate strategy P&L from behavioral cost.
    Clean trades = strategy working. Flagged trades = behavior destroying.
    """
    clean_pnl = 0.0
    flagged_pnl = 0.0

    for t in trades:
        pnl = t.get('realized_pnl') or 0
        is_flagged = (t.get('is_revenge_trade') or t.get('is_overconfidence_trap') or t.get('is_impulse_early_exit'))
        if is_flagged:
            flagged_pnl += pnl
        else:
            clean_pnl += pnl

    total_losses = sum(t.get('realized_pnl', 0) for t in trades if (t.get('realized_pnl') or 0) < 0)
    behavioral_pct = round(abs(flagged_pnl) / abs(total_losses) * 100, 1) if total_losses < 0 else 0

    return {
        "strategy_pnl": round(clean_pnl, 2),
        "behavioral_cost": round(flagged_pnl, 2),
        "potential_pnl": round(clean_pnl - flagged_pnl, 2),
        "behavioral_pct": behavioral_pct,
    }


# ---------------------------------------------------------------------------
# Fix One Thing First
# ---------------------------------------------------------------------------

def get_fix_one_thing(trades: list) -> dict:
    """Identify the single behavioral pattern causing the most damage."""
    patterns = {
        "Revenge Trading": {"cost": 0.0, "count": 0},
        "Overconfidence": {"cost": 0.0, "count": 0},
        "Impulse Exit": {"cost": 0.0, "count": 0},
    }

    for t in trades:
        pnl = t.get('realized_pnl') or 0
        if t.get('is_revenge_trade'):
            patterns["Revenge Trading"]["cost"] += pnl
            patterns["Revenge Trading"]["count"] += 1
        if t.get('is_overconfidence_trap'):
            patterns["Overconfidence"]["cost"] += pnl
            patterns["Overconfidence"]["count"] += 1
        if t.get('is_impulse_early_exit'):
            patterns["Impulse Exit"]["cost"] += pnl
            patterns["Impulse Exit"]["count"] += 1

    worst = min(patterns.items(), key=lambda x: x[1]["cost"])
    pattern_name = worst[0]
    data = worst[1]

    if data["count"] == 0:
        return {"pattern": None, "cost": 0, "count": 0, "recommendation": "No major behavioral patterns detected yet. Keep trading to build your profile."}

    return {
        "pattern": pattern_name,
        "cost": round(data["cost"], 2),
        "count": data["count"],
        "recommendation": f"Your {pattern_name.lower()} cost you ₹{abs(data['cost']):,.0f} across {data['count']} trades. Fix this ONE thing to see the biggest improvement.",
    }
