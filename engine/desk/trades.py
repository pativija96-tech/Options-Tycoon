"""
Desk trades — the honest journal (Phase 2).

One row per iron condor in `desk_trades`, built only from real fills (Kite orders,
the Kite tradebook, or prices you type in). P&L is never derived from the credit
or a formula; charges are an estimate and labelled as such.

Pure helpers first (testable without Kite or a database), storage after.
"""

import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone

NIFTY_OPTION = re.compile(r"^NIFTY\d")      # NIFTY weekly/monthly options; excludes BANKNIFTY, FINNIFTY, NIFTYNXT50


def is_nifty_option(symbol: str) -> bool:
    s = (symbol or "").upper()
    return bool(NIFTY_OPTION.match(s)) and (s.endswith("CE") or s.endswith("PE"))


def estimate_charges(orders: int) -> float:
    """Same estimate the signal engine uses: ₹20 brokerage per order + 18% GST + ₹50 STT/exchange/stamp."""
    brokerage = 20 * orders
    return round(brokerage + brokerage * 0.18 + 50, 2)


# ── Fills ───────────────────────────────────────────────────────────────────

def aggregate_kite_orders(orders):
    """
    COMPLETE NFO NIFTY option orders from kite.orders() → {(symbol, side): {"qty", "avg"}}.
    Uses filled_quantity and average_price (what actually executed).
    """
    agg = defaultdict(lambda: {"qty": 0, "value": 0.0})
    for o in orders or []:
        sym = o.get("tradingsymbol") or ""
        if o.get("status") != "COMPLETE" or o.get("exchange") != "NFO" or not is_nifty_option(sym):
            continue
        qty = int(o.get("filled_quantity") or o.get("quantity") or 0)
        px = float(o.get("average_price") or 0)
        if qty <= 0 or px <= 0:
            continue
        a = agg[(sym, o.get("transaction_type"))]
        a["qty"] += qty
        a["value"] += qty * px
    return {k: {"qty": v["qty"], "avg": round(v["value"] / v["qty"], 2)} for k, v in agg.items()}


def open_from_fills(ticket_orders, fills):
    """
    Match the ticket's 4 entry orders to real fills.
    Returns (legs, problems). legs only when every leg filled at the ticket quantity.
    """
    legs, problems = [], []
    for o in ticket_orders:
        f = fills.get((o["symbol"], o["side"]))
        if not f:
            problems.append(f"{o['side']} {o['symbol']}: no completed order found")
            continue
        if f["qty"] != o["qty"]:
            problems.append(f"{o['side']} {o['symbol']}: filled {f['qty']} of {o['qty']}")
            continue
        legs.append({"symbol": o["symbol"], "side": o["side"], "strike": o["strike"], "option": o["option"],
                     "qty": o["qty"], "entry_avg": f["avg"], "exit_avg": None})
    return (legs if not problems else None), problems


def entry_credit_per_share(legs):
    """Sum of sells minus sum of buys, per share (all legs share one quantity)."""
    return round(sum(l["entry_avg"] if l["side"] == "SELL" else -l["entry_avg"] for l in legs), 2)


def close_from_fills(legs, fills):
    """Opposite-side fills for each open leg → (legs with exit_avg, problems)."""
    out, problems = [], []
    for l in legs:
        opp = "BUY" if l["side"] == "SELL" else "SELL"
        f = fills.get((l["symbol"], opp))
        if not f:
            problems.append(f"{opp} {l['symbol']}: no completed closing order found")
            continue
        if f["qty"] != l["qty"]:
            problems.append(f"{opp} {l['symbol']}: closed {f['qty']} of {l['qty']}")
            continue
        out.append({**l, "exit_avg": f["avg"]})
    return (out if not problems else None), problems


def gross_pnl(legs):
    """Realised P&L from entry/exit averages: shorts earn entry − exit, longs earn exit − entry."""
    total = 0.0
    for l in legs:
        diff = (l["entry_avg"] - l["exit_avg"]) if l["side"] == "SELL" else (l["exit_avg"] - l["entry_avg"])
        total += diff * l["qty"]
    return round(total, 2)


# ── Kite tradebook CSV → closed iron condors ────────────────────────────────

def parse_tradebook(text):
    """
    Kite Console tradebook CSV rows → fills.
    Columns used: symbol, trade_date, trade_type, quantity, price, expiry_date, order_id
    (the columns listed for the existing /upload-tradebook importer).
    """
    import csv, io
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames:
        reader.fieldnames = [f.strip().lower().replace(" ", "_") for f in reader.fieldnames]
    fills = []
    for row in reader:
        sym = (row.get("symbol") or row.get("tradingsymbol") or "").strip().upper()
        if not is_nifty_option(sym):
            continue
        side = (row.get("trade_type") or "").strip().upper()
        side = "BUY" if side in ("BUY", "B") else "SELL" if side in ("SELL", "S") else None
        try:
            qty = abs(int(float(row.get("quantity") or 0)))
            price = float(row.get("price") or 0)
        except ValueError:
            continue
        d = (row.get("trade_date") or "").strip().split("T")[0].split(" ")[0]
        if not side or qty <= 0 or not d:
            continue
        fills.append({"symbol": sym, "side": side, "qty": qty, "price": price, "date": d,
                      "expiry": (row.get("expiry_date") or "").strip().split("T")[0].split(" ")[0] or None,
                      "order_id": (row.get("order_id") or "").strip() or None})
    return fills


def _strike_option(symbol):
    m = re.match(r"^NIFTY\w*?(\d{4,6})(CE|PE)$", symbol)
    return (int(m.group(1)), m.group(2)) if m else (None, None)


def _order_count(fills):
    """
    Brokerage is per executed order, and one order can fill in several tradebook rows.
    Count distinct order_ids when every row has one; otherwise one order per symbol
    and side (8 for a full iron condor, the signal engine's estimate).
    """
    if fills and all(f.get("order_id") for f in fills):
        return len({f["order_id"] for f in fills})
    return len({(f["symbol"], f["side"]) for f in fills})


def condors_from_tradebook(fills, lot_hint=None):
    """
    Group fills by expiry (falls back to symbol prefix) and keep groups that form a
    4-leg iron condor (2 CE + 2 PE, one long and one short of each). Returns
    (trades, skipped) where trades are closed or open journal rows and skipped
    explains every group that was not an iron condor (e.g. scalps).
    """
    groups = defaultdict(list)
    for f in fills:
        groups[f["expiry"] or f["symbol"][:10]].append(f)
    trades, skipped = [], []
    for key, gf in sorted(groups.items()):
        by_sym = defaultdict(list)
        for f in gf:
            by_sym[f["symbol"]].append(f)
        if len(by_sym) != 4:
            skipped.append({"group": key, "reason": f"{len(by_sym)} symbols — not a 4-leg iron condor", "fills": len(gf)})
            continue
        legs, ok = [], True
        for sym, sf in by_sym.items():
            sf.sort(key=lambda f: f["date"])
            first_side = sf[0]["side"]
            opening = [f for f in sf if f["side"] == first_side]
            closing = [f for f in sf if f["side"] != first_side]
            oq = sum(f["qty"] for f in opening)
            cq = sum(f["qty"] for f in closing)
            strike, opt = _strike_option(sym)
            if strike is None or (cq and cq != oq):
                ok = False
                break
            legs.append({"symbol": sym, "side": first_side, "strike": strike, "option": opt, "qty": oq,
                         "entry_avg": round(sum(f["qty"] * f["price"] for f in opening) / oq, 2),
                         "exit_avg": round(sum(f["qty"] * f["price"] for f in closing) / cq, 2) if cq else None,
                         "opened": opening[0]["date"], "closed": closing[-1]["date"] if closing else None})
        opts = sorted(l["option"] for l in legs) if ok else []
        sides = {(l["option"], l["side"]) for l in legs} if ok else set()
        if not ok or opts != ["CE", "CE", "PE", "PE"] or len(sides) != 4 or len({l["qty"] for l in legs}) != 1:
            skipped.append({"group": key, "reason": "4 symbols but not a balanced iron condor", "fills": len(gf)})
            continue
        closed = all(l["exit_avg"] is not None for l in legs)
        trade = {
            "expiry": key if re.match(r"^\d{4}-\d{2}-\d{2}$", str(key)) else None,
            "opened_on": min(l["opened"] for l in legs),
            "closed_on": max(l["closed"] for l in legs) if closed else None,
            "lot": legs[0]["qty"],
            "legs": [{k: v for k, v in l.items() if k not in ("opened", "closed")} for l in legs],
            "status": "closed" if closed else "open",
        }
        trade["entry_credit"] = entry_credit_per_share(trade["legs"])
        if closed:
            trade["pnl_gross"] = gross_pnl(trade["legs"])
            trade["charges_est"] = estimate_charges(_order_count(gf))
            trade["pnl_net"] = round(trade["pnl_gross"] - trade["charges_est"], 2)
        trades.append(trade)
    return trades, skipped


# ── Storage ─────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_trade(row):
    t = dict(row)
    for k in ("legs_json", "exit_plan_json"):
        t[k.replace("_json", "")] = json.loads(t.pop(k) or "null")
    return t


def list_trades(user_id, market="NIFTY", status=None):
    from db.database import get_connection
    sql = "SELECT * FROM desk_trades WHERE user_id = ? AND market = ?"
    params = [int(user_id), market]
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY opened_on DESC, id DESC"
    conn = get_connection()
    try:
        return [_row_to_trade(r) for r in conn.execute(sql, tuple(params)).fetchall()]
    finally:
        conn.close()


def get_open_trade(user_id, market="NIFTY"):
    rows = list_trades(user_id, market, "open")
    return rows[0] if rows else None


def insert_trade(user_id, trade, market="NIFTY", source="kite_sync"):
    """Insert one journal row; returns its id. Skips (returns None) an identical expiry + strikes + opened_on row."""
    from db.database import get_connection
    legs = trade["legs"]
    strikes = ",".join(f"{l['strike']}{l['option']}" for l in sorted(legs, key=lambda l: (l["option"], l["strike"])))
    conn = get_connection()
    try:
        dup = conn.execute(
            "SELECT id FROM desk_trades WHERE user_id = ? AND market = ? AND strikes = ? AND opened_on = ?",
            (int(user_id), market, strikes, trade["opened_on"])).fetchone()
        if dup:
            return None
        conn.execute(
            """INSERT INTO desk_trades (user_id, market, status, source, opened_on, closed_on, expiry, strikes, lot,
               legs_json, entry_credit, signal_credit, entry_spot, entry_vix, exit_plan_json, pnl_gross, charges_est,
               pnl_net, planned_risk, exit_reason, followed_plan, note, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (int(user_id), market, trade["status"], source, trade["opened_on"], trade.get("closed_on"),
             trade.get("expiry"), strikes, trade["lot"], json.dumps(legs), trade["entry_credit"],
             trade.get("signal_credit"), trade.get("entry_spot"), trade.get("entry_vix"),
             json.dumps(trade.get("exit_plan")), trade.get("pnl_gross"), trade.get("charges_est"),
             trade.get("pnl_net"), trade.get("planned_risk"), trade.get("exit_reason"), None, None, _now(), _now()))
        row = conn.execute(
            "SELECT id FROM desk_trades WHERE user_id = ? AND market = ? AND strikes = ? AND opened_on = ?",
            (int(user_id), market, strikes, trade["opened_on"])).fetchone()
        conn.commit()
        return row["id"] if row else None
    finally:
        conn.close()


def close_trade(user_id, trade_id, legs, closed_on, exit_reason):
    from db.database import get_connection
    gross = gross_pnl(legs)
    charges = estimate_charges(8)
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE desk_trades SET status = 'closed', legs_json = ?, closed_on = ?, pnl_gross = ?, charges_est = ?,
               pnl_net = ?, exit_reason = ?, updated_at = ? WHERE id = ? AND user_id = ? AND status = 'open'""",
            (json.dumps(legs), closed_on, gross, charges, round(gross - charges, 2), exit_reason, _now(),
             int(trade_id), int(user_id)))
        conn.commit()
    finally:
        conn.close()
    return {"pnl_gross": gross, "charges_est": charges, "pnl_net": round(gross - charges, 2)}


def review_trade(user_id, trade_id, followed_plan, note):
    from db.database import get_connection
    if followed_plan not in ("yes", "no", None):
        raise ValueError("followed_plan must be yes, no or empty")
    conn = get_connection()
    try:
        conn.execute("UPDATE desk_trades SET followed_plan = ?, note = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                     (followed_plan, (note or "")[:500] or None, _now(), int(trade_id), int(user_id)))
        conn.commit()
    finally:
        conn.close()
