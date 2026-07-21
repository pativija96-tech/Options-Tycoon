# Scripts

Utility scripts for the Options Tycoon signal engine. These are NOT part of the web server — they run separately via Task Scheduler or manual invocation.

## Production Scripts (Scheduled)

| Script | Trigger | Time | Purpose |
|--------|---------|------|---------|
| `signal_engine.py` (in engine/signals/) | Windows Task Scheduler | 10:30 AM PHT daily | Generates morning trade signal |
| `eod_report.py` | Windows Task Scheduler | 6:00 PM PHT daily | Runs end-of-day settlement, computes gate metrics |
| `telegram_bot.py` | Called by signal_engine.py | After signal generation | Sends signal to Telegram channel |
| `gate_checker.py` | Called by eod_report.py | After EOD settlement | Recomputes 7-metric unlock gate status |

## Debug/Dev Scripts (Manual)

| Script | Purpose |
|--------|---------|
| `verify_calculations.py` | Validates trade math (spread P&L, slippage) against known values |
| `show_matches.py` | Prints historical pattern matches for today's conditions (debugging) |

## Setup

These scripts require `config/settings.json` and `config/telegram.json` to be configured.
Run from the project root: `python scripts/eod_report.py`
