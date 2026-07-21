# Options Tycoon

A gamified options trading sandbox that measures and reflects user behavioral patterns. Practice options trading in a zero-liability paper-trading environment while the system builds a behavioral profile from your trading decisions.

## Overview

Options Tycoon is a local-first application built with:
- **Backend**: Python (FastAPI) serving REST API endpoints and static files
- **Frontend**: Vanilla HTML/JS/CSS (no build tools required)
- **Storage**: SQLite (single file, fully portable)

The platform is a mirror — it shows you your own trading data without ever providing financial advice, recommendations, or trading signals.

## Quick Start

### Windows
```
start-server.bat
```

### Linux / macOS
```bash
chmod +x start-server.sh
./start-server.sh
```

Then open http://localhost:8000 in your browser.

## Installation

```bash
pip install -r requirements.txt
```

## Project Structure

```
options-tycoon/
├── main.py              # FastAPI application entry point
├── requirements.txt     # Python dependencies
├── start-server.bat     # Windows launcher
├── start-server.sh      # Linux/Mac launcher
├── routes/              # API route handlers
├── engine/              # Business logic (Greeks, behavioral, settlement)
├── db/                  # Database schema and connection
├── data/                # Data loading utilities
│   └── mock/            # Bundled mock market data (JSON)
├── static/              # Frontend files served by FastAPI
│   ├── css/             # Stylesheets
│   └── js/              # Client-side JavaScript
├── backups/             # Database backup storage
└── tests/               # Test suite
```

## Disclaimer

**100% Simulated Paper-Trading. No Real Money. No Financial Advice.**

All trading activity in this platform is simulated. No real financial transactions occur. This software does not provide financial advice, recommendations, or trading signals. Deleting the application directory completely removes all application data.
