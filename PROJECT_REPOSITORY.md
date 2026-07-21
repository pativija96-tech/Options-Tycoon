# OPTIONS TYCOON — Project Repository

> **Single Source of Truth** — BRD, TRD, Features, API Inventory, Build Status
> Last Updated: 2026-07-06

---

## 0. PRODUCT PIVOT (July 2026) — DNA Tracking & Improvement

> ⚠️ This section supersedes the original gaming-first approach. The core product is now **behavioral DNA tracking from real trade data**, not the paper-trading simulator.

### New Core Product: Trader DNA Intelligence

**What it is:** Upload your broker trade history (CSV) → Get AI-powered behavioral analysis → Track improvement over time with weekly uploads.

**What it's NOT:** A paper-trading game. The $10K simulator is retained as a secondary "Practice Arena" feature, not the main product.

### Why the Pivot
- Paper trading has no emotional stakes — traders know it's fake
- Dozens of free paper trading apps already exist
- The **DNA Report from real data** is the unique value — nobody else does this for Indian retail options traders
- People will pay for ongoing tracking/improvement, not for a practice game

### New User Flow
```
1. LANDING → "See why you keep losing" (public)
2. UPLOAD CSV → Upload broker trade history (public, no login)
3. SIGN-IN GATE → "Your report is ready — sign in to see it" (captures email)
4. DNA REPORT → The devastating reveal (first-time wow moment)
5. DASHBOARD → Score trends, upload again, Fix One Thing (logged-in home)
6. WEEKLY UPLOAD → Track improvement over time (retention hook)
7. PRACTICE ARENA → $10K simulator (secondary, accessible from dashboard)
```

### Revenue Model (Phases)
- **Phase 1 (Now):** Everything FREE for first 100 users. Capture emails.
- **Phase 2 (After 100 users):** ₹499/month or ₹2999/year for PREMIUM features:
  - **Free forever (even after 100 users):** Base DNA Report (score, persona, behavioral %, patterns detected, story)
  - **Paid features (user 101+):**
    - Full report with drill-down to exact trades (click pattern → see which trades → timestamp, ₹ amount, what triggered it)
    - "How to fix" guidance per pattern (personalized advice cards)
    - Weekly upload tracking (score trend over time)
    - Email alerts ("Your pattern repeated today")
    - Compare this month vs last month
    - Export PDF of full report
    - Team/group features
- **Phase 3 (Scale):** Custom pricing, broker API integration, enterprise features

### Authentication (Phases)
- **Phase 1 (Now):** Google Sign-In only (free, 1-click, captures email)
- **Phase 2 (After 10-20 users):** Email + Password option
- **Phase 3 (When scaling):** Mobile OTP (₹0.15-0.25/msg via MSG91/Twilio)

### Notification System (Phases)
- **Phase 1 (Now):** Dashboard shows score history (no active notifications yet)
- **Phase 2:** Weekly email digest ("Your score changed: 34→41. Upload this week to keep tracking.")
- **Phase 3:** Browser push notifications + WhatsApp reminders

### Key Metrics to Track Per User
| Metric | Frequency |
|--------|-----------|
| DNA Score (0-100) | Per upload |
| Behavioral Loss % | Per upload |
| Fix One Thing recommendation | Per upload |
| Revenge Trade count | Per upload |
| Overconfidence count | Per upload |
| Impulse Exit count | Per upload |
| Discipline Rating | Per upload |
| Score trend (improving/declining) | Weekly |

### Pages & Their New Roles
| Page | Purpose | Auth Required |
|------|---------|--------------|
| `/` (landing) | Hook — "See why you keep losing" | No |
| `/static/upload-free.html` | Upload CSV | No |
| `/static/signin.html` | Google Sign-In gate | No (is the gate) |
| `/static/report.html` | DNA Report reveal | Yes |
| `/static/dashboard.html` | **HOME** — score trends, upload again, Fix One Thing | Yes |
| `/static/index.html` | Practice Arena ($10K sim) | Yes |
| `/static/behavioral.html` | Detailed metrics view | Yes |

### Cost for 100 Users
| Item | Monthly Cost |
|------|-------------|
| Railway hosting | $0-15 |
| Google Sign-In | Free |
| GitHub | Free |
| Domain (optional) | ~$1/month |
| **Total** | **₹0-1,200/month** |

---

## 1. Product Vision

Options Tycoon is a **behavioral intelligence platform** for options traders. It analyzes real trade history to detect self-sabotage patterns (revenge trading, overconfidence, impulse exits, disposition bias) and tracks improvement over time. The platform is a **mirror** — it shows users their own data without ever providing financial advice.

**Target User:** Retail options traders (primarily Indian market — NSE/BSE) who want to understand their own behavioral tendencies and improve trading discipline through data-driven self-observation.

**Core Value Proposition:** "We show you WHY you keep losing." Upload your broker trade history, get a brutal behavioral analysis, track your improvement weekly.

**Key Differentiators:**
- Instant DNA Report from real broker CSV (Zerodha, Groww, Angel One)
- Quantifies behavioral cost in ₹ (not vague advice)
- "Fix One Thing" — single actionable pattern to fix each week
- Score progression tracking (are you actually improving?)
- No financial advice ever (observational language only)
- Practice Arena available for building discipline

**Target User:** Retail options traders (primarily Indian market — NSE/BSE) who want to practice strategies, understand their own behavioral tendencies, and improve trading discipline through self-observation.

**Core Value Proposition:** "Mirror, not advisor" — the platform reflects your behavioral data back to you. It tracks patterns like revenge trading, overconfidence, impulse exits, and sizing inconsistency without ever telling you what to do. Think fitness tracker for trading psychology.

**Key Differentiators:**
- No financial advice ever (observational language only)
- Behavioral profiling from day one (progressive unlock A→B→C→D)
- No-reset game-over mechanic (permanent consequences create real stakes)
- Compare Mode (sim vs real parallel tracking)
- Instant Trader DNA from broker CSV upload (skip 25-trade wait)
- Fully local-first (no cloud, no data leaves your machine)
- One-folder isolation (delete folder = complete removal)

---

## 2. Business Requirements (BRD Summary)

**58 requirements across 7 phases.**

### Phase 1: Core Trading Simulation Engine (Reqs 1–12)

| # | Requirement | One-Line Description |
|---|-------------|---------------------|
| 1 | Virtual Portfolio Initialization | $10,000 starting balance, game-over at $0, no reset |
| 2 | Desktop 3-Pane Layout | Search + Options Chain + HUD panels, all visible simultaneously |
| 3 | Options Chain Display | Matrix of calls/puts by strike with bid/ask/volume/OI/IV, expiry tabs |
| 4 | Greeks Calculator | Black-Scholes Delta, Gamma, Theta, Vega for every contract, 4 decimals |
| 5 | IV Rank Tracking | Percentile of current IV vs 52-week range (0-100%), "Insufficient Data" if <20 points |
| 6 | Strategy Game Cards | Predefined templates: Iron Condor, Vertical Spread, Straddle, Strangle |
| 7 | Multi-Leg Strategy Builder | Custom 1-4 leg combos with max profit/loss/breakeven display |
| 8 | Trade Execution (Deploy Credits) | Execute paper trades, deduct cost + slippage, record to DB |
| 9 | Position Tracker | Open positions with live unrealized P&L, leg-by-leg breakdown |
| 10 | Mock Data Fallback | 10+ bundled JSON tickers, full offline operation |
| 11 | Legal Disclaimer | First-visit modal + persistent footer, no advisory language |
| 12 | SQLite Database | Local-only storage, auto-create on first launch, no external transmission |

### Phase 2: Behavioral Intelligence Engine (Reqs 13–26)

| # | Requirement | One-Line Description |
|---|-------------|---------------------|
| 13 | Discipline Rating | % of trades within 5% risk cap (0-100%) |
| 14 | Patience Score | Average seconds between chain open and trade execution |
| 15 | Sizing Consistency | Std deviation of position sizes as % of portfolio |
| 16 | Emotional Reactivity Score | Composite 0-100 from revenge/overconfidence/impulse/disposition |
| 17 | Revenge Trading Detector | Flag: size >150% avg AND loss within 24h |
| 18 | Overconfidence Trap Detector | Flag: size >150% avg AND 3+ consecutive wins preceding |
| 19 | Loss Disposition Bias Detector | Ratio of avg losing hold time vs avg winning hold time, flag if >1.2 |
| 20 | Impulse Early Exit Detector | Flag: closed at profit < 25% of peak unrealized profit |
| 21 | 25-Trade Diagnostic Summary | Auto-generated text narrative, observational language only |
| 22 | P&L Equity Curve Chart | Line chart of portfolio balance over time |
| 23 | Trade Journal | Free-text notes per trade, max 1000 chars |
| 24 | Visual Gauge Bars | Horizontal gauges (green/yellow/red) for all 4 behavioral metrics |
| 25 | Win/Loss Flash Feedback | Green flash (2s) on profit, red flash (2s) on loss |
| 26 | Progressive Profile Building | "Building Profile..." until 25 trades, "Preliminary" labels |

### Phase 3: Risk Guards & Discipline Mechanics (Reqs 27–38)

| # | Requirement | One-Line Description |
|---|-------------|---------------------|
| 27 | Anti-Impulse Risk Gate | Warning when max loss >5% of portfolio (does NOT prevent trade) |
| 28 | IV Crush Gate | Notice when earnings event within 48h (observational only) |
| 29 | Bid-Ask Slippage Gauge | 50% of spread deducted as friction at entry |
| 30 | Pre-Trade Behavioral State Display | Show current metrics before each trade with disclaimer |
| 31 | Earnings Calendar | Static JSON of upcoming earnings, display in chain pane |
| 32 | Manual Early Close with Outcome Tagging | Close positions early, tag as Success/Failure/Slippage |
| 33 | Telemetry Logging | Write every pre-trade display to feedback_loop.json |
| 34 | No-Reset Rule (Game Over Mechanic) | $0 = permanent lock, preserve history, prompt new profile |
| 35 | Streak Tracking | Consecutive disciplined trades counter, current + longest |
| 36 | Self-Competition Leaderboard | Best month P&L vs current month side-by-side |
| 37 | Penalty Multiplier | Exceed 5% → max allocation drops to 3% for 24h |
| 38 | Pre-Trade Confirmation Prompt | "Would you do this with real money?" Yes/Cancel |

### Phase 4: Time Machine & Data (Reqs 39–46)

| # | Requirement | One-Line Description |
|---|-------------|---------------------|
| 39 | Historical Time Machine | Replay past market windows, trades count toward behavioral profile |
| 40 | Time Machine Speed Controls | Auto-advance (1 day/10s) or manual click-to-step |
| 41 | End-of-Day Market Data (Optional) | Yahoo Finance EOD fetch, silent fallback to mock |
| 42 | NSE Bhavcopy CSV Upload | Parse NSE F&O data, populate chain, descriptive errors |
| 43 | Expiration Settlement Engine | Auto-close at expiry: ITM at intrinsic, OTM at zero |
| 44 | Multiple Strategy Profiles | Up to 5 named sub-profiles, independent balance/metrics |
| 45 | Export Trade History to CSV | Download CSV with all fields including behavioral flags |
| 46 | Backup and Restore Database | Timestamped backup to /backups, confirm before restore |

### Phase 5: Real Trade Journal / Parallel Mode (Reqs 47–51)

| # | Requirement | One-Line Description |
|---|-------------|---------------------|
| 47 | Mode Selection | "Sim Only" vs "Sim + Real Trade Journal", switchable anytime |
| 48 | Real Trade Manual Entry | Form for logging real trades: ticker, strike, size, outcome |
| 49 | Behavioral State at Real Trade Entry | Show metrics when logging real trades, same algorithms |
| 50 | Compare Mode | Side-by-side sim vs real: equity curves + all 4 metrics + Δ difference |
| 51 | Weekly Behavioral Gap Report | Auto-report when 5+ trades each side, observational only |

### Phase 6: Monetization (Reqs 52–54)

| # | Requirement | One-Line Description |
|---|-------------|---------------------|
| 52 | Instant Trader DNA from CSV Upload | Upload Zerodha/Groww/Angel One CSV → full behavioral profile instantly |
| 53 | Free Path Progressive Unlock (Phased) | Phase A→B→C→D as trades accumulate, DNA upload → instant Phase D |
| 54 | Payment Integration Stub | Stripe/Razorpay stubs (inactive), ₹499 one-time for Trader DNA |

### Phase 7: Cross-Cutting Concerns (Reqs 55–58)

| # | Requirement | One-Line Description |
|---|-------------|---------------------|
| 55 | No Financial Advice Guarantee | No directive language anywhere, observational only |
| 56 | Zero Real-Money Connection | No brokerage API, no real instruments, all currency labeled "Virtual" |
| 57 | Project Isolation and Deletion | Single folder, no system-wide artifacts, delete folder = complete removal |
| 58 | Local-First Architecture | Localhost only, full offline operation, no external CDN for core |

---

## 3. Technical Design (TRD Summary)

### Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend | Python 3.11+ / FastAPI | REST API + static file serving |
| Frontend | Vanilla HTML/JS/CSS | No build tools, no npm, no React |
| Database | SQLite (WAL mode) | Single file, auto-created |
| Compute | SciPy (Black-Scholes) | Greeks calculation via scipy.stats.norm |
| Testing | pytest + Hypothesis | Property-based + unit + integration |
| Server | Uvicorn | ASGI server, localhost only |
| Data | Bundled JSON mock files | 10 tickers + earnings calendar |

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    BROWSER (localhost:8000)                           │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  HTML/JS/CSS Frontend (static/ directory)                    │    │
│  │  • index.html (3-pane trading)  • behavioral.html            │    │
│  │  • compare.html                 • timemachine.html            │    │
│  │  • history.html                 • upload.html • profile.html  │    │
│  └───────────────────────────┬─────────────────────────────────┘    │
└──────────────────────────────┼──────────────────────────────────────┘
                               │ HTTP (fetch API calls)
┌──────────────────────────────┼──────────────────────────────────────┐
│                    FASTAPI SERVER                                     │
│  ┌───────────────────────────┼─────────────────────────────────┐    │
│  │                    API Routes                                │    │
│  │  routes/portfolio.py    routes/trading.py    routes/data.py  │    │
│  │  routes/behavioral.py   routes/timemachine.py                │    │
│  │  routes/telemetry.py    routes/real_trades.py                │    │
│  │  routes/risk_guards.py (helper, not a router)                │    │
│  └───────────┬─────────────────────────────────┬───────────────┘    │
│              │                                  │                     │
│  ┌───────────┴───────────┐     ┌───────────────┴───────────────┐    │
│  │    Engine Modules      │     │      Data Layer                │    │
│  │  engine/greeks.py      │     │  data/loader.py               │    │
│  │  engine/behavioral.py  │     │  data/mock/*.json (10 tickers)│    │
│  │  engine/settlement.py  │     │  data/mock/earnings.json      │    │
│  │  engine/slippage.py    │     │                               │    │
│  │  engine/strategies.py  │     │                               │    │
│  └───────────┬───────────┘     └───────────────────────────────┘    │
│              │                                                        │
│  ┌───────────┴───────────────────────────────────────────────┐      │
│  │                    Database Layer                           │      │
│  │  db/database.py (connection, schema init, WAL mode)        │      │
│  │  db/models.py (Pydantic request/response models)           │      │
│  └───────────┬───────────────────────────────────────────────┘      │
└──────────────┼──────────────────────────────────────────────────────┘
               │
┌──────────────┼──────────────────────────────────────────────────────┐
│              │         LOCAL STORAGE                                  │
│  ┌───────────┴──────┐  ┌────────────────┐  ┌────────────────────┐  │
│  │ options_tycoon.db │  │ feedback_loop  │  │ backups/           │  │
│  │ (SQLite, 9 tables)│  │   .json        │  │  timestamped .db   │  │
│  └──────────────────┘  └────────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Database Tables (9 Total)

| Table | Purpose |
|-------|---------|
| `profiles` | User profiles: balance, mode, is_locked, penalty_until, payment_status |
| `strategy_profiles` | Sub-profiles for A/B testing strategies (max 5 per profile) |
| `trades` | All simulated trade records with behavioral flags, journal, timing data |
| `real_trades` | Real trade journal entries (parallel mode) with behavioral state |
| `behavioral_metrics` | Cached metric computations (recomputed on each trade) |
| `telemetry` | Pre-trade behavioral state displays (also in feedback_loop.json) |
| `earnings_calendar` | Static earnings event data for IV crush warnings |
| `market_data_cache` | Cached external/uploaded market data |
| `monthly_pnl` | Monthly P&L aggregates for self-competition leaderboard |

### API Endpoints (Complete Inventory — 40 endpoints)

#### Portfolio & Profiles (6 endpoints)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/profiles` | Create new profile (initializes $10k) |
| GET | `/api/profiles` | List all profiles |
| GET | `/api/profiles/{id}` | Get profile with balance & metrics |
| DELETE | `/api/profiles/{id}` | Delete profile |
| POST | `/api/profiles/{id}/strategy-profiles` | Create strategy sub-profile (max 5) |
| GET | `/api/profiles/{id}/strategy-profiles` | List strategy sub-profiles |

#### Market Data & Options Chain (5 endpoints)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/chain/{ticker}` | Get full options chain (mock or cached) |
| GET | `/api/chain/{ticker}?expiry={date}` | Filter chain by expiration date |
| GET | `/api/tickers` | List all available tickers |
| GET | `/api/iv-rank/{ticker}` | Get IV Rank for underlying |
| GET | `/api/earnings/{ticker}` | Get earnings calendar events |

#### Trading (5 endpoints)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/trades` | Execute trade (deploy credits) |
| GET | `/api/trades/{profile_id}` | Get trade history |
| GET | `/api/positions/{profile_id}` | Get open positions with unrealized P&L |
| POST | `/api/positions/{id}/close` | Manual early close with outcome tag |
| PUT | `/api/trades/{id}/journal` | Add/update trade journal note |

#### Behavioral Metrics (5 endpoints)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/behavioral/{profile_id}` | Get all behavioral metrics |
| GET | `/api/behavioral/{profile_id}/diagnostic` | Get diagnostic summary text |
| GET | `/api/behavioral/{profile_id}/streak` | Get streak data (current + longest) |
| GET | `/api/behavioral/{profile_id}/monthly` | Get monthly P&L for leaderboard |
| GET | `/api/behavioral/{profile_id}/weekly-gap` | Get weekly sim vs real gap report |

#### Compare Mode & Real Trades (3 endpoints)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/real-trades/{profile_id}` | Log a real trade manually |
| GET | `/api/real-trades/{profile_id}` | Get real trade history |
| GET | `/api/compare/{profile_id}` | Get side-by-side sim vs real comparison |

#### Time Machine (4 endpoints)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/timemachine/windows` | List available historical replay windows |
| POST | `/api/timemachine/start` | Start a replay session |
| POST | `/api/timemachine/advance` | Advance one day in replay |
| GET | `/api/timemachine/state` | Get current replay state |

#### Data Management (6 endpoints)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/upload/bhavcopy` | Upload NSE bhavcopy CSV |
| POST | `/api/upload/broker-csv` | Upload broker trade history (Trader DNA, ₹499) |
| GET | `/api/export/{profile_id}` | Export trade history as CSV download |
| POST | `/api/backup` | Create timestamped database backup |
| POST | `/api/restore` | Restore database from backup |
| GET | `/api/telemetry/{profile_id}` | Get telemetry log entries |

#### System (2 endpoints)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Redirect to /static/index.html |
| GET | `/health` | Health check (status: ok) |

### Backend Modules (All Files)

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app entry, route mounting, CORS, startup, static serving |
| `routes/portfolio.py` | Profile CRUD, game-over detection, strategy sub-profiles |
| `routes/trading.py` | Trade execution, position management, journal, slippage |
| `routes/data.py` | Options chain, market data, tickers, CSV upload, export, backup |
| `routes/behavioral.py` | Behavioral metrics API, diagnostic, streak, monthly, weekly gap |
| `routes/telemetry.py` | Telemetry log read endpoint |
| `routes/real_trades.py` | Real trade CRUD, compare mode endpoint |
| `routes/timemachine.py` | Historical replay session management |
| `routes/risk_guards.py` | Risk gate, IV crush, penalty, pre-trade state (helper module) |
| `engine/greeks.py` | Black-Scholes Greeks + IV Rank computation |
| `engine/behavioral.py` | All behavioral algorithms + diagnostic generation |
| `engine/settlement.py` | Expiration auto-close at intrinsic value |
| `engine/slippage.py` | Bid-ask slippage cost calculation |
| `engine/strategies.py` | Strategy card templates + multi-leg builder logic |
| `db/database.py` | SQLite connection, schema init (9 tables), WAL mode |
| `db/models.py` | Pydantic models for request/response validation |
| `data/loader.py` | JSON mock data loading and caching |
| `seed_demo.py` | Demo data seeder for testing |

### Frontend Pages (Planned)

| File | Purpose | Status |
|------|---------|--------|
| `static/index.html` | Main 3-pane trading interface (search + chain + HUD) | ✅ Built |
| `static/css/styles.css` | Global stylesheet (3-pane grid, gauges, modals) | ✅ Built |
| `static/js/app.js` | Core client logic (API calls, HUD updates, disclaimer) | ✅ Built |
| `static/profile.html` | Profile creation, strategy profiles, mode selection | ❌ Not Built |
| `static/behavioral.html` | Full behavioral dashboard, diagnostics, phase progress | ❌ Not Built |
| `static/history.html` | Trade history log with flags + journal notes + export | ❌ Not Built |
| `static/compare.html` | Compare Mode — sim vs real side-by-side | ❌ Not Built |
| `static/timemachine.html` | Time Machine replay interface with speed controls | ❌ Not Built |
| `static/upload.html` | CSV upload (bhavcopy + broker) with format guidance | ❌ Not Built |
| `static/js/charts.js` | Equity curve chart + gauge bar rendering | ❌ Not Built |
| `static/js/chain.js` | Options chain matrix rendering + expiry tabs | ❌ Not Built |
| `static/js/trading.js` | Strategy builder + deploy flow + confirmation | ❌ Not Built |

---

## 4. User Experience Flow

### Complete User Journey

```
1. FIRST VISIT → Disclaimer Modal
   "100% Simulated Paper-Trading. No Real Money. No Financial Advice."
   User must click "I Understand" to proceed.

2. ONBOARDING → Mode Selection
   Choose: "Sim Only" or "Sim + Real Trade Journal"
   Create profile name → portfolio initialized at $10,000.

3. OPTIONAL: Upload Broker CSV → Instant Trader DNA (₹499)
   Upload Zerodha/Groww/Angel One trade history.
   System runs full behavioral analysis.
   Immediately unlocks Phase D (full profile).

4. MAIN TRADING → Select Ticker, Build Strategy, Deploy
   Left pane: Search tickers (NIFTY, BANKNIFTY, etc.)
   Center pane: View options chain → select strikes → build strategy (1-4 legs)
   Right pane: HUD shows balance, positions, behavioral gauges.

5. PRE-TRADE → Behavioral State Display
   Before execution, system shows:
   • Current Discipline Rating, Patience Score, Sizing Consistency, Emotional Reactivity
   • Risk Gate warning (if max loss > 5% of portfolio)
   • IV Crush notice (if earnings within 48h)
   • Slippage cost preview
   • "This is YOUR data. Not advice. All decisions are yours alone."
   • "Would you do this with real money?" → Yes/Cancel

6. POST-TRADE → Balance Update + Behavioral Flags
   • Balance deducted (cost + slippage)
   • Position added to tracker
   • Behavioral engine runs: revenge? overconfidence? impulse?
   • Win/loss flash on settlement (green 2s / red 2s)
   • Telemetry entry written to feedback_loop.json

7. PROGRESSIVE UNLOCK → Phase A → B → C → D
   Phase A (1-5 trades): Raw data only, "Profile Building..." indicator
   Phase B (6-14 trades): Discipline Rating + Sizing Consistency unlocked
   Phase C (15-24 trades): Patience Score + Emotional Reactivity unlocked
   Phase D (25+ trades): Full profile + Diagnostic Summary generated

8. AFTER 25 TRADES → Diagnostic Summary
   Auto-generated text narrative:
   "After 25 trades, your data shows the following patterns..."
   References all 4 metrics with current values.
   Regenerated every 25 trades.

9. BEHAVIORAL DASHBOARD → Full Profile View
   All 4 gauge bars (color-coded green/yellow/red)
   Streak counter (current + best)
   Self-competition leaderboard (best month vs current)
   Penalty indicator (if active)
   Diagnostic summary text

10. COMPARE MODE (if real trades logged)
    Side-by-side: sim metrics vs real metrics
    Dual equity curves on same time axis
    Numerical Δ difference for each metric
    Weekly gap report: "Your sim Discipline was 85% while real was 62%"

11. TIME MACHINE → Historical Replay
    Select historical window (e.g., "Jan 2024 NIFTY Expiry Cycle")
    Auto-advance (1 day/10s) or manual step
    Trades during replay count toward your behavioral profile
    Same 3-pane interface with historical data

12. WEEKLY REPORTS → Behavioral Gap Analysis
    Generated when 5+ sim + 5+ real trades in a week
    Identifies divergent metrics (>10 percentage point gap)
    Observational language only
```

### The Revenge Trading Example (Walkthrough)

```
1. Trader loses ₹800 on a NIFTY put at 2:15 PM.
2. Trader immediately opens BANKNIFTY chain at 2:18 PM.
3. Trader builds a straddle with 200% of their usual size.
4. PRE-TRADE DISPLAY shows:
   "Your current Emotional Reactivity is 42/100"
   "This position risks 8.2% of your portfolio"
   "Would you do this with real money?"
5. Trader clicks "Yes — Deploy"
6. POST-TRADE: System flags trade as REVENGE TRADE
   (size > 150% avg AND loss within 24h)
   Annotation: "Position size increase detected within 24h of loss"
7. Penalty activated: max allocation reduced to 3% for 24 hours.
8. Streak counter resets to 0.
9. Next diagnostic will reference the revenge trade pattern.
```

---

## 5. Feature Inventory with Build Status

### Legend
- ✅ Done — Fully implemented and tested
- 🔧 Partial — Core logic exists but incomplete integration or missing edge cases
- ❌ Not Built — Not yet implemented

### Phase 1: Core Trading Sim Engine

| # | Feature | Req | Backend | Frontend | Status |
|---|---------|-----|---------|----------|--------|
| 1 | Virtual Portfolio ($10k init) | 1 | ✅ | 🔧 | ✅ Done |
| 2 | 3-Pane Desktop Layout | 2 | N/A | ✅ | ✅ Done |
| 3 | Options Chain Display | 3 | ✅ | ✅ | ✅ Done |
| 4 | Greeks Calculator (Black-Scholes) | 4 | ✅ | ✅ | ✅ Done |
| 5 | IV Rank Tracking | 5 | ✅ | ✅ | ✅ Done |
| 6 | Strategy Game Cards | 6 | ✅ | ✅ | ✅ Done |
| 7 | Multi-Leg Strategy Builder | 7 | ✅ | ✅ | ✅ Done |
| 8 | Trade Execution (Deploy Credits) | 8 | ✅ | ✅ | ✅ Done |
| 9 | Position Tracker | 9 | 🔧 | 🔧 | 🔧 Partial |
| 10 | Mock Data Fallback (10 tickers) | 10 | ✅ | ✅ | ✅ Done |
| 11 | Legal Disclaimer Modal + Footer | 11 | N/A | ✅ | ✅ Done |
| 12 | SQLite Database (9 tables) | 12 | ✅ | N/A | ✅ Done |

### Phase 2: Behavioral Intelligence Engine

| # | Feature | Req | Backend | Frontend | Status |
|---|---------|-----|---------|----------|--------|
| 13 | Discipline Rating | 13 | ✅ | ❌ | 🔧 Partial |
| 14 | Patience Score | 14 | ✅ | ❌ | 🔧 Partial |
| 15 | Sizing Consistency | 15 | ✅ | ❌ | 🔧 Partial |
| 16 | Emotional Reactivity Score | 16 | ✅ | ❌ | 🔧 Partial |
| 17 | Revenge Trading Detector | 17 | ✅ | ❌ | 🔧 Partial |
| 18 | Overconfidence Trap Detector | 18 | ✅ | ❌ | 🔧 Partial |
| 19 | Loss Disposition Bias Detector | 19 | ✅ | ❌ | 🔧 Partial |
| 20 | Impulse Early Exit Detector | 20 | ✅ | ❌ | 🔧 Partial |
| 21 | 25-Trade Diagnostic Summary | 21 | ✅ | ❌ | 🔧 Partial |
| 22 | P&L Equity Curve Chart | 22 | ❌ | ❌ | ❌ Not Built |
| 23 | Trade Journal | 23 | ✅ | ❌ | 🔧 Partial |
| 24 | Visual Gauge Bars | 24 | N/A | 🔧 | 🔧 Partial |
| 25 | Win/Loss Flash Feedback | 25 | N/A | ❌ | ❌ Not Built |
| 26 | Progressive Profile Building | 26 | ✅ | 🔧 | 🔧 Partial |

### Phase 3: Risk Guards & Discipline Mechanics

| # | Feature | Req | Backend | Frontend | Status |
|---|---------|-----|---------|----------|--------|
| 27 | Anti-Impulse Risk Gate | 27 | ✅ | ❌ | 🔧 Partial |
| 28 | IV Crush Gate | 28 | ✅ | ❌ | 🔧 Partial |
| 29 | Bid-Ask Slippage Gauge | 29 | ✅ | ❌ | 🔧 Partial |
| 30 | Pre-Trade Behavioral State Display | 30 | ✅ | ❌ | 🔧 Partial |
| 31 | Earnings Calendar | 31 | ✅ | ❌ | 🔧 Partial |
| 32 | Manual Early Close + Outcome Tag | 32 | 🔧 | ❌ | 🔧 Partial |
| 33 | Telemetry Logging | 33 | 🔧 | ❌ | 🔧 Partial |
| 34 | No-Reset Rule (Game Over) | 34 | ✅ | 🔧 | ✅ Done |
| 35 | Streak Tracking | 35 | ✅ | 🔧 | 🔧 Partial |
| 36 | Self-Competition Leaderboard | 36 | ❌ | ❌ | ❌ Not Built |
| 37 | Penalty Multiplier | 37 | ✅ | ❌ | 🔧 Partial |
| 38 | Pre-Trade Confirmation Prompt | 38 | 🔧 | ❌ | 🔧 Partial |

### Phase 4: Time Machine & Data

| # | Feature | Req | Backend | Frontend | Status |
|---|---------|-----|---------|----------|--------|
| 39 | Historical Time Machine | 39 | 🔧 | ❌ | 🔧 Partial |
| 40 | Time Machine Speed Controls | 40 | 🔧 | ❌ | 🔧 Partial |
| 41 | End-of-Day Market Data (Yahoo) | 41 | ❌ | ❌ | ❌ Not Built |
| 42 | NSE Bhavcopy CSV Upload | 42 | ❌ | ❌ | ❌ Not Built |
| 43 | Expiration Settlement Engine | 43 | ✅ | ❌ | 🔧 Partial |
| 44 | Multiple Strategy Profiles | 44 | ✅ | ❌ | 🔧 Partial |
| 45 | Export Trade History to CSV | 45 | ❌ | ❌ | ❌ Not Built |
| 46 | Backup and Restore Database | 46 | ❌ | ❌ | ❌ Not Built |

### Phase 5: Real Trade Journal / Parallel Mode

| # | Feature | Req | Backend | Frontend | Status |
|---|---------|-----|---------|----------|--------|
| 47 | Mode Selection | 47 | 🔧 | ❌ | 🔧 Partial |
| 48 | Real Trade Manual Entry | 48 | 🔧 | ❌ | 🔧 Partial |
| 49 | Behavioral State at Real Trade Entry | 49 | ❌ | ❌ | ❌ Not Built |
| 50 | Compare Mode | 50 | 🔧 | ❌ | 🔧 Partial |
| 51 | Weekly Behavioral Gap Report | 51 | ❌ | ❌ | ❌ Not Built |

### Phase 6: Monetization

| # | Feature | Req | Backend | Frontend | Status |
|---|---------|-----|---------|----------|--------|
| 52 | Instant Trader DNA (CSV Upload) | 52 | ❌ | ❌ | ❌ Not Built |
| 53 | Free Path Progressive Unlock | 53 | ✅ | 🔧 | 🔧 Partial |
| 54 | Payment Integration Stub | 54 | ❌ | ❌ | ❌ Not Built |

### Phase 7: Cross-Cutting Concerns

| # | Feature | Req | Backend | Frontend | Status |
|---|---------|-----|---------|----------|--------|
| 55 | No Financial Advice Guarantee | 55 | ✅ | 🔧 | 🔧 Partial |
| 56 | Zero Real-Money Connection | 56 | ✅ | ✅ | ✅ Done |
| 57 | Project Isolation (Single Folder) | 57 | ✅ | N/A | ✅ Done |
| 58 | Local-First Architecture | 58 | ✅ | ✅ | ✅ Done |

### Build Status Summary

| Category | Done | Partial | Not Built | Total |
|----------|------|---------|-----------|-------|
| Phase 1 (Core Engine) | 11 | 1 | 0 | 12 |
| Phase 2 (Behavioral) | 0 | 12 | 2 | 14 |
| Phase 3 (Risk Guards) | 1 | 10 | 1 | 12 |
| Phase 4 (Time/Data) | 0 | 4 | 4 | 8 |
| Phase 5 (Real Trades) | 0 | 3 | 2 | 5 |
| Phase 6 (Monetization) | 0 | 1 | 2 | 3 |
| Phase 7 (Cross-Cutting) | 3 | 1 | 0 | 4 |
| **TOTAL** | **15** | **32** | **11** | **58** |

**Overall Progress: ~26% Complete (backend-heavy, frontend mostly pending)**

---

## 6. Key Design Principles

### 1. No Financial Advice (Observational Language Only)
Every piece of text shown to the user uses observational framing:
- ✅ "Your data shows..." / "The pattern indicates..." / "This position risks X%..."
- ❌ NEVER "You should..." / "Buy this..." / "We recommend..." / "Stop trading..."

### 2. Zero Liability Framing
- All currency labeled "Virtual" or "Simulated"
- No brokerage API connections
- No real financial instruments processed
- Disclaimer on every screen
- No advisory services implied anywhere

### 3. Mirror / Fitness-Tracker Metaphor
The platform is a **behavioral fitness tracker** for trading:
- It records your patterns (like a step counter records steps)
- It shows you data about yourself (like heart rate trends)
- It never tells you what to do (a scale doesn't say "eat less")
- You interpret the data and make your own decisions

### 4. Progressive Disclosure
Users aren't overwhelmed with metrics from day one:
- Phase A (1-5 trades): Just raw data, "Building Profile..." 
- Phase B (6-14): Discipline + sizing visible
- Phase C (15-24): Patience + emotional added
- Phase D (25+): Full profile, diagnostics, all gauges active
- Trader DNA upload: Skip straight to Phase D

### 5. No-Reset Game-Over Mechanic
- $0 balance = permanent profile lock
- Complete history preserved for review
- Must create new profile to continue
- Creates psychological "real stakes" in a paper environment
- Forces players to treat virtual money with respect

### 6. One-Folder Isolation
- ALL files (DB, logs, backups, config, static) in single directory
- No registry entries, no global packages, no system services
- Delete the folder = 100% complete uninstall
- No data residue anywhere on the machine

---

## 7. Monetization Model

### Free Tier (Unlimited)
All core simulation features are **permanently free**:
- Full options chain with Greeks
- Strategy builder (all 4 templates + custom)
- Trade execution with slippage
- Position tracking + manual close
- Behavioral metrics (progressive unlock via trading)
- Time Machine historical replay
- Trade journal (notes per trade)
- CSV export of trade history
- Database backup/restore
- Real trade journal (parallel mode)
- Compare mode (sim vs real)

### Premium Tier: Trader DNA (₹499 One-Time)
- Upload real brokerage CSV (Zerodha, Groww, Angel One)
- System parses full trade history
- Generates complete behavioral profile instantly
- Skips 25-trade waiting period → immediate Phase D
- Full diagnostic summary from day one
- One-time payment, not subscription

### Future Payment Integration
- **Stripe** (international) — stub code ready, inactive
- **Razorpay** (India) — stub code ready, inactive
- Requires explicit configuration to activate
- Payment status stored per profile in SQLite
- No payment processing until stubs are activated

### Revenue Philosophy
- Core value delivered free (builds trust + adoption)
- Premium = time savings (skip the 25-trade grind)
- No feature gating on core trading mechanics
- No recurring charges — one-time unlock

---

## 8. Next Steps (Priority Order)

### Immediate (Backend Completion)

1. **Complete Position Tracker endpoints** — GET positions with live P&L, POST close with outcome tagging (Task 4.5)
2. **Wire settlement engine into trade flow** — auto-settle expired positions on each API call (Task 4.7)
3. **Complete behavioral metrics API** — wire all computation into post-trade update, expose via GET endpoints (Task 6.22)
4. **Implement telemetry logging** — write to feedback_loop.json on each pre-trade display (Task 8.8)
5. **Implement monthly P&L tracking** — update on each realized trade, self-competition endpoint (Task 8.9)
6. **Implement risk guard integration** — wire risk gate + IV crush + penalty into trade execution flow (Tasks 8.1, 8.3, 8.5)
7. **Pre-trade confirmation flow** — full Deploy Credits pipeline with behavioral state + "Would you do this with real money?" (Task 8.7)

### Medium Priority (Data & Features)

8. **Time Machine implementation** — historical window selection, day-by-day progression (Task 10.1)
9. **NSE Bhavcopy upload** — parse CSV, populate chain data (Task 10.3)
10. **Trade history CSV export** — generate downloadable CSV with all fields (Task 10.4)
11. **Database backup/restore** — timestamped copies in /backups (Task 10.6)
12. **Real trade behavioral state** — metrics snapshot when logging real trades (Task 12.2)
13. **Weekly gap report** — generate when 5+ trades each side (Task 12.5)
14. **Yahoo Finance EOD** — optional external data with silent fallback (Task 10.2)

### Frontend Build (Full UI)

15. **Profile management page** — create/switch profiles, strategy profiles, mode selection (Task 15.1)
16. **Main trading page JS** — full app.js with API wiring, chain rendering, deploy flow (Tasks 15.3–15.5)
17. **Behavioral dashboard page** — gauge bars, equity curve, diagnostic, phase progress (Tasks 16.1–16.2)
18. **Trade history page** — full log with flags, journal, export button (Task 17.1)
19. **Compare Mode page** — dual equity curves, metric comparison, gap report (Task 17.2)
20. **Time Machine page** — replay UI with speed controls (Task 17.3)
21. **Upload page** — CSV upload with format guidance, error display (Task 17.4)
22. **Win/loss flash feedback** — CSS animations on HUD (Task 16.3)

### Final Phase (Monetization & Polish)

23. **Trader DNA from broker CSV** — parse Zerodha/Groww/Angel One, generate full profile (Task 13.1)
24. **Payment integration stubs** — Stripe/Razorpay inactive stubs, payment_status field (Task 13.2)
25. **Language compliance audit** — scan all UI text for directive language violations (Task 18.1)
26. **Integration testing** — full trade execution flow end-to-end (Task 19.3)
27. **Error handling middleware** — consistent error codes across all endpoints (Task 19.2)

---

## Appendix: Correctness Properties (26 Total)

These formal properties are validated via Hypothesis (property-based testing):

| # | Property | Validates |
|---|----------|-----------|
| 1 | Profile init round-trip: balance=10000, is_locked=False | Req 1.1, 1.2 |
| 2 | Locked profile immutability: reject all balance increases | Req 1.4, 34.1 |
| 3 | Greeks bounds: call_delta [0,1], put_delta [-1,0], gamma≥0, 4dp | Req 4.1, 4.3 |
| 4 | Greeks sensitivity: different inputs → different outputs | Req 4.2 |
| 5 | IV Rank formula: (current-min)/(max-min)*100, None if <20 | Req 5.1, 5.2 |
| 6 | Strategy leg count: accept iff 1≤n≤4 | Req 7.1 |
| 7 | Trade balance invariant: new = old - cost - slippage, or reject | Req 8.1, 8.3 |
| 8 | Discipline Rating: (disciplined/total)*100 | Req 13.1 |
| 9 | Patience Score: mean of positive elapsed seconds | Req 14.3 |
| 10 | Sizing Consistency: stdev of position_pct values | Req 15.1 |
| 11 | Emotional Reactivity: always 0≤score≤100 | Req 16.1 |
| 12 | Revenge Trade: size>1.5×avg AND loss within 24h | Req 17.1 |
| 13 | Overconfidence Trap: size>1.5×avg AND 3+ consecutive wins | Req 18.1 |
| 14 | Loss Disposition: ratio = avg_loss_hold / avg_win_hold, flag if >1.2 | Req 19.1, 19.2 |
| 15 | Impulse Early Exit: realized < 0.25 × max_unrealized | Req 20.1 |
| 16 | Slippage: sum of 0.5 × spread × quantity per leg | Req 29.1 |
| 17 | Streak: longest trailing contiguous with position_pct≤5.0 | Req 35.1, 35.2 |
| 18 | Penalty trigger: penalty_until = now + 24h when pct>5.0 | Req 37.1 |
| 19 | Settlement intrinsic: call=max(0,S-K)×qty, put=max(0,K-S)×qty | Req 43.1, 43.2 |
| 20 | Risk Gate: shown iff max_loss > 5% of balance | Req 27.1 |
| 21 | IV Crush warning: shown iff earnings within 48h | Req 28.1 |
| 22 | Phase determination: A[0-5], B[6-14], C[15-24], D[25+], DNA→D | Req 53.1 |
| 23 | Monthly P&L: sum of realized_pnl per calendar month | Req 36.1 |
| 24 | Journal validation: reject >1000 chars, accept ≤1000 | Req 23.4 |
| 25 | Compare Mode difference: exactly sim_value - real_value | Req 50.4 |
| 26 | CSV export round-trip: export and re-parse matches source | Req 45.2 |

---

## 9. Phase 9: Competitive & Advanced Behavioral Features

### Overview
Phase 9 introduces advanced behavioral intelligence features that differentiate Options Tycoon from every other trading journal/tracker in the market. These features transform raw behavioral data into actionable self-awareness.

### Features Added

| # | Feature | Description | Status |
|---|---------|-------------|--------|
| 1 | Trader DNA Score | Single composite score (0-100) summarizing overall trading discipline. Weighted combination of discipline rating, patience, sizing consistency, and emotional control. | ✅ Done |
| 2 | Strategy vs Behavior Cost | Separates strategy P&L (clean trades) from behavioral cost (flagged trades). Shows what the trader's P&L would be if they were fully disciplined. | ✅ Done |
| 3 | Fix One Thing First | Identifies the single worst behavioral pattern and provides a focused recommendation. Reduces overwhelm by giving one clear improvement target. | ✅ Done |
| 4 | Skip Upload CTA | "Skip upload — try the simulator" link on landing page for users who want to explore before committing to CSV upload. | ✅ Done |
| 5 | Sample Zerodha CSV | Bundled sample tradebook CSV (`data/sample_zerodha_export.csv`) so users can test the upload flow without needing their own broker export. | ✅ Done |
| 6 | Phase Threshold Refinement | Updated progressive unlock thresholds to A(1-5), B(6-14), C(15-24), D(25+) with clearer phase descriptions. | ✅ Done |

### Competitive Differentiators

These features directly address gaps in existing tools (Sensibull, Opstra, TradingView):

- **DNA Score**: No other Indian options tool provides a single behavioral composite score. Sensibull tracks P&L, not behavior.
- **Strategy vs Behavior Split**: Shows the exact ₹ cost of undisciplined trading — a gut-punch number that motivates change.
- **Fix One Thing**: Reduces decision paralysis. Instead of "improve everything," users get one concrete focus.
- **Sample CSV**: Removes friction from the upload funnel. Users can experience the analysis before providing real data.

### Files Modified/Created

| File | Change |
|------|--------|
| `routes/behavioral.py` | Removed `response_model=BehavioralMetrics`, added advanced metric computation inline |
| `static/behavioral.html` | Added DNA Score display, Strategy vs Behavior grid, Fix One Thing section, updated phase thresholds and descriptions |
| `static/landing.html` | Added "Skip upload — try the simulator" link in hero and final CTA sections |
| `static/upload-free.html` | Added sample CSV download link |
| `data/sample_zerodha_export.csv` | New file — 18-row realistic Zerodha tradebook with NIFTY and BANKNIFTY F&O trades |

---

## 8. PRODUCTION READINESS — Prioritized Build Plan (July 2026)

> Based on: Internal audit + Gemini AI review + ChatGPT Round 1 + ChatGPT Round 2 critic reviews
> Last consolidated: July 6, 2026

### Overview

Before launching to the first 100 users, the platform must pass legal compliance, security hardening, and infrastructure reliability checks. Items are prioritized as P0 (blocker), P1 (should-have first week), P2 (post-launch).

---

### 🔴 OWNER ACTION ITEMS (Pending decisions — blocks P0 execution)

| # | Decision Needed | Options | Status |
|---|-----------------|---------|--------|
| OA-1 | Python version locally | Keep 3.14 locally, pin 3.12 for Railway only | ✅ Pin 3.12 for Railway |
| OA-2 | PostgreSQL addon | Railway free PostgreSQL (1GB, $0) | ✅ YES — confirmed |
| OA-3 | Grievance Officer name | Placeholder for now | ✅ "Data Protection Officer, Options Tycoon · grievance@optionstycoon.app" |
| OA-4 | Razorpay merchant application | Start application (takes 2-4 weeks) | ⏳ Owner to do offline |
| OA-5 | HTTP-Only cookies | Deferred to P1 (not blocker for 100 beta users) | ✅ P1 |
| OA-6 | Google Console redirect URIs | Add Railway URL to authorized origins | ⏳ Owner to do before deploy |

---

### P0 — MUST HAVE (Cannot launch without. Blocks first user.)

#### P0-A: Infrastructure (Do first — everything else depends on this)

| # | Item | Owner | Time | Status |
|---|------|-------|------|--------|
| P0-1 | Pin Python 3.12 for Railway runtime | Dev | 15min | ❌ |
| P0-2 | PostgreSQL migration (replace SQLite) | Dev | 2-3h | ❌ |
| P0-3 | Alembic migration setup | Dev | 1h | ❌ |
| P0-4 | .env.example documenting all env vars | Dev | 10min | ❌ |
| P0-5 | Google Sign-In redirect URIs for production | **YOU** (manual in Google Console) | 5min | ❌ |

#### P0-B: Security (Do second — protect user data)

| # | Item | Owner | Time | Status |
|---|------|-------|------|--------|
| P0-6 | HTTP-Only secure session cookies (replace localStorage auth) | Dev | 2-3h | ❌ |
| P0-7 | Global error handler (no stack traces in production) | Dev | 30min | ❌ |
| P0-8 | Backend file size limit (10MB server-side) | Dev | 15min | ❌ |
| P0-9 | Remove hardcoded Google secret fallback | Dev | 10min | ❌ |
| P0-10 | Rate limit: User ID (authenticated) + IP (unauthenticated) | Dev | 30min | ❌ |
| P0-11 | Strict CSV type validation (reject non-numeric price/qty clearly) | Dev | 30min | ❌ |
| P0-12 | Broker format drift handling (graceful unknown format → log + friendly message) | Dev | 30min | ❌ |

#### P0-C: Legal & Compliance (Do third — cannot take real users without)

| # | Item | Owner | Time | Status |
|---|------|-------|------|--------|
| P0-13 | DPDPA two-checkbox consent (separate: email + trade data) | Dev | 30min | ❌ |
| P0-14 | Audit ALL report language — remove prescriptive words (should/avoid/stop/don't → descriptive only) | Dev | 1h | ❌ |
| P0-15 | Grievance Officer name + email displayed publicly (privacy page + footer) | Dev + **YOU** (provide name) | 10min | ❌ |
| P0-16 | "We strip your identity" trust banner on upload page | Dev | 10min | ❌ |

#### P0-D: Business (Start immediately — long lead time)

| # | Item | Owner | Time | Status |
|---|------|-------|------|--------|
| P0-17 | Apply for Razorpay merchant account | **YOU** | 30min (application), 2-4 weeks (approval) | ❌ |

**P0 Total Dev Time: ~10-12 hours**
**P0 Owner Actions: 4 decisions + 2 manual steps**

---

### P1 — SHOULD HAVE (Ship within first week after launch)

| # | Item | Category | Owner | Status |
|---|------|----------|-------|--------|
| P1-1 | Upload progress text status (simple loading text, not full stepper) | UX | Dev | ❌ |
| P1-2 | Success animation (1.5s "✅ Report ready!") | UX | Dev | ❌ |
| P1-3 | Error state with retry + help + "Report Parsing Issue" link | UX | Dev | ❌ |
| P1-4 | Browser storage consent banner (nice-to-have, not legally required in India) | Legal | Dev | ❌ |
| P1-5 | Graceful shutdown (SIGTERM handler) | Infra | Dev | ❌ |
| P1-6 | "Raw CSV never touches disk" code documentation + privacy policy note | Security | Dev | ❌ |
| P1-7 | Automated daily DB backups (PostgreSQL pg_dump scheduled) | Infra | Dev | ❌ |
| P1-8 | Email notification system (Resend free tier — weekly "upload reminder") | Retention | Dev | ❌ |
| P1-9 | Code obfuscation/minification (protect IP) | IP | Dev | ❌ |
| P1-10 | Mobile responsiveness testing + fixes (all 5 pages at 375px) | UX | Dev | ❌ |
| P1-11 | Server-side upload history wiring (API built, frontend not connected) | Data | Dev | ❌ |
| P1-12 | Paywall logic code (user count check, gate premium features for user 101+) | Revenue | Dev | ❌ |

---

### P2 — POST-LAUNCH (After 20-50 users, driven by feedback + revenue goals)

| # | Item | Category | Owner | Status |
|---|------|----------|-------|--------|
| P2-1 | Razorpay payment integration (once merchant approved) | Revenue | Dev | ❌ |
| P2-2 | RBI recurring mandate compliance OR fixed-package pricing (3-month/6-month) | Revenue | Dev + **YOU** | ❌ |
| P2-3 | Sentry error tracking (free tier) | Monitoring | Dev | ❌ |
| P2-4 | Custom domain (`optionstycoon.app` or `traderdna.in`) | Branding | **YOU** + Dev | ❌ |
| P2-5 | WCAG accessibility (ARIA, keyboard nav, contrast) | Compliance | Dev | ❌ |
| P2-6 | CDN for static assets (CloudFlare) | Performance | Dev | ❌ |
| P2-7 | Month-vs-month comparison feature | Feature | Dev | ❌ |
| P2-8 | Server-side PDF with branding/watermark | Virality | Dev | ❌ |
| P2-9 | Offline service worker (branded offline page) | UX | Dev | ❌ |
| P2-10 | DB encryption at rest (PostgreSQL level) | Security | Dev | ❌ |
| P2-11 | Browser push notifications ("upload reminder") | Retention | Dev | ❌ |
| P2-12 | Compare month vs month | Feature | Dev | ❌ |

---

### Execution Sequence

```
NOW (Owner):    Answer OA-1 through OA-6. Apply for Razorpay (OA-4).

STEP 1 (Dev):   P0-A (Infrastructure) — PostgreSQL, Alembic, Python pin, env vars
                 → Verify server starts with new DB

STEP 2 (Dev):   P0-B (Security) — Cookies, error handler, rate limits, CSV validation
                 → Verify auth flow works end-to-end

STEP 3 (Dev):   P0-C (Legal) — Consent screen, language audit, grievance officer, trust banner
                 → Verify upload flow shows consent + banner

STEP 4 (Dev):   Push to Railway. Test on production URL.
                 Owner: Configure Google redirect URIs (OA-6)

STEP 5 (Dev):   P1 items (first week post-launch)

STEP 6:         Launch to first 100 users

STEP 7:         P2 items (based on user feedback + Razorpay approval timeline)
```

---

### Security Architecture Summary

| Layer | Protection | Status |
|-------|-----------|--------|
| Transport | HTTPS/TLS (Railway SSL) | ✅ |
| API | Rate limiting (User ID + IP), CORS restriction, auth validation | P0 |
| Input | CSV formula injection stripping, file size limit, strict type validation, broker drift handling | P0 |
| Data | Personal identifiers stripped, raw CSV never stored, in-memory processing only | ✅ |
| Auth | Google OAuth → HTTP-Only secure cookies (SameSite=Strict) | P0 |
| Storage | PostgreSQL (Railway managed), daily backups | P0+P1 |
| Output | XSS sanitization, no stack traces, descriptive language only | P0 |
| Frontend | Code minification (P1), no secrets in client code | P1 |
| Legal | SEBI disclaimer, DPDPA consent (2-checkbox), Privacy Policy, Terms, Delete Account, Grievance Officer | P0 |

---

### Final Product Architecture (5 Pages)

```
Landing (/) → Upload → Sign-In Gate → Report → Dashboard
                                                    ↓
                                              Upload (weekly loop)
```

All old simulator pages redirect. Simulator code retained for Phase 3 reintroduction.

---

### Revenue Timeline

```
NOW:           Apply for Razorpay merchant account
WEEK 1-2:     Launch free (100 users)
WEEK 3-4:     Razorpay approved → Build paywall code (P1-12)
WEEK 4+:      User 101 → Premium gate activated
               Pricing: ₹499/month OR ₹2999/year (avoid RBI recurring mandate
               complexity by offering fixed packages: 3-month ₹1299, 6-month ₹2499, yearly ₹2999)
```

---

*End of Project Repository. This document is the single source of truth for Options Tycoon.*
