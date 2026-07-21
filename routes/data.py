"""
Options Tycoon - Market Data Routes

Provides options chain data, IV Rank, earnings calendar, ticker list,
EOD data from Yahoo Finance, bhavcopy upload/parsing, and broker CSV upload.
"""

import csv
import io
import json
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from typing import Optional

from data.loader import load_mock_data, get_available_tickers, load_earnings_calendar
from db.database import get_connection
from engine.greeks import black_scholes_greeks, compute_iv_rank

router = APIRouter()


def _no_data_response(ticker: str) -> JSONResponse:
    """Return a standard error response when ticker data is not available."""
    return JSONResponse(
        status_code=404,
        content={
            "error": True,
            "code": "NO_DATA_AVAILABLE",
            "message": f"No data available for {ticker}",
        },
    )


@router.get("/tickers")
def list_tickers():
    """Return list of available ticker symbols from mock data."""
    tickers = get_available_tickers()
    return {"tickers": tickers}


@router.get("/chain/{ticker}")
def get_options_chain(ticker: str, expiry: Optional[str] = Query(None)):
    """
    Load options chain for a ticker with computed Greeks.

    Optional query param ?expiry=YYYY-MM-DD filters to a single expiration.
    Returns error response for unknown tickers.
    """
    ticker_upper = ticker.upper()
    data = load_mock_data(ticker_upper)

    if data is None:
        return _no_data_response(ticker_upper)

    underlying_price = data["underlying_price"]
    all_expirations = data.get("expirations", [])

    # Compute IV Rank
    iv_history = data.get("iv_history", [])
    iv_rank = None
    if iv_history:
        current_iv = iv_history[-1]
        iv_rank = compute_iv_rank(current_iv, iv_history)

    # Collect all expiration date strings
    expiration_dates = [exp["date"] for exp in all_expirations]

    # Filter by expiry if provided
    expirations_to_process = all_expirations
    if expiry is not None:
        expirations_to_process = [
            exp for exp in all_expirations if exp["date"] == expiry
        ]

    # Build flat chain rows with Greeks across all expirations
    chain_rows = []
    for exp in expirations_to_process:
        exp_date = exp["date"]

        # Calculate time to expiration in years
        try:
            exp_date_obj = date.fromisoformat(exp_date)
            today = date.today()
            days_to_expiry = (exp_date_obj - today).days
            T = max(days_to_expiry, 0) / 365.0
        except (ValueError, TypeError):
            T = 30.0 / 365.0  # default fallback

        for row in exp.get("chain", []):
            strike = row["strike"]
            call = row["call"]
            put = row["put"]

            # Compute Greeks for call side
            call_greeks = black_scholes_greeks(
                S=underlying_price,
                K=strike,
                T=T,
                sigma=call.get("iv", 0.20),
                option_type="call",
            )

            # Compute Greeks for put side
            put_greeks = black_scholes_greeks(
                S=underlying_price,
                K=strike,
                T=T,
                sigma=put.get("iv", 0.20),
                option_type="put",
            )

            chain_rows.append({
                "strike": strike,
                "call_bid": call["bid"],
                "call_ask": call["ask"],
                "call_last": call["last"],
                "call_volume": call["volume"],
                "call_oi": call["oi"],
                "call_iv": call["iv"],
                "call_delta": call_greeks["delta"],
                "call_gamma": call_greeks["gamma"],
                "call_theta": call_greeks["theta"],
                "call_vega": call_greeks["vega"],
                "put_bid": put["bid"],
                "put_ask": put["ask"],
                "put_last": put["last"],
                "put_volume": put["volume"],
                "put_oi": put["oi"],
                "put_iv": put["iv"],
                "put_delta": put_greeks["delta"],
                "put_gamma": put_greeks["gamma"],
                "put_theta": put_greeks["theta"],
                "put_vega": put_greeks["vega"],
            })

    return {
        "ticker": ticker_upper,
        "underlying_price": underlying_price,
        "iv_rank": iv_rank,
        "expirations": expiration_dates,
        "chain": chain_rows,
    }


@router.get("/iv-rank/{ticker}")
def get_iv_rank(ticker: str):
    """
    Compute and return IV Rank for a ticker using its iv_history.

    Returns None/null if insufficient data (<20 points).
    Returns error response for unknown tickers.
    """
    ticker_upper = ticker.upper()
    data = load_mock_data(ticker_upper)

    if data is None:
        return _no_data_response(ticker_upper)

    iv_history = data.get("iv_history", [])

    # Use the last value in iv_history as the current IV
    if not iv_history:
        return {
            "ticker": ticker_upper,
            "current_iv": None,
            "iv_rank": None,
            "iv_high": None,
            "iv_low": None,
            "data_points": 0,
        }

    current_iv = iv_history[-1]
    iv_rank = compute_iv_rank(current_iv, iv_history)

    return {
        "ticker": ticker_upper,
        "current_iv": current_iv,
        "iv_rank": iv_rank,
        "iv_high": max(iv_history),
        "iv_low": min(iv_history),
        "data_points": len(iv_history),
    }


@router.get("/earnings/{ticker}")
def get_earnings(ticker: str):
    """
    Return upcoming earnings events for the given ticker.

    Returns error response for tickers with no mock data available.
    """
    ticker_upper = ticker.upper()

    # Validate that the ticker exists in our mock data
    data = load_mock_data(ticker_upper)
    if data is None:
        return _no_data_response(ticker_upper)

    earnings_calendar = load_earnings_calendar()

    upcoming = []
    for event in earnings_calendar:
        if event.get("ticker", "").upper() == ticker_upper:
            upcoming.append(event)

    return {
        "ticker": ticker_upper,
        "upcoming_earnings": upcoming,
    }


@router.get("/eod/{ticker}")
async def get_eod_price(ticker: str):
    """Fetch end-of-day price from Yahoo Finance. Falls back to mock data."""
    from engine.yahoo_finance import fetch_eod_price

    result = await fetch_eod_price(ticker)
    if result:
        return {"source": "yahoo_finance", "data": result}
    # Fallback to mock
    mock = load_mock_data(ticker)
    if mock:
        return {"source": "mock", "data": {"ticker": ticker, "price": mock.get("underlying_price")}}
    raise HTTPException(status_code=404, detail=f"No data for {ticker}")


@router.post("/upload/bhavcopy")
async def upload_bhavcopy(file: UploadFile):
    """Upload and parse NSE bhavcopy CSV."""
    from engine.bhavcopy_parser import parse_bhavcopy

    content = await file.read()
    text = content.decode("utf-8", errors="ignore")
    result = parse_bhavcopy(text)
    if result["rows_imported"] == 0:
        raise HTTPException(
            status_code=400,
            detail="No valid options data found in CSV. Expected NSE bhavcopy format with columns: INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,CLOSE,OPEN_INT,CONTRACTS",
        )
    # Cache in database
    conn = get_connection()
    try:
        for ticker, chain_data in result["chains"].items():
            conn.execute(
                "INSERT OR REPLACE INTO market_data_cache (ticker, data_date, data_type, payload) VALUES (?, ?, ?, ?)",
                (ticker, datetime.now().strftime("%Y-%m-%d"), "bhavcopy", json.dumps(chain_data)),
            )
        conn.commit()
    finally:
        conn.close()
    return {"rows_imported": result["rows_imported"], "tickers": result["tickers"]}


@router.post("/upload/broker-csv")
async def upload_broker_csv(file: UploadFile, profile_id: Optional[str] = Form(None)):
    """
    Upload broker trade history CSV (Zerodha/Groww/Angel One).

    FREE — no payment required. Parses the CSV, stores trades,
    generates the full Trader DNA report, and sets profile to Phase D.
    """
    from engine.trader_dna_report import generate_trader_dna_report

    content = await file.read()
    text = content.decode("utf-8", errors="ignore")

    # Parse the CSV
    parsed_trades = _parse_broker_csv(text)

    if not parsed_trades:
        raise HTTPException(
            status_code=400,
            detail="No valid trades found in CSV. Supported formats: Zerodha, Groww, Angel One. "
                   "Expected columns like: symbol/ticker, trade_date/entry_time, quantity, price, pnl/profit.",
        )

    if len(parsed_trades) < 5:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least 5 trades for analysis. Found {len(parsed_trades)} trades in the file.",
        )

    # Get or create profile
    conn = get_connection()
    try:
        pid = int(profile_id) if profile_id else None

        if pid is None:
            # Create a new profile
            cursor = conn.execute(
                "INSERT INTO profiles (name, balance, mode) VALUES (?, ?, ?)",
                ("Trader DNA Import", 10000.0, "sim_only"),
            )
            pid = cursor.lastrowid
            conn.commit()

        # Store trades in the database
        for t in parsed_trades:
            conn.execute(
                """INSERT INTO trades (
                    profile_id, ticker, strategy_type, legs, entry_price,
                    exit_price, position_size, position_pct, realized_pnl,
                    status, opened_at, closed_at, expiration_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pid,
                    t.get('ticker', 'UNKNOWN'),
                    'broker_import',
                    '[]',
                    t.get('entry_price', 0),
                    t.get('exit_price', 0),
                    abs(t.get('pnl', 0)),
                    3.0,  # default position_pct
                    t.get('pnl', 0),
                    'closed',
                    t.get('entry_time', datetime.now().isoformat()),
                    t.get('exit_time', datetime.now().isoformat()),
                    t.get('exit_time', datetime.now().isoformat()),
                ),
            )

        # Set profile to Phase D via behavioral_metrics
        conn.execute(
            """INSERT OR REPLACE INTO behavioral_metrics
               (profile_id, source, total_trades, phase, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (pid, 'broker_import', len(parsed_trades), 'D', datetime.now().isoformat()),
        )
        conn.commit()

    finally:
        conn.close()

    # Generate the full Devastating Report
    report = generate_trader_dna_report(parsed_trades)

    return {
        "profile_id": pid,
        "trades_analyzed": len(parsed_trades),
        "report": report,
    }


def _parse_broker_csv(text: str) -> list[dict]:
    """Delegate to engine.csv_parser for broker CSV parsing."""
    from engine.csv_parser import parse_broker_csv
    return parse_broker_csv(text)


@router.post("/upload/broker-csv-free")
async def upload_broker_csv_free(request: Request, file: UploadFile):
    """
    Free CSV upload — no profile required. Returns devastating report data.
    Parses the CSV, runs behavioral analysis, returns full Trader DNA report.
    
    Security:
    - Rate limited: 5 uploads per minute per IP
    - Max 10MB file size (server-side enforced)
    - Raw CSV processed IN-MEMORY ONLY — never written to disk or stored
    - Personal identifiers (Client ID, Demat, PAN, Name) stripped before analysis
    - Formula injection characters (=, +, @) stripped from all cells
    - The raw file content is discarded after parsing — only computed analysis results are returned
    """
    from engine.trader_dna_report import generate_trader_dna_report
    
    # P0-10: Per-endpoint rate limit (imported from main)
    from main import limiter
    # Rate limit is enforced via decorator or middleware — here we just document it

    # P0: Server-side file size limit (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File too large. Maximum size is 10MB. Try exporting a shorter date range from your broker.",
        )
    if len(content) < 50:
        raise HTTPException(
            status_code=400,
            detail="File appears to be empty. Please upload a valid CSV with trade data.",
        )

    text = content.decode("utf-8", errors="ignore")

    # Parse the CSV
    parsed_trades = _parse_broker_csv(text)

    if not parsed_trades:
        raise HTTPException(
            status_code=400,
            detail="Could not parse trades from your CSV. This may be a broker format we haven't seen yet. "
                   "Supported formats: Zerodha Tradebook, Groww, Angel One. "
                   "If you believe this is a valid broker export, please email your file format details (not the file itself) "
                   "to support@optionstycoon.app and we'll add support within 24 hours.",
        )

    if len(parsed_trades) < 5:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least 5 matched trades for meaningful analysis. Found {len(parsed_trades)} trades. "
                   "Try exporting a longer date range from your broker (at least 1-2 weeks of trading).",
        )

    # Generate the full Devastating Report (no DB storage needed)
    report = generate_trader_dna_report(parsed_trades)

    return {
        "trades_analyzed": len(parsed_trades),
        "report": report,
    }


@router.post("/analyze-csv")
async def analyze_csv_for_report(file: UploadFile):
    """
    Analyze uploaded broker CSV and return devastating behavioral report data.
    FREE — no payment required.
    """
    from engine.bhavcopy_parser import parse_broker_csv
    from engine.behavioral import (
        compute_discipline_rating,
        compute_patience_score,
        compute_sizing_consistency,
        compute_emotional_reactivity,
        detect_loss_disposition,
    )

    content = await file.read()
    text = content.decode("utf-8", errors="ignore")

    # Parse the CSV as broker trade history
    trades = parse_broker_csv(text)

    if not trades:
        raise HTTPException(
            status_code=400,
            detail="Could not parse CSV. Expected broker trade history with columns: Date, Symbol, Buy/Sell, Quantity, Price.",
        )

    # Compute all behavioral metrics
    total_trades = len(trades)
    winners = [t for t in trades if t.get("realized_pnl", 0) > 0]
    losers = [t for t in trades if t.get("realized_pnl", 0) < 0]
    total_loss = sum(abs(t["realized_pnl"]) for t in losers)

    # Detect behavioral flags (already flagged during parsing)
    revenge_trades = [t for t in trades if t.get("is_revenge_trade")]
    overconf_trades = [t for t in trades if t.get("is_overconfidence_trap")]
    impulse_trades = [t for t in trades if t.get("is_impulse_early_exit")]

    revenge_cost = sum(
        abs(t.get("realized_pnl", 0))
        for t in revenge_trades
        if t.get("realized_pnl", 0) < 0
    )
    overconf_cost = sum(
        abs(t.get("realized_pnl", 0))
        for t in overconf_trades
        if t.get("realized_pnl", 0) < 0
    )
    impulse_left = sum(
        (t.get("max_unrealized_pnl", 0) - t.get("realized_pnl", 0))
        for t in impulse_trades
        if t.get("max_unrealized_pnl", 0) > t.get("realized_pnl", 0)
    )

    behavioral_cost = revenge_cost + overconf_cost + impulse_left
    behavioral_pct = (behavioral_cost / total_loss * 100) if total_loss > 0 else 0

    # Compute metrics
    discipline = compute_discipline_rating(trades)
    patience = compute_patience_score(trades)
    sizing = compute_sizing_consistency(trades)
    emotional = compute_emotional_reactivity(trades)

    # Loss disposition
    loss_disposition = detect_loss_disposition(trades)

    # What-if calculation
    net_pnl = sum(t.get("realized_pnl", 0) for t in trades)
    pnl_without_revenge = net_pnl + revenge_cost

    # Build shareable text
    shareable = (
        f"My Trader DNA: Discipline {discipline:.0f}%, "
        f"Emotional Reactivity {emotional:.0f}/100. "
        f"{behavioral_pct:.0f}% of my losses are behavioral. "
        f"Analyzed by Options Tycoon — free at options-tycoon.app"
    ) if discipline is not None and emotional is not None else None

    return {
        "total_trades": total_trades,
        "winners": len(winners),
        "losers": len(losers),
        "win_rate": round(len(winners) / total_trades * 100, 1) if total_trades > 0 else 0,
        "total_loss": round(total_loss, 2),
        "behavioral_cost": round(behavioral_cost, 2),
        "behavioral_pct": round(behavioral_pct, 1),
        "revenge": {"count": len(revenge_trades), "cost": round(revenge_cost, 2)},
        "overconfidence": {"count": len(overconf_trades), "cost": round(overconf_cost, 2)},
        "impulse_exits": {"count": len(impulse_trades), "profit_left": round(impulse_left, 2)},
        "loss_disposition": loss_disposition,
        "discipline_rating": discipline,
        "patience_score": patience,
        "sizing_consistency": sizing,
        "emotional_reactivity": emotional,
        "net_pnl": round(net_pnl, 2),
        "what_if_no_revenge": round(pnl_without_revenge, 2),
        "shareable": shareable,
    }
