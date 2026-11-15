"""Export raw fire detections as per-region download packs for the web app (no server needed).

web/public/data/<aoi>/hotspots/<r2cell>.bin.gz  one file per H3 resolution-2 cell, gzip of a columnar
                                                little-endian table sorted by (day, hhmm):
    lat  int32   round(lat * 1e5)
    lon  int32   round(lon * 1e5)
    day  uint16  days since 2000-01-01
    hhmm uint16  UTC acquisition time as HHMM
    frp  uint16  round(frp * 10), clipped to 0..65535
    code uint8   bits 0-2 platform, bits 3-4 confidence, bit 5 night, bit 6 static source
web/public/data/<aoi>/hotspots/index.json       per-file row count, gzipped size and day range

python -m pipeline.hotspots --aoi india
"""
from __future__ import annotations

import argparse
import gzip
import json
from concurrent.futures import ThreadPoolExecutor

import h3
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .config import AOIS, INTERIM, WEB_DATA

RES = 2
EPOCH = "2000-01-01"
PLATFORMS = ["Terra", "Aqua", "SNPP", "NOAA20", "NOAA21"]
CONFIDENCE = ["low", "nominal", "high"]
COLUMNS = ["lat", "lon", "acq_date", "utc_hour", "platform", "conf_class", "daynight", "frp", "is_static", "h3_r7"]
LAYOUT = [("lat", "<i4"), ("lon", "<i4"), ("day", "<u2"), ("hhmm", "<u2"), ("frp", "<u2"), ("code", "u1")]


def _indices(col: pa.ChunkedArray) -> np.ndarray:
    return np.concatenate([c.indices.to_numpy(zero_copy_only=False) for c in col.chunks])


def _codes(col: pa.ChunkedArray, names: list[str]) -> np.ndarray:
    values = col.chunk(0).dictionary.to_pylist()
    unknown = set(values) - set(names)
    if unknown:
        raise ValueError(f"unexpected values {sorted(unknown)}")
    lut = np.array([names.index(v) for v in values], dtype=np.uint8)
    return lut[_indices(col)]


def hhmm_from_utc_hour(utc_hour: np.ndarray) -> np.ndarray:
    u = np.asarray(utc_hour, dtype=np.float64)
    h = np.floor(u)
    m = np.rint((u - h) * 60.0)
    carry = m == 60
    h = h + carry
    m = np.where(carry, 0, m)
    return (h * 100 + m).astype("<u2")


def encode(t: pa.Table) -> tuple[dict[str, np.ndarray], np.ndarray, list[str]]:
    """Encode a detections table into packed columns plus the r2 cell index of every row."""
    t = t.unify_dictionaries()

    r7 = t["h3_r7"].chunk(0).dictionary.to_pylist()
    parents = [h3.cell_to_parent(c, RES) for c in r7]
    cells = sorted(set(parents))
    cidx = {c: i for i, c in enumerate(cells)}
    r2 = np.array([cidx[p] for p in parents], dtype=np.int64)[_indices(t["h3_r7"])]

    lat = np.rint(t["lat"].to_numpy() * 1e5).astype("<i4")
    lon = np.rint(t["lon"].to_numpy() * 1e5).astype("<i4")
    d = t["acq_date"].to_numpy().astype("datetime64[D]")
    day = (d - np.datetime64(EPOCH, "D")).astype(np.int64)
    if day.min() < 0 or day.max() > 65535:
        raise ValueError("acq_date outside uint16 day range")
    hhmm = hhmm_from_utc_hour(t["utc_hour"].to_numpy())
    frp = np.clip(np.rint(t["frp"].to_numpy().astype(np.float64) * 10.0), 0, 65535).astype("<u2")

    plat = _codes(t["platform"], PLATFORMS)
    conf = _codes(t["conf_class"], CONFIDENCE)
    night = _codes(t["daynight"], ["D", "N"])
    static = t["is_static"].to_numpy(zero_copy_only=False).astype(np.uint8)
    code = (plat | (conf << 3) | (night << 5) | (static << 6)).astype("u1")

    cols = {"lat": lat, "lon": lon, "day": day.astype("<u2"), "hhmm": hhmm, "frp": frp, "code": code}
    return cols, r2, cells


def pack(cols: dict[str, np.ndarray]) -> bytes:
    return b"".join(np.ascontiguousarray(cols[name], dtype=dt).tobytes() for name, dt in LAYOUT)


def run(aoi: str) -> None:
    t = pq.ParquetFile(INTERIM / aoi / "detections.parquet", read_dictionary=["h3_r7"]).read(columns=COLUMNS)
    total = t.num_rows
    cols, r2, cells = encode(t)
    del t

    key = (r2 << 32) | (cols["day"].astype(np.int64) << 16) | cols["hhmm"].astype(np.int64)
    order = np.argsort(key, kind="stable")
    del key
    r2 = r2[order]
    cols = {k: v[order] for k, v in cols.items()}
    del order

    starts = np.flatnonzero(np.r_[True, r2[1:] != r2[:-1]])
    ends = np.r_[starts[1:], len(r2)]

    out = WEB_DATA / aoi / "hotspots"
    out.mkdir(parents=True, exist_ok=True)

    def write(se: tuple[int, int]) -> tuple[str, dict]:
        s, e = se
        cell = cells[r2[s]]
        blob = gzip.compress(pack({k: v[s:e] for k, v in cols.items()}), compresslevel=6, mtime=0)
        (out / f"{cell}.bin.gz").write_bytes(blob)
        day = cols["day"]
        return cell, {"n": int(e - s), "bytes": len(blob), "day_min": int(day[s]), "day_max": int(day[e - 1])}

    with ThreadPoolExecutor() as ex:
        files = dict(sorted(ex.map(write, zip(starts.tolist(), ends.tolist()))))

    index = {"res": RES, "epoch": EPOCH, "platforms": PLATFORMS, "confidence": CONFIDENCE, "files": files}
    (out / "index.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")

    gz = sum(f["bytes"] for f in files.values())
    print(f"{aoi}: {total:,} detections -> {len(files)} files, {gz / 1e6:.1f} MB gzipped -> {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--aoi", required=True, choices=list(AOIS))
    run(p.parse_args().aoi)
