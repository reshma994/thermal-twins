"""Round-trip check of hotspot packs against the source detections.

python -m pipeline.hotspots_verify --aoi india [--cells <r2cell> <r2cell>]
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
from datetime import date

import h3
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from .config import AOIS, INTERIM, WEB_DATA

PROBES = {"Punjab": (30.9, 75.85), "Uttarakhand": (30.1, 79.0)}
REGIONS = {"Punjab": (73.8, 29.5, 77.0, 32.6), "Uttarakhand": (77.5, 28.7, 81.1, 31.5)}


def decode(path, n: int) -> dict[str, np.ndarray]:
    buf = gzip.decompress(path.read_bytes())
    assert len(buf) == 15 * n, (path.name, len(buf), n)
    o = {"lat": 0, "lon": 4 * n, "day": 8 * n, "hhmm": 10 * n, "frp": 12 * n, "code": 14 * n}
    return {
        "lat": np.frombuffer(buf, "<i4", n, o["lat"]),
        "lon": np.frombuffer(buf, "<i4", n, o["lon"]),
        "day": np.frombuffer(buf, "<u2", n, o["day"]),
        "hhmm": np.frombuffer(buf, "<u2", n, o["hhmm"]),
        "frp": np.frombuffer(buf, "<u2", n, o["frp"]),
        "code": np.frombuffer(buf, "u1", n, o["code"]),
    }


def source_rows(aoi: str, cell: str) -> pa.Table:
    f = pq.ParquetFile(INTERIM / aoi / "detections.parquet")
    h = pc.unique(f.read(columns=["h3_r7"])["h3_r7"]).to_pylist()
    keep = pa.array([c for c in h if h3.cell_to_parent(c, 2) == cell], type=pa.large_string())
    cols = ["lat", "lon", "acq_date", "utc_hour", "platform", "conf_class", "daynight", "frp", "is_static", "h3_r7"]
    return pq.read_table(INTERIM / aoi / "detections.parquet", columns=cols, filters=pc.field("h3_r7").isin(keep))


def check(aoi: str, cell: str, meta: dict, index: dict, sample: int, rng: np.random.Generator) -> None:
    d = decode(WEB_DATA / aoi / "hotspots" / f"{cell}.bin.gz", meta["n"])
    key = d["day"].astype(np.int64) * 10000 + d["hhmm"]
    assert np.all(np.diff(key) >= 0), "rows not sorted by (day, hhmm)"
    assert int(d["day"].min()) == meta["day_min"] and int(d["day"].max()) == meta["day_max"]
    assert np.all((d["code"] & 7) < 5) and np.all(((d["code"] >> 3) & 3) < 3) and np.all(d["code"] < 128)

    src = source_rows(aoi, cell)
    assert src.num_rows == meta["n"], (src.num_rows, meta["n"])

    plats, confs, epoch = index["platforms"], index["confidence"], date.fromisoformat(index["epoch"])
    rows = src.take(rng.choice(src.num_rows, min(sample, src.num_rows), replace=False)).to_pylist()
    for r in rows:
        day = (r["acq_date"].date() - epoch).days
        u = r["utc_hour"]
        hh = math.floor(u)
        mm = round((u - hh) * 60)
        if mm == 60:
            hh, mm = hh + 1, 0
        k = day * 10000 + hh * 100 + mm
        lo, hi = np.searchsorted(key, k, "left"), np.searchsorted(key, k, "right")
        frp_exp = min(max(r["frp"], 0.0), 6553.5)
        ok = False
        for i in range(lo, hi):
            c = int(d["code"][i])
            if (abs(d["lat"][i] / 1e5 - r["lat"]) <= 1e-5 + 1e-9 and abs(d["lon"][i] / 1e5 - r["lon"]) <= 1e-5 + 1e-9
                    and plats[c & 7] == r["platform"] and confs[(c >> 3) & 3] == r["conf_class"]
                    and bool(c >> 5 & 1) == (r["daynight"] == "N") and bool(c >> 6 & 1) == r["is_static"]
                    and abs(d["frp"][i] / 10 - frp_exp) <= 0.05 + 1e-9):
                ok = True
                break
        assert ok, f"no decoded match for source row {r}"
    print(f"  {cell}: n={meta['n']:,} matches source count; {len(rows)} sampled rows round-trip OK")


def region_cells(bbox, step: float = 0.1) -> set[str]:
    w, s, e, n = bbox
    return {h3.latlng_to_cell(la, lo, 2) for la in np.arange(s, n + 1e-9, step) for lo in np.arange(w, e + 1e-9, step)}


def main(aoi: str, cells: list[str] | None, sample: int) -> None:
    index = json.loads((WEB_DATA / aoi / "hotspots" / "index.json").read_text(encoding="utf-8"))
    files = index["files"]
    probe = {name: h3.latlng_to_cell(la, lo, 2) for name, (la, lo) in PROBES.items()}
    largest = max(files, key=lambda c: files[c]["n"])
    cells = cells or list(dict.fromkeys([*probe.values(), largest]))[:2]
    rng = np.random.default_rng(0)
    print("round-trip:")
    for c in cells:
        check(aoi, c, files[c], index, sample, rng)

    sizes = {c: f["bytes"] for c, f in files.items()}
    big = max(sizes, key=sizes.get)
    print(f"files: {len(files)}  total: {sum(sizes.values()) / 1e6:.1f} MB  "
          f"rows: {sum(f['n'] for f in files.values()):,}  largest: {big} {sizes[big] / 1e6:.1f} MB")
    for name, c in probe.items():
        f = files.get(c, {"n": 0, "bytes": 0})
        print(f"{name} point {PROBES[name]}: {c}  {f['bytes'] / 1e6:.1f} MB  n={f['n']:,}")
        extra = sorted(region_cells(REGIONS[name]) - {c})
        for x in extra:
            if x in files:
                print(f"  also overlaps {name} bbox: {x}  {files[x]['bytes'] / 1e6:.1f} MB  n={files[x]['n']:,}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--aoi", required=True, choices=list(AOIS))
    p.add_argument("--cells", nargs="*")
    p.add_argument("--sample", type=int, default=3000)
    a = p.parse_args()
    main(a.aoi, a.cells, a.sample)
