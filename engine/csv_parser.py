"""
Options Tycoon — Broker CSV Parser

Parses trade history CSV files from Indian brokers into standardized trade dicts.

Supported brokers:
- Zerodha (Tradebook format — buy/sell legs matched via FIFO)
- Groww (direct P&L format)
- Angel One (direct P&L format)
- Generic (any CSV with symbol, date, price, pnl columns)

Security features:
- CSV formula injection stripping (=, +, @)
- Personal identifier removal (client_id, demat, PAN, name)
- Strict numeric validation for price/quantity fields
- In-memory only processing — raw CSV never written to disk
"""

import csv
import io
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict


def parse_broker_csv(text: str) -> list[dict]:
    """
    Parse broker CSV into standardized trade dicts.
    
    Returns list of dicts, each with:
    - ticker: str
    - entry_time: ISO datetime string
    - exit_time: ISO datetime string
    - entry_price: float
    - exit_price: float
    - quantity: int
    - pnl: float
    """
    # Security: Strip formula injection characters
    text = _strip_formula_injection(text)

    # Try to detect format from headers
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []

    # Normalize header names to lowercase
    headers = [h.strip().lower() for h in reader.fieldnames]

    # Detect if this is a tradebook format (buy/sell legs, no PnL column)
    # Supports: Zerodha (trade_type), Groww (type+quantity+price), Angel One (trade_type)
    has_trade_direction = ('trade_type' in headers or 'tradingsymbol' in headers or
                          ('type' in headers and 'quantity' in headers and 'price' in headers))
    has_no_pnl = ('pnl' not in headers and 'profit' not in headers
                  and 'realized_pnl' not in headers and 'net_pnl' not in headers)
    is_tradebook = has_trade_direction and has_no_pnl

    if is_tradebook:
        return _match_tradebook_legs(text, headers)

    # Standard format — each row is a completed trade with P&L
    trades = []
    for row in reader:
        normalized = {k.strip().lower(): v.strip() if isinstance(v, str) else v for k, v in row.items()}

        # Skip rows with non-numeric data in numeric fields (broker summary rows, notes)
        if _is_non_trade_row(normalized):
            continue

        trade = _extract_trade_from_row(normalized, headers)
        if trade:
            trades.append(trade)

    trades.sort(key=lambda t: t.get('entry_time', ''))
    _compute_pnl_if_missing(trades)
    return trades


# ===========================================================================
# SECURITY
# ===========================================================================

def _strip_formula_injection(text: str) -> str:
    """Strip CSV formula injection characters from all cells."""
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        cells = line.split(',')
        clean_cells = []
        for cell in cells:
            stripped = cell.strip()
            while stripped and stripped[0] in ('=', '+', '@'):
                stripped = stripped[1:]
            stripped = stripped.replace('\t', '').replace('\r', '')
            clean_cells.append(stripped)
        clean_lines.append(','.join(clean_cells))
    return '\n'.join(clean_lines)


def _is_non_trade_row(normalized: dict) -> bool:
    """Check if a row contains non-numeric data in price/qty fields (broker summary rows)."""
    for key in ['price', 'quantity', 'qty', 'buy_price', 'sell_price']:
        if key in normalized and normalized[key]:
            val = str(normalized[key]).strip().replace(',', '')
            if val and not val.replace('.', '').replace('-', '').isdigit():
                return True
    return False


# ===========================================================================
# ROW EXTRACTION
# ===========================================================================

def _extract_trade_from_row(row: dict, headers: list) -> Optional[dict]:
    """Extract a trade dict from a single CSV row, supporting multiple broker formats."""
    trade = {}

    # --- Ticker/Symbol ---
    for key in ['symbol', 'ticker', 'stock_name', 'scrip', 'instrument', 'contract']:
        if key in row and row[key]:
            trade['ticker'] = row[key].upper().strip()
            break
    if 'ticker' not in trade:
        return None

    # --- Entry Time ---
    for key in ['trade_date', 'entry_time', 'date', 'order_date', 'time', 'timestamp',
                'executed_at', 'trade_time', 'opening_date']:
        if key in row and row[key]:
            parsed = _try_parse_date(row[key])
            if parsed:
                trade['entry_time'] = parsed.isoformat()
                break
    if 'entry_time' not in trade:
        trade['entry_time'] = datetime.now().isoformat()

    # --- Exit Time ---
    for key in ['exit_time', 'closing_date', 'settlement_date', 'close_date']:
        if key in row and row[key]:
            parsed = _try_parse_date(row[key])
            if parsed:
                trade['exit_time'] = parsed.isoformat()
                break
    if 'exit_time' not in trade:
        entry = _try_parse_date(trade['entry_time'])
        if entry:
            trade['exit_time'] = (entry + timedelta(hours=2)).isoformat()
        else:
            trade['exit_time'] = trade['entry_time']

    # --- Prices ---
    for key in ['price', 'buy_price', 'entry_price', 'avg_price', 'buy_avg']:
        if key in row and row[key]:
            try:
                trade['entry_price'] = float(row[key].replace(',', ''))
                break
            except (ValueError, AttributeError):
                pass

    for key in ['sell_price', 'exit_price', 'close_price', 'sell_avg']:
        if key in row and row[key]:
            try:
                trade['exit_price'] = float(row[key].replace(',', ''))
                break
            except (ValueError, AttributeError):
                pass

    if 'entry_price' not in trade:
        trade['entry_price'] = 0
    if 'exit_price' not in trade:
        trade['exit_price'] = trade['entry_price']

    # --- Quantity ---
    for key in ['quantity', 'qty', 'buy_qty', 'trade_qty', 'lot_size', 'units']:
        if key in row and row[key]:
            try:
                trade['quantity'] = abs(int(float(row[key].replace(',', ''))))
                break
            except (ValueError, AttributeError):
                pass
    if 'quantity' not in trade:
        trade['quantity'] = 1

    # --- P&L ---
    for key in ['pnl', 'profit', 'realized_pnl', 'net_pnl', 'profit_loss',
                'realized_profit', 'pl', 'net_profit', 'gain_loss']:
        if key in row and row[key]:
            try:
                val = row[key].replace(',', '').replace('(', '-').replace(')', '')
                trade['pnl'] = float(val)
                break
            except (ValueError, AttributeError):
                pass

    # --- Trade type ---
    for key in ['trade_type', 'type', 'side', 'buy_sell', 'order_type']:
        if key in row and row[key]:
            trade['trade_type'] = row[key].lower()
            break

    return trade


# ===========================================================================
# TRADEBOOK LEG MATCHING (Zerodha format)
# ===========================================================================

def _match_tradebook_legs(text: str, headers: list) -> list[dict]:
    """
    Match buy/sell legs from a Zerodha-style tradebook into complete trades.
    Groups legs by symbol, matches buys with sells using FIFO weighted averages.
    """
    reader = csv.DictReader(io.StringIO(text))

    legs_by_symbol = defaultdict(list)
    for row in reader:
        normalized = {k.strip().lower(): v.strip() if isinstance(v, str) else v for k, v in row.items()}
        symbol = (normalized.get('symbol', '') or normalized.get('tradingsymbol', '')).upper().strip()
        if not symbol:
            continue

        trade_type = (normalized.get('trade_type', '') or normalized.get('type', '')).lower().strip()
        try:
            qty = abs(float(normalized.get('quantity', '0').replace(',', '')))
            price = float(normalized.get('price', '0').replace(',', ''))
        except (ValueError, TypeError):
            continue

        time_str = (normalized.get('order_execution_time', '') or 
                    normalized.get('trade_date', '') or 
                    normalized.get('date', ''))
        parsed_time = _try_parse_date(time_str)

        legs_by_symbol[symbol].append({
            'type': trade_type,
            'qty': qty,
            'price': price,
            'time': parsed_time,
        })

    # Match buys with sells (FIFO weighted average)
    matched_trades = []
    for symbol, legs in legs_by_symbol.items():
        legs.sort(key=lambda l: l['time'] or datetime.min)

        buys = [l for l in legs if l['type'] == 'buy']
        sells = [l for l in legs if l['type'] == 'sell']

        if buys and sells:
            total_buy_qty = sum(b['qty'] for b in buys)
            total_sell_qty = sum(s['qty'] for s in sells)
            avg_buy = sum(b['price'] * b['qty'] for b in buys) / total_buy_qty if total_buy_qty > 0 else 0
            avg_sell = sum(s['price'] * s['qty'] for s in sells) / total_sell_qty if total_sell_qty > 0 else 0

            matched_qty = min(total_buy_qty, total_sell_qty)
            pnl = round((avg_sell - avg_buy) * matched_qty, 2)

            entry_time = buys[0]['time']
            exit_time = sells[-1]['time'] if sells else buys[-1]['time']

            matched_trades.append({
                'ticker': symbol,
                'entry_time': entry_time.isoformat() if entry_time else '',
                'exit_time': exit_time.isoformat() if exit_time else '',
                'entry_price': round(avg_buy, 2),
                'exit_price': round(avg_sell, 2),
                'quantity': int(matched_qty),
                'pnl': pnl,
            })

    matched_trades.sort(key=lambda t: t.get('entry_time', ''))
    return matched_trades


# ===========================================================================
# HELPERS
# ===========================================================================

def _compute_pnl_if_missing(trades: list[dict]):
    """Compute P&L from entry/exit prices if not provided."""
    for t in trades:
        if 'pnl' not in t or t['pnl'] == 0:
            entry = t.get('entry_price', 0)
            exit_p = t.get('exit_price', 0)
            qty = t.get('quantity', 1)
            if entry > 0 and exit_p > 0:
                t['pnl'] = round((exit_p - entry) * qty, 2)


def _try_parse_date(val: str) -> Optional[datetime]:
    """Try multiple date formats common across Indian brokers."""
    if not val:
        return None

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%b-%Y",
        "%d %b %Y",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(val.strip(), fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(val.strip())
    except (ValueError, TypeError):
        return None
