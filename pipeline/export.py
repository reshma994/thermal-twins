"""Export the harmonized series as a compact static bundle for the web app (no server needed).

web/public/data/<aoi>/meta.json      cells, column layout, splice/drift/validation metadata, presets
web/public/data/<aoi>/monthly.bin.gz columnar typed arrays, one row per (H3 r5 cell, month)

python -m pipeline.export --aoi india
"""
from __future__ import annotations

import argparse
import gzip
import json
from datetime import date

import numpy as np
import pandas as pd

from .config import AOIS, PROCESSED, WEB_DATA

YM0 = 2000 * 12  # month index origin (Jan 2000)
SCALE = 10  # fixed-point for fractional counts

PRESETS = {
    "india": [
        {"id": "all", "name": "All India", "bbox": None},
        {"id": "punjab_haryana", "name": "Punjab & Haryana (crop residue)", "bbox": [73.8, 27.6, 77.6, 32.6]},
        {"id": "uttarakhand", "name": "Uttarakhand (Himalayan forests)", "bbox": [77.5, 28.7, 81.1, 31.5]},
        {"id": "central_india", "name": "Central India forests (MP / Chhattisgarh)", "bbox": [78.0, 19.0, 84.5, 24.5]},
        {"id": "odisha", "name": "Odisha", "bbox": [81.3, 17.8, 87.5, 22.6]},
        {"id": "northeast_jhum", "name": "Mizoram & Manipur (shifting cultivation)", "bbox": [92.2, 21.9, 94.8, 25.7]},
        {"id": "deccan", "name": "Telangana & Andhra Pradesh", "bbox": [76.7, 12.6, 84.8, 19.9]},
    ]
}


def run(aoi: str) -> None:
    src = PROCESSED / aoi
    h = pd.read_parquet(src / "harmonized_r5_week.parquet")
    meta_h = json.loads((src / "harmonize_meta.json").read_text(encoding="utf-8"))
    models = json.loads((src / "dpt_models.json").read_text(encoding="utf-8"))

    cells = sorted(h["cell"].unique())
    cidx = {c: i for i, c in enumerate(cells)}
    wk = h.pivot_table(index=["cell", "ym"], columns="wk", values="meq", aggfunc="sum", fill_value=0)
    wk = wk.reindex(columns=[0, 1, 2, 3], fill_value=0)
    agg = h.groupby(["cell", "ym"]).agg(
        src=("src", "max"), lo=("meq_lo", "sum"), hi=("meq_hi", "sum"), var=("meq_var", "sum"),
        vmeq=("viirs_meq", "sum"), mu=("modis_units", "sum"), mp=("modis_pix", "sum"),
        vu=("viirs_units", "sum"), vp=("viirs_pix", "sum"))
    t = agg.join(wk).reset_index().sort_values(["ym", "cell"])

    def u16(x, scale=1):
        return np.clip(np.rint(np.asarray(x, float) * scale), 0, 65535).astype("<u2")

    cols = [
        ("cell", t["cell"].map(cidx).to_numpy().astype("<u2"), 1),
        ("ym", (t["ym"] - YM0).to_numpy().astype("<u2"), 1),
        ("w0", u16(t[0], SCALE), SCALE), ("w1", u16(t[1], SCALE), SCALE),
        ("w2", u16(t[2], SCALE), SCALE), ("w3", u16(t[3], SCALE), SCALE),
        ("lo", u16(t["lo"], SCALE), SCALE), ("hi", u16(t["hi"], SCALE), SCALE),
        ("var", u16(t["var"], SCALE), SCALE), ("vmeq", u16(t["vmeq"], SCALE), SCALE),
        ("mu", u16(t["mu"]), 1), ("mp", u16(t["mp"]), 1), ("vu", u16(t["vu"]), 1), ("vp", u16(t["vp"]), 1),
        ("src", t["src"].to_numpy().astype("u1"), 1),
    ]
    layout, buf, off = [], bytearray(), 0
    for name, arr, scale in cols:
        b = arr.tobytes()
        layout.append({"name": name, "dtype": "uint16" if arr.dtype.itemsize == 2 else "uint8",
                       "offset": off, "length": int(arr.size), "scale": scale})
        buf += b
        off += len(b)
    out = WEB_DATA / aoi
    out.mkdir(parents=True, exist_ok=True)
    with gzip.open(out / "monthly.bin.gz", "wb", compresslevel=9) as f:
        f.write(bytes(buf))

    val = {k: models[k]["validation"] for k in ("SNPP->Aqua", "SNPP->Terra")}
    curve = {k: models[k]["detection_curve"] for k in ("SNPP->Aqua", "SNPP->Terra")}
    meta = {
        "aoi": aoi, "name": AOIS[aoi].name, "generated": date.today().isoformat(),
        "data_end": "2026-11-14", "ym0": YM0, "n": int(len(t)), "h3_res": 5, "cells": cells, "columns": layout,
        "splice_ym": meta_h["splice_ym"] - YM0, "snpp_last_ym": meta_h["snpp_last_ym"] - YM0,
        "aqua_first_ym": meta_h["aqua_first_ym"] - YM0, "viirs_first_ym": meta_h["viirs_first_ym"] - YM0,
        "modis_first_ym": 2000 * 12 + 10 - YM0, "drift": meta_h["drift"], "validation": val,
        "detection_curve": curve, "collocated": models.get("collocated_SNPP_Aqua"),
        "presets": PRESETS.get(aoi, []),
        "src_codes": {"0": "MODIS observed (Terra+Aqua)", "1": "MODIS Terra observed + modeled Aqua (pre-Jul 2002)",
                      "2": "VIIRS-derived MODIS-equivalent (DPT)"},
    }
    (out / "meta.json").write_text(json.dumps(meta, separators=(",", ":"), default=float), encoding="utf-8")
    print(f"[export] {len(t):,} rows, {len(cells):,} cells -> {out} "
          f"({(out / 'monthly.bin.gz').stat().st_size / 1e6:.1f} MB gz, raw {len(buf) / 1e6:.1f} MB)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--aoi", required=True, choices=list(AOIS))
    run(p.parse_args().aoi)
