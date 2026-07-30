# BuyAI Tech — Automated Trading Content Pipeline BRD

> **Version:** 2.0 | **Last Updated:** 2026-07-30
> **Status:** GREEN LIGHT — Building now
> **Brand:** BuyAI Tech
> **Estimated Build Time:** ~12 hours
> **Monthly Cost:** $0 (ElevenLabs free tier + free APIs)

---

## 1. Concept

Automated video/audio content pipeline that turns live Options Tycoon trade data into social media content. Publishes to X (Twitter) and YouTube automatically. Zero monthly cost.

**Brand:** BuyAI Tech (existing X account + new YouTube channel)
**Niche:** AI-powered retail automation that bypasses institutional cost barriers (QQQ + NIFTY trading)
**Hook:** Raw, unfiltered transparency — live database records, exact slippage, win rates, zero hiding
**Monetization (later):** Content → Trust → DMs → Paid services (custom bots, automation consulting)

---

## 2. Content Strategy

### Primary Formats

| Format | Platform | Frequency | Length | Words |
|--------|----------|-----------|--------|-------|
| Daily Flash (Short) | YouTube Shorts + X | Daily (trading days) | 30-60s | 50-80 words |
| Weekly Recap | YouTube Long-form | Weekly | 3-5 min | 500-700 words |

### Teaser Phase (Before Live Trades — NOW)

| Week | Content | Hook |
|------|---------|------|
| Week 0 | System architecture | "I built a $5/month algo that trades like a hedge fund" |
| Week 1 | Backtest results | "98.2% win rate on 1,250 days of QQQ data. Going live next week." |
| Week 2 | First live trade | "Day 1: The system placed its first real trade. Here's what happened." |
| Week 3+ | Real performance | Actual P&L, slippage, wins/losses — the real show |

### Non-Trading Day Fallback
When system sits out (FOMC, VIX spike, no edge):
- Pull market context (VIX movement, why algo stayed in cash)
- "Why the algorithm chose cash today" — builds trust by showing discipline

### Retention Mechanic
Accountability through radical transparency. Real DB numbers. No curated highlights.

---

## 3. Publishing Strategy

### Phase 1 (Automated)

| Platform | Method | Cost |
|----------|--------|------|
| **YouTube** (Shorts + Long-form) | YouTube Data API v3 (fully automated) | $0 |
| **X / Twitter** | X API v2 (fully automated) | $0 |

### Phase 2 (Semi-Automated — when audience grows)

| Platform | Method | Cost |
|----------|--------|------|
| **TikTok** | Save MP4 to S3/Telegram → manual phone upload (30s/day) | $0 |
| **Instagram Reels** | Same — manual upload from phone | $0 |

**No direct TikTok/IG API** (requires business verification, weeks of review, gets rejected for new accounts). Manual upload is faster and avoids platform bans.

### Phase 3 (When demand exists)

| Item | Trigger |
|------|---------|
| Landing page (buyaitech.com) | When people DM asking "how do I buy?" |
| Paid services page | When you have 3+ paying inquiries |
| Domain purchase | When landing page is needed ($12/year) |

---

## 4. Technical Pipeline

```
[Railway Cron (Post-Market Close)]
  │
  ▼
[Options Tycoon PostgreSQL]
  → Pull QQQ/NIFTY P&L, win rates, slippage
  → If no trades today → pull market context (VIX, indices)
  │
  ▼
[AWS Bedrock (Claude 3.5)]
  → Generate script (cost-barrier disruption narrative)
  → Punchy, 50-80 words for Shorts / 500-700 for weekly
  │
  ▼
[Content Safety Gate]
  → Verify financial figures match DB
  → Ensure no advisory language
  → Add mandatory disclaimer text
  │
  ├──────────────────────────────────┐
  ▼                                  ▼
[ElevenLabs API (Free Tier)]    [Matplotlib / MoviePy]
(Professional voiceover)         (Dark-mode P&L charts, NIFTY/QQQ visuals)
  │                                  │
  └──────────┬───────────────────────┘
             ▼
[MoviePy Video Composer]
  → Merge voiceover + charts + captions
  → 2-second disclaimer overlay at START
  → Disclaimer watermark throughout
  → Output: 9:16 vertical (Shorts) + 16:9 horizontal (Long-form)
  │
  ▼
[AWS S3 Bucket]
  → Archive master .mp4 files
  → Telegram notification with download link (for manual TikTok/IG upload)
  │
  ├──────────────────────────────────┐
  ▼                                  ▼
[YouTube Data API v3]          [X/Twitter API v2]
(Auto-publish Shorts +         (Auto-post video + text)
 Long-form with metadata)
```

---

## 5. Project Structure

```
c:\KIRO\buyaitech\              ← SEPARATE from Options Tycoon
├── pipeline/
│   ├── orchestrator.py         → Main cron entry point
│   ├── data_fetcher.py         → Pulls from Options Tycoon DB + market fallback
│   ├── script_generator.py     → Claude/Bedrock script synthesis
│   ├── chart_renderer.py       → Matplotlib dark-mode visualizations
│   ├── voice_generator.py      → ElevenLabs TTS
│   ├── video_composer.py       → MoviePy assembly + disclaimers
│   └── safety_gate.py          → Verifies figures + compliance
├── publishers/
│   ├── youtube_publisher.py    → YouTube Data API v3
│   ├── twitter_publisher.py    → X API v2 (media upload + tweet)
│   └── telegram_notifier.py   → Sends MP4 link for manual IG/TikTok
├── assets/
│   ├── fonts/                  → Caption fonts
│   ├── music/                  → Background tracks (royalty-free)
│   └── templates/              → Video templates, overlays, disclaimer
├── config/
│   ├── settings.json           → API keys, schedule, content prefs
│   └── credentials.json        → Gitignored API secrets
├── output/                     → Generated videos (ephemeral)
├── requirements.txt
├── Procfile                    → Railway deployment
└── README.md
```

**Isolation guarantee:** This project has ZERO imports from Options Tycoon code. It only reads from the shared PostgreSQL database (read-only queries).

---

## 6. Regulatory Safety (Hardcoded)

Every single video MUST include:
1. **2-second disclaimer overlay at START:** "Educational content only. Not financial advice."
2. **Persistent watermark:** "Personal trading journal. Past performance ≠ future results."
3. **No advisory language:** No "you should", "buy this", "guaranteed returns"
4. **No solicitation:** Content shows what YOU did, never tells viewers what to do

---

## 7. Data Sources

### Primary (Internal — from Options Tycoon PostgreSQL)
- QQQ 0DTE IC: daily fills, slippage, wing adjustments, win/loss, P&L
- NIFTY Weekly IC: strike selections, credit collected, expiry outcomes
- System decisions: FOMC skips, VIX thresholds, event filter triggers

### Secondary (External — fallback for no-trade days)
- VIX level and spikes (yfinance)
- Major index movements (S&P 500, NIFTY, QQQ)
- Macro context from event_calendar.json

### Teaser Phase Data (Before live trades)
- Backtest results (1,250 days of historical QQQ data)
- System architecture screenshots
- Validation history (8 rounds of testing)

---

## 8. Cost Structure

| Item | Monthly Cost |
|------|-------------|
| Railway hosting | $0 (separate service on existing plan) |
| AWS Bedrock (Claude) | ~$0.30 (few thousand tokens/day) |
| ElevenLabs | $0 (free tier: 10K chars/month — enough for 3-4 shorts/week) |
| YouTube API | $0 |
| X/Twitter API | $0 (free tier: 1,500 tweets/month) |
| AWS S3 (video archive) | ~$0.10 (few GB/month) |
| **Total** | **~$0.40/month** |

---

## 9. Voice Configuration

**Provider:** ElevenLabs (free tier)
**Voice:** Professional male analyst (e.g., "Adam" or "Antoni" — test during build)
**Fallback:** AWS Polly Neural (if ElevenLabs quota exhausted mid-month)
**Upgrade trigger:** When publishing daily (needs 30K+ chars/month) → $5/mo Starter plan

**Character budget (free tier = 10,000 chars/month):**
- 3 Shorts/week × 400 chars = 4,800 chars/month
- 1 Weekly recap × 3,500 chars = 3,500 chars/month
- Total: ~8,300 chars/month (within free limit) ✅

---

## 10. First Teaser Script

**Hook:** "I built a $5-a-month automated trading bot that runs entirely on the cloud. Here is how the backtest looks before it goes live this week."

**Script (30s Short):**
> Most quant funds charge $100K minimums and run Bloomberg terminals at $24,000 a year.
> I built the same thing for five dollars a month on Railway.
> 98% win rate across 1,250 days of QQQ data.
> Zero human intervention. Zero overnight risk.
> Next week, it goes live with real money.
> Follow to watch the results in real-time.

**Character count:** ~380 chars ✅ (within free tier)

---

## 11. Accounts & Credentials Needed

| Item | Status | Action |
|------|--------|--------|
| X/Twitter account (BuyAI Tech) | ✅ Exists | Need API keys from developer.twitter.com |
| YouTube channel (BuyAI Tech) | ❌ Create | Create channel → enable API → OAuth |
| ElevenLabs account | ✅ Exists | Get API key from elevenlabs.io dashboard |
| AWS Bedrock (Claude) | ✅ Available | Use existing AWS account |
| AWS S3 bucket | ✅ Available | Create bucket `buyaitech-media` |
| Options Tycoon DB access | ✅ Available | Read-only PostgreSQL connection string |

---

## 12. Build Sequence

| Step | Task | Effort |
|------|------|--------|
| 1 | Project scaffolding + config | 30min |
| 2 | Data fetcher (DB queries + market fallback) | 2h |
| 3 | Script generator (Bedrock/Claude integration) | 2h |
| 4 | Chart renderer (matplotlib dark-mode) | 2h |
| 5 | Voice generator (ElevenLabs API) | 1h |
| 6 | Video composer (MoviePy + disclaimers) | 3h |
| 7 | YouTube publisher (API v3) | 1h |
| 8 | X/Twitter publisher (API v2) | 1h |
| 9 | Telegram notifier (MP4 link for manual IG/TikTok) | 30min |
| 10 | Cron orchestrator + Railway deploy | 30min |
| **Total** | | **~13h** |

---

## 13. External Review Notes (July 30, 2026)

**Approved:**
- Teaser phase using backtest data ✅
- Single-asset video reuse across platforms ✅
- SQL query switch (backtest → live) architecture ✅
- ElevenLabs over Polly for audio quality ✅
- No direct TikTok/IG API (manual upload instead) ✅
- 2-second disclaimer at video start (platform safety) ✅

**Deferred:**
- Landing page → build when demand arrives
- Domain purchase → when people ask where to buy
- TikTok/IG automation → Phase 2 (Buffer/Later when audience grows)
- Paid ElevenLabs → when daily publishing exceeds free tier

---

*Build starts now. Trading system stays untouched. Separate project, separate repo, read-only DB access.*
