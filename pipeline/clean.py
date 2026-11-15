"""Raw FIRMS files (country CSVs + API chunks) -> one normalized detections table per AOI.

python -m pipeline.clean --aoi india
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .config import AOIS, INTERIM, RAW, SOURCES

PLATFORM_DT = pd.CategoricalDtype(["Terra", "Aqua", "SNPP", "NOAA20", "NOAA21"])
FAMILY_DT = pd.CategoricalDtype(["MODIS", "VIIRS"])
PROC_DT = pd.CategoricalDtype(["SP", "NRT"])
SOURCE_DT = pd.CategoricalDtype(list(SOURCES))
CONF_DT = pd.CategoricalDtype(["low", "nominal", "high"], ordered=True)
DN_DT = pd.CategoricalDtype(["D", "N"])

READ_DTYPES = {
    "latitude": "float64", "longitude": "float64", "brightness": "float32", "bright_ti4": "float32",
    "scan": "float32", "track": "float32", "acq_date": "string", "acq_time": "int32",
    "satellite": "category", "confidence": "category", "bright_t31": "float32", "bright_ti5": "float32",
    "frp": "float32", "daynight": "category", "type": "float32",
}
VIIRS_PLATFORM = {"VIIRS_SNPP": "SNPP", "VIIRS_NOAA20": "NOAA20", "VIIRS_NOAA21": "NOAA21"}


def _read_source(src_dir: Path) -> pd.DataFrame | None:
    parts = []
    for f in sorted(src_dir.glob("*.csv")):
        if f.stat().st_size == 0:
            continue
        try:
            df = pd.read_csv(f, usecols=lambda c: c in READ_DTYPES, dtype=READ_DTYPES)
        except pd.errors.EmptyDataError:
            continue
        if len(df):
            parts.append(df)
    if not parts:
        return None
    for p in parts:  # align category columns before concat
        for c in ("satellite", "confidence", "daynight"):
            if c in p:
                p[c] = p[c].astype(str)
    return pd.concat(parts, ignore_index=True)


def _conf_class(family: str, conf: pd.Series) -> pd.Series:
    c = conf.astype(str).str.strip().str.lower()
    if family == "MODIS":
        num = pd.to_numeric(c, errors="coerce").to_numpy()
        cls = np.select([num < 30, num < 80], ["low", "nominal"], "high")
        return pd.Series(cls, index=conf.index).astype(CONF_DT)
    return c.str[:1].map({"l": "low", "n": "nominal", "h": "high"}).astype(CONF_DT)


def normalize(raw: pd.DataFrame, source: str) -> pd.DataFrame:
    src = SOURCES[source]
    if src.family == "MODIS":
        sat = raw["satellite"].astype(str).str.strip().str.upper().str[:1]
        platform = sat.map({"T": "Terra", "A": "Aqua"})
        bright, bright2 = raw["brightness"], raw["bright_t31"]
    else:
        platform = pd.Series(next(v for k, v in VIIRS_PLATFORM.items() if source.startswith(k)), index=raw.index)
        bright, bright2 = raw["bright_ti4"], raw["bright_ti5"]
    t = raw["acq_time"].to_numpy()
    utc = (t // 100 + (t % 100) / 60).astype("float32")
    lon = raw["longitude"].to_numpy()
    out = pd.DataFrame({
        "lat": raw["latitude"].to_numpy(),
        "lon": lon,
        "acq_date": pd.to_datetime(raw["acq_date"], format="%Y-%m-%d"),
        "utc_hour": utc,
        "lst_hour": ((utc + lon / 15) % 24).astype("float32"),
        "daynight": raw["daynight"].astype(str).str.upper().str[:1].astype(DN_DT),
        "platform": platform.astype(PLATFORM_DT),
        "family": pd.Categorical([src.family] * len(raw), dtype=FAMILY_DT),
        "processing": pd.Categorical([src.processing] * len(raw), dtype=PROC_DT),
        "source": pd.Categorical([source] * len(raw), dtype=SOURCE_DT),
        "frp": raw["frp"].astype("float32"),
        "scan": raw["scan"].astype("float32"),
        "track": raw["track"].astype("float32"),
        "bright": bright.astype("float32"),
        "bright2": bright2.astype("float32"),
        "conf_class": _conf_class(src.family, raw["confidence"]),
        "type": raw["type"].astype("float32") if "type" in raw else np.float32(np.nan),
    })
    return out.dropna(subset=["platform"])


def run(aoi: str) -> Path:
    print(f"[clean] {AOIS[aoi].name}", flush=True)
    frames = []
    for src_dir in sorted((RAW / aoi).glob("*")):
        if not (src_dir.is_dir() and src_dir.name in SOURCES):
            continue
        raw = _read_source(src_dir)
        if raw is None:
            continue
        frames.append(normalize(raw, src_dir.name))
        print(f"  {src_dir.name}: {len(raw):,} rows", flush=True)
    if not frames:
        raise SystemExit(f"no raw data for {aoi}; run pipeline.bulk / pipeline.fetch first")
    df = pd.concat(frames, ignore_index=True)
    # Standard Processing wins: drop NRT rows on/before each platform's last SP date.
    sp_max = df[df.processing == "SP"].groupby("platform", observed=True)["acq_date"].max()
    drop = np.zeros(len(df), dtype=bool)
    for plat, last in sp_max.items():
        drop |= ((df.platform == plat) & (df.processing == "NRT") & (df.acq_date <= last)).to_numpy()
    df = df[~drop]
    df = df.drop_duplicates(subset=["platform", "lat", "lon", "acq_date", "utc_hour"])
    df = df.sort_values(["acq_date", "utc_hour"]).reset_index(drop=True)
    dest = INTERIM / aoi
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "detections.parquet"
    df.to_parquet(path, index=False)
    summary = df.groupby(["platform", "processing"], observed=True).agg(
        rows=("lat", "size"), first=("acq_date", "min"), last=("acq_date", "max"))
    print(summary.to_string(), flush=True)
    return path


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--aoi", required=True, choices=list(AOIS))
    run(p.parse_args().aoi)
