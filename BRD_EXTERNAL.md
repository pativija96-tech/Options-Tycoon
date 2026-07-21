# OPTIONS TYCOON — Business Requirements Document (BRD)

> **Version:** 2.0 | **Last Updated:** 2026-07-21  
> **Status:** Live on Production (Railway + PostgreSQL)  
> **URL:** https://options-tycoon.com  
> **GitHub:** https://github.com/pativija96-tech/Options-Tycoon

---

## 1. EXECUTIVE SUMMARY

Options Tycoon is a **behavioral intelligence platform** for Indian retail options traders. It combines two core capabilities:

1. **Trader DNA Intelligence** — Upload broker CSV (Zerodha, Groww, Angel One) → Get behavioral analysis revealing WHY you keep losing → Track improvement weekly
2. **Live Signal Engine** — AI-powered daily NIFTY trade signals with pattern matching, quality filters, paper trading with EOD resolution, and a 30-trade unlock gate to live trading

**Target Market:** Retail options traders (NSE/BSE) — primarily Zerodha/Groww/Angel One users  
**Monetization:** Free for first 100 users → ₹499/month or ₹2999/year for premium features  
**Stage:** Live beta, 1 active user (founder testing), Railway production

---

## 2. PRODUCT ARCHITECTURE

### User Flows (Two Entry Points)

```
FLOW A: DNA TRACKING (Retention Product)
Landing → Upload CSV → Sign-In Gate → DNA Report → Dashboard → Weekly Upload Loop

FLOW B: LIVE SIGNAL ENGINE (Daily Engagement)
Dashboard → Live Signals → Generate Signal → Execute (Paper) → EOD Resolution → Gate Metrics
                                                                                    ↓
                                                                    30 Trades + 7 Metrics Pass
                                                                                    ↓
                                                                        UNLOCK LIVE TRADING (Zerodha)
```

### Pages & Roles

| Page | Purpose | Auth |
|------|---------|------|
| `/` (landing) | Marketing hook — "See why you keep losing" | No |
| `/static/upload-free.html` | Upload broker CSV for DNA analysis | No |
| `/static/signin.html` | Google Sign-In gate | No |
| `/static/report.html` | DNA Report (devastating reveal) | Yes |
| `/static/dashboard.html` | **HOME** — DNA score, trends, upload again | Yes |
| `/static/live.html` | **LIVE SIGNALS** — daily trades, positions, EOD | Yes |
| `/static/index.html` | Practice Arena ($10K paper trading sim) | Yes |
| `/static/behavioral.html` | Detailed behavioral metrics | Yes |
| `/static/timemachine.html` | Historical replay mode | Yes |

---

## 3. FEATURE INVENTORY (Current State)

### Module A: Live Signal Engine (PRIMARY — Daily Engagement)

| # | Feature | Status | Description |
|---|---------|--------|-------------|
| A1 | Morning Signal Generation | ✅ Live | Fetches overnight US/VIX/DXY data, runs 5-year NIFTY pattern matching, picks strategy |
| A2 | Strategy Matrix (27 combos) | ✅ Live | Maps (direction × confidence × volatility) → Bull Call, Bear Put, Iron Condor, Straddle |
| A3 | 7 Quality Filters | ✅ Live | Historical confidence, global alignment, Gift Nifty, R:R, liquidity, event conflict, FII flow |
| A4 | Position Sizing | ✅ Live | Full/Reduced/Minimum based on filter score |
| A5 | Iron Condor Builder | ✅ Live | 4-leg neutral strategy with dynamic strike selection |
| A6 | Paper Trade Execution | ✅ Live | Per-user, one trade per day, saved to PostgreSQL |
| A7 | EOD Resolution | ✅ Live | Fetches real NIFTY close, resolves open trades with actual P&L |
| A8 | 7-Metric Unlock Gate | ✅ Live | Win rate, profit factor, drawdown, expectancy — all 7 must pass to unlock live |
| A9 | Open Positions Panel | ✅ Live | Current P&L, exit suggestions, trail SL, manual exit |
| A10 | Signal History (DB) | ✅ Live | Every generated signal saved to PostgreSQL (append-only, for model learning) |
| A11 | Zerodha Kite OAuth | ✅ Live | Login redirect, access token handling, live price fetch |
| A12 | Live Prices (Kite API) | ✅ Live | Fetches LTP for signal strikes when authenticated |
| A13 | Stock Scanner (Watchlist) | ✅ Live | Scans 10 stocks for secondary signals with earnings catalysts |
| A14 | Telegram Notifications | ✅ Live | Sends daily signal to Telegram channel |
| A15 | Trade Log (per-user) | ✅ Live | Full history with win/loss, P&L, strategy breakdown |

### Module B: Trader DNA Intelligence (RETENTION — Weekly Upload)

| # | Feature | Status | Description |
|---|---------|--------|-------------|
| B1 | Broker CSV Parsing | ✅ Live | Zerodha, Groww, Angel One format detection and parsing |
| B2 | DNA Score (0-100) | ✅ Live | Composite behavioral score from discipline, patience, sizing, emotional control |
| B3 | Pattern Detection | ✅ Live | Revenge trades, overconfidence traps, impulse exits, disposition bias |
| B4 | Behavioral Cost (₹) | ✅ Live | Quantifies exact ₹ lost due to undisciplined trading |
| B5 | Fix One Thing | ✅ Live | Single worst pattern → actionable focus for the week |
| B6 | Upload History | ✅ Live | Score progression tracking over multiple uploads |
| B7 | Google Sign-In | ✅ Live | 1-click auth, email capture, profile persistence |
| B8 | Dashboard (Score Trends) | ✅ Live | DNA score over time, last upload info, quick upload CTA |

### Module C: Practice Arena (SECONDARY — Simulator)

| # | Feature | Status | Description |
|---|---------|--------|-------------|
| C1 | Virtual Portfolio ($10K) | ✅ Built | Game-over at $0, no reset, real stakes psychology |
| C2 | Options Chain + Greeks | ✅ Built | Black-Scholes Delta/Gamma/Theta/Vega, 10 mock tickers |
| C3 | Strategy Builder (1-4 legs) | ✅ Built | Custom combos with P&L visualization |
| C4 | Behavioral Metrics (Progressive) | ✅ Built | Phase A→D unlock as trades accumulate |
| C5 | Risk Guards | ✅ Built | 5% risk gate, IV crush warning, penalty multiplier |
| C6 | Settlement Engine | ✅ Built | Auto-close expired positions at intrinsic |
| C7 | Time Machine | 🔧 Partial | Historical replay with day-by-day progression |
| C8 | Compare Mode (Sim vs Real) | 🔧 Partial | Side-by-side behavioral comparison |

---

## 4. TECHNICAL ARCHITECTURE

### Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+ / FastAPI (ASGI) |
| Frontend | Vanilla HTML/JS/CSS (no build tools) |
| Database | PostgreSQL (Railway, production) + SQLite (local dev) |
| Compute | SciPy (Black-Scholes), yfinance (market data), pandas/numpy (pattern matching) |
| Broker | Kite Connect (Zerodha OAuth + live prices) |
| Notifications | Telegram Bot API, Resend (email) |
| Hosting | Railway.app (Singapore region) |
| CDN | Cloudflare |
| Auth | Google Sign-In (OAuth 2.0) |
| Rate Limiting | slowapi |

### Database Tables (15 Total)

| Table | Purpose |
|-------|---------|
| `profiles` | Simulator user profiles (balance, mode, penalties) |
| `strategy_profiles` | Sub-profiles for strategy experimentation |
| `trades` | Simulated trade records with all behavioral flags |
| `real_trades` | Real trade journal entries (parallel mode) |
| `behavioral_metrics` | Cached metric computations |
| `telemetry` | Pre-trade behavioral state snapshots |
| `earnings_calendar` | Static earnings event data |
| `market_data_cache` | Cached market data |
| `monthly_pnl` | Monthly P&L aggregates |
| `users` | Google Sign-In profiles |
| `upload_history` | DNA upload records with scores |
| `signal_history` | **NEW** — Append-only signal archive for model learning |
| `live_trades` | **NEW** — Per-user paper/live trade execution records |
| `schema_version` | Migration tracking |

### API Endpoints (Live Signal Engine — 18 endpoints)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/live/signal` | Today's trade card |
| POST | `/api/live/generate-signal` | Trigger on-demand signal generation |
| GET | `/api/live/gate-status` | 7-metric unlock gate (computed from DB) |
| POST | `/api/live/paper-execute` | Execute paper trade (1/day/user) |
| GET | `/api/live/my-trades` | User's trade history |
| GET | `/api/live/open-positions` | Open trades with live P&L + suggestions |
| POST | `/api/live/exit-trade` | Manual exit at estimated P&L |
| POST | `/api/live/trail-sl` | Update stop-loss |
| POST | `/api/live/run-eod` | EOD resolution (real NIFTY close) |
| GET | `/api/live/eod-report` | Today's EOD report |
| GET | `/api/live/auth-status` | Kite auth state |
| GET | `/api/live/kite-login` | Redirect to Zerodha OAuth |
| GET | `/api/live/kite-callback` | OAuth callback handler |
| GET | `/api/live/live-prices` | Kite LTP for signal strikes |
| GET | `/api/live/settings` | Capital and risk parameters |
| GET | `/api/live/signal-history` | Query historical signals (DB) |
| GET | `/api/live/signal-stats` | Aggregate signal statistics |
| GET | `/api/live/admin/all-trades` | Admin view all users' trades |

---

## 5. LIVE SIGNAL ENGINE — Detailed Flow

### Morning Signal Generation (Daily @ 9:00 AM IST)

```
Step 1: Fetch Global Data (yfinance)
├── S&P 500 overnight close + % change
├── VIX level + % change  
├── DXY (Dollar Index) + % change
└── Gift Nifty (projected NIFTY opening)

Step 2: Pattern Matching (5-year NIFTY history)
├── Bucket today's conditions (US move, VIX regime, DXY direction)
├── Find matching historical days (minimum 10 matches required)
├── Calculate: direction (bullish/bearish/neutral), confidence %, expected move
└── Output: {direction, confidence, avg_move, matching_days}

Step 3: Strategy Selection (27-combo matrix)
├── Map (direction × confidence_tier × vol_regime) → strategy type
├── Bull Call Spread (bullish, high/moderate confidence)
├── Bear Put Spread (bearish, high/moderate confidence)
├── Iron Condor (neutral, or low confidence any direction)
└── Long Straddle (neutral + high volatility)

Step 4: Trade Construction
├── Calculate optimal strikes (round to 50-pt NIFTY strikes)
├── Estimate premiums (Black-Scholes)
├── Verify within 2% per-trade risk cap
├── Calculate max profit, max loss, breakevens, R:R ratio
└── Include Zerodha charges (brokerage + GST + STT + exchange fees)

Step 5: 7 Quality Filters
├── 1. Historical Confidence (>70% with 10+ matches)
├── 2. Global Alignment (2+ factors agree)
├── 3. Gift Nifty Confirmation (pre-market not contradicting)
├── 4. Risk/Reward Ratio (minimum 2:1)
├── 5. Liquidity/Volatility (VIX 10-40 range)
├── 6. No Event Conflict (no RBI/Budget/Election)
├── 7. FII Flow Alignment (not contradicting)
└── Score determines position sizing: 7/7=Full, 5-6=Reduced, 3-4=Minimum

Step 6: Save to Signal History (PostgreSQL — append-only)
Step 7: Send Telegram Notification
Step 8: Serve via /api/live/signal
```

### Paper Trading → Live Unlock Gate

```
User executes paper trades daily (1/day max)
    ↓
EOD Resolution: Real NIFTY close resolves each trade as win/loss
    ↓
7 Metrics computed on trailing 30 trades:
    1. Trade Count ≥ 30
    2. Win Rate > 50%
    3. Profit Factor > 1.5
    4. Avg Win/Loss Ratio > 1.0
    5. Max Drawdown < 15%
    6. Consecutive Losses < 5
    7. Expectancy > Rs.0
    ↓
ALL 7 PASS → Status changes from LOCKED to LIVE
    ↓
Zerodha login enabled → Real trade execution via Kite API
```

---

## 6. REVENUE MODEL

### Phase 1 (Current): Free for First 100 Users
- All features free (DNA + Live Signals)
- Goal: Capture emails, prove value, get testimonials

### Phase 2 (After 100 users): ₹499/month or ₹2999/year
**Free forever:**
- Base DNA Report (score, persona, top patterns)
- Live signal viewing (generate + view daily)
- Paper trading (up to 5 trades)

**Premium (₹499/month):**
- Full DNA drill-down (click pattern → see exact trades)
- Unlimited paper trading (30 trades for unlock)
- Live trading unlock (after gate passes)
- Weekly upload tracking (score trends)
- "How to fix" personalized advice cards
- Email alerts ("Your pattern repeated today")
- Export PDF of full report
- Compare month vs month

### Phase 3: Enterprise
- Custom pricing for prop firms
- Team/group features
- White-label DNA reports

---

## 7. COMPETITIVE POSITIONING

| Feature | Options Tycoon | Sensibull | Opstra | TradingView |
|---------|---------------|-----------|--------|-------------|
| Behavioral DNA from CSV | ✅ | ❌ | ❌ | ❌ |
| Quantified ₹ cost of bad behavior | ✅ | ❌ | ❌ | ❌ |
| Fix One Thing recommendation | ✅ | ❌ | ❌ | ❌ |
| AI signal generation (pattern match) | ✅ | ❌ | ❌ | ❌ |
| 7-metric unlock gate to live | ✅ | ❌ | ❌ | ❌ |
| Paper → Live progression | ✅ | ❌ | ❌ | ❌ |
| Options chain + Greeks | ✅ | ✅ | ✅ | ✅ |
| Strategy builder | ✅ | ✅ | ✅ | ❌ |
| P&L tracking | ✅ | ✅ | ✅ | ✅ |
| Indian broker integration | Zerodha | Zerodha | Zerodha | ❌ |

**Unique moat:** Nobody else in India does behavioral DNA from real broker data + AI-powered signal engine with progressive live unlock.

---

## 8. PRODUCTION STATUS

### Infrastructure

| Component | Status | Details |
|-----------|--------|---------|
| Railway hosting | ✅ Live | Singapore region, auto-deploy from GitHub |
| PostgreSQL | ✅ Live | Railway managed, persistent |
| Cloudflare CDN | ✅ Live | options-tycoon.com |
| GitHub CI/CD | ✅ Live | Push to main → auto-deploy |
| Google OAuth | ✅ Live | Production credentials configured |
| Kite Connect | ✅ Live | API key in Railway env vars |
| Telegram Bot | ✅ Live | Signal notifications active |
| Resend Email | ✅ Live | Transactional emails configured |

### Security

| Layer | Status |
|-------|--------|
| HTTPS/TLS | ✅ (Railway + Cloudflare) |
| Rate limiting | ✅ (slowapi, per-IP) |
| CORS restriction | ✅ (allowed origins configured) |
| No stack traces in prod | ✅ (global error handler) |
| CSV injection prevention | ✅ (formula stripping) |
| Secrets in env vars only | ✅ (no hardcoded credentials) |

### Known Gaps (P0 for scale)

| # | Gap | Risk | Priority |
|---|-----|------|----------|
| 1 | HTTP-Only cookies (currently localStorage) | Session hijacking XSS | P1 |
| 2 | DPDPA 2-checkbox consent | Legal compliance | P0 |
| 3 | Razorpay integration | Revenue | P2 |
| 4 | Automated DB backups | Data loss | P1 |
| 5 | Mobile responsiveness | UX on phones | P1 |
| 6 | Sentry error tracking | Blind to production errors | P2 |

---

## 9. KEY METRICS (Tracking)

| Metric | Current | Target (100 users) |
|--------|---------|---------------------|
| Registered users | 1 | 100 |
| Weekly active uploads | 1 | 30 |
| Daily signal generations | ~1 | 50+ |
| Paper trades executed | 4 (lost in migration) | 500+ |
| Live unlock achieved | 0 | 5-10 users |
| Revenue | ₹0 | ₹0 (Phase 1 free) |
| Avg DNA Score improvement | N/A | +10 pts over 4 weeks |

---

## 10. COST STRUCTURE (100 Users)

| Item | Monthly Cost |
|------|-------------|
| Railway hosting (Hobby) | $5-15 |
| Railway PostgreSQL | $0 (included) |
| Cloudflare | Free |
| Google Sign-In | Free |
| GitHub | Free |
| Resend email (100/day free) | Free |
| Telegram Bot | Free |
| Kite Connect API | ₹2000/month (when live trading) |
| **Total** | **$5-15 (~₹400-1200/month)** |

---

## 11. RISK REGISTER

| Risk | Impact | Mitigation |
|------|--------|-----------|
| SEBI advisory language violation | Legal notice/shutdown | Observational language only, no "should/buy/sell" anywhere |
| User data breach | Reputation, legal | PostgreSQL encrypted at rest, no PII in signals, delete account available |
| Signal engine generates bad trades | User trust loss | 7 quality filters, position sizing, 30-trade gate before live |
| Railway downtime | Service unavailable | Signal saved to DB on generation, ephemeral filesystem accepted |
| Kite API subscription cost | Margin erosion | Only activated post-gate (30 winning trades) — engaged users only |
| yfinance rate limiting | Signal generation fails | Cached data fallback, clear error messages |

---

## 12. ROADMAP (Next 90 Days)

### July 2026 (Current Sprint)
- [x] Signal History (PostgreSQL persistence)
- [x] Iron Condor strategy builder
- [x] Low-confidence signal generation (no more "No Edge" gaps)
- [x] Live Signals nav link in dashboard
- [x] Full live.html restoration (positions, EOD, Zerodha)
- [ ] DPDPA consent checkboxes
- [ ] Mobile responsive pass

### August 2026
- [ ] First 10 external beta users
- [ ] Email weekly digest ("Your score changed")
- [ ] PDF export of DNA report
- [ ] Signal performance tracking (predicted vs actual)
- [ ] Month-over-month comparison

### September 2026
- [ ] 100 user milestone
- [ ] Razorpay payment integration
- [ ] Premium feature gating
- [ ] First live trading user (gate unlock)
- [ ] Broker API auto-import (Zerodha API instead of CSV)

---

*End of BRD. This document is for external validation and investor/reviewer consumption.*
