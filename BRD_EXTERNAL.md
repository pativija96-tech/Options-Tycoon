# OPTIONS TYCOON — Business Requirements Document (BRD)

> **Version:** 5.0 | **Last Updated:** 2026-07-25
> **Status:** Dual-Mode System (NIFTY + QQQ)
> **Disclaimer:** Personal trading tool. Not financial advice.

---

## 1. SYSTEM OVERVIEW

Options Tycoon operates in **two independent modes** on the same infrastructure:

| Mode | Market | Broker | Underlying | Status |
|------|--------|--------|-----------|--------|
| **NIFTY** | India (NSE) | Zerodha (Kite) | NIFTY 50 Index | Ready — pending wife's account NFO activation |
| **QQQ** | US (NASDAQ) | Interactive Brokers | QQQ ETF (Nasdaq 100) | Building — IBKR account pending activation |

Both modes share: Railway hosting, PostgreSQL DB, signal history, UI, automated scheduler.
Both modes are independent: different broker APIs, different strategies, different schedules.

---

## 2. MODE A: QQQ (US Market via IBKR) — PRIMARY

### Strategy
**QQQ ±$15 Iron Condor, $7 wings, daily, hold to same-day expiry (0DTE)**

### Validated Numbers

| Metric | Value |
|--------|-------|
| Win rate | 98.2% |
| Realistic EV/trade | $7.70–$8.00 |
| Win: avg profit | +$42 |
| Loss: avg loss | -$25 (shallow breach) |
| Loss: max loss | -$700 (wing cap, very rare) |
| Slippage (entry only, 4 legs × $0.02) | -$8.00 |
| Commission (IBKR) | -$4.00 |
| Annual ROI | ~115-120% |
| Tax (PH resident) | 0% |

### Execution

```
10:30 PM PH (US market open):
  → System auto-connects to IBKR
  → Gets QQQ opening price
  → Places 4-leg Iron Condor as combo limit order at midpoint
  → Trade is live

5:00 AM PH (US market close):
  → Options expire (0DTE)
  → Win: premium kept automatically (no action)
  → Loss: settled by IBKR (capped at wing width)
  → Result logged to DB

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
- API: `ib_insync` (Python async)
- Order type: BAG (Combo) limit at midpoint
- Data: Real-time QQQ price + VIX
- Settlement: Automatic (0DTE expiry)
- Funding: Wise USD → IBKR wire

---

## 3. MODE B: NIFTY (India via Zerodha) — SECONDARY

### Strategy
**NIFTY ±250pt Iron Condor, 100pt wings, hold to Tuesday weekly expiry**

### Validated Numbers

| Metric | Value |
|--------|-------|
| Win rate | 86.5% |
| Realistic EV/trade | Rs.192 (before tax) |
| Tax (NRI via DTAA refund) | 0% after refund (30% TDS upfront, reclaim annually) |
| Slippage breakeven | Rs.191/trade |
| Annual ROI | ~50% (after cash flow drag from TDS) |

### Execution

```
9:15 AM IST (Indian market open):
  → System connects to Kite
  → Gets NIFTY opening price
  → Places 4-leg IC via Kite API
  → Trade holds to Tuesday expiry

3:35 PM IST (automated daily):
  → EOD check: SL breach? → auto-exit
  → Tuesday: auto-resolve at expiry

Wife's Zerodha account (resident, not NRI) → no 30% TDS issue.
```

### Status
- Zerodha NFO activation: Pending (wife's account)
- Kite API: Configured, IP whitelisted
- System code: Complete and tested
- All validation: Done (5 rounds passed)

---

## 4. TECHNICAL ARCHITECTURE (Dual-Mode)

### Code Structure

```
engine/
├── signals/
│   ├── simple_ic_engine.py     → NIFTY signal generator
│   └── qqq_ic_engine.py        → QQQ signal generator (NEW)
├── broker/
│   ├── kite_auth.py            → Zerodha OAuth + LTP
│   ├── kite_executor.py        → NIFTY order placement
│   ├── ibkr_auth.py            → IBKR connection (NEW)
│   └── ibkr_executor.py        → QQQ combo order placement (NEW)
├── scheduler.py                → Dual scheduler (NIFTY 3:35 PM IST + QQQ 9:30 PM PH)
└── session.py                  → Founder allowlist (unchanged)

routes/
├── live.py                     → Serves both modes based on TRADING_MODE env var
└── (all other routes unchanged)

config/
└── settings.json               → Has both NIFTY and QQQ parameters
```

### Configuration

```json
{
  "trading_mode": "qqq",
  "nifty": {
    "capital": 10000,
    "offset_pts": 250,
    "wing_width": 100,
    "lot_size": 25,
    "risk_per_trade": 0.25
  },
  "qqq": {
    "capital": 1000,
    "offset_pts": 15,
    "wing_width": 7,
    "lot_size": 100,
    "risk_per_trade": 0.70
  }
}
```

### Environment Variables

| Variable | QQQ Mode | NIFTY Mode |
|----------|----------|------------|
| TRADING_MODE | qqq | nifty |
| IBKR_HOST | 127.0.0.1 | (not used) |
| IBKR_PORT | 7497 | (not used) |
| IBKR_CLIENT_ID | 1 | (not used) |
| KITE_API_KEY | (not used) | (set) |
| KITE_API_SECRET | (not used) | (set) |
| FOUNDER_ALLOWED_EMAILS | (set) | (set) |

### Scheduler (Dual Timezone)

```
QQQ Mode:
  - 10:30 PM PH (9:30 AM EST): Place trade
  - 5:00 AM PH (4:00 PM EST): Verify expiry result
  
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
| QQQ gaps >$15 overnight (earnings) | Loss capped at $700 | $7 wings; avoid holding through mega-cap earnings |
| IBKR connection failure | Missed trade | Retry logic; manual backup via IBKR app |
| Slippage higher than backtest | EV reduced or negative | Phase 1 validates; stop if >$12/trade |
| Extended loss streak | Drawdown | Pre-committed rules in Section 2 |
| Regulatory change (PH taxes foreign gains) | Tax liability | Monitor annually; currently 0% |
| Railway downtime | Missed auto-trade | Health monitoring; manual backup |

---

## 8. NEXT STEPS

1. [x] Strategy validated (QQQ: 7 rounds passed)
2. [ ] BRD updated with dual-mode architecture ← DONE NOW
3. [ ] Build QQQ/IBKR execution module (`ib_insync`)
4. [ ] Build dual-mode scheduler
5. [ ] Wait for IBKR account activation
6. [ ] Fund $1,000 via Wise
7. [ ] Phase 1: 10 trades (validate real fills)
8. [ ] If passes → Phase 2 → Phase 3

---

*End of BRD v5.0. Dual-mode system: QQQ (primary, tax-free) + NIFTY (secondary, via wife's account). Both validated, independent, same infrastructure.*
