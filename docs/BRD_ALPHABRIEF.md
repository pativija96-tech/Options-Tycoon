# AlphaBrief — Automated Trading Content Pipeline BRD

> **Version:** 1.0 | **Status:** PARKED (build after 2-4 weeks of live trade data)
> **Priority:** After NIFTY + QQQ are executing live
> **Estimated Build Time:** ~12 hours

---

## 1. Concept

Automated video/audio content pipeline that turns live Options Tycoon trade data into YouTube content. Zero monthly software overhead (<$15/month total).

**Brand:** AlphaBrief
**Niche:** Institutional-grade retail quant automation (QQQ + NIFTY only — no genomics)
**Hook:** Raw, unfiltered transparency — live database records, exact slippage, win rates, zero hiding

---

## 2. Content Strategy

### Primary Format
- **Weekly Recap (3-5 min):** Full week P&L, trades fired, trades skipped, slippage analysis
- **Daily Flash (30s Shorts):** Single-number P&L card with chart

### Retention Mechanic
Accountability through radical transparency — showing the actual database, not curated highlights.

### Non-Trading Day Fallback
When system sits out (FOMC, VIX spike, no edge):
- Pull external market data (VIX movement, index performance)
- Script: "Why the algorithm chose cash today" — builds trust by showing discipline

---

## 3. Technical Pipeline

```
[Railway Cron (Post-Market Close)]
  │
  ▼
[Options Tycoon PostgreSQL] → Pull QQQ/NIFTY P&L, win rates, slippage
  │
  ▼
[AWS Bedrock (Claude)] → Generate script (cost-barrier disruption narrative)
  │
  ▼
[Content Safety Gate] → Verify financial figures, add disclaimers
  │
  ├──────────────────────────────────┐
  ▼                                  ▼
[AWS Polly (Neural)]          [Matplotlib/MoviePy]
(Voiceover)                   (Charts, dark-mode visuals)
  │                                  │
  └──────────┬───────────────────────┘
             ▼
[MoviePy Video Composer] → Merge audio + video + captions + disclaimer watermark
  │
  ▼
[AWS S3] → Archive master .mp4
  │
  ▼
[YouTube Data API v3] → Auto-publish (Shorts + Long-form)
```

---

## 4. Data Sources

### Primary (Internal — from Options Tycoon DB)
- QQQ 0DTE IC: daily fill prices, slippage, wing adjustments, win/loss, P&L curves
- NIFTY Weekly IC: index price, strike selections, credit collected, Tuesday expiry outcomes
- System metrics: FOMC skips, VIX thresholds triggered, behavioral discipline scores

### Secondary (External — fallback for no-trade days)
- VIX level and spikes (yfinance)
- Major index movements (S&P 500, NIFTY)
- Upcoming macro catalysts (from event_calendar.json)

---

## 5. Regulatory Safety

Every video MUST include:
- Automated disclaimer watermark: "Personal trading journal. Not financial advice. Past performance doesn't guarantee future results."
- No solicitation language
- No "you should" or "buy this" language (same observational rules as Options Tycoon)

---

## 6. Cost Structure

| Item | Cost |
|------|------|
| Railway hosting | $0 additional (shared with Options Tycoon) |
| AWS Bedrock (Claude) | <$0.50/month |
| AWS Polly | <$0.50/month |
| MoviePy rendering | $0 (runs on Railway container) |
| YouTube API | Free (within 10K daily quota) |
| **Total** | **<$1.50/month** |

---

## 7. Prerequisites (Before Building)

- [ ] 10+ real QQQ trades logged in DB (need data to tell stories about)
- [ ] 4+ real NIFTY trades logged in DB
- [ ] At least 1 "system sat out" day logged (for discipline narrative)
- [ ] Decide: ElevenLabs ($5/mo for natural voice) vs. AWS Polly (free-tier robotic)
- [ ] Record 3-5 manual test videos first to find winning format

---

## 8. Kiro's Review Notes (July 30, 2026)

- Drop genomics — keep strictly QQQ + NIFTY trading
- Primary format: weekly recap (3-5 min) + daily 30s Shorts
- Manual first 5 videos → find format → then automate
- Polly sounds AI — consider ElevenLabs for more natural voice
- Regulatory disclaimer is mandatory (watermark in every frame)
- YouTube rewards watch time > upload frequency
- The "discipline" narrative (showing why you sat out) builds more trust than daily forced trades

---

*Parked until live trade data is flowing. Ping Kiro to build when ready.*
