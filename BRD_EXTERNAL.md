# OPTIONS TYCOON — Business Requirements Document (BRD)

> **Version:** 8.1 | **Last Updated:** 2026-08-13
> **Status:** NIFTY Live (manual execution from signals) | QQQ pending IBKR activation
> **Disclaimer:** Personal trading tool. Not financial advice.

---

## 1. SYSTEM OVERVIEW

Options Tycoon is a **dual-mode automated options trading system** with behavioral intelligence. It generates Iron Condor signals and either auto-executes or provides signals for manual execution.

| Mode | Market | Broker | Underlying | Strategy | Status |
|------|--------|--------|-----------|----------|--------|
| **NIFTY** | India (NSE) | Zerodha (Kite) | NIFTY 50 Index | ±250pt IC, 100pt wings | ✅ Live — signals generated, manual execution via Kite basket |
| **QQQ** | US (NASDAQ) | Interactive Brokers | QQQ ETF | ±$15 IC, $5 wings (0DTE) | ⏳ Blocked — IBKR document validation pending |

Both modes share: Railway hosting, PostgreSQL DB, signal history, UI, automated scheduler.
Both modes are independent: different broker APIs, different strategies, different schedules, different tabs.

---

## 2. CURRENT STATUS (August 13, 2026)

### What's Working Now

| Component | Status | Details |
|-----------|--------|---------|
| NIFTY signal generation | ✅ Active | Generates IC strikes daily at 9:20 AM IST |
| NIFTY manual execution | ✅ Active | User places trades via Kite web basket order |
| Email/Telegram alerts | ✅ Active | Sends exact strikes + basket-ready format + profit target |
| EOD tracking | ✅ Active | Auto-resolves win/loss on Tuesday expiry |
| 50% profit target | ✅ Active | Alerts when position can be closed early at 50% max profit |
| Kite basket format | ✅ Active | Numbered leg sequence (BUY 1→2, SELL 3→4) in signals |
| Trade history (Fetch from Kite) | ✅ Active | Pull executed orders via Kite API |
| Trade history (Tradebook CSV upload) | ✅ Active | Upload Kite Console CSV for batch import |
| Trade history (Manual entry) | ✅ Active | Manual form for logging trades |
| Trade resolution | ✅ Active | Mark trades as win/loss with actual P&L |
| Railway deployment | ✅ Running | Auto-deploys from GitHub main branch |
| Live UI (NIFTY tab) | ✅ Active | `live-nifty.html` — signals, trade history, P&L tracking |

### What's Blocked

| Component | Status | Blocker | Resolution |
|-----------|--------|---------|------------|
| QQQ auto-execution | ⏳ Pending | IBKR account can't trade options with India tax residence | Changed tax residence to Philippines, submitted documents for validation + support ticket |
| NIFTY auto-execution via API | ❌ Abandoned | Railway IP changes, Kite blocks market orders, API legs don't get spread margin | Manual execution is the permanent model |

### Key Decisions Made

1. **NIFTY = signal-only, manual execution** — System generates signals, user places via Kite web UI basket order.
2. **QQQ/IBKR = waiting** — Tax residence change to Philippines submitted. Code complete, needs account activation.
3. **Capital funded: ₹75,000** — Covers ₹67,234 margin requirement.
4. **50% profit target exit rule** — Close early when 50% of max credit is captured (avoids Tuesday gamma risk).
5. **0DTE Tuesday strategy: SHELVED** — Backtested at 84% win rate but only ₹85/trade realistic edge after friction. Not viable.
6. **Tradebook CSV upload** — Primary method for importing trade history from Kite Console.

---

## 3. MODE A: NIFTY (India via Zerodha) — ACTIVE

### Strategy
**NIFTY ±250pt Iron Condor, 100pt wings, hold to Tuesday weekly expiry**

### Validated Numbers

| Metric | Value |
|--------|-------|
| Win rate (backtested) | 86.5% |
| Reward per trade (net after charges) | ₹2,519 |
| Risk per trade (max loss) | ₹3,980 |
| R:R | 0.74:1 |
| Tax | 0% (wife's resident account — no TDS) |
| Trades per week | 3-4 (Wed, Thu, Fri, Tue) |
| Monthly net estimate (realistic) | ₹15,000–18,000 |

### Capital

| Item | Amount |
|------|--------|
| Available capital | ₹75,000 |
| Actual margin required (Kite basket, 4-leg IC, NRML) | ₹67,234 |
| Buffer | ₹7,766 |

### Execution Model

```
SIGNAL GENERATION (automated, 9:20 AM IST daily):
  → System generates signal on Railway
  → Sends EMAIL to founder with exact strikes + order sequence
  → Signal visible on live-nifty.html page

EXECUTION (manual by user):
  → User opens Kite WEB (not app)
  → Creates basket order with 4 legs (BUY first, SELL second)
  → Uses LIMIT orders at LTP (Kite blocks naked market orders)
  → Kite calculates spread margin (₹67K for current strategy)
  → User executes if margin available

EOD TRACKING (automated, 3:35 PM IST daily):
  → System checks NIFTY close vs short strikes
  → Resolves win/loss on Tuesday expiry
  → Logs to DB for performance tracking
```

### Why Auto-Execution Was Abandoned

1. **IP whitelist**: Railway changes outbound IP on every deploy. Kite allows only 2 whitelisted IPs, updatable once per week.
2. **Order type**: Kite blocks market orders via API for options — requires LIMIT with price.
3. **Margin**: Individual API legs don't get spread margin benefit — need basket order via web UI.

### Broker: Zerodha (Kite)
- Account: Badakala Raghu Raj (wife's account)
- API: Used for price data + signal generation only
- NFO Segment: ✅ Activated
- Kite Connect: ✅ Connected (API key + secret set)

---

## 4. MODE B: QQQ (US Market via IBKR) — PENDING

### Strategy
**QQQ ±$15 Iron Condor, $5 wings (Phase 1), daily, hold to same-day expiry (0DTE)**

### Validated Numbers

| Metric | Value |
|--------|-------|
| Win rate | 98.2% |
| Realistic EV/trade | $7.70–$8.00 |
| Win: avg profit | +$42 |
| Loss: avg loss | -$25 (shallow breach) |
| Loss: max loss | -$500 (Phase 1: $5 wing cap) |
| Slippage (entry only, 4 legs × $0.02) | -$8.00 |
| Commission (IBKR) | -$4.00 |
| Annual ROI | ~115-120% |
| Tax (PH resident) | 0% |

### Current Blocker

**IBKR account with India tax residence cannot trade US options.**

Resolution in progress:
- Changed tax residence from India → Philippines
- Documents submitted for IBKR validation
- Support ticket filed with IBKR
- Waiting for approval (timeline unknown)

### Once Unblocked — Execution Flow

```
9:35 AM EST (scheduled, fully automated):
  → Scheduler triggers auto-trade
  → Signal engine generates QQQ IC parameters
  → ibkr_executor authenticates (OAuth 2.0 signed JWT)
  → Fetches QQQ price from IBKR (yfinance fallback)
  → Resolves 4 option conids (short/long call + short/long put)
  → Places 4-leg combo order via REST API
  → If combo rejected → places 4 individual market orders
  → Auto-confirms any IBKR prompts
  → Trade is live

4:05 PM EST (scheduled):
  → Options expire (0DTE)
  → Win: premium kept automatically (no action)
  → Loss: settled by IBKR (capped at wing width)
  → EOD resolver logs result to DB

Every 55 seconds (always running):
  → IBKR session heartbeat (tickle) keeps REST session alive
```

### Capital & Scaling Plan

| Deposit | Contracts | Monthly Income | Annual |
|---------|-----------|---------------|--------|
| $1,000 | 1 | ~$170 | ~$2,000 |
| $5,000 | 2-3 | ~$500 | ~$6,000 |
| $10,000 | 5 | ~$840 | ~$10,000 |
| $50,000 | 25 | ~$4,200 | ~$50,000 |

### Risk Rules (Pre-Committed)

| Condition | Action |
|-----------|--------|
| Single-day loss > $500 | Full stop. Review. |
| 5 consecutive losses | Continue (normal variance) |
| 10 consecutive losses | Reduce to half contracts |
| Account drops 30% from peak | Full stop |
| Real slippage > $12/trade over 10 trades | Strategy not viable. Stop. |

### Broker: Interactive Brokers
- API: IBKR Web API v1.0 (REST/HTTPS + OAuth 2.0 private_key_jwt)
- No TWS/Gateway required — runs headless on Railway
- Order type: Combo order (4-leg IC) with individual-leg fallback
- Auth: OAuth 2.0 (signed JWT → access token, auto-refresh)
- Session: Heartbeat tickle every 55s via background scheduler
- Funding: Wise USD → IBKR wire
- **Status: ⏳ Document validation pending (India → PH tax residence change)**

---

## 5. TECHNICAL ARCHITECTURE

### Code Structure

```
engine/
├── signals/
│   ├── simple_ic_engine.py     → NIFTY signal generator
│   ├── qqq_ic_engine.py        → QQQ signal generator
│   ├── signal_engine.py        → Main orchestrator (pattern match pipeline)
│   ├── data_fetcher.py         → yfinance global data collection
│   ├── pattern_matcher.py      → Statistical pattern bucketing
│   ├── quality_filters.py      → 7-filter quality gate
│   ├── strategy_picker.py      → Conditions → strategy → strikes
│   └── stock_scanner.py        → Watchlist stock scanning
├── broker/
│   ├── kite_auth.py            → Zerodha OAuth + LTP
│   ├── kite_executor.py        → NIFTY order placement (signal-only mode)
│   ├── kite_ticker.py          → Zerodha WebSocket live quotes
│   └── ibkr_executor.py        → QQQ IBKR REST API v1.0 executor (complete, pending activation)
├── scheduler.py                → Dual scheduler (IST + EST) + IBKR heartbeat
└── session.py                  → Founder allowlist

routes/
├── live.py                     → Serves both modes (NIFTY/QQQ) based on TRADING_MODE
├── auth.py                     → Google OAuth + session management
├── behavioral.py               → Behavioral metrics API
├── dashboard.py                → Dashboard data endpoints
├── data.py                     → Options chain + market data
├── portfolio.py                → Profile CRUD
├── trading.py                  → Trade execution
└── (additional route modules)

config/
└── settings.json               → Has both NIFTY and QQQ parameters
```

### Configuration (settings.json)

```json
{
  "trading_mode": "qqq",
  "nifty": {
    "capital": 75000,
    "offset_pts": 250,
    "wing_width": 100,
    "lot_size": 65,
    "preferred_expiry": "current_week"
  },
  "qqq": {
    "capital": 1000,
    "offset_pts": 15,
    "wing_width": 5,
    "lot_size": 100,
    "phase": 1,
    "phase_notes": "Phase 1: $5 wings ($500 max loss) until capital > $2,500"
  }
}
```

### Environment Variables

| Variable | QQQ Mode | NIFTY Mode |
|----------|----------|------------|
| TRADING_MODE | qqq | nifty |
| IBKR_CLIENT_ID | OAuth client ID | (not used) |
| IBKR_ACCOUNT_ID | Account number | (not used) |
| IBKR_PRIVATE_KEY_PEM | RSA private key (PEM) | (not used) |
| KITE_API_KEY | (not used) | ✅ Set |
| KITE_API_SECRET | (not used) | ✅ Set |
| FOUNDER_ALLOWED_EMAILS | ✅ Set | ✅ Set |

### Scheduler (Dual Timezone)

```
NIFTY Mode (currently active):
  - 9:20 AM IST: Generate signal + send email
  - 3:35 PM IST: EOD SL check
  - Tuesday 3:35 PM IST: Expiry resolution

QQQ Mode (pending IBKR activation):
  - 9:35 AM EST (13:35 UTC): Auto-generate signal + place trade
  - 4:05 PM EST (20:05 UTC): EOD verify expiry result
  - Every 55 seconds: IBKR session heartbeat (tickle)
```

### Deployment

| Environment | Status | Details |
|-------------|--------|---------|
| GitHub (main) | ✅ Up to date | Auto-deploys to Railway |
| Railway (production) | ✅ Running | Hosts both NIFTY signals + QQQ (when ready) |
| Kite Auth (NIFTY) | ✅ Connected | OAuth flow verified, API key set |
| IBKR Auth (QQQ) | ⏳ Pending | Env vars not set (waiting on account) |

---

## 6. TRADE HISTORY

| Date | Mode | Strategy | Result | Notes |
|------|------|----------|--------|-------|
| Aug 5, 2026 | NIFTY | Scalp (3 round-trips) | +₹3,120 | 24950CE +₹709, 24250CE +₹2,408, 24250PE +₹3 |
| Aug 6, 2026 | NIFTY | Scalp (2 round-trips) | +₹16.25 | 25000CE +₹13, 24300PE +₹3.25 |
| Aug 12, 2026 | NIFTY | IC ±250pt | TBD | Manual execution, successful placement |

---

## 7. VALIDATION HISTORY

| # | Market | Strategy | Result | Conclusion |
|---|--------|----------|--------|-----------|
| 1 | NIFTY | Directional prediction | 42.9% OOS | ❌ Worse than coin flip |
| 2 | NIFTY | Range bucketing | 77.2% (below baseline) | ❌ Bucketing subtracts value |
| 3 | NIFTY | IC flat premium | +Rs.1,308 (artifact) | ❌ Mixed regimes incorrectly |
| 4 | NIFTY | IC grid search | High-vol only: n=7 | ❌ Insufficient sample |
| 5 | NIFTY | IC ±250pt daily | Rs.192 EV, 0 decay | ✅ Validated |
| 6 | SPX | IC grid search | All negative | ❌ Too efficient |
| 7 | IWM | IC ±$5/$3 | $8.70 EV | ✅ Validated |
| 8 | QQQ | IC ±$15/$7 full pipeline | $8 realistic EV | ✅ Validated (7 rounds) |

---

## 8. RISK REGISTER

| Risk | Impact | Mitigation |
|------|--------|-----------|
| IBKR account never approved | QQQ mode dead | Focus on NIFTY; explore alternative brokers (Tastytrade, Saxo) |
| NIFTY gaps beyond ±250pt | Max loss ₹3,980 per trade | Pre-committed stop rules; weekly expiry limits exposure |
| Railway downtime | Missed signal | Email still sends; manual check of live-nifty.html |
| Kite token expiry | Can't fetch LTP for signals | Daily re-auth via login flow |
| QQQ gaps >$15 overnight (earnings) | Loss capped at $500 (Phase 1) | $5 wings; FOMC/CPI/NFP event filter skips high-impact days |
| IBKR connection failure | Missed trade | Retry logic (3x exponential backoff); self-healing restart auth |
| Slippage higher than backtest | EV reduced or negative | Phase 1 validates; stop if >$12/trade |
| Partial execution (QQQ) | Unhedged position | Risk-first ordering (BUY wings first); abort SELL if wing fails |

---

## 9. NEXT ACTIONS

### Immediate (Do after restart)
- [ ] Clean old test trades from Railway: visit `options-tycoon.com/api/live/cleanup-old-trades?before=2026-08-05` (DELETE request from browser console)
- [ ] Re-upload tradebook CSV on production to populate real trades only

### Waiting
- [ ] IBKR document validation (India → PH tax residence) — waiting on IBKR
- [ ] Once approved: Set IBKR env vars on Railway → paper test → go live

### Active (NIFTY)
- [x] Generate daily signals with basket-ready format
- [x] 50% profit target exit rule + Telegram alerts
- [x] Trade history tracking via Tradebook CSV upload
- [x] Kite API order fetch for real-time import
- [ ] Continue logging all trades for performance review
- [ ] Validate profit target alerts work in next trading cycle

### Future (QQQ — once IBKR unblocked)
- [ ] Set env vars: IBKR_CLIENT_ID, IBKR_ACCOUNT_ID, IBKR_PRIVATE_KEY_PEM
- [ ] Paper sandbox test (10 trades)
- [ ] Fund $1,000 via Wise → IBKR
- [ ] Go live Phase 1

---

## 10. IBKR EXECUTOR — IMPLEMENTATION SUMMARY (Complete, Pending Activation)

### Architecture
Pure REST/HTTPS — no TWS, no Gateway, no `ib_insync`. Runs headless on Railway.

### Components Built

| Component | Status |
|-----------|--------|
| OAuth 2.0 Auth (private_key_jwt) | ✅ |
| Session Heartbeat (tickle every 55s) | ✅ |
| Contract Resolution (symbol → conid) | ✅ |
| Option Chain Fetch | ✅ |
| Option Conid Resolution (strike+right+expiry) | ✅ |
| QQQ Live Price (market data snapshot) | ✅ |
| 4-Leg Iron Condor Combo Order | ✅ |
| Individual-Leg Fallback (if combo fails) | ✅ |
| Auto-Confirm Order Prompts | ✅ |
| Top-level Entry Point (`execute_qqq_sync`) | ✅ |
| yfinance Price Fallback | ✅ |
| Route Integration (`/api/live/live-execute`) | ✅ |
| Mock test suite (14 tests passing) | ✅ |
| Retry + partial execution recovery | ✅ |
| FOMC/CPI/Earnings event filter | ✅ |
| Risk-first individual-leg ordering | ✅ |
| Self-healing scheduler startup | ✅ |
| Telegram notification integration | ✅ |

---

## 11. PRODUCT PLATFORM (Behavioral Intelligence — Separate Track)

Options Tycoon also has a **Trader DNA behavioral intelligence platform** for retail traders (separate from the live trading system above). This is the consumer-facing product:

### Core Product: Trader DNA Intelligence
- Upload broker trade history (Zerodha/Groww/Angel One CSV)
- Get AI-powered behavioral analysis (revenge trading, overconfidence, impulse exits, disposition bias)
- Track improvement over time with weekly uploads
- Practice Arena ($10K paper trading simulator)

### Revenue Model
- Free: First 100 users (all features)
- Paid (user 101+): ₹499/month or ₹2999/year for premium features

### Tech Stack
- Python 3.12 / FastAPI
- PostgreSQL (Railway)
- Vanilla HTML/JS/CSS frontend
- Google Sign-In auth
- Hosted on Railway

### Production Readiness Status
- P0 items (infrastructure, security, legal): Not yet started
- See PROJECT_REPOSITORY.md for full build plan

---

*End of BRD v8.0. This document is the single source of truth for the live trading system status. For the full product platform details (58 requirements, API inventory, feature status), see PROJECT_REPOSITORY.md.*
