# OPTIONS TYCOON — Business Requirements Document (BRD)

> **Version:** 3.1 | **Last Updated:** 2026-07-23
> **Status:** Live on Production (Railway + PostgreSQL)
> **URL:** https://options-tycoon.com
> **GitHub:** https://github.com/pativija96-tech/Options-Tycoon

---

## 1. EXECUTIVE SUMMARY

Options Tycoon is two products under one roof:

1. **Trader DNA Intelligence** (public, multi-user) — Upload broker CSV → Get behavioral analysis → Track improvement weekly
2. **Live Signal Engine** (restricted, founder-only) — AI-powered daily NIFTY signals with 30-trade paper gate before live trading

**Target Market:** Indian retail options traders (Zerodha/Groww/Angel One)
**Stage:** 5 paper trades completed, 25 remaining before gate evaluation
**Critical Finding:** Walk-forward validation shows 42.9% OOS win rate — pattern matcher needs tuning before gate unlock is meaningful

---

## 2. ACCESS CONTROL (Two-Tier Model)

| Tier | Product | Access | Auth |
|------|---------|--------|------|
| Tier 1 — Public | DNA Intelligence, Practice Arena | Any signed-in user | Google OAuth |
| Tier 2 — Restricted | Live Signal Engine | Founder only | Cookie + allowlist |

**Implementation:**
- Router-level `require_founder` dependency on all `/api/live/*` routes
- HTTP-Only signed session cookie (set on Google auth)
- `FOUNDER_ALLOWED_EMAILS` env var (single entry)
- X-User-Id header accepted as fallback (same-origin only, temporary)
- `/api/live/kite-callback` exempt (Zerodha redirect has no session)
- "Live Signals" nav link hidden from non-founder sessions

---

## 3. LIVE SIGNAL ENGINE — How It Works

### Daily Flow

```
Morning (9:00 AM IST / 11:30 AM PH):
  Generate Signal → Review → Execute (paper trade logged as 'open')

During Market Hours:
  Open Positions panel shows live P&L + suggestions (Trail SL / Exit Now)

After Market Close (3:30 PM IST / 6:00 PM PH):
  Run EOD → resolves open trades using actual NIFTY close → win/loss recorded
```

### Signal Generation Pipeline

```
1. Fetch Global Data (yfinance) → S&P 500, VIX, DXY, Gift Nifty
2. Pattern Match (5-year NIFTY history, min 20 matches, Wilson CI)
3. Strategy Selection (27-combo matrix: direction × confidence × volatility)
4. Trade Construction (Black-Scholes premiums, 2% risk cap, Zerodha charges)
5. 7 Quality Filters → Position Sizing (Full/Reduced/Minimum)
6. Save to signal_history DB (append-only, survives redeploys)
7. Telegram notification (founder's private chat)
```

### Strategies Generated

| Condition | Strategy |
|-----------|----------|
| Bullish + high confidence | Bull Call Spread (wide) |
| Bullish + moderate/low | Bull Call Spread (small) |
| Bearish + high confidence | Bear Put Spread (wide) |
| Bearish + moderate/low | Bear Put Spread (small) |
| Neutral / low confidence | Iron Condor |
| Neutral + high volatility | Long Straddle |

### 7 Quality Filters

1. Historical Confidence (>70% with 20+ matches)
2. Global Alignment (2+ of US/VIX/DXY agree)
3. Gift Nifty Confirmation (pre-market direction)
4. Risk/Reward Ratio (minimum 2:1)
5. Liquidity/Volatility (VIX 10-40 range)
6. No Event Conflict (no RBI/Budget/Election)
7. FII Flow Alignment (not against institutional flow)

### 30-Trade Unlock Gate (7 Metrics)

| Metric | Threshold | Current |
|--------|-----------|---------|
| Trade Count | ≥ 30 | 5/30 FAIL |
| Win Rate | > 50% | 40% FAIL |
| Profit Factor | > 1.5 | 1.08 FAIL |
| Avg Win/Loss | > 1.0 | 1.62 PASS |
| Max Drawdown | < 15% | 0.8% PASS |
| Consec Losses | < 5 | 3 PASS |
| Expectancy | > Rs.0 | Rs.124 PASS |

**CRITICAL:** Gate unlock also requires walk-forward validation >50% OOS (currently FAILING at 42.9%).

---

## 4. HARD BLOCKERS ON LIVE TRADING

The gate passing (30 trades + 7 metrics) is necessary but NOT sufficient. These must ALSO pass:

| Blocker | Status | Why |
|---------|--------|-----|
| Walk-forward >50% OOS win rate | ❌ FAILING (42.9%) | Pattern matching has no proven edge on unseen data |
| Confidence calibration (stated % ≈ actual %) | ⏳ Needs 15+ trades | Don't trust sizing if confidence scores are miscalibrated |
| Intraday SL simulation active | ⏳ Not built | Paper EOD-only resolution doesn't match real intraday behavior |

A 30-trade pass on a system with no validated edge is statistical noise. The gate cannot unlock until these are resolved.

---

## 5. TECHNICAL ARCHITECTURE

### Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+ / FastAPI |
| Frontend | Vanilla HTML/JS/CSS |
| Database | PostgreSQL (Railway) + SQLite (local) |
| Compute | SciPy, yfinance, pandas, numpy |
| Broker | Kite Connect (founder's Zerodha) |
| Auth | Google OAuth → HTTP-Only cookies + allowlist |
| Hosting | Railway.app (Singapore) + Cloudflare CDN |

### Database (15 tables)

Key tables for Live Signal Engine:
- `signal_history` — every generated signal (append-only)
- `live_trades` — paper/live trade execution records
- `users` — Google Sign-In profiles

### API Endpoints (17 under /api/live/*)

All founder-gated except `/kite-callback`:

| Method | Path | Purpose |
|--------|------|---------|
| GET | /signal | Today's trade card (file → DB fallback) |
| POST | /generate-signal | Trigger signal generation |
| GET | /gate-status | 7-metric unlock gate |
| POST | /paper-execute | Log paper trade (1/day) |
| GET | /my-trades | Trade history |
| GET | /open-positions | Live P&L + suggestions |
| POST | /exit-trade | Manual exit |
| POST | /trail-sl | Update stop-loss |
| POST | /run-eod | EOD resolution |
| GET | /eod-report | EOD report |
| GET | /auth-status | Kite state |
| GET | /kite-login | Zerodha OAuth redirect |
| GET | /kite-callback | OAuth callback (exempt from allowlist) |
| GET | /live-prices | Kite LTP |
| GET | /settings | Capital/risk params |
| GET | /signal-history | Historical signals |
| GET | /signal-stats | Aggregate stats |
| POST | /run-backup | Database backup |

---

## 6. SIGNAL ACCURACY IMPROVEMENT PLAN

All items must pass BEFORE gate unlock authorizes live capital.

| # | Item | Status | Deadline |
|---|------|--------|----------|
| 1 | Min matches raised to 20 + Wilson CI | ✅ Done | — |
| 2 | Walk-forward validation (train 3yr, test 1yr) | ✅ Built — **FAILING** (42.9% OOS) | **HARD BLOCKER** |
| 3 | Per-filter predictive value analysis | ✅ Built — needs 10+ resolved trades | After trade #10 |
| 4 | Intraday SL simulation in EOD | ❌ Not built | Before trade #15 |
| 5 | Calibration chart (confidence vs actual win rate) | ❌ Needs 15+ trades | Before trade #20 |
| 6 | Monthly recalibration | ❌ Not built | Before gate unlock |
| 7 | **Fix pattern matcher to show >50% OOS** | ❌ **THE CRITICAL TASK** | **Before gate unlock** |

### What "Fix Pattern Matcher" Means

The current approach (bucket yesterday's NIFTY move → predict today's direction) produces 42.9% out-of-sample accuracy. Options to improve:
- Add multi-factor conditions (combine US + VIX + DXY buckets simultaneously)
- Use a different matching algorithm (nearest-neighbor, weighted by recency)
- Expand the dataset (10yr instead of 5yr)
- Add market microstructure features (open-to-close vs close-to-close)
- Accept that simple pattern matching may not produce an edge → switch to premium-selling strategies that don't require directional prediction

---

## 7. CURRENT STATUS (2026-07-23)

### Production Health

| Component | Status |
|-----------|--------|
| Signal generation | ✅ Working (Iron Condor today) |
| Paper trade execution | ✅ Working (5 trades logged) |
| EOD resolution | ✅ Working (real NIFTY close) |
| Signal persistence (survives redeploy) | ✅ Fixed (DB fallback) |
| Founder allowlist | ✅ Active |
| DB backups | ✅ Working (29 rows backed up) |
| Kite OAuth | ⚠️ Callback redirect URL needs fixing on developers.kite.trade |

### Trading Performance

- **Trades:** 5/30
- **Win Rate:** 40% (2W / 3L)
- **P&L:** Rs.+124
- **Gates Passed:** 4/7
- **Status:** LOCKED (25 more trades + walk-forward fix needed)

### Known Issues

| # | Issue | Impact | Priority |
|---|-------|--------|----------|
| 1 | Walk-forward 42.9% OOS | No proven edge — gate unlock blocked | **P0 BLOCKER** |
| 2 | 4/7 vs 5 PASS filter display mismatch | Cosmetic | P2 |
| 3 | Run EOD button needs confirm dialog fix | UX — use console as workaround | P2 |
| 4 | Kite callback "Invalid session" | Redirect URL config on Kite dashboard | Owner action |

---

## 8. REVENUE MODEL (DNA Intelligence Only)

Live Signal Engine has no monetization and is not offered to others.

- **Phase 1 (Now):** Free for first 100 DNA users
- **Phase 2 (After 100):** ₹499/month or ₹2999/year for premium DNA features
- **Phase 3:** Enterprise (prop firms, team reports)

---

## 9. RISK REGISTER

| Risk | Mitigation |
|------|-----------|
| Live Signal Engine accessed by non-founder | Allowlist + cookies + same-origin check |
| Pattern matcher has no edge (proven by walk-forward) | Gate unlock blocked until fixed |
| DB data loss | Automated backup script + API endpoint |
| Signal lost on Railway redeploy | Falls back to signal_history DB |
| SEBI RA/IA regulatory exposure | Founder-only, no monetization, legal review pending |

---

## 10. NEXT STEPS (Priority Order)

### Immediate (This Week)
1. [ ] **Fix pattern matcher** — the only P0 blocker. Explore multi-factor matching, recency weighting, or strategy pivot
2. [ ] Run backup daily after EOD
3. [ ] Fix Kite redirect URL (owner: developers.kite.trade)

### Before Trade #15
4. [ ] Intraday SL simulation
5. [ ] Fix filter count display bug
6. [ ] Fix Run EOD button UX
7. [ ] DPDPA consent checkboxes (DNA module)

### Before Gate Unlock
8. [ ] Walk-forward must show >50% OOS
9. [ ] Calibration chart confirms confidence accuracy
10. [ ] Monthly recalibration run completed
11. [ ] All Section 6 criteria pass

---

*End of BRD v3.1. The walk-forward failure (42.9% OOS) is the single most important thing to fix. Everything else is operational polish.*
