"""Full end-to-end verification of all trade calculations."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.signals.strategy_picker import estimate_premium, LOT_SIZE, generate_trade_card, _calculate_charges

print("=" * 60)
print("OPTIONS TYCOON — CALCULATION VERIFICATION")
print("=" * 60)

# Check LOT_SIZE
print(f"\n1. LOT SIZE: {LOT_SIZE}")
assert LOT_SIZE == 65, f"WRONG! Expected 65, got {LOT_SIZE}"
print("   CORRECT (65 per SEBI Jan 2026 revision)")

# Test premium calculation
spot = 24000
print(f"\n2. PREMIUM CALCULATIONS (Spot: {spot})")
print("   Using Black-Scholes, IV=18%, 3 days to expiry:")

test_strikes = [23800, 23900, 24000, 24100, 24200, 24400]
for strike in test_strikes:
    ce = estimate_premium(spot, strike, 3, "call", 0.18)
    pe = estimate_premium(spot, strike, 3, "put", 0.18)
    print(f"   Strike {strike}: CE=Rs.{ce:.2f}, PE=Rs.{pe:.2f}")

# Verify: ATM should have highest time value, deep ITM should be ~intrinsic
atm_ce = estimate_premium(spot, 24000, 3, "call", 0.18)
itm_ce = estimate_premium(spot, 23800, 3, "call", 0.18)
otm_ce = estimate_premium(spot, 24200, 3, "call", 0.18)
print(f"\n   ATM CE (24000): Rs.{atm_ce:.2f} — should be ~Rs.100-200")
print(f"   ITM CE (23800): Rs.{itm_ce:.2f} — should be > Rs.200 (intrinsic=200)")
print(f"   OTM CE (24200): Rs.{otm_ce:.2f} — should be < Rs.100")

# Test Bull Call Spread
print("\n3. BULL CALL SPREAD CALCULATION")
long_strike = 24000
short_strike = 24200
width = 200
long_prem = estimate_premium(spot, long_strike, 3, "call", 0.18)
short_prem = estimate_premium(spot, short_strike, 3, "call", 0.18)
net_cost_per_unit = long_prem - short_prem
net_cost_total = net_cost_per_unit * LOT_SIZE
max_profit = (width - net_cost_per_unit) * LOT_SIZE
max_loss = net_cost_total

print(f"   BUY {long_strike} CE @ Rs.{long_prem:.2f}")
print(f"   SELL {short_strike} CE @ Rs.{short_prem:.2f}")
print(f"   Net cost per unit: Rs.{net_cost_per_unit:.2f}")
print(f"   Net cost total ({LOT_SIZE} qty): Rs.{net_cost_total:.2f}")
print(f"   Max Profit: Rs.{max_profit:.2f}")
print(f"   Max Loss: Rs.{max_loss:.2f}")
print(f"   R:R: {max_profit/max_loss:.2f}:1")

# Sanity checks
assert net_cost_per_unit > 0, "Net cost should be positive (buying more expensive option)"
assert max_profit > 0, "Max profit should be positive"
assert max_profit > max_loss, "Profit should exceed loss for a valid spread"
print("   ALL SPREAD CALCULATIONS CORRECT")

# Test risk cap
print("\n4. RISK CAP VERIFICATION")
capital = 1000000
max_risk = capital * 0.02
print(f"   Capital: Rs.{capital:,}")
print(f"   2% cap: Rs.{max_risk:,.0f}")
print(f"   Trade max loss: Rs.{max_loss:.2f}")
print(f"   Within cap: {max_loss <= max_risk} {'PASS' if max_loss <= max_risk else 'FAIL - TRADE SHOULD BE REJECTED'}")

# Test charges
print("\n5. CHARGES CALCULATION")
trade = {
    "legs": [
        {"action": "BUY", "option": "CE", "strike": long_strike, "premium_est": long_prem},
        {"action": "SELL", "option": "CE", "strike": short_strike, "premium_est": short_prem},
    ],
    "net_cost": net_cost_per_unit,
    "max_loss": max_loss,
    "max_profit": max_profit,
}
charges = _calculate_charges(trade)
print(f"   Brokerage: Rs.{charges['brokerage']} (Rs.20 x {len(trade['legs'])} legs x 2 orders)")
print(f"   GST (18%): Rs.{charges['gst']}")
print(f"   STT: Rs.{charges['stt']}")
print(f"   Exchange: Rs.{charges['exchange']}")
print(f"   SEBI: Rs.{charges['sebi']}")
print(f"   Stamp: Rs.{charges['stamp']}")
print(f"   TOTAL CHARGES: Rs.{charges['total']}")
print(f"   ")
print(f"   Net Max Profit (after charges): Rs.{max_profit - charges['total']:.2f}")
print(f"   Net Max Loss (incl charges): Rs.{max_loss + charges['total']:.2f}")
print(f"   Net R:R: {(max_profit - charges['total']) / (max_loss + charges['total']):.2f}:1")

# Test full signal generation
print("\n6. FULL SIGNAL GENERATION TEST")
from engine.signals.data_fetcher import fetch_global_data
from engine.signals.pattern_matcher import generate_pattern_signal
from engine.signals.quality_filters import run_all_filters

global_data = fetch_global_data("output")
pattern = generate_pattern_signal(global_data)
print(f"   Direction: {pattern.get('direction')}")
print(f"   Confidence: {pattern.get('confidence')}%")
print(f"   Matching days: {pattern.get('matching_days')}")

# Get projected open
nifty_data = global_data.get("data", {}).get("gift_nifty")
projected_open = nifty_data["last_close"] if nifty_data else 24000
print(f"   Projected open: {projected_open}")

trade_card = generate_trade_card(pattern, projected_open)
if trade_card.get("action") == "trade":
    t = trade_card["trade"]
    print(f"   Strategy: {t.get('type')}")
    print(f"   Legs:")
    for leg in t.get("legs", []):
        print(f"     {leg['action']} NIFTY {leg['strike']} {leg['option']} @ Rs.{leg['premium_est']}")
    print(f"   Net Cost: Rs.{t.get('net_cost_total')}")
    print(f"   Max Profit: Rs.{t.get('max_profit')}")
    print(f"   Max Loss: Rs.{t.get('max_loss')}")
    print(f"   Charges: Rs.{t.get('charges', {}).get('total', 0)}")
    print(f"   Net Profit: Rs.{t.get('net_max_profit')}")
    print(f"   Net Loss: Rs.{t.get('net_max_loss')}")
    print(f"   Expiry: {t.get('expiry_date')}")
    print(f"   R:R: {t.get('risk_reward')}:1")
    
    # Run quality filters
    filters = run_all_filters(global_data, pattern, trade_card)
    print(f"\n   Quality Filters: {filters['passed']}/{filters['total']} PASS")
    print(f"   Strength: {filters['strength']}")
    for k, f in filters["filters"].items():
        status = "PASS" if f["pass"] else "FAIL"
        print(f"     [{status}] {f['name']}")
else:
    print(f"   SKIPPED: {trade_card.get('reason')}")

print("\n" + "=" * 60)
print("VERIFICATION COMPLETE")
print("=" * 60)
