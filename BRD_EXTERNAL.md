# OPTIONS TYCOON — Business Requirements Document (BRD)

> **Version:** 8.2 | **Last Updated:** 2026-08-24
> **Status:** NIFTY Live (manual execution from signals) | QQQ Live — IBKR activated, manual execution first (auto signal generation)
> **Disclaimer:** Personal trading tool. Not financial advice.

---

## 1. SYSTEM OVERVIEW

Options Tycoon is a **dual-mode automated options trading system** with behavioral intelligence. It generates Iron Condor signals and either auto-executes or provides signals for manual execution.

| Mode | Market | Broker | Underlying | Strategy | Status |
|------|--------|--------|-----------|----------|--------|
| **NIFTY** | India (NSE) | Zerodha (Kite) | NIFTY 50 Index | ±250pt IC, 100pt wings | ✅ Live — signals generated, manual execution (sequential, hedges-first) |
| **QQQ** | US (NASDAQ) | Interactive Brokers | QQQ ETF | ±$15 IC, $5 wings (0DTE) | ✅ Live — IBKR activated (PH residence). Manual execution first: signal auto-generates on EST schedule, operator executes manually |

Both modes share: Railway hosting, PostgreSQL DB, signal history, UI, automated scheduler.
Both modes are independent: different broker APIs, different strategies, different schedules, different tabs.

---

## 2. CURRENT STATUS (August 24, 2026)

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

### QQQ Status (Aug 24, 2026)

| Component | Status | Details |
|-----------|--------|---------|
| IBKR account (PH residence) | ✅ Activated | Tax residence change India → Philippines approved; account can trade US options |
| Options permission level | ⏳ Upgrade required | Account currently at **Options Level 1** (long options + covered calls only). Iron Condor is a defined-risk spread and needs the level that lists **spreads / combinations / iron condors** — on this account that is **Level 3**. Must request the upgrade (choose by the described capability, not the number). Level 1 will reject the IC. |
| QQQ signal generation | ✅ Active | Auto-generates on EST schedule (9:35 AM EST / 13:35 UTC) |
| QQQ execution | 🔧 Manual first | Operator reviews signal, then triggers `/api/live/live-execute?mode=qqq` manually. Auto-execution intentionally OFF until live fills are validated (mirrors NIFTY's cautious rollout) |
| IBKR session keep-alive | ✅ Active | Startup OAuth auth + 55s heartbeat (tickle) when TRADING_MODE=qqq |

### What's Abandoned

| Component | Status | Blocker | Resolution |
|-----------|--------|---------|------------|
| NIFTY auto-execution via API | ❌ Abandoned | Railway IP changes, Kite blocks market orders, API legs don't get spread margin | Manual execution is the permanent model |

### Key Decisions Made

1. **NIFTY = signal-only, manual execution** — System generates signals, user places sequentially via Kite web (hedges-first, not basket).
2. **QQQ = manual execution first** — IBKR PH account activated. Signal auto-generates on the EST schedule; operator executes manually via `/live-execute?mode=qqq` while learning how fills behave. Switch to fully hands-off later, after live validation.
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
| Buffer (steady-state) | ₹7,766 |
| ⚠️ Expiry-day peak (incl. additional ELM, observed 24 Aug 2026) | ~₹1,32,367 — exceeds capital by ~₹53.8k |

> **Capital note:** ₹75,000 is sized for the *steady-state* IC margin. On expiry day, the exchange adds ELM on expiring contracts and the requirement can nearly double (~₹1.32L observed). Either exit before expiry morning (preferred — matches the 50% target) or hold a ~₹55k buffer. See Risk Register.

### Execution Model

```
SIGNAL GENERATION (automated, 9:20 AM IST daily):
  → System generates signal on Railway
  → Sends EMAIL to founder with exact strikes + order sequence
  → Signal visible on live-nifty.html page

EXECUTION (manual by user) — SEQUENTIAL, ONE ORDER AT A TIME:
  → User opens Kite WEB (not app)
  → DO NOT use the basket order — it duplicates legs on partial-fill/retry
  → PHASE A: Place BOTH buy hedges first (long PE + long CE), LIMIT at LTP.
    Wait until both show COMPLETE.
  → PHASE B: Then place the two short legs (short PE + short CE), LIMIT at LTP.
    Shorts get spread margin (~₹32K each) only because hedges are already filled.
  → Confirm each order COMPLETE before placing the next.
  → To reduce/exit a leg: fresh opposite order with EXACT qty (never "Exit" —
    it defaults to full position and can create a naked short → margin rejection).

  LESSON (Aug 19, 2026): Basket order caused leg duplication (130 qty hedges) and
  repeated naked-margin rejections. Sequential hedges-first is the reliable method.

EOD TRACKING (automated, 3:35 PM IST daily):
  → System checks NIFTY close vs short strikes
  → Resolves win/loss on Tuesday expiry
  → Logs to DB for performance tracking
```

### Why Auto-Execution Was Abandoned

1. **IP whitelist**: Railway changes outbound IP on every deploy. Kite allows only 2 whitelisted IPs, updatable once per week.
2. **Order type**: Kite blocks market orders via API for options — requires LIMIT with price.
3. **Margin**: Individual API legs don't get spread margin unless the hedge is filled first.

### Manual Execution Best Practice (learned Aug 19, 2026)

- **Sequential, one order at a time** — NOT Kite basket.
- **Hedges (BUY) first**, wait for COMPLETE, then **shorts (SELL)**.
- Shorts get spread margin (~₹32K) only when the paired hedge is already in the account.
- Basket order caused duplication (retries re-added filled legs → 130 qty) and naked-margin
  rejections (shorts firing before hedges registered). Sequential method avoids both.

### Broker: Zerodha (Kite)
- Account: Badakala Raghu Raj (wife's account)
- API: Used for price data + signal generation only
- NFO Segment: ✅ Activated
- Kite Connect: ✅ Connected (API key + secret set)

---

## 4. MODE B: QQQ (US Market via IBKR) — LIVE (MANUAL EXECUTION FIRST)

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

### Blocker — RESOLVED (Aug 24, 2026)

**IBKR PH account is now activated.** Tax residence changed India → Philippines and approved; the account can trade US options. QQQ is live.

### Current Execution Flow — MANUAL FIRST

Rationale: NIFTY's manual rollout surfaced many execution bugs (leg duplication, naked-margin
rejections). QQQ starts the same cautious way — operator watches live fills before going
hands-off. QQQ trades during US hours (operator is in IST), so the plan is to validate a
handful of trades manually, then switch to end-to-end automation.

```
9:35 AM EST (scheduled — AUTOMATED signal generation only):
  → Scheduler triggers _run_auto_trade (TRADING_MODE=qqq)
  → Signal engine generates QQQ IC parameters
  → Signal saved to today_signal_qqq.json + Telegram alert with strikes
  → NO order placed automatically

EXECUTION (MANUAL by operator, when watching the US market):
  → Operator reviews the QQQ signal on the live page
  → Triggers POST /api/live/live-execute?mode=qqq
  → ibkr_executor authenticates (OAuth 2.0 signed JWT)
  → Fetches QQQ price from IBKR (yfinance fallback)
  → Resolves 4 option conids (short/long call + short/long put)
  → Places 4-leg combo order via REST API
  → If combo rejected → places 4 individual market orders (risk-first: BUY wings first)
  → Auto-confirms any IBKR prompts
  → Trade is live

4:05 PM EST (scheduled):
  → Options expire (0DTE)
  → Win: premium kept automatically (no action)
  → Loss: settled by IBKR (capped at wing width)
  → EOD resolver logs result to DB

Every 55 seconds (always running when TRADING_MODE=qqq):
  → IBKR session heartbeat (tickle) keeps REST session alive
  → (Plus startup OAuth auth on scheduler boot — self-healing across Railway restarts)
```

### Combo Execution Policy (implemented Aug 24, 2026)

- IC executes as a single atomic combo via IBKR Web API `conidex`
  (`28812380;;;{conid}/{ratio},...`; ratio +1 = BUY, −1 = SELL).
- Order type is **LMT** at estimated net credit (combo mid from per-leg snapshots).
- **Price walk:** up to **3 attempts**, conceding **$0.02/attempt** (max **$0.05** total).
- If unfilled after 3 attempts → **ABORT, place no legs**, alert
  `"QQQ IC combo limit order unfilled — trade aborted"`.
- **Individual-leg fallback DEPRECATED** (`_place_individual_legs_DEPRECATED`, unused) —
  0DTE legging risk (orphaned long wings) outweighs a missed trade.

### Future — Switch to Hands-Off (after manual validation)

Once live fills are validated over several manual trades, wire `execute_qqq_sync` into
`_run_auto_trade()` (scheduler) so the 9:35 AM EST trigger places the order automatically.
Until then, auto-execution is intentionally OFF (documented in `engine/scheduler.py`).

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
- **Status: ✅ Activated (India → PH tax residence change approved). Manual execution first.**

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

QQQ Mode (IBKR activated — TRADING_MODE=qqq):
  - 9:35 AM EST (13:35 UTC): Auto-generate signal ONLY (manual execution via /live-execute?mode=qqq)
  - 4:05 PM EST (20:05 UTC): EOD verify expiry result
  - Every 55 seconds: IBKR session heartbeat (tickle)
  - Scheduler boot: IBKR startup OAuth auth (self-healing across restarts)
```

### Deployment

| Environment | Status | Details |
|-------------|--------|---------|
| GitHub (main) | ✅ Up to date | Auto-deploys to Railway |
| Railway (production) | ✅ Running | Hosts both NIFTY signals + QQQ |
| Kite Auth (NIFTY) | ✅ Connected | OAuth flow verified, API key set |
| IBKR Auth (QQQ) | ✅ Activated | PH account live. Set env vars: IBKR_CLIENT_ID, IBKR_ACCOUNT_ID, IBKR_PRIVATE_KEY_PEM |

---

## 6. TRADE HISTORY

| Date | Mode | Strategy | Result | Notes |
|------|------|----------|--------|-------|
| Aug 5, 2026 | NIFTY | Scalp (3 round-trips) | +₹3,120 | 24950CE +₹709, 24250CE +₹2,408, 24250PE +₹3 |
| Aug 6, 2026 | NIFTY | Scalp (2 round-trips) | +₹16.25 | 25000CE +₹13, 24300PE +₹3.25 |
| Aug 12, 2026 | NIFTY | IC ±250pt | TBD | Manual execution, successful placement |
| Aug 24–25, 2026 | NIFTY | IC (23850/23750 PE + 24350/24450 CE, 65 qty) | +₹1,927.25 gross / ~₹1,450 net *(provisional)* | Entered Aug 24. Hit expiry-day ELM margin call (see Risk Register); added ₹54k to clear the shortfall (avoid penalty/square-off), NOT to hold to expiry. Exited Aug 25 (Tue) at market open, ~89% of max credit captured. Gross +₹1,927.25 (Positions tab); net ~₹1,450 after ~₹477 charges (shown as "Unrealised" due to Kite's overnight-carry bucketing). **Exact net pending tradebook upload (T+1, avail Aug 26).** Entry credit ~₹33.2/sh → close cost ~₹3.6/sh. |

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
| IBKR PH account restricted/frozen | QQQ mode dead | RESOLVED for now (account activated). Fallback: explore alternative brokers (Tastytrade, Saxo) |
| Manual QQQ execution during IST night hours | Missed/late trade (US market open = IST night) | Manual-first is deliberate for learning; switch to hands-off automation once fills validated |
| NIFTY gaps beyond ±250pt | Max loss ₹3,980 per trade | Pre-committed stop rules; weekly expiry limits exposure |
| **Expiry-day ELM margin spike (NIFTY)** | Additional ELM on expiring contracts can nearly double margin requirement. Observed 24 Aug 2026: required jumped to ₹1,32,367 vs ₹78,556 available → ~₹53,811 extra needed by 9:14 AM, risking penalty/auto-square-off | ₹75k capital covers steady-state margin (~₹67k) but NOT the expiry-day ELM peak. Mitigation: exit/de-risk expiring positions before expiry day (aligns with 50% profit target), or hold ~₹55k buffer. Do not carry an open IC into expiry morning without either. |
| Railway downtime | Missed signal | Email still sends; manual check of live-nifty.html |
| Kite token expiry | Can't fetch LTP for signals | Daily re-auth via login flow |
| QQQ gaps >$15 overnight (earnings) | Loss capped at $500 (Phase 1) | $5 wings; FOMC/CPI/NFP event filter skips high-impact days |
| IBKR connection failure | Missed trade | Retry logic (3x exponential backoff); self-healing restart auth |
| Slippage higher than backtest | EV reduced or negative | Phase 1 validates; stop if >$12/trade |
| Partial execution (QQQ) — orphaned long wings | Longs bleed theta fast on 0DTE with no offsetting credit → avoidable loss | Execute IC ATOMICALLY as a combo (conidex). On combo failure, RETRY combo at adjusted limit; do NOT split into individual market orders. If combo still won't fill → place no legs, skip trade + alert. (Individual-leg fallback deprecated per external review — legging risk on 0DTE outweighs the missed-trade cost.) |

---

## 9. NEXT ACTIONS

### Immediate (Do after restart)
- [ ] Clean old test trades from Railway: visit `options-tycoon.com/api/live/cleanup-old-trades?before=2026-08-05` (DELETE request from browser console)
- [ ] Re-upload tradebook CSV on production to populate real trades only

### QQQ — Activation in progress (manual execution first)
- [x] IBKR document validation (India → PH tax residence) — APPROVED, account activated
- [ ] **BLOCKER: Upgrade options permission.** Account is at Level 1 (long/covered only). Update financial profile, then request the level that includes **spreads / iron condors** (Level 3 on this account). QQQ is an ETF, so Index Options permission is NOT needed. Do not trade until approved.
- [ ] Set IBKR env vars on Railway: IBKR_CLIENT_ID, IBKR_ACCOUNT_ID, IBKR_PRIVATE_KEY_PEM
- [ ] Set TRADING_MODE=qqq so scheduler uses EST times + IBKR heartbeat
- [ ] Confirm IBKR OAuth auth succeeds (check scheduler startup log / heartbeat)
- [ ] Execute first QQQ IC manually via /api/live/live-execute?mode=qqq (1 contract)
- [ ] Verify fills in IBKR + EOD resolution logs correctly
- [ ] After several validated manual trades → switch to hands-off (wire execute_qqq_sync into scheduler)

### Active (NIFTY)
- [x] Generate daily signals with basket-ready format
- [x] 50% profit target exit rule + Telegram alerts
- [x] Trade history tracking via Tradebook CSV upload
- [x] Kite API order fetch for real-time import
- [ ] Continue logging all trades for performance review
- [ ] Validate profit target alerts work in next trading cycle

### Future (QQQ — path to hands-off)
- [ ] Fund $1,000 via Wise → IBKR (if not already funded)
- [ ] Complete several manual Phase 1 trades and review fills/slippage
- [ ] Wire execute_qqq_sync into scheduler _run_auto_trade() to enable auto-execution
- [ ] Monitor first automated trades closely before scaling contracts

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
