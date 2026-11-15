"""Calibrate and test the 90% uncertainty band of VIIRS-derived MODIS-equivalent counts.

Variance of an area-month = detection noise (Bernoulli/Poisson, summed over fire units)
                          + (tau_s * predicted)^2   (model error, shared by all cells of the area)
tau_s is estimated per spatial scale s by split-conformal calibration on out-of-sample years
2017-2018 (the DPT model and regional factors were fitted on 2012-2016), then coverage is
measured on held-out 2019-2020 against observed Terra+Aqua MODIS units (orbits still nominal).

python -m pipeline.coverage --aoi india
"""
from __future__ import annotations

import argparse
import json

import h3
import numpy as np
import pandas as pd

from .config import AOIS, PROCESSED

Z90 = 1.645
CAL = (2017 * 12, 2018 * 12 + 11)
TEST = (2019 * 12, 2020 * 12 + 11)
# scale name -> grouping key and the AOI size (in H3 r5 cells) it represents in the app
SCALES = {
    "cell": (["cell", "ym"], 1),
    "r4_1770km2": (["r4", "ym"], 7),
    "r3_12400km2": (["r3", "ym"], 49),
    "r2_87000km2": (["r2", "ym"], 343),
    "national": (["ym"], 100000),
}


def _agg(h: pd.DataFrame, key) -> pd.DataFrame:
    g = h.groupby(key)[["modis_units", "viirs_meq", "viirs_lo", "viirs_hi", "viirs_var"]].sum()
    return g[(g.viirs_meq > 0) | (g.modis_units > 0)]


def bounds(g: pd.DataFrame, a: float, b2: float, k: float):
    """90% band: mid -/+ k * 1.645 * sd, sd^2 = detection noise + a*mid (overdispersion) + b2*mid^2 (model)."""
    mid = g.viirs_meq.to_numpy()
    sd = np.sqrt(g.viirs_var.to_numpy() + a * mid + b2 * mid ** 2)
    lo = np.maximum(np.minimum(g.viirs_lo.to_numpy(), mid) - k * Z90 * sd, 0)
    hi = np.maximum(g.viirs_hi.to_numpy(), mid) + k * Z90 * sd
    return lo, hi


def covered(g, a, b2, k) -> np.ndarray:
    lo, hi = bounds(g, a, b2, k)
    y = g.modis_units.to_numpy()
    return (y >= lo) & (y <= hi)


def fit_variance(g: pd.DataFrame) -> tuple[float, float]:
    """Non-negative moment fit of (resid^2 - detection var) ~ a*mid + b2*mid^2."""
    from scipy.optimize import nnls
    mid = g.viirs_meq.to_numpy()
    r2 = (g.modis_units.to_numpy() - mid) ** 2 - g.viirs_var.to_numpy()
    w = 1 / np.maximum(mid, 1)  # stabilise: weight by 1/mid (variance grows with mid)
    (a, b2), _ = nnls(np.column_stack([mid, mid ** 2]) * w[:, None], r2 * w)
    return float(a), float(b2)


def calibrate(g: pd.DataFrame, a: float, b2: float) -> float:
    """Smallest k whose calibration coverage reaches the finite-sample split-conformal level ceil((n+1)*0.9)/n."""
    n = len(g)
    target = min(1.0, np.ceil((n + 1) * 0.90) / n)
    lo, hi = 0.1, 12.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if covered(g, a, b2, mid).mean() >= target:
            hi = mid
        else:
            lo = mid
    return hi


def run(aoi: str) -> dict:
    out = PROCESSED / aoi
    h = pd.read_parquet(out / "harmonized_r5_week.parquet",
                        columns=["cell", "ym", "modis_units", "viirs_meq", "viirs_lo", "viirs_hi", "viirs_var"])
    h = h.groupby(["cell", "ym"], as_index=False).sum()
    cells = h.cell.unique()
    for r in (4, 3, 2):
        h[f"r{r}"] = h.cell.map({c: h3.cell_to_parent(c, r) for c in cells})
    cal, test = h[h.ym.between(*CAL)], h[h.ym.between(*TEST)]
    res = {"method": "split-conformal; calibrate 2017-2018, test 2019-2020", "scales": []}
    for name, (key, ncells) in SCALES.items():
        gc, gt = _agg(cal, key), _agg(test, key)
        a, b2 = fit_variance(gc)
        k = calibrate(gc, a, b2)
        cov = float(covered(gt, a, b2, k).mean())
        lo, hi = bounds(gt, a, b2, k)
        mid = gt.viirs_meq.to_numpy()
        big = mid >= 20
        rel_w = float(np.median((hi - lo)[big] / 2 / mid[big])) if big.any() else float("nan")
        res["scales"].append({"scale": name, "cells": ncells, "a": round(a, 4), "b2": round(b2, 5), "k": round(k, 3),
                              "coverage_test": round(cov, 3), "median_rel_halfwidth_ge20": round(rel_w, 3),
                              "n_cal": int(len(gc)), "n_test": int(len(gt))})
        print(f"{name:14s} a={a:.3f} b={np.sqrt(b2):.3f} k={k:.2f} | held-out coverage {cov:.1%} | "
              f"median half-width (areas with >=20 units) {rel_w:.0%} | n={len(gt):,}")
    (out / "coverage.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--aoi", required=True, choices=list(AOIS))
    run(p.parse_args().aoi)
