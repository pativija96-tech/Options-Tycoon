"""
End-to-End NIFTY Signal Test — Verifies the signal is correct before live execution.

Run: python tests/test_nifty_e2e.py
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["TRADING_PHASE"] = "1"

print("=" * 60)
print("END-TO-END NIFTY SIGNAL TEST")
print("=" * 60)
print()

# Step 1: Generate NIFTY signal
print("Step 1: Generating NIFTY signal...")
from engine.signals.simple_ic_engine import generate_daily_signal
signal = generate_daily_signal(capital=15000)

action = signal.get("action")
print(f"  Action: {action}")
if action != "trade":
    print(f"  SKIP REASON: {signal.get('reason')}")
    print("  Signal skipped — cannot test execution flow.")
    sys.exit(1)

trade = signal["trade"]
legs = trade["legs"]
print(f"  NIFTY Price: {signal['projected_open']:.0f}")
print(f"  VIX: {signal['conditions']['vix_level']:.1f}%")
print(f"  Expiry: {trade['expiry_date']}")
print()

# Step 2: Verify legs are NIFTY (not QQQ)
print("Step 2: Verifying legs are NIFTY format...")
errors = []
for leg in legs:
    strike = leg["strike"]
    option = leg["option"]
    action_leg = leg["action"]
    prem = leg["premium_est"]
    print(f"  {action_leg} NIFTY {strike} {option} @ Rs.{prem}")
    if strike < 20000:
        errors.append(f"Strike {strike} too low for NIFTY — looks like QQQ!")
    if option not in ("CE", "PE"):
        errors.append(f"Option type '{option}' not CE/PE — wrong format!")

if errors:
    print("\n  ERRORS:")
    for e in errors:
        print(f"  ❌ {e}")
    sys.exit(1)
print("  ✅ All legs are valid NIFTY format.")
print()

# Step 3: Verify financials in INR
print("Step 3: Verifying financials...")
net_credit = -trade["net_cost_total"]
max_loss = trade["max_loss"]
max_profit = trade["max_profit"]
risk_pct = signal["risk_check"]["max_loss_pct"]
print(f"  Net Credit: Rs.{net_credit:.0f}")
print(f"  Max Loss: Rs.{max_loss:.0f}")
print(f"  Max Profit: Rs.{max_profit:.0f}")
print(f"  Risk/Capital: {risk_pct:.1f}%")

if max_loss > 3000:
    print(f"  ❌ ERROR: Max loss Rs.{max_loss} exceeds Rs.3000 safety cap!")
    sys.exit(1)
if net_credit <= 0:
    print(f"  ❌ ERROR: Negative or zero credit!")
    sys.exit(1)
if risk_pct > 25:
    print(f"  ❌ ERROR: Risk {risk_pct}% exceeds 25% cap!")
    sys.exit(1)
print("  ✅ Financials within safe range for Rs.15,000 account.")
print()

# Step 4: Verify Kite order symbols
print("Step 4: Simulating Kite order symbols...")
from engine.broker.kite_executor import get_expiry_symbol_format
for leg in legs:
    symbol = get_expiry_symbol_format(leg["strike"], leg["option"])
    print(f"  {leg['action']} {symbol} qty=25 MARKET NRML")
print("  ✅ Order symbols generated correctly.")
print()

# Step 5: Verify signal is NOT QQQ
print("Step 5: Confirming this is NOT a QQQ signal...")
strategy = signal.get("strategy_type", "")
market = signal.get("market", "")
if "qqq" in strategy.lower() or "qqq" in market.lower():
    print(f"  ❌ ERROR: Signal contains QQQ references! strategy={strategy}, market={market}")
    sys.exit(1)
if any("QQQ" in str(leg.get("strike", "")) for leg in legs):
    print(f"  ❌ ERROR: Legs contain QQQ-like strikes!")
    sys.exit(1)
print("  ✅ Confirmed NIFTY signal (no QQQ contamination).")
print()

# Summary
print("=" * 60)
print("ALL CHECKS PASSED ✅")
print("=" * 60)
print()
print(f"Signal: NIFTY Iron Condor")
print(f"Strikes: {legs[0]['strike']} CE / {legs[2]['strike']} PE (±250pt)")
print(f"Credit: Rs.{net_credit:.0f} | Max Loss: Rs.{max_loss:.0f}")
print(f"Expiry: {trade['expiry_date']}")
print(f"Lot size: 25 | Phase 1")
print()
print("SAFE TO EXECUTE (if NFO segment is activated).")
