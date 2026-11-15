"""FIRMS Area API downloader: resumable 5-day chunk cache, transaction-aware throttling.

Usage:
  python -m pipeline.fetch status
  python -m pipeline.fetch availability
  python -m pipeline.fetch run --aoi punjab_haryana [--sources MODIS_SP,VIIRS_SNPP_SP] [--workers 4]
"""
from __future__ import annotations

import argparse
import io
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

from .config import AOIS, BULK_LAST_YEAR, COUNTRY_PRODUCTS, DAY_RANGE, FIRMS_BASE, RAW, SOURCES, SP_TO_NRT, map_key

BULK_SOURCES = {src for src, _, _ in COUNTRY_PRODUCTS.values()}

KEY = ""
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "thermal-twins/0.1 (research pipeline)"
_lock = threading.Lock()
_calls = 0
_pause_until = 0.0


def _mask(text: str) -> str:
    return text.replace(KEY, "***") if KEY else text


def status() -> dict:
    r = SESSION.get(f"{FIRMS_BASE}/mapserver/mapkey_status/", params={"MAP_KEY": KEY}, timeout=30)
    r.raise_for_status()
    return r.json()


def availability() -> pd.DataFrame:
    r = SESSION.get(f"{FIRMS_BASE}/api/data_availability/csv/{KEY}/ALL", timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    RAW.mkdir(parents=True, exist_ok=True)
    df.to_csv(RAW / "_availability.csv", index=False)
    return df


def _throttle() -> None:
    global _calls, _pause_until
    with _lock:
        _calls += 1
        check = _calls % 40 == 0
    wait = _pause_until - time.time()
    if wait > 0:
        time.sleep(wait)
    if check:
        try:
            s = status()
            used, limit = int(s.get("current_transactions", 0)), int(s.get("transaction_limit", 5000))
            if used > 0.85 * limit:
                with _lock:
                    _pause_until = time.time() + 90
                print(f"  [throttle] {used}/{limit} transactions used; pausing 90 s", flush=True)
        except Exception as e:  # status failures must not kill the run
            print(f"  [throttle] status check failed: {_mask(str(e))}", flush=True)


def fetch_chunk(source: str, bbox: tuple, start: date, days: int) -> str:
    area = ",".join(f"{v:g}" for v in bbox)
    url = f"{FIRMS_BASE}/api/area/csv/{KEY}/{source}/{area}/{days}/{start.isoformat()}"
    for attempt in range(6):
        _throttle()
        try:
            r = SESSION.get(url, timeout=120)
            text = r.text
            head = text.lstrip()[:200].lower()
            if r.status_code == 200 and (head.startswith("latitude") or head == ""):
                return text
            if "invalid" in head and "key" in head:
                raise SystemExit("FIRMS rejected the MAP_KEY. Check .env.")
            if "exceed" in head or "limit" in head or r.status_code in (429, 503, 502, 504):
                global _pause_until
                with _lock:
                    _pause_until = time.time() + 120
                print(f"  [retry] {source} {start}: rate/server ({r.status_code}); backing off", flush=True)
            else:
                print(f"  [retry] {source} {start}: HTTP {r.status_code} {_mask(head[:80])!r}", flush=True)
        except requests.RequestException as e:
            print(f"  [retry] {source} {start}: {_mask(str(e))[:120]}", flush=True)
        time.sleep(min(60, 5 * 2 ** attempt))
    raise RuntimeError(f"giving up on {source} {start}")


def _range_for(source: str, avail: pd.DataFrame, today: date, has_bulk: bool) -> tuple[date, date] | None:
    src = SOURCES[source]
    row = avail[avail["data_id"] == source]
    if row.empty:
        return None
    a_min = pd.to_datetime(row["min_date"].iloc[0]).date()
    a_max = pd.to_datetime(row["max_date"].iloc[0]).date()
    start = max(src.default_start, a_min)
    if has_bulk and source in BULK_SOURCES:  # complete years come from country files
        start = max(start, date(BULK_LAST_YEAR + 1, 1, 1))
    end = min(src.default_end or today, a_max, today)
    if src.processing == "NRT":  # only fill the gap after standard processing ends
        sp = next((k for k, v in SP_TO_NRT.items() if v == source), None)
        sp_row = avail[avail["data_id"] == sp] if sp else avail.iloc[0:0]
        if not sp_row.empty:
            start = max(start, pd.to_datetime(sp_row["max_date"].iloc[0]).date() + timedelta(days=1))
    return (start, end) if start <= end else None


def run(aoi_key: str, sources: list[str], workers: int) -> None:
    aoi = AOIS[aoi_key]
    avail = availability()
    today = datetime.now(timezone.utc).date()
    jobs = []
    for s in sources:
        rng = _range_for(s, avail, today, aoi.country is not None)
        if not rng:
            print(f"{s}: not available, skipped")
            continue
        start, end = rng
        out_dir = RAW / aoi.key / s
        out_dir.mkdir(parents=True, exist_ok=True)
        d = start
        while d <= end:
            days = min(DAY_RANGE, (end - d).days + 1)
            f = out_dir / f"{d.isoformat()}_{days}.csv"
            fresh = (d + timedelta(days=days)) >= today - timedelta(days=2)
            if fresh or not f.exists():
                jobs.append((s, d, days, f))
            d += timedelta(days=days)
        print(f"{s}: {start} -> {end}")
    print(f"{aoi.name}: {len(jobs)} chunks to fetch with {workers} workers", flush=True)

    t0, done, rows = time.time(), 0, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_chunk, s, aoi.bbox, d, n): (s, d, f) for s, d, n, f in jobs}
        for fut in as_completed(futs):
            s, d, f = futs[fut]
            text = fut.result()
            tmp = f.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(f)
            done += 1
            rows += max(0, text.count("\n") - 1)
            if done % 50 == 0 or done == len(jobs):
                rate = done / max(1e-6, time.time() - t0)
                eta = (len(jobs) - done) / max(rate, 1e-6) / 60
                print(f"  {done}/{len(jobs)} chunks, ~{rows:,} rows, ETA {eta:.1f} min", flush=True)
    print("done", flush=True)


def main(argv: list[str] | None = None) -> None:
    global KEY
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("availability")
    r = sub.add_parser("run")
    r.add_argument("--aoi", required=True, choices=list(AOIS))
    r.add_argument("--sources", default=",".join(SOURCES))
    r.add_argument("--workers", type=int, default=4)
    a = p.parse_args(argv)
    KEY = map_key()
    if a.cmd == "status":
        print(status())
    elif a.cmd == "availability":
        print(availability().to_string(index=False))
    else:
        run(a.aoi, [s.strip() for s in a.sources.split(",") if s.strip()], a.workers)


if __name__ == "__main__":
    sys.exit(main())
