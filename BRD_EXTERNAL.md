# OPTIONS TYCOON — Business Requirements Document (BRD)

> **Version:** 4.0 | **Last Updated:** 2026-07-23
> **Status:** Live on Production | Strategy Validated (5 rounds)
> **URL:** https://options-tycoon.com
> **GitHub:** https://github.com/pativija96-tech/Options-Tycoon
> **Disclaimer:** This document describes a personal trading tool. Nothing here is financial advice.

---

## 1. VALIDATED STRATEGY

After five rounds of progressively harder validation (directional → range → flat-premium → grid search → tail risk), one strategy survived every test:

**±250pt Iron Condor, 100pt wings, every trading day. No directional signal. No pattern matching. Pure structural premium collection.**

| Metric | Value |
|--------|-------|
| Walk-forward EV (train vs test) | Rs.191 → Rs.192/trade (zero decay) |
| Block bootstrap (30 trades, 10K sims) | 69.4% profitable |
| Win rate | 86.5% |
| Avg win | Rs.1,019 |
| Avg loss | Rs.-2,941 |
| Max drawdown (5yr backtest) | Rs.44,860 |
| Max consecutive losses | 21 days |
| Slippage breakeven | Rs.191/trade |
| Annual return on Rs.10L | 4.7% |
| Dataset worst day | -5.93% (genuine crisis-magnitude) |

### What Was Retired

The pattern matcher, VIX-regime gating, directional signal, and bucket-matching system **add zero value** over simply selling wide premium every day. Five validation rounds proved this:

1. **Directional model:** 42.9% OOS (worse than coin flip)
2. **Range bucketing:** 77.2% OOS but BELOW 80.3% unconditional baseline (bucketing subtracts value)
3. **VIX gating:** Circular (VIX predicting volatility is tautological, not a discovery)
4. **Flat-premium IC:** Positive EV was an artifact of mixing high-vol premiums with low-vol containment
5. **High-vol only:** n=7 episodes (insufficient sample despite 72 days)

### What Survived

Simple, unfiltered, daily premium selling at wide strikes. The edge is the **volatility risk premium** (VRP) — implied vol systematically exceeds realized vol. This is documented, structural, and not data-mined.

---

## 2. LOAD-BEARING RISK RULES (Pre-Committed, Not Negotiable)

These rules are decided NOW, in calm conditions. They cannot be overridden during a drawdown.

### 2.1 Drawdown Protocol

| Condition | Rule |
|-----------|------|
| **Single-day loss > Rs.15,000** | **Full stop. Single-event circuit breaker — exceeds any normal IC max loss.** |
| 5 consecutive losses | Review but continue. System is functioning as designed. |
| 10 consecutive losses | Reduce to half size (1→0.5 lots). Continue taking signals. |
| 15 consecutive losses | Pause for 5 trading days. Review market regime. Resume at half size. |
| 21+ consecutive losses (backtest max) | Full stop. This exceeds historical worst case — something structural may have changed. |
| Rs.25,000 cumulative drawdown | Reduce to half size regardless of streak count. |
| Rs.45,000 cumulative drawdown (backtest max) | Full stop. |

**The rule:** During a losing streak, the system's rules override in-the-moment judgment. No "making it back" with bigger size. No skipping days. No emotional overrides.

**Note on tail events:** The backtest's worst day is -5.93%. NIFTY has done -13% (COVID 2020). A -13% day would trigger max loss on the IC regardless — the single-event circuit breaker exists for exactly this case. Defined-risk structure caps loss at wing width (Rs.~6,500 per lot), but the circuit breaker fires anyway to force a pause and reassessment.

### 2.2 Margin Risk

Exchange margin requirements can increase 2-3x during volatility spikes — exactly when this strategy is already losing. Pre-commit:
- Keep 2x estimated margin in account at all times (Rs.20,000 vs Rs.9,750 required)
- If margin requirement doubles, reduce position to fit — do not add capital mid-drawdown

### 2.3 Live Phase Sizing

Gate unlock does NOT mean full-size immediately:
- **Phase 1 (first 30 live trades):** Half size (0.5 lots). This validates real slippage vs model.
- **Phase 2 (if slippage < Rs.150):** Full size (1 lot).
- **Phase 3 (after 100 live trades):** Consider 2 lots if EV remains positive with real fills.

If real slippage > Rs.150/trade over 30 trades → **strategy is not viable at this strike distance. STOP.** Do not search for a sixth configuration to rescue it — the calm pre-commitment to stop is as important as the pre-commitment to continue during drawdowns. Finding out at Phase 1 that slippage kills the edge is a success of the validation process, not a failure of the system.

### 2.4 Margin Requirements (Verify Before Live)

Before going live, confirm with Zerodha/Kite:
- Actual SPAN margin for NIFTY weekly IC at ±250pt strikes, 100pt wings
- Historical margin requirement changes during vol spikes (how fast, how much)
- Whether margin can increase mid-position (forcing additional capital or forced exit)

Do not estimate — get the actual numbers from the broker.

---

## 3. SIGNAL ENGINE — SIMPLIFIED

The validated strategy requires no directional prediction. The signal engine simplifies to:

```
Daily (9:15 AM IST):
1. Get NIFTY opening price (yfinance or Kite)
2. Calculate strikes: Short CE = Open + 250, Short PE = Open - 250
3. Calculate wings: Long CE = Short CE + 100, Long PE = Short PE - 100
4. Estimate premium (Black-Scholes at current IV)
5. Verify: max_loss < 2% of capital
6. Generate trade card → display on live.html
```

**Removed:** Pattern matching, 5-year bucket lookup, directional signal, confidence scoring, most quality filters.

**Kept:**
- Risk cap check (2% per trade)
- VIX sanity check (don't trade if VIX > 40 — too chaotic for defined-risk spreads)
- Position sizing (half size in drawdown per Section 2.1)
- Signal history DB (all trades logged for ongoing validation)
- EOD resolution (actual NIFTY close → win/loss)

---

## 4. PAPER TRADING GATE (Revised)

### Why Still Paper Trade?

The backtest validates the strategy class. The paper phase validates:
1. **Real slippage** — do actual fills match modeled credit?
2. **Execution discipline** — can you actually take the trade every day, including during losing streaks?
3. **System reliability** — does the infrastructure work daily without manual intervention?

### Gate Metrics (30 trades)

| Metric | Threshold | Purpose |
|--------|-----------|---------|
| Trade Count | ≥ 30 | Minimum sample for live validation |
| Avg Credit Captured | Within Rs.150 of modeled | Validates slippage assumption |
| Max Drawdown | < Rs.25,000 | Within expected bounds |
| Consecutive Losses | < 15 | System functioning normally |
| Execution Rate | > 90% of trading days | Discipline validation |

### Gate Unlock ≠ Full Size

Gate unlock → Phase 1 (half size) → validate real fills → Phase 2 (full size). See Section 2.3.

---

## 5. PRODUCT ARCHITECTURE

### Two-Tier Access (Unchanged)

| Tier | Product | Access |
|------|---------|--------|
| Tier 1 — Public | DNA Intelligence + Practice Arena | Any signed-in user |
| Tier 2 — Restricted | Live Signal Engine | Founder only (allowlist + cookie) |

### Key Infrastructure

| Component | Status |
|-----------|--------|
| Railway + PostgreSQL | ✅ Live |
| Founder allowlist + HTTP-Only cookies | ✅ Deployed |
| Signal persistence (survives redeploy) | ✅ DB fallback |
| Automated DB backups | ✅ Script + API endpoint |
| Kite Connect (Zerodha) | ⚠️ Callback redirect URL needs fixing |
| EOD Resolution | ✅ Working (real NIFTY close) |
| Position management (Trail SL / Exit) | ✅ Working |

### API Endpoints (17 under /api/live/*)

All founder-gated. Full list in codebase (`routes/live.py`).

---

## 6. VALIDATION PROCESS (How We Got Here)

| Round | Hypothesis | Result | What Killed It |
|-------|-----------|--------|----------------|
| 1 | Directional prediction from overnight data | 42.9% OOS | Worse than coin flip |
| 2 | Range containment prediction via bucketing | 77.2% OOS | Below 80.3% unconditional baseline |
| 3 | Iron Condor with flat premium assumption | Rs.+1,308 EV | Flat premium mixed regimes incorrectly |
| 4 | Regime-specific premium (grid search) | High-vol: 15/15 positive | Only 7 episodes (n too small) |
| 5 | **Wide-strike daily IC (validated)** | **Rs.192 EV, zero decay, 69% MC** | **Survived** |

**What validated means:** Walk-forward stable, block-bootstrap profitable 69% of the time, tail events present in dataset, slippage buffer exists (Rs.191 breakeven > Rs.150 estimated real slippage).

**What validated does NOT mean:** Guaranteed profit. Risk-free. Tested against every possible market condition. The -5.93% worst day in dataset is large but not the worst NIFTY has ever done (COVID 2020: -13%). Defined-risk structure caps loss per trade regardless.

---

## 7. KNOWN LIMITATIONS (Stated Plainly)

1. **21 consecutive losses is real.** The backtest shows it happened. It will happen again. The protocol (Section 2.1) exists for this.
2. **Slippage margin is thin.** Rs.191 EV vs Rs.50-150 estimated slippage = it works, but barely. Phase 1 (half size) validates this before full commitment.
3. **4.7% annual return on Rs.10L is modest.** This isn't a get-rich system. It's a mechanical, low-effort income stream — like a recurring deposit with more variance.
4. **VRP isn't free money.** It's compensation for bearing tail risk. The defined-risk structure limits that risk to wing width per trade, but consecutive-loss clustering during regime shifts is the real danger.
5. **The dataset is 5 years, not forever.** Market microstructure can change (lot size changes, margin rules, electronic trading patterns). Annual recalibration against fresh data is required.

---

## 8. NEXT STEPS (In Order)

### Immediate
1. [x] Strategy validated through 5 rounds
2. [ ] Simplify signal engine (remove pattern matcher, implement daily IC generator)
3. [ ] Continue paper trading with new simplified engine
4. [ ] Fix Kite callback (developers.kite.trade redirect URL)

### During 30-Trade Paper Phase
5. [ ] Track real slippage vs modeled credit
6. [ ] Validate execution discipline (no missed days)
7. [ ] Run backup after each EOD

### After Gate Unlock
8. [ ] Phase 1: Half-size live trades (30 trades)
9. [ ] Validate: real slippage < Rs.150/trade?
10. [ ] Phase 2: Full size (if slippage validates)
11. [ ] Annual recalibration run

---

## 9. COST STRUCTURE & PURPOSE

### Why Run This System?

The point is **not** the Rs.1,400/month net profit. At Rs.10L capital, the per-trade edge (Rs.192) is modest and partially eroded by fixed infrastructure costs. The actual purpose:

1. **Discipline infrastructure** — a mechanical system that enforces pre-committed rules during drawdowns
2. **Validation pipeline** — a process that rigorously tests any strategy before real capital is risked
3. **Scale preparation** — the same strategy at Rs.50L+ capital nets Rs.7,000+/month with the same infrastructure cost
4. **Learning asset** — 5 rounds of validation, with failures documented, creates institutional knowledge for future strategy development

If the goal were solely Rs.1,400/month, a fixed deposit would be simpler. The goal is building a tested, disciplined, scalable trading infrastructure.

### Cost Reality

| Item | Monthly |
|------|---------|
| Railway hosting | $5-15 (~Rs.1,200) |
| Kite Connect API | Rs.2,000 (once live) |
| Total infrastructure | ~Rs.3,200/month |
| Expected monthly profit (if validated live, 1 lot) | ~Rs.3,900 |
| **Net after costs** | **~Rs.700/month on Rs.10L** |
| At Rs.50L capital (5 lots) | ~Rs.19,500 profit, ~Rs.16,300 net |

At minimum viable capital (Rs.10L), the system barely covers costs. It becomes meaningful at Rs.30L+. This is stated plainly so it doesn't become a reason to skip safeguards under pressure.

---

## 10. DNA INTELLIGENCE (Public Product — Unchanged)

The Trader DNA module (CSV upload → behavioral analysis → score tracking) remains:
- Separate from the Live Signal Engine
- Open to multiple users
- Revenue target: ₹499/month for premium features after 100 users
- No changes from previous BRD versions

---

*End of BRD v4.0. Five validation rounds completed. Strategy validated with explicit limitations and pre-committed risk rules. None of this is financial advice — it's a documentation of a personal tool's analysis process.*
