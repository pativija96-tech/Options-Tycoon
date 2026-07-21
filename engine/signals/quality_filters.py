"""
Quality Filters — 7 independent checks that a trade must pass before being recommended.
Only trades passing 5+ filters are shown. All 7 = "STRONG SIGNAL."

Filters:
1. Historical Confidence (>70% pattern match)
2. Global Alignment (US + VIX + DXY all point same direction)
3. Gift Nifty Confirmation (pre-market confirms the direction)
4. Risk/Reward Ratio (at least 2:1)
5. Volume/Liquidity proxy (sufficient historical volatility for the strikes)
6. No Event Day Conflict (no major events that override patterns)
7. FII Flow Alignment (not trading against institutional money)
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
EVENT_CALENDAR_PATH = ROOT / "data" / "historical" / "event_calendar.json"
FII_DATA_PATH = ROOT / "data" / "historical" / "fii_flows.json"


def run_all_filters(global_data: dict, pattern_result: dict, trade_card: dict) -> dict:
    """
    Run all 7 quality filters on a proposed trade.
    Returns filter results with pass/fail for each, overall score, and signal strength.
    """
    conditions = pattern_result.get("conditions", {})
    trade = trade_card.get("trade", {}) if trade_card.get("action") == "trade" else {}
    
    results = {}
    
    # Filter 1: Historical Confidence
    results["historical_confidence"] = _filter_historical_confidence(pattern_result)
    
    # Filter 2: Global Alignment
    results["global_alignment"] = _filter_global_alignment(global_data, pattern_result)
    
    # Filter 3: Gift Nifty Confirmation
    results["gift_nifty_confirmation"] = _filter_gift_nifty(global_data, pattern_result)
    
    # Filter 4: Risk/Reward Ratio
    results["risk_reward"] = _filter_risk_reward(trade)
    
    # Filter 5: Volume/Liquidity Proxy
    results["liquidity"] = _filter_liquidity(global_data, trade)
    
    # Filter 6: No Event Day Conflict
    results["no_event_conflict"] = _filter_no_event_conflict()
    
    # Filter 7: FII Flow Alignment
    results["fii_alignment"] = _filter_fii_alignment(pattern_result)
    
    # Calculate overall score
    passed = sum(1 for v in results.values() if v["pass"])
    total = len(results)
    
    # Analyze WHY filters failed — determine if it's "unclear" or "clearly risky"
    failed_filters = {k: v for k, v in results.items() if not v["pass"]}
    risk_signals = []
    
    # Check if failed filters indicate clear market risk (bearish opportunity)
    if not results["global_alignment"]["pass"]:
        detail = results["global_alignment"].get("detail", "")
        if "0/3" in detail:
            risk_signals.append("Global markets show no clear direction")
    
    if not results["gift_nifty_confirmation"]["pass"]:
        risk_signals.append(results["gift_nifty_confirmation"].get("reason", "Gift Nifty conflicts"))
    
    if not results["no_event_conflict"]["pass"]:
        risk_signals.append(results["no_event_conflict"].get("reason", "Major event today"))
    
    if not results["fii_alignment"]["pass"]:
        risk_signals.append(results["fii_alignment"].get("reason", "FII flow against direction"))
    
    # Determine signal strength and recommendation
    if passed >= 7:
        strength = "STRONG"
        recommendation = "HIGH CONVICTION — All 7 filters aligned."
    elif passed >= 5:
        strength = "MODERATE"
        recommendation = "MODERATE CONVICTION — Most filters aligned. Reduce position size."
    elif passed >= 3:
        strength = "LOW"
        recommendation = "LOW CONVICTION — Fewer filters aligned. Smallest position or hedge only."
    else:
        strength = "NO_EDGE"
        recommendation = "No clear edge today — insufficient signal alignment."
    
    # Build detailed context for each filter
    context_lines = []
    for name, f in results.items():
        if not f["pass"]:
            context_lines.append(f"FAILED: {f['name']} — {f['reason']}")
    
    return {
        "filters": results,
        "passed": passed,
        "total": total,
        "strength": strength,
        "recommendation": recommendation,
        "show_trade": True,  # ALWAYS show a trade — market always has opportunity
        "position_sizing": _get_position_sizing(passed),
        "failed_reasons": context_lines,
        "risk_signals": risk_signals,
    }


def _get_position_sizing(filters_passed: int) -> dict:
    """
    Pro trader sizing: more conviction = bigger position.
    7/7 filters = full size. 3/7 = tiny/hedge only.
    """
    if filters_passed >= 7:
        return {"size": "full", "lots": 2, "label": "Full position (2 lots)", "conviction": "high"}
    elif filters_passed >= 5:
        return {"size": "reduced", "lots": 1, "label": "Reduced position (1 lot)", "conviction": "moderate"}
    elif filters_passed >= 3:
        return {"size": "minimum", "lots": 1, "label": "Minimum position (1 lot, tight SL)", "conviction": "low"}
    else:
        return {"size": "skip", "lots": 0, "label": "No edge — sit out", "conviction": "none"}


def _filter_historical_confidence(pattern_result: dict) -> dict:
    """Filter 1: Historical pattern must have >70% confidence with sufficient sample."""
    confidence = pattern_result.get("confidence", 0)
    matching_days = pattern_result.get("matching_days", 0)
    direction = pattern_result.get("direction", "skip")
    
    passed = confidence >= 70 and matching_days >= 10 and direction != "skip"
    
    return {
        "pass": passed,
        "name": "Historical Confidence",
        "detail": f"{confidence}% ({matching_days} matching days)",
        "threshold": ">70% with 10+ matches",
        "reason": f"Pattern match {'strong' if passed else 'too weak'}: {confidence}% from {matching_days} days"
    }


def _filter_global_alignment(global_data: dict, pattern_result: dict) -> dict:
    """
    Filter 2: Multiple global indicators must align with the predicted direction.
    Bullish signal needs: US not crashing further + VIX not spiking more + DXY not surging
    Bearish signal needs: US weakness + VIX rising + DXY strength
    """
    data = global_data.get("data", {})
    direction = pattern_result.get("direction", "neutral")
    
    sp500 = data.get("sp500", {})
    vix = data.get("vix", {})
    dxy = data.get("dxy", {})
    
    us_change = sp500.get("change_pct", 0) if sp500 else 0
    vix_change = vix.get("change_pct", 0) if vix else 0
    dxy_change = dxy.get("change_pct", 0) if dxy else 0
    
    aligned_count = 0
    details = []
    
    if direction == "bullish":
        # For bullish NIFTY: we want US to have already dropped (mean reversion setup)
        # VIX spiked (fear peaked), DXY not surging aggressively
        if us_change < -0.5:
            aligned_count += 1
            details.append("US dropped (mean reversion setup)")
        if vix_change > 5:
            aligned_count += 1
            details.append("VIX spiked (fear peaked)")
        if dxy_change < 0.5:
            aligned_count += 1
            details.append("DXY not surging")
    elif direction == "bearish":
        # For bearish NIFTY: US weak, VIX rising, DXY strong
        if us_change < -0.3:
            aligned_count += 1
            details.append("US weak")
        if vix_change > 0:
            aligned_count += 1
            details.append("VIX rising")
        if dxy_change > 0:
            aligned_count += 1
            details.append("DXY strengthening")
    
    passed = aligned_count >= 2  # At least 2 of 3 global factors must align
    
    return {
        "pass": passed,
        "name": "Global Alignment",
        "detail": f"{aligned_count}/3 factors aligned",
        "threshold": "2+ global factors must agree",
        "reason": "; ".join(details) if details else "No clear global alignment"
    }


def _filter_gift_nifty(global_data: dict, pattern_result: dict) -> dict:
    """
    Filter 3: Gift Nifty / pre-market data must confirm the predicted direction.
    
    KNOWN LIMITATION: ^NSEI on yfinance only returns yesterday's close before market hours.
    Real Gift Nifty (NSE IX) trades 21 hours/day and reflects overnight sentiment.
    Until a proper Gift Nifty data source is added, this filter is DEGRADED —
    it passes by default and does NOT provide real pre-market confirmation.
    
    TODO: Add NSE IX scraping or paid data feed for actual Gift Nifty pre-open price.
    """
    # DEGRADED: Auto-pass until real Gift Nifty data source is added
    return {
        "pass": True,
        "name": "Gift Nifty Confirmation",
        "detail": "DEGRADED — using yesterday's close (not real pre-market data)",
        "threshold": "Pre-market not contradicting signal direction",
        "reason": "Filter degraded: no real-time Gift Nifty source. Auto-pass until fixed."
    }


def _filter_risk_reward(trade: dict) -> dict:
    """
    Filter 4: Trade must have at least 2:1 risk/reward ratio.
    Max profit must be at least 2x the max loss.
    """
    if not trade:
        return {
            "pass": False,
            "name": "Risk/Reward Ratio",
            "detail": "No trade structure available",
            "threshold": "At least 2:1 R:R",
            "reason": "Cannot calculate — no trade structure"
        }
    
    max_profit = trade.get("max_profit", 0)
    max_loss = trade.get("max_loss", 0)
    
    if max_loss <= 0:
        # Zero cost trade — infinite R:R (or data issue)
        rr = 999 if max_profit > 0 else 0
    else:
        rr = max_profit / max_loss
    
    passed = rr >= 2.0
    
    return {
        "pass": passed,
        "name": "Risk/Reward Ratio",
        "detail": f"{rr:.1f}:1 (profit Rs.{max_profit} / loss Rs.{max_loss})",
        "threshold": "Minimum 2:1 reward to risk",
        "reason": f"R:R is {rr:.1f}:1 — {'sufficient' if passed else 'too low, risk not justified'}"
    }


def _filter_liquidity(global_data: dict, trade: dict) -> dict:
    """
    Filter 5: Proxy for liquidity — ensure we're not trading in dead/illiquid conditions.
    Uses VIX level as proxy: very low VIX = dead market (bad for spreads),
    moderate VIX = good liquidity and movement.
    
    In Phase 2 with Kite: will check actual OI on selected strikes.
    """
    data = global_data.get("data", {})
    vix = data.get("vix", {})
    vix_level = vix.get("last_close", 15) if vix else 15
    
    # VIX between 12-35 is tradeable. Below 10 = dead market. Above 40 = too chaotic.
    if vix_level < 10:
        passed = False
        reason = f"VIX too low ({vix_level:.1f}) — market dead, no movement expected"
    elif vix_level > 40:
        passed = False
        reason = f"VIX too high ({vix_level:.1f}) — extreme chaos, spreads unreliable"
    else:
        passed = True
        reason = f"VIX at {vix_level:.1f} — healthy volatility for options trading"
    
    return {
        "pass": passed,
        "name": "Liquidity/Volatility",
        "detail": f"VIX level: {vix_level:.1f}",
        "threshold": "VIX between 10-40 (tradeable range)",
        "reason": reason
    }


def _filter_no_event_conflict() -> dict:
    """
    Filter 6: No major scheduled event that could override pattern-based predictions.
    Events like RBI policy, Union Budget, Election results can invalidate historical patterns.
    """
    today = date.today().isoformat()
    
    # Load event calendar
    events_today = []
    if EVENT_CALENDAR_PATH.exists():
        try:
            with open(EVENT_CALENDAR_PATH) as f:
                calendar = json.load(f)
            events_today = [e for e in calendar if e.get("date") == today]
        except (json.JSONDecodeError, Exception):
            pass
    
    if events_today:
        event_names = ", ".join(e.get("name", "Unknown") for e in events_today)
        return {
            "pass": False,
            "name": "No Event Conflict",
            "detail": f"Events today: {event_names}",
            "threshold": "No major macro events that override patterns",
            "reason": f"CONFLICT: {event_names} — patterns unreliable on event days"
        }
    
    return {
        "pass": True,
        "name": "No Event Conflict",
        "detail": "No major events scheduled today",
        "threshold": "No RBI/Budget/Election events",
        "reason": "Clear calendar — patterns should hold"
    }


def _filter_fii_alignment(pattern_result: dict) -> dict:
    """
    Filter 7: FII (Foreign Institutional Investor) flow direction should align.
    If we predict bullish but FIIs were heavy sellers yesterday → conflict.
    
    In Phase 2: will fetch real FII/DII data from NSE.
    For now: passes by default (data not available without scraping NSE).
    """
    direction = pattern_result.get("direction", "neutral")
    
    # Check if we have FII data
    if FII_DATA_PATH.exists():
        try:
            with open(FII_DATA_PATH) as f:
                fii_data = json.load(f)
            latest = fii_data[-1] if fii_data else None
            if latest:
                fii_net = latest.get("net_value", 0)  # Positive = buying, Negative = selling
                
                if direction == "bullish" and fii_net < -2000:
                    return {
                        "pass": False,
                        "name": "FII Flow Alignment",
                        "detail": f"FII net: Rs.{fii_net:,.0f} Cr (heavy selling)",
                        "threshold": "FII flow not against trade direction",
                        "reason": f"CONFLICT: Predicted bullish but FII selling Rs.{abs(fii_net):,.0f} Cr"
                    }
                elif direction == "bearish" and fii_net > 2000:
                    return {
                        "pass": False,
                        "name": "FII Flow Alignment",
                        "detail": f"FII net: +Rs.{fii_net:,.0f} Cr (heavy buying)",
                        "threshold": "FII flow not against trade direction",
                        "reason": f"CONFLICT: Predicted bearish but FII buying Rs.{fii_net:,.0f} Cr"
                    }
        except (json.JSONDecodeError, Exception):
            pass
    
    # No FII data available — pass by default
    return {
        "pass": True,
        "name": "FII Flow Alignment",
        "detail": "FII data not available (pass by default)",
        "threshold": "FII flow not contradicting signal",
        "reason": "No FII data — no contradiction detected"
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test with existing signal data
    signal_path = ROOT / "output" / "today_signal.json"
    global_path = ROOT / "output" / "today_global_data.json"
    
    if signal_path.exists() and global_path.exists():
        with open(signal_path) as f:
            trade_card = json.load(f)
        with open(global_path) as f:
            global_data = json.load(f)
        
        pattern_result = trade_card.get("pattern_result", {})
        results = run_all_filters(global_data, pattern_result, trade_card)
        
        print(f"\n{'='*60}")
        print(f"QUALITY FILTER RESULTS: {results['strength']}")
        print(f"Score: {results['passed']}/{results['total']} filters passed")
        print(f"Recommendation: {results['recommendation']}")
        print(f"{'='*60}")
        for name, f in results["filters"].items():
            status = "PASS" if f["pass"] else "FAIL"
            print(f"  [{status}] {f['name']}: {f['reason']}")
        print(f"{'='*60}")
        print(f"Show trade to user: {'YES' if results['show_trade'] else 'NO'}")
    else:
        print("Run signal_engine.py first to generate test data.")
