"""Bulk history from FIRMS country yearly CSVs (no MAP_KEY, no transaction quota).

Files land in data/raw/<aoi>/<SOURCE>/<year>_country.csv so pipeline.clean reads them
alongside API chunks.

python -m pipeline.bulk --aoi india
"""
from __future__ import annotations

import argparse
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

from .config import AOIS, COUNTRY_BASE, COUNTRY_PRODUCTS, RAW

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "thermal-twins/0.1 (research pipeline)"


def _download(url: str) -> bytes | None:
    for attempt in range(5):
        try:
            r = SESSION.get(url, timeout=600)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.content
        except requests.RequestException as e:
            print(f"  [retry] {url.rsplit('/', 1)[1]}: {str(e)[:100]}", flush=True)
            time.sleep(5 * 2 ** attempt)
    raise RuntimeError(f"failed: {url}")


def _job(aoi_key: str, product: str, source: str, year: int) -> tuple[str, int, int]:
    aoi = AOIS[aoi_key]
    out = RAW / aoi.key / source / f"{year}_country.csv"
    if out.exists() and out.stat().st_size > 0:
        return (f"{source} {year}", -1, 0)
    url = f"{COUNTRY_BASE}/{product}/{year}/{product}_{year}_{aoi.country}.csv"
    content = _download(url)
    out.parent.mkdir(parents=True, exist_ok=True)
    if content is None:
        out.write_text("", encoding="utf-8")
        return (f"{source} {year}", 0, 0)
    if aoi.crop:
        df = pd.read_csv(io.BytesIO(content), dtype=str)
        w, s, e, n = aoi.bbox
        lat, lon = df["latitude"].astype(float), df["longitude"].astype(float)
        df = df[lat.between(s, n) & lon.between(w, e)]
        tmp = out.with_suffix(".tmp")
        df.to_csv(tmp, index=False)
        rows = len(df)
    else:
        tmp = out.with_suffix(".tmp")
        tmp.write_bytes(content)
        rows = content.count(b"\n") - 1
    tmp.replace(out)
    return (f"{source} {year}", rows, len(content))


def run(aoi_key: str, workers: int) -> None:
    aoi = AOIS[aoi_key]
    if not aoi.country:
        raise SystemExit(f"{aoi_key} has no FIRMS country mapping")
    jobs = [(p, src, y) for p, (src, y0, y1) in COUNTRY_PRODUCTS.items() for y in range(y0, y1 + 1)]
    print(f"[bulk] {aoi.name} from {aoi.country} files: {len(jobs)} files, crop={aoi.crop}", flush=True)
    t0, total = time.time(), 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_job, aoi_key, p, s, y) for p, s, y in jobs]
        for i, f in enumerate(as_completed(futs), 1):
            name, rows, size = f.result()
            total += max(size, 0)
            state = "cached" if rows < 0 else ("missing" if size == 0 else f"{rows:,} rows, {size / 1e6:.1f} MB")
            print(f"  [{i}/{len(jobs)}] {name}: {state}  ({total / 1e6:.0f} MB, {time.time() - t0:.0f} s)", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--aoi", required=True, choices=list(AOIS))
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    run(a.aoi, a.workers)
