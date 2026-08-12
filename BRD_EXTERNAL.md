# OPTIONS TYCOON — Business Requirements Document (BRD)

> **Version:** 7.0 | **Last Updated:** 2026-08-06
> **Status:** NIFTY Live Trading (Kite connected, executing) | QQQ pending IBKR activation
> **Disclaimer:** Personal trading tool. Not financial advice.

---

## 1. SYSTEM OVERVIEW

Options Tycoon operates in **two independent modes** on the same infrastructure:

| Mode | Market | Broker | Underlying | Status |
|------|--------|--------|-----------|--------|
| **NIFTY** | India (NSE) | Zerodha (Kite) | NIFTY 50 Index | ✅ Live — Kite connected, executing trades (Aug 5: +₹3K manual) |
| **QQQ** | US (NASDAQ) | Interactive Brokers | QQQ ETF (Nasdaq 100) | ✅ Code complete — IBKR account pending activation |

Both modes share: Railway hosting, PostgreSQL DB, signal history, UI, automated scheduler.
Both modes are independent: different broker APIs, different strategies, different schedules.

---

## 2. MODE A: QQQ (US Market via IBKR) — PRIMARY

### Strategy
**QQQ ±$15 Iron Condor, $5 wings (Phase 1), daily, hold to same-day expiry (0DTE)**

> Wing width starts at $5 during Phase 1 ($1K capital) to limit max loss to $500.
> Increases to $7 after capital exceeds $2,500.

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

### Execution

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

You: Sleep through it. Check results in the morning.
```

### Capital & Scaling

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
- API: **IBKR Web API v1.0** (REST/HTTPS + OAuth 2.0 private_key_jwt)
- No TWS/Gateway required — runs headless on Railway
- Order type: Combo order (4-leg IC) with individual-leg fallback
- Auth: OAuth 2.0 (signed JWT → access token, auto-refresh)
- Session: Heartbeat tickle every 55s via background scheduler
- Data: Real-time QQQ price from `/iserver/marketdata/snapshot`
- Contract resolution: Symbol → conid → option chain → specific strikes
- Settlement: Automatic (0DTE expiry)
- Funding: Wise USD → IBKR wire

---

## 3. MODE B: NIFTY (India via Zerodha) — ON HOLD (Capital Insufficient)

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

### CURRENT PROBLEM: Margin Requirement vs Capital

| Item | Amount |
|------|--------|
| Available capital | ₹38,814 |
| **Actual margin required** (Kite basket, 4-leg IC, NRML) | **₹67,234** |
| **Shortfall** | **₹28,420** |

**Root cause:** Zerodha's margin for a 1-lot NIFTY Iron Condor (±250pt, 100pt wings, NRML) is ₹67K — not ₹35K as originally estimated. The ₹35K estimate was wrong. Kite's basket order shows the actual "Final margin" which includes SPAN + exposure margin for the spread.

**Why auto-execution via API failed additionally:**
1. Kite IP whitelist: Railway changes outbound IP on every deploy. Kite allows only 2 whitelisted IPs, updatable once per week.
2. Kite blocks market orders via API (requires LIMIT with price).
3. Individual API legs don't get spread margin — need basket order via web UI.

### OPTIONS FOR EXTERNAL REVIEW

| Option | Capital Needed | Monthly Return | Notes |
|--------|---------------|----------------|-------|
| **A: Fund ₹70K for NIFTY (NRML)** | ₹70,000 | ~₹15-18K (21-25% monthly) | Manual basket order on Kite web. Hold to Tuesday expiry. System generates signals + emails strikes. EOD auto-tracked. |
| **B: Use MIS (Intraday) with ₹38K** | ₹38,000 (current) | Needs validation | Intraday margin is lower (~₹20-25K for IC spread). Positions auto-close at 3:25 PM IST — cannot hold to expiry. Theta decay benefit reduced. |
| **C: Reduce wings to 50pt** | ~₹35-40K (current) | ~₹800-1,200/month | Smaller max loss, lower margin. May not be profitable after ₹238 charges per trade. Needs backtesting. |
| **D: Sell only one side (credit spread, not IC)** | ~₹35K | ~₹1,000-1,500/month | 2-leg trade instead of 4-leg. Lower margin. Higher directional risk. |

### Questions for Reviewer

1. Is MIS (intraday) viable for Iron Condor at ₹38K? What's the actual intraday margin for a 1-lot NIFTY IC spread?
2. With 50pt wings instead of 100pt: does the reward-to-charges ratio still make sense (charges are ₹238 fixed)?
3. Is a single credit spread (bull put or bear call, 2 legs) a better fit for ₹38K capital?
4. Any broker alternatives to Zerodha that give better spread margin for API-based execution?

### Execution Model (Revised)

```
SIGNAL GENERATION (automated, 9:20 AM IST daily):
  - System generates signal on Railway
  - Sends EMAIL to founder with exact strikes + order sequence
  - Signal visible on live-nifty.html page

EXECUTION (manual by user):
  - User opens Kite WEB (not app)
  - Creates basket order with 4 legs (BUY first, SELL second)
  - Kite calculates spread margin (₹67K for current strategy)
  - User executes if margin available

EOD TRACKING (automated, 3:35 PM IST daily):
  - System checks NIFTY close vs short strikes
  - Resolves win/loss on Tuesday expiry
  - Logs to DB for performance tracking

NO AUTO-EXECUTION via API — margin and IP issues make it unreliable.
```

### Status (as of Aug 6, 2026)
- Zerodha NFO: ✅ Activated
- Kite API: ✅ Connected (Badakala Raghu Raj) — used for price data + signal generation
- First live trade: Aug 5, 2026 — +₹3K profit (placed manually via basket order)
- Auto-execution: ❌ Not viable (IP whitelist + margin issues)
- Current mode: Signal generation + email alerts → user places manually
- Account balance: ₹38,814
- Margin needed: ₹67,234 (shortfall ₹28,420)
- **Decision needed: Fund more or pivot to QQQ**

---

## 4. TECHNICAL ARCHITECTURE (Dual-Mode)

### Code Structure

```
engine/
├── signals/
│   ├── simple_ic_engine.py     → NIFTY signal generator
│   ├── qqq_ic_engine.py        → QQQ signal generator ✅
│   ├── signal_engine.py        → Main orchestrator (pattern match pipeline) ✅
│   ├── data_fetcher.py         → yfinance global data collection ✅
│   ├── pattern_matcher.py      → Statistical pattern bucketing ✅
│   ├── quality_filters.py      → 7-filter quality gate ✅
│   ├── strategy_picker.py      → Conditions → strategy → strikes ✅
│   └── stock_scanner.py        → Watchlist stock scanning ✅
├── broker/
│   ├── kite_auth.py            → Zerodha OAuth + LTP ✅
│   ├── kite_executor.py        → NIFTY order placement ✅
│   ├── kite_ticker.py          → Zerodha WebSocket live quotes ✅
│   └── ibkr_executor.py        → QQQ IBKR REST API v1.0 executor ✅ (NEW — complete)
├── scheduler.py                → Dual scheduler + IBKR heartbeat ✅ (updated)
└── session.py                  → Founder allowlist (unchanged)

routes/
├── live.py                     → Serves both modes (NIFTY/QQQ) based on TRADING_MODE ✅
├── auth.py                     → Google OAuth + session management ✅
├── behavioral.py               → Behavioral metrics API ✅
├── dashboard.py                → Dashboard data endpoints ✅
├── data.py                     → Options chain + market data ✅
├── portfolio.py                → Profile CRUD ✅
├── trading.py                  → Trade execution ✅
└── (8 more route modules)

config/
└── settings.json               → Has both NIFTY and QQQ parameters ✅
```

### Configuration (Live on Railway)

```json
{
  "trading_mode": "qqq",
  "nifty": {
    "capital": 15000,
    "offset_pts": 250,
    "wing_width": 100,
    "lot_size": 65
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
| IBKR_ACCOUNT_ID | Account number (e.g., U12345678) | (not used) |
| IBKR_PRIVATE_KEY_PEM | RSA private key (PEM) | (not used) |
| KITE_API_KEY | (not used) | (set) |
| KITE_API_SECRET | (not used) | (set) |
| FOUNDER_ALLOWED_EMAILS | (set) | (set) |

### Scheduler (Dual Timezone)

```
QQQ Mode:
  - 9:35 AM EST (13:35 UTC): Auto-generate signal + place trade
  - 4:05 PM EST (20:05 UTC): EOD verify expiry result
  - Every 55 seconds: IBKR session heartbeat (tickle)
  
NIFTY Mode:
  - 9:15 AM IST: Place trade (if market day)
  - 3:35 PM IST: EOD SL check
  - Tuesday 3:35 PM IST: Expiry resolution
```

---

## 5. VALIDATION HISTORY

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

## 6. PHASED DEPLOYMENT

### Phase 1: Slippage Discovery (QQQ)
- Capital: $1,000
- Contracts: 1
- Duration: 10 trades
- Goal: Confirm real fills match backtest ($8/trade)
- Stop if: slippage > $12/trade

### Phase 2: Validation (QQQ)
- Capital: $2,000
- Contracts: 1-2
- Duration: 50 trades
- Goal: Confirm win rate + drawdown match Monte Carlo
- Stop if: drawdown > $1,500 or win rate < 90%

### Phase 3: Scale (QQQ)
- Capital: $5,000-$50,000
- Contracts: proportional to capital
- Full drawdown protocol applies
- Monthly review

### NIFTY (Parallel, when wife's account is ready)
- Same phase approach
- Capital: Rs.15,000 initially
- Independent from QQQ

---

## 7. RISK REGISTER

| Risk | Impact | Mitigation |
|------|--------|-----------|
| QQQ gaps >$15 overnight (earnings) | Loss capped at $500 (Phase 1) | $5 wings; FOMC/CPI/NFP event filter skips trade on high-impact days |
| IBKR connection failure | Missed trade | Retry logic (3x exponential backoff); self-healing restart auth; manual backup via IBKR app |
| Slippage higher than backtest | EV reduced or negative | Phase 1 validates; stop if >$12/trade |
| Partial execution (some legs fail) | Unhedged position | Risk-first ordering (BUY wings first); abort SELL if wing fails; Telegram alert for manual intervention |
| Extended loss streak | Drawdown | Pre-committed rules in Section 2 |
| Regulatory change (PH taxes foreign gains) | Tax liability | Monitor annually; currently 0% |
| Railway downtime/restart | Missed trade or expired session | Self-healing `_ibkr_startup_auth()` on boot; heartbeat every 55s |

---

## 8. NEXT STEPS

### ⏰ TOMORROW MORNING (July 31, 2026)

1. Login to Kite: `options-tycoon.com/static/live-nifty.html` → click "Login to Zerodha"
2. Verify: "🟢 Zerodha Connected" shows
3. Click "Generate Signal" → should show NIFTY IC trade card with ₹ values
4. If NFO segment is active → click "Execute" for FIRST REAL TRADE
5. If NFO still pending → just verify signal looks correct, don't execute

### System Status (July 30, 2026 — End of Day)

| System | Status | Next Action |
|--------|--------|-------------|
| **NIFTY Trading** | ✅ Code complete, Kite connected (MEA520), signal engine validated | Execute first trade tomorrow (NFO activating tonight 10:20 PM IST) |
| **QQQ Trading** | ✅ Code complete, deployed to Railway | Wait for IBKR account activation → set env vars → paper test |
| **BuyAI Tech Pipeline** | ✅ Code on GitHub, credentials in Railway | Deploy to Railway when ready for first teaser video |

### Full Pending List

**Trading (Priority 1):**
1. [x] Strategy validated (QQQ: 7 rounds, NIFTY: 5 rounds)
2. [x] BRD updated with dual-mode architecture
3. [x] QQQ/IBKR execution module complete + deployed
4. [x] NIFTY/Kite execution module complete + deployed
5. [x] Kite OAuth working (MEA520 — Badakala Raghu Raj)
6. [x] Signal engine validated (NIFTY: ₹970 credit, expiry Aug 4 Tue)
7. [x] Independent pages (NIFTY + QQQ each get their own signal)
8. [x] Code deployed to Railway (commit `6c5b947`)
9. [ ] **NIFTY first live trade** ← TOMORROW
10. [ ] IBKR account activation → QQQ paper sandbox
11. [ ] Fund $1,000 via Wise → IBKR

**BuyAI Tech Content Pipeline (Priority 2):**
12. [x] Pipeline code built (13 modules)
13. [x] Pushed to GitHub (`pativija96-tech/BuyAI-Tech`)
14. [x] All credentials saved in Railway (ElevenLabs, X, YouTube)
15. [ ] Deploy to Railway (when ready for first teaser)
16. [ ] Add `OPTIONS_TYCOON_DB_URL` (when live trade data flows)
17. [ ] First teaser video published
18. [ ] Set up cron schedule (daily post-market)

### Deployment Status

| Environment | Status | Last Deploy | Commit |
|-------------|--------|-------------|--------|
| GitHub (`main`) | ✅ Up to date | July 30, 2026 | `6c5b947` |
| Railway (production) | ✅ Auto-deployed from `main` | July 30, 2026 | `6c5b947` |
| Local (dev laptop) | ✅ Clean working tree | — | Same as above |
| Kite Auth (NIFTY) | ✅ Connected (MEA520) | — | OAuth flow verified |
| IBKR Auth (QQQ) | ⏳ Pending account activation | — | Env vars not set yet |

### NIFTY Dry-Run Results (July 30, 2026)

| Parameter | Value |
|-----------|-------|
| NIFTY Price | 24,261 (yfinance) |
| VIX | 12.2% |
| Short Call | 24,500 CE |
| Long Call | 24,600 CE |
| Short Put | 24,000 PE |
| Long Put | 23,900 PE |
| Net Credit | ₹970 (25 qty × ₹38.8/share) |
| Max Loss | ₹1,530 |
| Max Profit | ₹970 |
| Risk % of Capital | 11.8% |
| Expiry | Aug 4, 2026 (Tuesday) |
| Signal Status | ✅ Trade generated correctly |
| Kite Auth | ✅ Connected (Badakala Raghu Raj) |
| NFO Segment | ⏳ Pending (blocks order placement only) |

### Pre-Launch Checklist (Phase 1 Readiness)

| # | Item | Status |
|---|------|--------|
| 1 | IBKR Paper Sandbox Testing | ⏳ Blocked on account activation |
| 2 | Phase 1 Wing Width Adjustment ($5 wings, $500 max loss) | ✅ Done — `config/settings.json` updated, executor reads from config |
| 3 | Telegram Integration (execution alerts) | ✅ Done — `_notify_trade_result()` wired into `execute_qqq_sync` |
| 4 | Event Calendar Audit (FOMC/CPI/NFP 2026) | ✅ Done — 40 events in `event_calendar.json` |
| 5 | Wise USD Liquidity Pipeline | ⏳ Manual action (owner) |
| 6 | FOMC/Earnings event filter in signal engine | ✅ Done — `_is_high_impact_event_day()` in `qqq_ic_engine.py` |
| 7 | Risk-first individual-leg ordering | ✅ Done — BUY wings first, abort if wing fails |
| 8 | Railway restart self-healing | ✅ Done — `_ibkr_startup_auth()` on scheduler boot |
| 9 | Mock test suite (14 tests) | ✅ Done — `tests/test_ibkr_executor.py` all passing |
| 10 | Retry + partial execution recovery | ✅ Done — exponential backoff, partial fill detection |
| 11 | Code pushed to GitHub + Railway | ✅ Done — commit `75734a3` deployed |
| 12 | Set IBKR env vars in Railway | ⏳ After account activation |

### Remaining Technical Items
- [x] Mock/dry-run test suite for `execute_qqq_sync` (14 tests passing)
- [x] Error handling + retry for partial execution / connection timeout
- [x] FOMC / CPI / Earnings event filter — skips 0DTE on high-impact days
- [x] Risk-first individual-leg ordering (BUY wings first)
- [x] Self-healing scheduler startup (re-auth on Railway restart)
- [x] Telegram notification integration for trade results
- [x] Phase 1 wing width adjusted to $5 (configurable via settings.json)
- [x] Code deployed to production (GitHub → Railway auto-deploy)
- [ ] EOD resolution endpoint wiring for QQQ mode (auto-settle 0DTE)
- [ ] Mid-price limit order with price-walking (pending IBKR paper testing)
- [ ] Set Railway env vars: IBKR_CLIENT_ID, IBKR_ACCOUNT_ID, IBKR_PRIVATE_KEY_PEM

---

## 9. IBKR EXECUTOR — IMPLEMENTATION SUMMARY (v1.0 Complete)

### Architecture
Pure REST/HTTPS — no TWS, no Gateway, no `ib_insync`. Runs headless on Railway.

### Components Built

| Component | File | Status |
|-----------|------|--------|
| OAuth 2.0 Auth (private_key_jwt) | `engine/broker/ibkr_executor.py` | ✅ |
| Session Heartbeat (tickle every 55s) | `engine/scheduler.py` | ✅ |
| Contract Resolution (symbol → conid) | `engine/broker/ibkr_executor.py` | ✅ |
| Option Chain Fetch | `engine/broker/ibkr_executor.py` | ✅ |
| Option Conid Resolution (strike+right+expiry) | `engine/broker/ibkr_executor.py` | ✅ |
| QQQ Live Price (market data snapshot) | `engine/broker/ibkr_executor.py` | ✅ |
| 4-Leg Iron Condor Combo Order | `engine/broker/ibkr_executor.py` | ✅ |
| Individual-Leg Fallback (if combo fails) | `engine/broker/ibkr_executor.py` | ✅ |
| Auto-Confirm Order Prompts | `engine/broker/ibkr_executor.py` | ✅ |
| Top-level Entry Point (`execute_qqq_sync`) | `engine/broker/ibkr_executor.py` | ✅ |
| yfinance Price Fallback | `engine/broker/ibkr_executor.py` | ✅ |
| Route Integration (`/api/live/live-execute`) | `routes/live.py` | ✅ |

### Execution Flow
```
Scheduler (9:35 AM EST) → generate signal → live-execute endpoint
  → authenticate() (OAuth 2.0 signed JWT → access token)
  → get_qqq_price() (IBKR market data, yfinance fallback)
  → place_iron_condor(spot_price)
    → search_contract("QQQ") → conid
    → resolve_option_conid() × 4 legs (strike/right/expiry → option conid)
    → submit combo order (all 4 legs in one ticket)
    → if combo fails → _place_individual_legs() fallback
    → auto-confirm order prompts
  → return result to DB

Scheduler (every 55s) → send_heartbeat() → /iserver/tickle

Scheduler (4:05 PM EST) → run EOD → settle 0DTE
```

### Dependencies
```
PyJWT[crypto]>=2.8.0    # Signed JWT for OAuth 2.0
cryptography>=41.0.0    # RSA key handling
httpx                   # HTTP client (already in project)
```

---

## 10. EXTERNAL REVIEW RESPONSE (Grade: A — July 28, 2026)

### Feedback Received & Actions Taken

| # | Feedback Item | Status | Implementation |
|---|---------------|--------|----------------|
| 1 | FOMC / Earnings event filter | ✅ Done | `qqq_ic_engine.py` checks `event_calendar.json` (FOMC, CPI, NFP dates). Skips trade on high-impact days. |
| 2 | Mid-price limit order with price-walking | ⏳ Pending paper test | Combo orders need live IBKR connection to fetch mid-price. Architecture ready, will implement price-walking during paper sandbox phase. |
| 3 | Risk-first individual-leg ordering | ✅ Done | `_place_individual_legs()` places BUY (wings) first. If wing fails → aborts before placing naked SELL legs. |
| 4 | Railway restart self-healing | ✅ Done | `_ibkr_startup_auth()` re-authenticates on scheduler startup. Handles Railway deploy cycles seamlessly. |
| 5 | Telegram/Webhook alerts for execution | ✅ Done | `_notify_trade_result()` sends success/failure/partial-execution alerts via Telegram immediately after order. |
| 6 | Wing width reduction for Phase 1 | ✅ Done | `config/settings.json` now sets `qqq.wing_width: 5` ($500 max loss). Both `ibkr_executor.py` and `qqq_ic_engine.py` read from config. Will increase to $7 after $2.5K capital. |
| 7 | DB row-level locking for dual-timezone | ✅ N/A | Scheduler runs one mode at a time (`TRADING_MODE` env var). No concurrent NIFTY+QQQ writes possible on same instance. |

### Safety Improvements Implemented

1. **Retry with exponential backoff** — All IBKR API calls retry 3× on timeout (1s, 2s, 4s delays)
2. **Order prompt depth cap** — Max 5 confirmation rounds to prevent infinite recursion
3. **IBKR cold-start handling** — Market data sometimes returns empty on first request; auto-retries after 2s
4. **Partial execution detection** — Tracks `filled_count` vs `failed_count`, logs explicit warnings
5. **Risk-first leg ordering** — Never places a naked short; BUY wings are placed before SELL shorts
6. **Event calendar filter** — 8 FOMC + 12 CPI + 12 NFP dates blocked for 2026

---

*End of BRD v6.1. Dual-mode system: QQQ (primary, tax-free, execution module complete & deployed) + NIFTY (secondary, via wife's account). Both validated, independent, same infrastructure. No laptop dependency — runs fully on Railway.*
