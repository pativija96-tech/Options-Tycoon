"""
NSE F&O bhavcopy → NIFTY index-option rows, for the Phase 5 replay.

Two NSE file layouts exist; both are read by column name:
  old (until early July 2024): INSTRUMENT, SYMBOL, EXPIRY_DT, STRIKE_PR, OPTION_TYP,
       OPEN, HIGH, LOW, CLOSE, SETTLE_PR, TIMESTAMP   (dates like 30-Jan-2024; the same
       columns engine/bhavcopy_parser.py reads)
  new "UDiFF" (from July 2024): TradDt, FinInstrmTp, TckrSymb, XpryDt, StrkPric, OptnTp,
       OpnPric, HghPric, LwPric, ClsPric, SttlmPric   (dates like 2024-07-08)
The new-format names are checked against the first real file before any replay is
trusted: a file missing a required column raises BhavcopyFormatError naming it.

Unlike engine/bhavcopy_parser.py, nothing is invented here — no bid/ask, no IV.
"""

import csv
import io
from datetime import date, datetime

OLD = {"date": "TIMESTAMP", "instrument": "INSTRUMENT", "symbol": "SYMBOL", "expiry": "EXPIRY_DT",
       "strike": "STRIKE_PR", "opt": "OPTION_TYP", "open": "OPEN", "high": "HIGH", "low": "LOW",
       "close": "CLOSE", "settle": "SETTLE_PR"}
NEW = {"date": "TradDt", "instrument": "FinInstrmTp", "symbol": "TckrSymb", "expiry": "XpryDt",
       "strike": "StrkPric", "opt": "OptnTp", "open": "OpnPric", "high": "HghPric", "low": "LwPric",
       "close": "ClsPric", "settle": "SttlmPric"}
INDEX_OPTION = {"OPTIDX", "IDO"}
COMPACT_FIELDS = ["date", "expiry", "strike", "opt", "open", "high", "low", "close", "settle"]


class BhavcopyFormatError(ValueError):
    pass


def _date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d%b%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date {s!r}")


def _num(s):
    try:
        v = float(str(s).strip())
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def nifty_options(csv_text: str):
    """NIFTY (not BANKNIFTY / FINNIFTY / NIFTYNXT50) index-option rows from one bhavcopy."""
    reader = csv.DictReader(io.StringIO(csv_text))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = headers
    lower = {h.lower(): h for h in headers}
    if "instrument" in lower and "symbol" in lower:
        cols, layout = OLD, "old"
    elif "fininstrmtp" in lower and "tckrsymb" in lower:
        cols, layout = NEW, "new"
    else:
        raise BhavcopyFormatError(f"Not a known F&O bhavcopy layout. Columns: {', '.join(headers[:20])}")
    actual = {}
    for key, name in cols.items():
        if name.lower() not in lower:
            raise BhavcopyFormatError(f"{layout} layout but column {name!r} is missing. Columns: {', '.join(headers[:30])}")
        actual[key] = lower[name.lower()]

    out = []
    for row in reader:
        if (row.get(actual["instrument"]) or "").strip().upper() not in INDEX_OPTION:
            continue
        if (row.get(actual["symbol"]) or "").strip().upper() != "NIFTY":
            continue
        opt = (row.get(actual["opt"]) or "").strip().upper()
        strike = _num(row.get(actual["strike"]))
        if opt not in ("CE", "PE") or not strike:
            continue
        out.append({"date": _date(row[actual["date"]]).isoformat(), "expiry": _date(row[actual["expiry"]]).isoformat(),
                    "strike": int(round(strike)), "opt": opt,
                    **{k: _num(row.get(actual[k])) for k in ("open", "high", "low", "close", "settle")}})
    return out


def write_compact(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COMPACT_FIELDS)
        w.writeheader()
        w.writerows(rows)


def read_compact(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [{"date": r["date"], "expiry": r["expiry"], "strike": int(r["strike"]), "opt": r["opt"],
                 **{k: _num(r[k]) for k in ("open", "high", "low", "close", "settle")}}
                for r in csv.DictReader(f)]


def price(row):
    """Closing price of a contract, else its settlement price (NSE fills one when there were no trades)."""
    if row is None:
        return None
    for k in ("close", "settle"):
        v = row.get(k)
        if v is not None and v > 0:
            return v
    return None


def build_days(rows):
    """{trade date: {expiry: {(strike, opt): row}}}."""
    days = {}
    for r in rows:
        days.setdefault(r["date"], {}).setdefault(r["expiry"], {})[(r["strike"], r["opt"])] = r
    return days


def parity_spot(chain):
    """NIFTY level implied by put-call parity at the strike where call and put are closest: K + C − P."""
    best = None
    for (k, opt), r in chain.items():
        if opt != "CE":
            continue
        c, p = price(r), price(chain.get((k, "PE")))
        if c is None or p is None:
            continue
        gap = abs(c - p)
        if best is None or gap < best[0]:
            best = (gap, k + c - p)
    return None if best is None else round(best[1], 2)


def as_date(s) -> date:
    return date.fromisoformat(s[:10])
