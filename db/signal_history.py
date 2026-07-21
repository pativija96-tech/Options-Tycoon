"""
Signal History Repository — Append-only persistence for generated signals.

Every signal produced by the signal engine is saved here with full details.
Never overwrites — always appends. Used for:
- Model learning (pattern performance over time)
- Performance review (what signals were generated vs market outcome)
- Strategy refinement (filter effectiveness, directional accuracy)

Usage:
    from db.signal_history import save_signal, get_signal_history

    # After generating a signal:
    save_signal(trade_card)

    # Query historical signals:
    history = get_signal_history(days=30)
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from db.database import get_connection

logger = logging.getLogger("options_tycoon.signal_history")


def save_signal(signal: dict) -> Optional[int]:
    """
    Persist a generated signal to the signal_history table.

    Args:
        signal: The full trade card dict (same structure as today_signal.json).

    Returns:
        The inserted row ID, or None if save failed.
    """
    if not signal:
        logger.warning("save_signal called with empty signal — skipping")
        return None

    conn = get_connection()
    try:
        # Extract key fields for queryable columns
        action = signal.get("action", "unknown")
        direction = signal.get("direction")
        confidence = signal.get("confidence")
        strategy_type = signal.get("strategy_type")
        projected_open = signal.get("projected_open")
        reasoning = signal.get("reasoning")
        signal_date = signal.get("date", datetime.now().strftime("%Y-%m-%d"))
        skip_reason = signal.get("reason") if action != "trade" else None

        # Serialize nested objects to JSON strings
        trade_json = json.dumps(signal.get("trade"), default=str) if signal.get("trade") else None
        conditions_json = json.dumps(signal.get("conditions"), default=str) if signal.get("conditions") else None
        pattern_result_json = json.dumps(signal.get("pattern_result"), default=str) if signal.get("pattern_result") else None

        # Quality filters
        quality_filters = signal.get("quality_filters")
        quality_filters_json = json.dumps(quality_filters, default=str) if quality_filters else None
        filters_passed = quality_filters.get("passed") if quality_filters else None
        filters_total = quality_filters.get("total") if quality_filters else None
        filter_strength = quality_filters.get("strength") if quality_filters else None

        # Position sizing & risk
        position_sizing_json = json.dumps(signal.get("position_sizing"), default=str) if signal.get("position_sizing") else None
        risk_check_json = json.dumps(signal.get("risk_check"), default=str) if signal.get("risk_check") else None

        # Stock signals
        stock_signals_json = json.dumps(signal.get("stock_signals"), default=str) if signal.get("stock_signals") else None

        # Full signal as fallback (complete record)
        full_signal_json = json.dumps(signal, default=str)

        cursor = conn.execute(
            """
            INSERT INTO signal_history (
                signal_date, action, direction, confidence, strategy_type,
                projected_open, trade_json, reasoning, conditions_json,
                pattern_result_json, quality_filters_json, filters_passed,
                filters_total, filter_strength, position_sizing_json,
                risk_check_json, stock_signals_json, skip_reason,
                full_signal_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_date, action, direction, confidence, strategy_type,
                projected_open, trade_json, reasoning, conditions_json,
                pattern_result_json, quality_filters_json, filters_passed,
                filters_total, filter_strength, position_sizing_json,
                risk_check_json, stock_signals_json, skip_reason,
                full_signal_json,
            )
        )
        conn.commit()

        row_id = cursor.lastrowid
        logger.info(f"Signal saved to history: id={row_id}, date={signal_date}, "
                    f"action={action}, direction={direction}, confidence={confidence}")
        return row_id

    except Exception as e:
        logger.error(f"Failed to save signal to history: {e}")
        return None
    finally:
        conn.close()


def get_signal_history(
    days: Optional[int] = None,
    direction: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
) -> list:
    """
    Query signal history with optional filters.

    Args:
        days: Only return signals from the last N days.
        direction: Filter by direction (bullish, bearish, neutral).
        action: Filter by action (trade, skip).
        limit: Max rows to return (default 100).

    Returns:
        List of signal history rows as dicts.
    """
    conn = get_connection()
    try:
        query = "SELECT * FROM signal_history WHERE 1=1"
        params = []

        if days is not None:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            query += " AND signal_date >= ?"
            params.append(cutoff)

        if direction:
            query += " AND direction = ?"
            params.append(direction)

        if action:
            query += " AND action = ?"
            params.append(action)

        query += " ORDER BY signal_date DESC, generated_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        # Convert to plain dicts
        return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Failed to query signal history: {e}")
        return []
    finally:
        conn.close()


def get_signal_stats(days: int = 30) -> dict:
    """
    Compute summary statistics over recent signal history.

    Returns:
        Dict with counts, direction breakdown, avg confidence, filter stats.
    """
    conn = get_connection()
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM signal_history WHERE signal_date >= ?",
            (cutoff,)
        ).fetchone()

        trades = conn.execute(
            "SELECT COUNT(*) as cnt FROM signal_history WHERE signal_date >= ? AND action = 'trade'",
            (cutoff,)
        ).fetchone()

        skips = conn.execute(
            "SELECT COUNT(*) as cnt FROM signal_history WHERE signal_date >= ? AND action = 'skip'",
            (cutoff,)
        ).fetchone()

        direction_counts = conn.execute(
            """SELECT direction, COUNT(*) as cnt
               FROM signal_history
               WHERE signal_date >= ? AND action = 'trade'
               GROUP BY direction""",
            (cutoff,)
        ).fetchall()

        avg_confidence = conn.execute(
            "SELECT AVG(confidence) as avg_conf FROM signal_history WHERE signal_date >= ? AND action = 'trade'",
            (cutoff,)
        ).fetchone()

        avg_filters = conn.execute(
            "SELECT AVG(filters_passed) as avg_fp FROM signal_history WHERE signal_date >= ? AND action = 'trade'",
            (cutoff,)
        ).fetchone()

        return {
            "period_days": days,
            "total_signals": total["cnt"] if total else 0,
            "trade_signals": trades["cnt"] if trades else 0,
            "skip_signals": skips["cnt"] if skips else 0,
            "direction_breakdown": {row["direction"]: row["cnt"] for row in direction_counts},
            "avg_confidence": round(avg_confidence["avg_conf"], 1) if avg_confidence and avg_confidence["avg_conf"] else None,
            "avg_filters_passed": round(avg_filters["avg_fp"], 1) if avg_filters and avg_filters["avg_fp"] else None,
        }

    except Exception as e:
        logger.error(f"Failed to compute signal stats: {e}")
        return {"error": str(e)}
    finally:
        conn.close()
