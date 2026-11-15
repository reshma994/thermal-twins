"""Detections -> harmonization units on a common H3 grid, plus a static-source mask.

Unit = (platform, H3 r7 cell, date, day/night). Collapsing to units removes VIIRS 375 m pixel
multiplicity and MODIS bow-tie duplicates in one step (artifact A1).

python -m pipeline.grid --aoi punjab_haryana
"""
from __future__ import annotations

import argparse
from pathlib import Path

import h3
import numpy as np
import pandas as pd

from .config import AOIS, BULK_LAST_YEAR, COUNTRY_PRODUCTS, H3_AGG_RES, H3_UNIT_RES, INTERIM

STATIC_TYPES = {1, 2, 3}  # volcano, other static land source, offshore
PERSISTENCE_THRESHOLD = 0.6  # share of observed months with a detection
MIN_MONTHS = 24
BULK_SOURCES = [s for s, _, _ in COUNTRY_PRODUCTS.values()]


def clip_to_country(df: pd.DataFrame, aoi: str) -> pd.DataFrame:
    """API rows come from a bbox that spills into neighbours; keep only cells inside the country footprint
    (H3 r7 cells seen in FIRMS's own country files), so every year and platform covers the same domain."""
    a = AOIS[aoi]
    if not a.country:
        return df
    year = df["acq_date"].dt.year.to_numpy()
    from_bulk = df["source"].isin(BULK_SOURCES).to_numpy() & (year <= BULK_LAST_YEAR)
    cells = df["h3_r7"]
    foot = pd.Index(cells[from_bulk].unique())
    pd.DataFrame({"h3_r7": foot}).to_parquet(INTERIM / aoi / "footprint.parquet", index=False)
    keep = from_bulk | cells.isin(foot).to_numpy()
    # Holdout: how many genuine in-country detections would this rule drop? (2025 vs footprint from <=2024)
    hist = pd.Index(cells[from_bulk & (year < BULK_LAST_YEAR)].unique())
    test = cells[from_bulk & (year == BULK_LAST_YEAR)]
    miss = float((~test.isin(hist)).mean()) if len(test) else float("nan")
    print(f"[grid] clip to {a.country}: footprint {len(foot):,} r7 cells; dropped {int((~keep).sum()):,} of "
          f"{int((~from_bulk).sum()):,} API rows; holdout false-drop rate {miss:.2%}", flush=True)
    return df[keep]


def add_cells(df: pd.DataFrame) -> pd.DataFrame:
    lat, lon = df["lat"].to_numpy(), df["lon"].to_numpy()
    df["h3_r7"] = [h3.latlng_to_cell(a, b, H3_UNIT_RES) for a, b in zip(lat, lon)]
    return df


def static_mask(df: pd.DataFrame) -> pd.DataFrame:
    """Cells flagged as non-vegetation sources: FIRMS SP type 1-3 majority, or persistent all-year activity."""
    typed_rows = df.loc[df["type"].notna(), ["h3_r7", "type"]]
    by_type = typed_rows["type"].isin(list(STATIC_TYPES)).groupby(typed_rows["h3_r7"]).mean()
    typed = set(by_type[by_type >= 0.5].index)
    d = pd.to_datetime(df["acq_date"])
    ym = (d.dt.year * 12 + d.dt.month).astype("int32")
    span = int(ym.max() - ym.min()) + 1
    months_active = pd.DataFrame({"h3_r7": df["h3_r7"], "ym": ym}).drop_duplicates().groupby("h3_r7").size()
    persistent = set(months_active[(months_active >= MIN_MONTHS) & (months_active / span >= PERSISTENCE_THRESHOLD)].index)
    cells = sorted(typed | persistent)
    return pd.DataFrame({"h3_r7": cells, "by_type": [c in typed for c in cells], "persistent": [c in persistent for c in cells]})


def to_units(df: pd.DataFrame) -> pd.DataFrame:
    conf_rank = df["conf_class"].cat.codes.astype("int8")
    g = df.assign(conf_rank=conf_rank).groupby(["platform", "family", "h3_r7", "acq_date", "daynight"], observed=True)
    u = g.agg(
        n_pix=("lat", "size"),
        frp_sum=("frp", "sum"),
        frp_max=("frp", "max"),
        bright_max=("bright", "max"),
        scan_mean=("scan", "mean"),
        track_mean=("track", "mean"),
        lst_hour=("lst_hour", "mean"),
        utc_hour=("utc_hour", "mean"),
        conf_max=("conf_rank", "max"),
        processing=("processing", "first"),
    ).reset_index()
    u["h3_r6"] = [h3.cell_to_parent(c, H3_AGG_RES) for c in u["h3_r7"].to_numpy()]
    u["pix_area_km2"] = (u["scan_mean"] * u["track_mean"]).astype("float32")
    return u


def run(aoi: str) -> Path:
    src = INTERIM / aoi / "detections.parquet"
    df = add_cells(pd.read_parquet(src).drop(columns=["h3_r7", "is_static"], errors="ignore"))
    df = clip_to_country(df, aoi).reset_index(drop=True)
    mask = static_mask(df)
    mask.to_parquet(INTERIM / aoi / "static_mask.parquet", index=False)
    static = set(mask["h3_r7"])
    df["is_static"] = df["h3_r7"].isin(static) | df["type"].isin(list(STATIC_TYPES)).fillna(False)
    df.to_parquet(src, index=False)
    units = to_units(df[~df["is_static"]])
    path = INTERIM / aoi / "units.parquet"
    units.to_parquet(path, index=False)
    print(f"[grid] {AOIS[aoi].name}: {len(df):,} detections -> {len(units):,} units; "
          f"{len(static)} static cells masked ({int(df['is_static'].sum()):,} detections)")
    yearly = units.assign(year=pd.to_datetime(units["acq_date"]).dt.year).pivot_table(
        index="year", columns="platform", values="n_pix", aggfunc="size", fill_value=0)
    print(yearly.to_string())
    return path


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--aoi", required=True, choices=list(AOIS))
    run(p.parse_args().aoi)
