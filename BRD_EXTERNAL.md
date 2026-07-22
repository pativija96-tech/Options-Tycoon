# OPTIONS TYCOON — Business Requirements Document (BRD)

> **Version:** 3.0 | **Last Updated:** 2026-07-21
> **Status:** Live on Production (Railway + PostgreSQL)
> **URL:** https://options-tycoon.com
> **GitHub:** https://github.com/pativija96-tech/Options-Tycoon
> **Prepared for:** KIRO build/implementation
> **Change from v2.0:** Splits the product into two access tiers — see Section 0.

---

## 0. WHAT CHANGED IN THIS VERSION (READ FIRST)

v2.0 described one product with two modules at the same access level — anyone with the link could reach both DNA Intelligence and the Live Signal Engine. That's no longer the intended scope.

The product is now **two tiers** with different audiences and different risk profiles:

| Tier | Product | Audience | Why |
|------|---------|----------|-----|
| **Tier 1 — Public** | Trader DNA Intelligence | Anyone with the link, multi-user | Retrospective analysis of a user's own trade history. No advice generated, no third party directed to take action. Low regulatory exposure. |
| **Tier 2 — Restricted** | Live Signal Engine | Founder only (single allowlisted account) | Generates specific, actionable options trade signals (strikes, sizing, entries). Once a second person receives and acts on those signals, the relationship resembles investment research/advisory activity, regulated in India (SEBI RA/IA framework). Until reviewed with a lawyer, this stays a personal trading tool. |

**This is the single most important build requirement:** the Live Signal Engine must be technically inaccessible to anyone but the founder, not just "not advertised." A public URL that works for anyone who signs in does not satisfy this — see Section 4.

---

## 1. EXECUTIVE SUMMARY

Options Tycoon is two things under one roof:

1. **Trader DNA Intelligence** (public product) — Upload broker CSV → Get behavioral analysis → Track improvement weekly. Built for multi-user growth and eventual monetization.
2. **Live Signal Engine** (personal tool, access-restricted) — AI-powered daily NIFTY trade signals with pattern matching, quality filters, paper trading with EOD resolution, and a 30-trade unlock gate to live trading via the founder's own Zerodha account. Not offered to other users.

**Target Market (Tier 1 only):** Retail options traders (NSE/BSE) — primarily Zerodha/Groww/Angel One users
**Monetization (Tier 1 only):** Free for first 100 users → ₹499/month or ₹2999/year for premium DNA features
**Live Signal Engine:** No monetization, no external users, no beta rollout until regulatory review is complete
**Stage:** Live in production; DNA module open to multi-user testing; Live Signal Engine restricted to founder's account only

---

## 2. PRODUCT ARCHITECTURE

### User Flows (Two Tiers, Different Access Rules)

```
TIER 1 — DNA TRACKING (Public, Multi-User, Retention Product)
Landing → Upload CSV → Sign-In Gate → DNA Report → Dashboard → Weekly Upload Loop
(Open to anyone with the link. No allowlist.)

TIER 2 — LIVE SIGNAL ENGINE (Restricted, Founder-Only, Personal Trading Tool)
Dashboard (founder session only) → Live Signals → Generate Signal → Execute (Paper) → EOD Resolution → Gate Metrics
                                                                                    ↓
                                                                    30 Trades + 7 Metrics Pass
                                                                                    ↓
                                                                UNLOCK LIVE TRADING (founder's own Zerodha only)

Any non-founder account that reaches a /api/live/* route or live.html receives a 403 / redirect.
```

### Pages & Roles

| Page | Purpose | Auth | Access Tier |
|------|---------|------|-------------|
| `/` (landing) | Marketing hook | No | Public |
| `/static/upload-free.html` | Upload broker CSV | No | Public |
| `/static/signin.html` | Google Sign-In gate | No | Public |
| `/static/report.html` | DNA Report reveal | Yes | Public (any signed-in user) |
| `/static/dashboard.html` | HOME — DNA score, trends | Yes | Public — Live Signals nav link only rendered for founder |
| `/static/live.html` | LIVE SIGNALS — trades, positions, EOD | Yes + allowlist | **Restricted — founder only** |
| `/static/index.html` | Practice Arena ($10K sim) | Yes | Public |
| `/static/behavioral.html` | Detailed behavioral metrics | Yes | Public |
| `/static/timemachine.html` | Historical replay mode | Yes | Public |

---

## 3. FEATURE INVENTORY (Current State)

### Module A: Live Signal Engine (RESTRICTED — Founder Only)

Access requirement: gated behind founder-allowlist check (Section 4). None are multi-user features.

| # | Feature | Status | Description |
|---|---------|--------|-------------|
| A1 | Morning Signal Generation | ✅ Live | Fetches overnight US/VIX/DXY data, runs 5-year NIFTY pattern matching |
| A2 | Strategy Matrix (27 combos) | ✅ Live | Maps (direction × confidence × volatility) → strategy type |
| A3 | 7 Quality Filters | ✅ Live | Historical confidence, global alignment, Gift Nifty, R:R, liquidity, event, FII |
| A4 | Position Sizing | ✅ Live | Full/Reduced/Minimum based on filter score |
| A5 | Iron Condor Builder | ✅ Live | 4-leg neutral strategy with dynamic strike selection |
| A6 | Paper Trade Execution | ✅ Live | Founder only, one trade per day, saved to PostgreSQL |
| A7 | EOD Resolution | ✅ Live | Fetches real NIFTY close, resolves open trades with actual P&L |
| A8 | 7-Metric Unlock Gate | ✅ Live | Win rate, profit factor, drawdown, expectancy — all 7 must pass |
| A9 | Open Positions Panel | ✅ Live | Current P&L, exit suggestions, trail SL, manual exit |
| A10 | Signal History (DB) | ✅ Live | Every signal saved to PostgreSQL (append-only, model learning) |
| A11 | Zerodha Kite OAuth | ✅ Live | Founder's own login, access token, live price fetch |
| A12 | Live Prices (Kite API) | ✅ Live | Fetches LTP for signal strikes when authenticated |
| A13 | Stock Scanner (Watchlist) | ✅ Live | Scans 10 stocks for secondary signals with earnings catalysts |
| A14 | Telegram Notifications | ✅ Live | Sends daily signal to founder's private chat (not broadcast) |
| A15 | Trade Log (founder) | ✅ Live | Full history with win/loss, P&L, strategy breakdown |
| A16 | Founder allowlist middleware | ❌ P0 — build required | Every /api/live/* route checks session email against allowlist |
| A17 | Conditional nav rendering | ❌ P0 — build required | "Live Signals" link only renders for founder session |
| A18 | HTTP-Only session cookies | ❌ P0 — build required | Replace localStorage auth with server-side secure cookies |

### Module B: Trader DNA Intelligence (PUBLIC — Multi-User)

| # | Feature | Status | Description |
|---|---------|--------|-------------|
| B1 | Broker CSV Parsing | ✅ Live | Zerodha, Groww, Angel One format detection |
| B2 | DNA Score (0-100) | ✅ Live | Composite behavioral score |
| B3 | Pattern Detection | ✅ Live | Revenge, overconfidence, impulse, disposition bias |
| B4 | Behavioral Cost (₹) | ✅ Live | Quantifies ₹ lost due to undisciplined trading |
| B5 | Fix One Thing | ✅ Live | Single worst pattern → weekly focus |
| B6 | Upload History | ✅ Live | Score progression tracking |
| B7 | Google Sign-In | ✅ Live | 1-click auth, email capture |
| B8 | Dashboard (Score Trends) | ✅ Live | DNA score over time, upload CTA |

### Module C: Practice Arena (PUBLIC — Simulator)

| # | Feature | Status | Description |
|---|---------|--------|-------------|
| C1 | Virtual Portfolio ($10K) | ✅ Built | Game-over at $0, no reset |
| C2 | Options Chain + Greeks | ✅ Built | Black-Scholes, 10 mock tickers |
| C3 | Strategy Builder (1-4 legs) | ✅ Built | Custom combos with P&L visualization |
| C4 | Behavioral Metrics (Progressive) | ✅ Built | Phase A→D unlock |
| C5 | Risk Guards | ✅ Built | 5% gate, IV crush, penalty multiplier |
| C6 | Settlement Engine | ✅ Built | Auto-close expired positions |
| C7 | Time Machine | 🔧 Partial | Historical replay |
| C8 | Compare Mode | 🔧 Partial | Sim vs real comparison |

---

## 4. ACCESS CONTROL REQUIREMENT (P0 — BUILD FIRST)

This is the load-bearing requirement of v3.0. Build and verify before any further Live Signal Engine work. **Allowlist and HTTP-Only cookies ship together as one P0 unit** — the allowlist's security model depends on session integrity.

### 4.1 Founder Allowlist

```
FOUNDER_ALLOWED_EMAILS = ["<founder's Google account email>"]
```

Stored as a Railway environment variable, not hardcoded. Single entry. No multi-entry admin UI.

### 4.2 Implementation

#### 4.2.1 Kite OAuth Flow (Special Handling)

`/api/live/kite-login` carries the founder allowlist check and issues a signed, single-use state parameter. `/api/live/kite-callback` validates that state instead of re-checking identity. A valid callback can only descend from an already-gated `kite-login` call — non-founders cannot reach it with a valid state.

#### 4.2.2 All Other Routes (15 endpoints)

Standard middleware dependency that:
1. Confirms valid Google Sign-In session (HTTP-Only cookie, not localStorage)
2. Confirms session email is in `FOUNDER_ALLOWED_EMAILS`
3. If either check fails: return 403 Forbidden (generic message — don't leak whether the route exists vs. wrong account)

### 4.3 HTTP-Only Session Cookies (Bundled with Allowlist)

Replace current localStorage-based auth with server-side HTTP-Only secure cookies:
- `Set-Cookie: session=<signed_token>; HttpOnly; Secure; SameSite=Strict; Path=/`
- JavaScript cannot read or modify the session token
- Eliminates XSS session forgery — the allowlist check is only as strong as the session mechanism

### 4.4 Frontend Enforcement

- `/static/live.html` redirects to dashboard if session email doesn't match allowlist
- "Live Signals" nav item on dashboard doesn't render at all for non-founder sessions (not disabled, not hidden — absent from DOM)

### 4.5 What Does NOT Need Gating

- DNA Intelligence (Module B) — open to any signed-in user
- Practice Arena (Module C) — open to any signed-in user

### 4.6 Endpoint Inventory (Final Count: 17)

After removing dead endpoints (`/trade-log` superseded by `/my-trades`, `/admin/all-trades` no purpose in single-user model):

- **15 standard-gated routes** (allowlist middleware)
- **2 state-parameter routes** (`kite-login`, `kite-callback` per 4.2.1)
- **Total: 17 endpoints** under `/api/live/*`

### 4.7 Verification Checklist

- [ ] Sign in with non-founder Google account → `/static/live.html` redirects away
- [ ] Non-founder session → no "Live Signals" nav link visible
- [ ] Non-founder session → all 17 `/api/live/*` endpoints return 403
- [ ] Founder account → full unimpeded access to all Live Signal Engine features
- [ ] DNA Intelligence and Practice Arena unaffected for non-founder accounts
- [ ] Session uses HTTP-Only cookies (verify: `document.cookie` in console returns nothing session-related)
- [ ] XSS test: injected script cannot read session token

**Note:** This checklist is not considered "closed" from a security standpoint until both the allowlist AND HTTP-Only cookies are deployed together.

---

## 5. TECHNICAL ARCHITECTURE

### Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+ / FastAPI (ASGI) |
| Frontend | Vanilla HTML/JS/CSS (no build tools) |
| Database | PostgreSQL (Railway, production) + SQLite (local dev) |
| Compute | SciPy, yfinance, pandas/numpy |
| Broker | Kite Connect (founder's account only) |
| Notifications | Telegram (private chat), Resend (email) |
| Hosting | Railway.app (Singapore) |
| CDN | Cloudflare |
| Auth | Google Sign-In → HTTP-Only secure cookies + founder allowlist for Tier 2 |
| Rate Limiting | slowapi |

### Database Tables (15 Total)

| Table | Purpose | Tier |
|-------|---------|------|
| `profiles` | Simulator user profiles | Tier 1 (Practice Arena) |
| `strategy_profiles` | Sub-profiles for strategy experimentation | Tier 1 |
| `trades` | Simulated trade records with behavioral flags | Tier 1 |
| `real_trades` | Real trade journal entries | Tier 1 |
| `behavioral_metrics` | Cached metric computations | Tier 1 |
| `telemetry` | Pre-trade behavioral state snapshots | Tier 1 |
| `earnings_calendar` | Static earnings event data | Tier 2 |
| `market_data_cache` | Cached market data | Tier 2 |
| `monthly_pnl` | Monthly P&L aggregates | Tier 1 |
| `users` | Google Sign-In profiles | Both |
| `upload_history` | DNA upload records with scores | Tier 1 |
| `signal_history` | Append-only signal archive (founder only) | Tier 2 |
| `live_trades` | Paper/live trade records (founder only) | Tier 2 |
| `schema_version` | Migration tracking | Both |

### API Endpoints — Live Signal Engine (17 endpoints, ALL founder-gated per Section 4)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/live/signal` | Today's trade card |
| POST | `/api/live/generate-signal` | Trigger on-demand signal generation |
| GET | `/api/live/gate-status` | 7-metric unlock gate |
| POST | `/api/live/paper-execute` | Execute paper trade (1/day) |
| GET | `/api/live/my-trades` | Trade history |
| GET | `/api/live/open-positions` | Open trades with live P&L + suggestions |
| POST | `/api/live/exit-trade` | Manual exit |
| POST | `/api/live/trail-sl` | Update stop-loss |
| POST | `/api/live/run-eod` | EOD resolution (real NIFTY close) |
| GET | `/api/live/eod-report` | Today's EOD report |
| GET | `/api/live/auth-status` | Kite auth state |
| GET | `/api/live/kite-login` | Redirect to Zerodha OAuth (state-parameter gated) |
| GET | `/api/live/kite-callback` | OAuth callback (state-validated per 4.2.1) |
| GET | `/api/live/live-prices` | Kite LTP for signal strikes |
| GET | `/api/live/settings` | Capital and risk parameters |
| GET | `/api/live/signal-history` | Query historical signals |
| GET | `/api/live/signal-stats` | Aggregate signal statistics |

**Removed:** `/trade-log` (dead — superseded by `/my-trades`), `/admin/all-trades` (no purpose in single-user model)

---

## 6. LIVE SIGNAL ENGINE — Detailed Flow (Founder-Only)

### Morning Signal Generation (Daily @ 9:00 AM IST)

```
Step 1: Fetch Global Data (yfinance)
├── S&P 500 overnight close + % change
├── VIX level + % change
├── DXY (Dollar Index) + % change
└── Gift Nifty (projected NIFTY opening)

Step 2: Pattern Matching (5-year NIFTY history)
├── Bucket today's conditions
├── Find matching historical days (min 10 required)
└── Output: {direction, confidence, avg_move, matching_days}

Step 3: Strategy Selection (27-combo matrix)
├── Bull Call Spread (bullish)
├── Bear Put Spread (bearish)
├── Iron Condor (neutral / low confidence)
└── Long Straddle (neutral + high volatility)

Step 4: Trade Construction
├── Optimal strikes, Black-Scholes premiums
├── 2% per-trade risk cap verification
└── Zerodha charges included

Step 5: 7 Quality Filters → Position Sizing
Step 6: Save to Signal History (PostgreSQL, append-only)
Step 7: Telegram notification (founder's private chat)
Step 8: Serve via /api/live/signal (founder-only)
```

### Paper Trading → Live Unlock Gate

```
Founder executes paper trades daily (1/day max)
→ EOD Resolution: Real NIFTY close → win/loss
→ 7 Metrics on trailing 30 trades:
    1. Trade Count ≥ 30
    2. Win Rate > 50%
    3. Profit Factor > 1.5
    4. Avg Win/Loss > 1.0
    5. Max Drawdown < 15%
    6. Consecutive Losses < 5
    7. Expectancy > Rs.0
→ ALL 7 PASS → LOCKED → LIVE
→ Founder's own Zerodha execution via Kite API
```

---

## 7. REVENUE MODEL (DNA INTELLIGENCE ONLY)

Live Signal Engine: No monetization, not in scope until regulatory review.

**Phase 1 (Current):** Free for first 100 DNA users
**Phase 2 (After 100):** ₹499/month or ₹2999/year — DNA features only
**Phase 3:** Enterprise (prop firms, team reports)

---

## 8. COMPETITIVE POSITIONING (DNA Intelligence Only)

| Feature | Options Tycoon (DNA) | Sensibull | Opstra | TradingView |
|---------|---------------------|-----------|--------|-------------|
| Behavioral DNA from CSV | ✅ | ❌ | ❌ | ❌ |
| Quantified ₹ cost of bad behavior | ✅ | ❌ | ❌ | ❌ |
| Fix One Thing recommendation | ✅ | ❌ | ❌ | ❌ |
| Options chain + Greeks | ✅ | ✅ | ✅ | ✅ |
| Strategy builder | ✅ | ✅ | ✅ | ❌ |
| Indian broker integration | Zerodha | Zerodha | Zerodha | ❌ |

Live Signal Engine intentionally excluded — not a market-facing product.

---

## 9. PRODUCTION STATUS

### Known Gaps (Prioritized)

| # | Gap | Risk | Priority |
|---|-----|------|----------|
| 1 | Founder-only access control + HTTP-Only cookies | Unauthorized signal access; session forgery | **P0 — ship together** |
| 2 | Automated DB backups | Data loss (already occurred once — 4 trades lost) | P0 |
| 3 | DPDPA 2-checkbox consent | Legal compliance (DNA module) | P0 |
| 4 | Remove dead endpoints (`/trade-log`, `/admin/all-trades`) | Unnecessary attack surface | P0 (trivial, bundle with #1) |
| 5 | Mobile responsiveness | UX on phones (DNA module) | P1 |
| 6 | Razorpay integration | Revenue (DNA only) | P2 |
| 7 | Sentry error tracking | Blind to production errors | P2 |

---

## 10. KEY METRICS

### Tier 1 — DNA Intelligence (growth targets)

| Metric | Current | Target (100 users) |
|--------|---------|---------------------|
| Registered users | 1 | 100 |
| Weekly active uploads | 1 | 30 |
| Avg DNA Score improvement | N/A | +10 pts over 4 weeks |

### Tier 2 — Live Signal Engine (founder performance, not growth)

| Metric | Current | Notes |
|--------|---------|-------|
| Paper trades executed | 0 (reset after migration) | Progressing toward 30-trade gate |
| Live unlock achieved | 0 | Founder's own progression |
| Revenue | ₹0 | Not monetized |

---

## 11. RISK REGISTER

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Live Signal Engine accessed by non-founder | SEBI RA/IA regulatory exposure | **Architectural:** founder-only access control (Section 4) + HTTP-Only cookies. Not just language. |
| Allowlist bypassed via XSS/session forgery | Same as above | HTTP-Only cookies bundled with allowlist (same P0 deploy) |
| DNA module data breach | DPDPA violation, reputation | PostgreSQL encrypted at rest, delete account, consent checkboxes |
| Signal engine poor trade (founder's capital) | Personal financial loss | 7 filters, position sizing, 30-trade gate. Accepted as personal risk. |
| DB data loss | History lost (already happened once) | Automated backups — P0 |
| Railway downtime | Service unavailable | Signals persist in DB, ephemeral filesystem accepted |

---

## 12. ROADMAP (Next 90 Days)

### July 2026 (Current Sprint — Build Order Matters)

1. [ ] **Founder allowlist + HTTP-Only cookies** (Section 4) — build first, ship together
2. [ ] **Remove dead endpoints** (`/trade-log`, `/admin/all-trades`) — bundle with #1
3. [ ] **Verification checklist** (Section 4.7) passed
4. [ ] **Automated DB backups** — already burned once
5. [ ] **DPDPA consent checkboxes** (DNA module)
6. [x] Signal History (PostgreSQL persistence)
7. [x] Iron Condor strategy builder
8. [x] Low-confidence signal generation
9. [x] Full live.html restoration (positions, EOD, Zerodha)
10. [ ] Mobile responsive pass (DNA module)
11. [ ] **Legal consult:** "Does a founder-only, non-monetized signal tool require RA/IA registration if ever extended to a second user?"

### August 2026 (DNA Module Only)

- [ ] First 10 external beta users — DNA Intelligence only
- [ ] Email weekly digest
- [ ] PDF export of DNA report
- [ ] Month-over-month comparison

### September 2026 (DNA Module Only)

- [ ] 100 user milestone
- [ ] Razorpay payment integration
- [ ] Premium feature gating
- [ ] Re-evaluate Live Signal Engine multi-user rollout **only if legal consult has produced a clear answer**

---

*End of BRD v3.0. Build order in Section 12 is sequential — Section 4 is a prerequisite for all other Module A work.*


---

## 13. SIGNAL ACCURACY IMPROVEMENT PLAN

> **Context:** The founder intends to go live with real capital after ~30-35 paper trade days. All accuracy improvements below must be built and validated BEFORE the gate unlocks — they are prerequisites for trusting the system with real money, not post-launch enhancements.

### Timeline: Build during the 30-day paper trading window (July-August 2026)

| # | Improvement | Build | Priority | Deadline |
|---|-------------|-------|----------|----------|
| 1 | Raise minimum historical matches from 10 → 20-25 | Config change + confidence interval in pattern output | **Immediate** (this weekend) | Before trade #2 |
| 2 | Walk-forward validation (train years 1-3, test year 4, roll forward) | Analysis script against existing 5yr CSV | **This weekend** | Before trade #5 |
| 3 | Per-filter predictive value tracking | SQL analysis on signal_history → outcome correlation | **This weekend** | Before trade #10 |
| 4 | Intraday high/low in EOD resolution (simulate stop-loss triggers) | Fetch OHLC in run-eod, check if SL would've hit before close | **Week 2** | Before trade #15 |
| 5 | Calibration chart (stated confidence % vs actual win rate) | Dashboard view querying signal_history + live_trades | **Week 3** (needs 15+ resolved trades) | Before trade #20 |
| 6 | Rolling monthly recalibration | Scheduled re-run of pattern matching against updated dataset, log when strategy assignments change | **Week 4** | Before gate unlock |

### 13.1 Raise Minimum Matches (Build This Weekend)

**Current:** `min_matches = 10` in `engine/signals/pattern_matcher.py`
**Target:** `min_matches = 20` (configurable via `config/settings.json`)

Additionally, report confidence interval on win rate:
```
"win_rate": 68%,
"confidence_interval_95": [52%, 84%],  // Wilson score interval
"sample_size": 25
```

This lets the founder distinguish "68% from 25 matches" (meaningful) from "70% from 11 matches" (noise).

### 13.2 Walk-Forward Validation (Build This Weekend)

Split `nifty_daily_5yr.csv` into rolling windows:
- Train: Years 1-3 (bucket boundaries, direction probabilities)
- Test: Year 4 (out-of-sample win rate)
- Roll forward by 6 months, repeat

Output: a validation report showing whether the pattern-matching edge holds on data the system didn't see during tuning. If it doesn't → the VIX/DXY bucket cutoffs need adjustment before going live.

### 13.3 Per-Filter Predictive Value (Build This Weekend)

Every signal already logs all 7 filter pass/fail results in `signal_history.quality_filters_json`. After 10+ resolved trades, run:

```sql
-- Does win rate actually improve with more filters passing?
SELECT filters_passed, 
       COUNT(*) as signals,
       AVG(CASE WHEN lt.status = 'win' THEN 1 ELSE 0 END) as actual_win_rate
FROM signal_history sh
JOIN live_trades lt ON sh.signal_date = lt.date
GROUP BY filters_passed ORDER BY filters_passed;
```

If certain filters don't discriminate (e.g., FII flow is uncorrelated with outcome), flag them for review — a filter that adds noise reduces the system's value.

### 13.4 Intraday SL Simulation (Week 2)

**Problem:** Paper trades resolve at EOD close only. Real trading uses intraday stop-losses. The gate validates a different behavior than live execution.

**Fix:** In `run_eod`, after fetching the daily close, also fetch the day's high/low. Check:
- For bull call spreads: did NIFTY hit below `projected_open - SL_points` at any point during the day?
- If yes: resolve as loss at SL price, not at close price.

This makes paper trade P&L more honest and the 30-trade gate more predictive of live performance.

### 13.5 Calibration Chart (Week 3, After 15+ Trades)

Add `/api/live/calibration` endpoint:
- Bucket signals by stated confidence (40-55%, 55-70%, 70%+)
- For each bucket: actual win rate from resolved `live_trades`
- If "70%+ confidence" bucket only wins 50% in practice → the confidence score is miscalibrated → adjust pattern matcher thresholds

Render as a simple bar chart on the live page (below gate metrics).

### 13.6 Monthly Recalibration (Week 4)

Scheduled script that:
1. Re-downloads latest NIFTY data (extend the 5yr CSV)
2. Re-runs pattern matching on the full updated dataset
3. Compares: did the strategy assignments for common condition buckets change?
4. If yes → log the change and surface it as a notification

This prevents the system from going stale as market regimes shift.

### 13.7 Success Criteria (Gate Unlock Readiness)

Before the 30-trade gate is trusted as a "go live" signal, ALL of the following must be true:

- [ ] Min matches raised to 20+ and confidence intervals displayed
- [ ] Walk-forward validation shows positive edge on out-of-sample data
- [ ] Per-filter analysis shows monotonic improvement (more filters → higher win rate)
- [ ] Intraday SL simulation active in EOD resolution
- [ ] Calibration shows confidence % is within ±10% of actual win rate per bucket
- [ ] At least one monthly recalibration run completed

If any of these fail: the gate unlock should NOT be treated as permission to go live — it means the gate itself is validating against an insufficiently honest paper model.


---

## 14. STATUS UPDATE (2026-07-23)

### Completed This Session

| # | Item | Status |
|---|------|--------|
| 1 | Founder allowlist middleware | ✅ Deployed — all /api/live/* routes gated |
| 2 | HTTP-Only session cookies | ✅ Deployed — set on Google auth |
| 3 | Legacy X-User-Id fallback | ✅ Deployed — works until full cookie migration |
| 4 | Kite callback exempt from allowlist | ✅ Fixed — Zerodha redirect no longer blocked |
| 5 | Kite reads from env vars (not file) | ✅ Fixed — KITE_API_KEY/SECRET from Railway vars |
| 6 | Conditional nav rendering | ✅ Deployed — Live Signals hidden for non-founders |
| 7 | Dead endpoints removed (/trade-log, /admin/all-trades) | ✅ Done |
| 8 | Min matches raised to 20 + Wilson CI | ✅ Deployed |
| 9 | Walk-forward validation script | ✅ Built — result: 42.9% OOS (no reliable edge) |
| 10 | Per-filter analysis script | ✅ Built — ready to run after 10 resolved trades |
| 11 | Iron Condor strategy builder | ✅ Live — generates 4-leg neutral trades |
| 12 | Signal persists after Railway redeploy | ✅ Fixed — falls back to signal_history DB |
| 13 | Signal engine never returns None | ✅ Fixed — always returns skip card with reason |
| 14 | Telegram asyncio crash fix | ✅ Fixed — handles event loop conflicts |
| 15 | Paper trade #1 executed + EOD resolved | ✅ Won (Iron Condor, NIFTY stayed in range) |

### Current Production State

- **Trades: 5/30** (2 wins, 3 losses, 40% win rate)
- **P&L: Rs.124** (positive expectancy)
- **Gates Passed: 4/7** (Avg Win/Loss, Drawdown, Consec Losses, Expectancy)
- **Still Failing:** Trade count (5/30), Win Rate (40%), Profit Factor (1.08)
- **Status: LOCKED** — 25 more trades needed

### Known Issues (Not Blocking)

| # | Issue | Impact | Fix Planned |
|---|-------|--------|-------------|
| 1 | 4/7 vs 5 PASS filter count display mismatch | Cosmetic — R:R filter returns string type in some edge cases | Next session |
| 2 | Run EOD button doesn't respond on first click (needs console call) | UX — may be confirm() dialog being blocked | Next session |
| 3 | Walk-forward shows 42.9% OOS win rate (no edge) | Pattern matching needs tuning before trusting gate | Before trade #15 |
| 4 | Kite callback "Invalid or expired session" | Redirect URL on developers.kite.trade may need updating | Owner action |

### Next Steps (Priority Order)

**This Week (Before Trade #10):**
1. [ ] Fix Run EOD button (confirm dialog or fallback)
2. [ ] Fix 4/7 filter count display bug
3. [ ] Automated DB backups (P0 — already burned once)
4. [ ] Address walk-forward result — tune pattern matching or add multi-factor conditions

**Before Trade #15:**
5. [ ] Intraday SL simulation in EOD resolution
6. [ ] DPDPA 2-checkbox consent (DNA module)
7. [ ] Fix Kite redirect URL (owner: developers.kite.trade)

**Before Gate Unlock (Trade #30):**
8. [ ] Calibration chart (confidence % vs actual win rate)
9. [ ] Monthly recalibration script
10. [ ] All Section 13 success criteria must pass

### Daily Workflow (Established)

```
9:00 AM IST / 11:30 AM PH  → Open live.html → Regenerate Signal
9:15 AM IST                 → Review signal → Execute or Pass
3:30 PM IST / 6:00 PM PH   → Run EOD (via console if button fails)
                            → Refresh → Check updated stats
```
