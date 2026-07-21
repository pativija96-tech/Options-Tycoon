"""
Options Tycoon - Demo Seed Script

Creates a realistic 25-trade history for "Demo Trader" that demonstrates
emotional trading patterns: revenge trading, overconfidence traps,
impulse exits, and loss disposition bias.

Run with: python seed_demo.py
"""

import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

# Ensure project imports work
sys.path.insert(0, str(Path(__file__).parent))

from db.database import get_db_path, get_connection, init_db


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = get_db_path()
STARTING_BALANCE = 10000.0
PROFILE_NAME = "Demo Trader"

# Base date: 14 days ago from now
BASE_DATE = datetime.now() - timedelta(days=14)


def delete_existing_db():
    """Remove existing database for a fresh start."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"  Deleted existing database: {DB_PATH}")
    # Also remove WAL/SHM files if present
    for ext in ["-wal", "-shm"]:
        path = DB_PATH + ext
        if os.path.exists(path):
            os.remove(path)


def create_profile(conn: sqlite3.Connection) -> int:
    """Create the Demo Trader profile and return its ID."""
    cursor = conn.execute(
        """INSERT INTO profiles (name, balance, mode, disclaimer_acknowledged)
           VALUES (?, ?, 'sim_only', 1)""",
        (PROFILE_NAME, STARTING_BALANCE)
    )
    conn.commit()
    return cursor.lastrowid


# ---------------------------------------------------------------------------
# Trade Data Generator
# ---------------------------------------------------------------------------

def make_legs(ticker: str, option_type: str, strike: float, qty: int = 1,
              direction: str = "buy", second_leg=None) -> str:
    """Build JSON legs array for a trade."""
    legs = [{
        "ticker": ticker,
        "option_type": option_type,
        "strike": strike,
        "quantity": qty,
        "direction": direction
    }]
    if second_leg:
        legs.append(second_leg)
    return json.dumps(legs)


def generate_trades():
    """
    Generate 25 trades telling the emotional story.
    Returns list of trade dicts ready for insertion.
    """
    trades = []
    balance = STARTING_BALANCE
    trade_num = 0

    def add_trade(day_offset, hour, minute, ticker, strategy_type, legs,
                  entry_price, exit_price, slippage, position_pct,
                  status="closed", hold_days=1, deliberation_secs=90,
                  is_revenge=0, is_overconfidence=0, is_impulse_exit=0,
                  max_unrealized=None):
        nonlocal trade_num, balance
        trade_num += 1

        position_size = entry_price
        realized_pnl = exit_price - entry_price - slippage

        opened_at = BASE_DATE + timedelta(days=day_offset, hours=hour, minutes=minute)
        closed_at = opened_at + timedelta(days=hold_days)
        chain_opened_at = opened_at - timedelta(seconds=deliberation_secs)
        trade_executed_at = opened_at

        # Calculate actual position_pct from current balance
        actual_pct = round((position_size / balance) * 100, 2)

        if max_unrealized is None:
            if realized_pnl > 0:
                max_unrealized = realized_pnl * 1.2
            else:
                max_unrealized = max(realized_pnl * 0.3, 0)

        trade = {
            "profile_id": 1,
            "ticker": ticker,
            "strategy_type": strategy_type,
            "legs": legs,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "slippage_cost": slippage,
            "position_size": position_size,
            "position_pct": actual_pct if position_pct is None else position_pct,
            "max_unrealized_pnl": max_unrealized,
            "realized_pnl": realized_pnl,
            "status": status,
            "opened_at": opened_at.strftime("%Y-%m-%d %H:%M:%S"),
            "closed_at": closed_at.strftime("%Y-%m-%d %H:%M:%S"),
            "expiration_date": (opened_at + timedelta(days=7)).strftime("%Y-%m-%d"),
            "is_revenge_trade": is_revenge,
            "is_overconfidence_trap": is_overconfidence,
            "is_impulse_early_exit": is_impulse_exit,
            "chain_opened_at": chain_opened_at.strftime("%Y-%m-%d %H:%M:%S"),
            "trade_executed_at": trade_executed_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

        balance += realized_pnl
        trades.append(trade)
        return trade

    # ===================================================================
    # TRADES 1-5: Disciplined Start
    # Small positions (3-5%), patient entries, mix of wins/losses
    # ===================================================================

    # Trade 1: BANKNIFTY CE win
    add_trade(day_offset=0, hour=10, minute=15, ticker="BANKNIFTY",
              strategy_type="single",
              legs=make_legs("BANKNIFTY", "CE", 44500),
              entry_price=350, exit_price=420, slippage=8,
              position_pct=3.5, deliberation_secs=95)

    # Trade 2: NIFTY PE small loss
    add_trade(day_offset=1, hour=11, minute=30, ticker="NIFTY",
              strategy_type="single",
              legs=make_legs("NIFTY", "PE", 21800),
              entry_price=280, exit_price=245, slippage=7,
              position_pct=2.8, deliberation_secs=110)

    # Trade 3: RELIANCE CE win
    add_trade(day_offset=2, hour=9, minute=45, ticker="RELIANCE",
              strategy_type="single",
              legs=make_legs("RELIANCE", "CE", 2500),
              entry_price=180, exit_price=225, slippage=5,
              position_pct=1.8, deliberation_secs=120)

    # Trade 4: BANKNIFTY vertical spread, small win
    add_trade(day_offset=3, hour=10, minute=0, ticker="BANKNIFTY",
              strategy_type="vertical",
              legs=make_legs("BANKNIFTY", "CE", 44600, direction="buy",
                           second_leg={"ticker": "BANKNIFTY", "option_type": "CE",
                                       "strike": 44800, "quantity": 1, "direction": "sell"}),
              entry_price=420, exit_price=485, slippage=12,
              position_pct=4.2, deliberation_secs=85)

    # Trade 5: NIFTY CE small loss
    add_trade(day_offset=4, hour=14, minute=0, ticker="NIFTY",
              strategy_type="single",
              legs=make_legs("NIFTY", "CE", 21900),
              entry_price=310, exit_price=275, slippage=8,
              position_pct=3.1, deliberation_secs=60)

    # ===================================================================
    # TRADES 6-8: First Real Loss + Revenge Trading
    # ===================================================================

    # Trade 6: Larger loss (-800)
    add_trade(day_offset=5, hour=10, minute=30, ticker="BANKNIFTY",
              strategy_type="single",
              legs=make_legs("BANKNIFTY", "CE", 44700),
              entry_price=520, exit_price=280, slippage=12,
              position_pct=5.2, deliberation_secs=75)

    # Trade 7: REVENGE TRADE — 30 min later, 12% position, another loss
    add_trade(day_offset=5, hour=11, minute=0, ticker="BANKNIFTY",
              strategy_type="single",
              legs=make_legs("BANKNIFTY", "PE", 44400),
              entry_price=950, exit_price=680, slippage=18,
              position_pct=12.0, deliberation_secs=15,
              is_revenge=1)

    # Trade 8: REVENGE TRADE — 15 min later, 15% position, big loss
    add_trade(day_offset=5, hour=11, minute=15, ticker="BANKNIFTY",
              strategy_type="single",
              legs=make_legs("BANKNIFTY", "CE", 44800),
              entry_price=1000, exit_price=620, slippage=20,
              position_pct=15.0, deliberation_secs=8,
              is_revenge=1)

    # ===================================================================
    # TRADES 9-12: Recovery and Calm
    # Back to normal sizing, patient entries
    # ===================================================================

    # Trade 9: NIFTY PE win
    add_trade(day_offset=7, hour=10, minute=45, ticker="NIFTY",
              strategy_type="single",
              legs=make_legs("NIFTY", "PE", 21750),
              entry_price=200, exit_price=265, slippage=6,
              position_pct=4.5, deliberation_secs=100)

    # Trade 10: RELIANCE CE win
    add_trade(day_offset=7, hour=14, minute=30, ticker="RELIANCE",
              strategy_type="single",
              legs=make_legs("RELIANCE", "CE", 2520),
              entry_price=165, exit_price=210, slippage=5,
              position_pct=4.0, deliberation_secs=130)

    # Trade 11: BANKNIFTY vertical spread, small loss
    add_trade(day_offset=8, hour=11, minute=0, ticker="BANKNIFTY",
              strategy_type="vertical",
              legs=make_legs("BANKNIFTY", "PE", 44300, direction="buy",
                           second_leg={"ticker": "BANKNIFTY", "option_type": "PE",
                                       "strike": 44100, "quantity": 1, "direction": "sell"}),
              entry_price=380, exit_price=340, slippage=10,
              position_pct=4.8, deliberation_secs=90)

    # Trade 12: NIFTY CE win — confidence rebuilding
    add_trade(day_offset=9, hour=9, minute=30, ticker="NIFTY",
              strategy_type="single",
              legs=make_legs("NIFTY", "CE", 21950),
              entry_price=250, exit_price=320, slippage=7,
              position_pct=4.2, deliberation_secs=105)

    # ===================================================================
    # TRADES 13-16: Overconfidence After Winning Streak
    # Trades 13-15 wins, Trade 16 overconfidence trap
    # ===================================================================

    # Trade 13: BANKNIFTY CE win
    add_trade(day_offset=9, hour=14, minute=0, ticker="BANKNIFTY",
              strategy_type="single",
              legs=make_legs("BANKNIFTY", "CE", 44900),
              entry_price=300, exit_price=385, slippage=8,
              position_pct=4.5, deliberation_secs=80)

    # Trade 14: RELIANCE PE win
    add_trade(day_offset=10, hour=10, minute=15, ticker="RELIANCE",
              strategy_type="single",
              legs=make_legs("RELIANCE", "PE", 2480),
              entry_price=195, exit_price=260, slippage=6,
              position_pct=3.8, deliberation_secs=95)

    # Trade 15: NIFTY CE win — 3rd consecutive
    add_trade(day_offset=10, hour=14, minute=45, ticker="NIFTY",
              strategy_type="single",
              legs=make_legs("NIFTY", "CE", 22000),
              entry_price=280, exit_price=345, slippage=7,
              position_pct=4.2, deliberation_secs=70)

    # Trade 16: OVERCONFIDENCE TRAP — size jumps to 10% after 3 wins, loss
    add_trade(day_offset=11, hour=10, minute=0, ticker="BANKNIFTY",
              strategy_type="single",
              legs=make_legs("BANKNIFTY", "CE", 45100),
              entry_price=750, exit_price=480, slippage=15,
              position_pct=10.0, deliberation_secs=25,
              is_overconfidence=1)

    # ===================================================================
    # TRADES 17-20: Mixed, with Impulse Early Exit
    # ===================================================================

    # Trade 17: IMPULSE EXIT — good entry, exited at 20% of peak profit
    add_trade(day_offset=11, hour=14, minute=30, ticker="NIFTY",
              strategy_type="single",
              legs=make_legs("NIFTY", "PE", 21850),
              entry_price=220, exit_price=250, slippage=6,
              position_pct=4.5, deliberation_secs=100,
              is_impulse_exit=1,
              max_unrealized=150)  # Could have made 150, only took 24

    # Trade 18: RELIANCE CE small win
    add_trade(day_offset=12, hour=10, minute=0, ticker="RELIANCE",
              strategy_type="single",
              legs=make_legs("RELIANCE", "CE", 2540),
              entry_price=175, exit_price=210, slippage=5,
              position_pct=3.5, deliberation_secs=85)

    # Trade 19: BANKNIFTY PE loss
    add_trade(day_offset=12, hour=13, minute=45, ticker="BANKNIFTY",
              strategy_type="single",
              legs=make_legs("BANKNIFTY", "PE", 44600),
              entry_price=340, exit_price=285, slippage=9,
              position_pct=4.8, deliberation_secs=75)

    # Trade 20: NIFTY vertical spread, small win
    add_trade(day_offset=12, hour=15, minute=0, ticker="NIFTY",
              strategy_type="vertical",
              legs=make_legs("NIFTY", "CE", 22050, direction="buy",
                           second_leg={"ticker": "NIFTY", "option_type": "CE",
                                       "strike": 22200, "quantity": 1, "direction": "sell"}),
              entry_price=290, exit_price=330, slippage=8,
              position_pct=4.2, deliberation_secs=110)

    # ===================================================================
    # TRADES 21-25: Loss Disposition Bias
    # Winners closed in 1 day, losers held 4+ days
    # ===================================================================

    # Trade 21: BANKNIFTY CE winner — closed after 1 day
    add_trade(day_offset=13, hour=9, minute=45, ticker="BANKNIFTY",
              strategy_type="single",
              legs=make_legs("BANKNIFTY", "CE", 45000),
              entry_price=320, exit_price=395, slippage=8,
              position_pct=4.5, hold_days=1, deliberation_secs=90)

    # Trade 22: NIFTY PE winner — closed after 1 day
    add_trade(day_offset=13, hour=11, minute=30, ticker="NIFTY",
              strategy_type="single",
              legs=make_legs("NIFTY", "PE", 21900),
              entry_price=240, exit_price=295, slippage=7,
              position_pct=3.8, hold_days=1, deliberation_secs=100)

    # Trade 23: RELIANCE CE loser — held for 4 days (disposition bias)
    add_trade(day_offset=13, hour=14, minute=0, ticker="RELIANCE",
              strategy_type="single",
              legs=make_legs("RELIANCE", "CE", 2560),
              entry_price=200, exit_price=130, slippage=6,
              position_pct=4.0, hold_days=4, deliberation_secs=80,
              status="settled")

    # Trade 24: BANKNIFTY PE loser — held for 5 days (disposition bias)
    add_trade(day_offset=13, hour=15, minute=0, ticker="BANKNIFTY",
              strategy_type="single",
              legs=make_legs("BANKNIFTY", "PE", 44500),
              entry_price=280, exit_price=145, slippage=10,
              position_pct=4.2, hold_days=5, deliberation_secs=70,
              status="settled")

    # Trade 25: NIFTY CE loser — held for 4 days (disposition bias)
    add_trade(day_offset=14, hour=10, minute=0, ticker="NIFTY",
              strategy_type="single",
              legs=make_legs("NIFTY", "CE", 22100),
              entry_price=260, exit_price=175, slippage=8,
              position_pct=4.0, hold_days=4, deliberation_secs=65,
              status="settled")

    return trades, balance


# ---------------------------------------------------------------------------
# Insert trades into database
# ---------------------------------------------------------------------------

def insert_trades(conn: sqlite3.Connection, trades: list):
    """Insert all generated trades into the trades table."""
    columns = [
        "profile_id", "ticker", "strategy_type", "legs",
        "entry_price", "exit_price", "slippage_cost",
        "position_size", "position_pct", "max_unrealized_pnl",
        "realized_pnl", "status", "opened_at", "closed_at",
        "expiration_date", "is_revenge_trade", "is_overconfidence_trap",
        "is_impulse_early_exit", "chain_opened_at", "trade_executed_at"
    ]
    placeholders = ", ".join(["?"] * len(columns))
    col_str = ", ".join(columns)

    for trade in trades:
        values = [trade[col] for col in columns]
        conn.execute(
            f"INSERT INTO trades ({col_str}) VALUES ({placeholders})",
            values
        )
    conn.commit()


def update_profile_balance(conn: sqlite3.Connection, final_balance: float):
    """Update the profile balance to reflect all P&L."""
    conn.execute(
        "UPDATE profiles SET balance = ? WHERE id = 1",
        (round(final_balance, 2),)
    )
    conn.commit()


def update_monthly_pnl(conn: sqlite3.Connection, trades: list):
    """Aggregate and insert monthly P&L totals."""
    monthly = {}
    for trade in trades:
        month_key = trade["opened_at"][:7]  # YYYY-MM
        if month_key not in monthly:
            monthly[month_key] = {"pnl": 0.0, "count": 0}
        monthly[month_key]["pnl"] += trade["realized_pnl"]
        monthly[month_key]["count"] += 1

    for year_month, data in monthly.items():
        conn.execute(
            """INSERT INTO monthly_pnl (profile_id, year_month, realized_pnl, trade_count)
               VALUES (1, ?, ?, ?)""",
            (year_month, round(data["pnl"], 2), data["count"])
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Summary Printer
# ---------------------------------------------------------------------------

def print_summary(trades: list, final_balance: float):
    """Print a summary of the seeded data."""
    total_pnl = sum(t["realized_pnl"] for t in trades)
    winners = [t for t in trades if t["realized_pnl"] > 0]
    losers = [t for t in trades if t["realized_pnl"] <= 0]
    revenge_trades = [t for t in trades if t["is_revenge_trade"]]
    overconf_trades = [t for t in trades if t["is_overconfidence_trap"]]
    impulse_trades = [t for t in trades if t["is_impulse_early_exit"]]

    print("\n" + "=" * 60)
    print("  OPTIONS TYCOON — Demo Seed Complete")
    print("=" * 60)
    print(f"\n  Profile:          {PROFILE_NAME}")
    print(f"  Starting Balance: ₹{STARTING_BALANCE:,.2f}")
    print(f"  Final Balance:    ₹{final_balance:,.2f}")
    print(f"  Net P&L:          ₹{total_pnl:,.2f}")
    print(f"\n  Total Trades:     {len(trades)}")
    print(f"  Winners:          {len(winners)}")
    print(f"  Losers:           {len(losers)}")
    print(f"  Win Rate:         {len(winners)/len(trades)*100:.1f}%")
    print(f"\n  Behavioral Flags:")
    print(f"    Revenge Trades:       {len(revenge_trades)}")
    print(f"    Overconfidence Traps: {len(overconf_trades)}")
    print(f"    Impulse Exits:        {len(impulse_trades)}")
    print(f"    Disposition Bias:     3 (trades 23-25 held 4+ days)")
    print(f"\n  Database: {DB_PATH}")
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("\n🎯 Options Tycoon — Seeding Demo Data\n")

    # Step 1: Delete existing DB
    print("[1/5] Deleting existing database...")
    delete_existing_db()

    # Step 2: Initialize schema
    print("[2/5] Initializing schema...")
    init_db()

    # Step 3: Create profile
    print("[3/5] Creating Demo Trader profile...")
    conn = get_connection()
    try:
        profile_id = create_profile(conn)
        print(f"  Created profile ID: {profile_id}")

        # Step 4: Generate and insert trades
        print("[4/5] Inserting 25 trades with behavioral patterns...")
        trades, final_balance = generate_trades()
        insert_trades(conn, trades)
        print(f"  Inserted {len(trades)} trades")

        # Step 5: Update balance and monthly P&L
        print("[5/5] Updating balance and monthly P&L...")
        update_profile_balance(conn, final_balance)
        update_monthly_pnl(conn, trades)

        # Print summary
        print_summary(trades, final_balance)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
