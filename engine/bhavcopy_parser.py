"""NSE Bhavcopy CSV parser and Broker CSV parser for Options Tycoon."""
import csv
import io
from datetime import datetime, timedelta
from typing import Optional


def parse_bhavcopy(csv_content: str) -> dict:
    """
    Parse NSE F&O bhavcopy CSV content.

    NSE bhavcopy columns typically:
    INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP

    Returns:
        {
            "tickers": ["NIFTY", "BANKNIFTY", ...],
            "rows_imported": 150,
            "chains": {
                "NIFTY": {
                    "expirations": [
                        {
                            "date": "2025-01-30",
                            "chain": [
                                {"strike": 22500, "call": {...}, "put": {...}},
                                ...
                            ]
                        }
                    ]
                }
            }
        }
    """
    reader = csv.DictReader(io.StringIO(csv_content))

    chains = {}
    rows_imported = 0

    for row in reader:
        try:
            instrument = row.get("INSTRUMENT", "").strip()
            if instrument not in ("OPTSTK", "OPTIDX"):
                continue

            symbol = row.get("SYMBOL", "").strip()
            expiry_raw = row.get("EXPIRY_DT", "").strip()
            strike = float(row.get("STRIKE_PR", 0))
            option_type = row.get("OPTION_TYP", "").strip()  # CE or PE
            close_price = float(row.get("CLOSE", 0))
            open_int = int(row.get("OPEN_INT", 0))
            volume = int(row.get("CONTRACTS", 0))

            if not symbol or not expiry_raw or strike <= 0:
                continue

            # Parse expiry date (DD-Mon-YYYY format from NSE)
            from datetime import datetime
            try:
                expiry_dt = datetime.strptime(expiry_raw, "%d-%b-%Y")
                expiry_str = expiry_dt.strftime("%Y-%m-%d")
            except ValueError:
                expiry_str = expiry_raw

            # Initialize chain structure
            if symbol not in chains:
                chains[symbol] = {"expirations": {}}
            if expiry_str not in chains[symbol]["expirations"]:
                chains[symbol]["expirations"][expiry_str] = {}

            chain = chains[symbol]["expirations"][expiry_str]

            if strike not in chain:
                chain[strike] = {"strike": strike, "call": None, "put": None}

            # Build option data
            spread = max(0.5, close_price * 0.01)
            option_data = {
                "bid": round(max(0.05, close_price - spread / 2), 2),
                "ask": round(close_price + spread / 2, 2),
                "last": round(close_price, 2),
                "volume": volume,
                "oi": open_int,
                "iv": 0.20,  # Default IV, would need calculation
            }

            if option_type == "CE":
                chain[strike]["call"] = option_data
            elif option_type == "PE":
                chain[strike]["put"] = option_data

            rows_imported += 1

        except (ValueError, KeyError):
            continue

    # Convert to list format
    result_chains = {}
    for symbol, data in chains.items():
        result_chains[symbol] = {"expirations": []}
        for expiry_str, strikes_dict in sorted(data["expirations"].items()):
            chain_list = []
            for strike_val in sorted(strikes_dict.keys()):
                entry = strikes_dict[strike_val]
                if entry["call"] and entry["put"]:
                    chain_list.append(entry)
            if chain_list:
                result_chains[symbol]["expirations"].append({
                    "date": expiry_str,
                    "chain": chain_list,
                })

    return {
        "tickers": list(result_chains.keys()),
        "rows_imported": rows_imported,
        "chains": result_chains,
    }


# ---------------------------------------------------------------------------
# Broker Trade History CSV Parser
# ---------------------------------------------------------------------------

# Column name mappings for different brokers
_COLUMN_ALIASES = {
    "date": ["trade_date", "date", "order_date", "execution_date", "trade date", "order date"],
    "symbol": ["symbol", "tradingsymbol", "trading_symbol", "scrip", "instrument", "stock"],
    "trade_type": ["trade_type", "type", "buy/sell", "buy_sell", "side", "order_type", "transaction_type"],
    "quantity": ["quantity", "qty", "filled_quantity", "filled qty", "traded_quantity", "net_qty"],
    "price": ["price", "avg_price", "average_price", "trade_price", "avg price", "traded_price"],
    "order_time": ["order_execution_time", "time", "execution_time", "trade_time", "order_time"],
    "exchange": ["exchange", "segment", "market"],
}


def _find_column(headers: list[str], field: str) -> Optional[str]:
    """Find the actual column name from headers that matches a field alias."""
    lower_headers = {h.lower().strip(): h for h in headers}
    for alias in _COLUMN_ALIASES.get(field, []):
        if alias.lower() in lower_headers:
            return lower_headers[alias.lower()]
    return None


def _parse_date(value: str) -> Optional[datetime]:
    """Try parsing a date string in common Indian broker formats."""
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%d-%b-%Y",
        "%d %b %Y",
    ]
    value = value.strip()
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def parse_broker_csv(csv_content: str) -> list[dict]:
    """
    Parse broker trade history CSV (Zerodha, Groww, Angel One formats).

    Expected columns (flexible matching):
    - Date (trade_date, date, order_date, etc.)
    - Symbol (symbol, tradingsymbol, scrip, etc.)
    - Trade Type (buy/sell, trade_type, side, etc.)
    - Quantity (quantity, qty, filled_quantity, etc.)
    - Price (price, avg_price, trade_price, etc.)
    - Time (optional: order_execution_time, time, etc.)

    Returns list of trade dicts with computed fields:
    - realized_pnl, position_pct, opened_at, closed_at, is_revenge_trade,
      is_overconfidence_trap, is_impulse_early_exit, max_unrealized_pnl
    """
    reader = csv.DictReader(io.StringIO(csv_content))

    if not reader.fieldnames:
        return []

    headers = list(reader.fieldnames)

    # Map columns
    date_col = _find_column(headers, "date")
    symbol_col = _find_column(headers, "symbol")
    type_col = _find_column(headers, "trade_type")
    qty_col = _find_column(headers, "quantity")
    price_col = _find_column(headers, "price")
    time_col = _find_column(headers, "order_time")

    if not date_col or not symbol_col or not type_col or not qty_col or not price_col:
        return []

    # Collect raw entries
    raw_entries = []
    for row in reader:
        try:
            date_str = row.get(date_col, "").strip()
            symbol = row.get(symbol_col, "").strip()
            trade_type = row.get(type_col, "").strip().upper()
            qty = abs(float(row.get(qty_col, "0").replace(",", "")))
            price = abs(float(row.get(price_col, "0").replace(",", "")))
            time_str = row.get(time_col, "").strip() if time_col else ""

            if not symbol or qty <= 0 or price <= 0:
                continue

            # Normalize trade type
            if trade_type in ("BUY", "B", "BOUGHT"):
                side = "BUY"
            elif trade_type in ("SELL", "S", "SOLD"):
                side = "SELL"
            else:
                continue

            # Parse datetime
            dt = None
            if time_str and date_str:
                dt = _parse_date(date_str + " " + time_str)
            if not dt:
                dt = _parse_date(date_str)
            if not dt:
                continue

            raw_entries.append({
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": price,
                "datetime": dt,
                "value": qty * price,
            })
        except (ValueError, TypeError, KeyError):
            continue

    if not raw_entries:
        return []

    # Sort by datetime
    raw_entries.sort(key=lambda x: x["datetime"])

    # Match buys to sells per symbol (FIFO) to compute realized P&L
    trades = _match_trades(raw_entries)

    # Compute behavioral flags
    _flag_behavioral_patterns(trades)

    return trades


def _match_trades(entries: list[dict]) -> list[dict]:
    """
    Match buy/sell entries into closed trades using FIFO per symbol.
    Returns list of trade dicts with realized_pnl, opened_at, closed_at, etc.
    """
    # Group by symbol
    positions = {}  # symbol -> list of open entries
    closed_trades = []

    # Estimate portfolio value for position_pct
    total_capital = sum(e["value"] for e in entries) / max(1, len(entries)) * 10  # rough estimate

    for entry in entries:
        symbol = entry["symbol"]
        side = entry["side"]

        if symbol not in positions:
            positions[symbol] = {"buys": [], "sells": []}

        if side == "BUY":
            # Try to match against existing sells (short covering)
            matched = _try_match(positions[symbol]["sells"], entry, total_capital, closed_trades, is_short=True)
            if not matched:
                positions[symbol]["buys"].append(entry)
        else:  # SELL
            # Try to match against existing buys (closing long)
            matched = _try_match(positions[symbol]["buys"], entry, total_capital, closed_trades, is_short=False)
            if not matched:
                positions[symbol]["sells"].append(entry)

    return closed_trades


def _try_match(open_entries: list, closing_entry: dict, total_capital: float, closed_trades: list, is_short: bool) -> bool:
    """Try to match closing entry against open entries FIFO."""
    if not open_entries:
        return False

    remaining_qty = closing_entry["qty"]
    matched_any = False

    while remaining_qty > 0 and open_entries:
        opening = open_entries[0]
        match_qty = min(remaining_qty, opening["qty"])

        if is_short:
            # Closing a short: sold first, buying back now
            pnl = (opening["price"] - closing_entry["price"]) * match_qty
            opened_at = opening["datetime"]
            closed_at = closing_entry["datetime"]
        else:
            # Closing a long: bought first, selling now
            pnl = (closing_entry["price"] - opening["price"]) * match_qty
            opened_at = opening["datetime"]
            closed_at = closing_entry["datetime"]

        trade_value = opening["price"] * match_qty
        position_pct = (trade_value / total_capital * 100) if total_capital > 0 else 5.0

        # Simulate max_unrealized_pnl (estimate: between realized and 2x realized for winners)
        if pnl > 0:
            max_unrealized = pnl * (1.5 + (hash(opening["symbol"]) % 100) / 100.0)
        else:
            max_unrealized = max(0, pnl * 0.1)

        closed_trades.append({
            "symbol": opening["symbol"],
            "realized_pnl": round(pnl, 2),
            "position_pct": round(min(position_pct, 25), 2),
            "opened_at": opened_at.isoformat(),
            "closed_at": closed_at.isoformat(),
            "quantity": match_qty,
            "entry_price": opening["price"],
            "exit_price": closing_entry["price"],
            "max_unrealized_pnl": round(max_unrealized, 2),
            "is_revenge_trade": False,
            "is_overconfidence_trap": False,
            "is_impulse_early_exit": False,
        })

        remaining_qty -= match_qty
        opening["qty"] -= match_qty
        if opening["qty"] <= 0:
            open_entries.pop(0)
        matched_any = True

    return matched_any


def _flag_behavioral_patterns(trades: list[dict]) -> None:
    """Flag behavioral patterns on matched trades in-place."""
    if not trades:
        return

    from engine.behavioral import (
        detect_revenge_trade,
        detect_overconfidence_trap,
        detect_impulse_early_exit,
    )

    # Average position size
    avg_pct = sum(t["position_pct"] for t in trades) / len(trades)

    for i, trade in enumerate(trades):
        # Recent closed trades before this one
        recent = trades[max(0, i - 10):i]

        # Revenge trade detection
        trade["is_revenge_trade"] = detect_revenge_trade(
            trade_position_size=trade["position_pct"],
            avg_position_size=avg_pct,
            recent_trades=recent,
            trade_opened_at=trade["opened_at"],
        )

        # Overconfidence detection
        recent_closed = sorted(
            [t for t in recent if t.get("realized_pnl") is not None],
            key=lambda t: t.get("closed_at", ""),
            reverse=True,
        )
        trade["is_overconfidence_trap"] = detect_overconfidence_trap(
            trade_position_size=trade["position_pct"],
            avg_position_size=avg_pct,
            recent_closed_trades=recent_closed,
        )

        # Impulse early exit detection
        trade["is_impulse_early_exit"] = detect_impulse_early_exit(
            realized_pnl=trade.get("realized_pnl", 0),
            max_unrealized_pnl=trade.get("max_unrealized_pnl", 0),
        )
