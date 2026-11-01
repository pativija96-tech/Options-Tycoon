"""
Phase 5 data — download NSE F&O bhavcopies and keep only NIFTY index-option rows.

Run only after approval (it downloads one zip per trading day from NSE's public archive):

    python scripts/phase5_fetch_bhavcopy.py --start 2020-11-02 --end 2026-10-30
    python scripts/phase5_fetch_bhavcopy.py --start 2026-10-26 --end 2026-10-30   # try a few days first

Sources (NSE's public archive; the URL patterns are checked on the first files fetched):
  until early July 2024  https://archives.nseindia.com/content/historical/DERIVATIVES/YYYY/MON/foDDMONYYYYbhav.csv.zip
  from July 2024 (UDiFF) https://archives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip

Each day becomes data/nse_fo/nifty_YYYYMMDD.csv (NIFTY options only); the zip is not kept.
Weekends are skipped; a 404 is recorded as a holiday. One request per second; days
already saved are skipped, so the script can be stopped and resumed.
"""

import argparse
import io
import json
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.research.bhavcopy import BhavcopyFormatError, nifty_options, write_compact  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
UDIFF_FROM = date(2024, 7, 1)   # try the new layout first from here, the old one before; each falls back to the other


def urls(d: date):
    old = (f"https://archives.nseindia.com/content/historical/DERIVATIVES/{d.year}/{d.strftime('%b').upper()}/"
           f"fo{d.strftime('%d')}{d.strftime('%b').upper()}{d.year}bhav.csv.zip")
    new = f"https://archives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{d.strftime('%Y%m%d')}_F_0000.csv.zip"
    return [new, old] if d >= UDIFF_FROM else [old, new]


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Referer": "https://www.nseindia.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def csv_from_zip(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        return z.read(name).decode("utf-8", errors="replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", default=str(ROOT / "data" / "nse_fo"))
    ap.add_argument("--pause", type=float, default=1.0)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log = {"saved": [], "holiday_or_missing": [], "errors": [], "bytes_downloaded": 0}
    d, end = date.fromisoformat(a.start), date.fromisoformat(a.end)
    while d <= end:
        if d.weekday() >= 5:
            d += timedelta(days=1)
            continue
        target = out / f"nifty_{d.strftime('%Y%m%d')}.csv"
        if target.exists():
            d += timedelta(days=1)
            continue
        got = None
        for u in urls(d):
            try:
                blob = fetch(u)
                log["bytes_downloaded"] += len(blob)
                got = (u, blob)
                break
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    log["errors"].append(f"{d} {u}: HTTP {e.code}")
            except Exception as e:
                log["errors"].append(f"{d} {u}: {str(e)[:120]}")
            time.sleep(a.pause)
        if got is None:
            log["holiday_or_missing"].append(d.isoformat())
        else:
            try:
                rows = nifty_options(csv_from_zip(got[1]))
                write_compact(rows, target)
                log["saved"].append(d.isoformat())
                print(f"{d}  {len(rows):5d} NIFTY option rows  ({len(got[1]) // 1024} KB)  {got[0]}")
            except (BhavcopyFormatError, zipfile.BadZipFile, StopIteration, ValueError) as e:
                log["errors"].append(f"{d} {got[0]}: {str(e)[:300]}")
                print(f"{d}  FORMAT PROBLEM: {str(e)[:200]}")
        time.sleep(a.pause)
        d += timedelta(days=1)
    (out / "fetch_log.json").write_text(json.dumps(log, indent=2))
    print(f"\nSaved {len(log['saved'])} days, {len(log['holiday_or_missing'])} holidays/missing, "
          f"{len(log['errors'])} errors, {log['bytes_downloaded'] / 1e6:.1f} MB downloaded. Log: {out / 'fetch_log.json'}")


if __name__ == "__main__":
    main()
