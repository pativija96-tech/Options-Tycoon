"""
Options Tycoon - Trader DNA Report Routes.

Generates the Devastating Report from trade history — the viral hook that
shows traders exactly why they're losing money.
"""

from fastapi import APIRouter, HTTPException
from db.database import get_connection
from engine.report_generator import generate_devastating_report

router = APIRouter()


@router.get("/report/{profile_id}")
def get_trader_dna_report(profile_id: int):
    """Generate the Devastating Report from trade history."""
    conn = get_connection()
    try:
        trades = conn.execute(
            "SELECT * FROM trades WHERE profile_id = ? AND status IN ('closed', 'settled') ORDER BY opened_at",
            (profile_id,)
        ).fetchall()

        # Convert to the format the report generator expects
        trade_list = []
        for t in trades:
            trade_list.append({
                'ticker': t['ticker'],
                'entry_time': t['opened_at'],
                'exit_time': t['closed_at'],
                'entry_price': t['entry_price'],
                'exit_price': t['exit_price'] if t['exit_price'] else t['entry_price'],
                'pnl': t['realized_pnl'] if t['realized_pnl'] else 0,
                'quantity': 1,
            })

        if len(trade_list) < 5:
            return {
                "error": "Need at least 5 closed trades to generate report",
                "trade_count": len(trade_list),
            }

        report = generate_devastating_report(trade_list)
        return report
    finally:
        conn.close()
