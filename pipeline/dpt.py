"""Detection-Physics Transfer (DPT).

How many MODIS fire units does a set of VIIRS fire units imply?

    mu_dn(cell, month) = f_region * ( c + sum_b w_dn[b] * N_viirs_dn[b](cell, month) ),   dn in {day, night}

N_viirs_dn[b] = VIIRS fire units (H3 r7, per overpass) whose summed FRP falls in bin b.
w_dn[b] >= 0 = effective probability that MODIS records a fire unit of that intensity (a detection curve
learned from data). f_region = empirical-Bayes regional factor (local burn-timing / cloud regime).
Fitted by non-negative Poisson maximum likelihood on years when Aqua flew its nominal 13:30 orbit.

A second, independent estimate of the curve comes from overpass-level collocation (Aqua vs S-NPP,
same cell or neighbour, same date and day/night).

python -m pipeline.dpt --aoi india
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

import h3
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit, minimize

from .config import AOIS, INTERIM, PROCESSED

FRP_EDGES = np.array([0, 1, 2, 4, 8, 16, 32, 64, np.inf])  # MW, summed per unit
BIN_LABELS = ["<1", "1-2", "2-4", "4-8", "8-16", "16-32", "32-64", ">64"]
TRAIN_YEARS = range(2012, 2017)
TEST_YEARS = range(2017, 2021)
CELL_RES, REGION_RES = 5, 3  # ~252 km2 cells, ~12,400 km2 regions
ALPHA = 30.0  # shrinkage (pseudo-units) for regional factors
DN = ("D", "N")


def load_units(aoi: str) -> pd.DataFrame:
    cache = INTERIM / aoi / "units_dpt.parquet"
    src = INTERIM / aoi / "units.parquet"
    if cache.exists() and cache.stat().st_mtime > src.stat().st_mtime:
        return pd.read_parquet(cache)
    u = pd.read_parquet(src, columns=["platform", "h3_r7", "acq_date", "daynight", "n_pix", "frp_sum", "lst_hour"])
    r7 = u["h3_r7"].astype("category")
    cats = r7.cat.categories
    cell = np.array([h3.cell_to_parent(c, CELL_RES) for c in cats], dtype=object)
    region = np.array([h3.cell_to_parent(c, REGION_RES) for c in cats], dtype=object)
    codes = r7.cat.codes.to_numpy()
    u["cell"], u["region"] = cell[codes], region[codes]
    d = pd.to_datetime(u["acq_date"])
    u["ym"] = (d.dt.year * 12 + d.dt.month - 1).astype("int32")
    u["bin"] = pd.cut(u["frp_sum"].fillna(0), FRP_EDGES, right=False, labels=BIN_LABELS)
    u["platform"] = u["platform"].astype(str)
    u["daynight"] = u["daynight"].astype(str)
    u.to_parquet(cache, index=False)
    return u


def months_of(years) -> pd.Index:
    return pd.Index([y * 12 + m for y in years for m in range(12)])


def table(u: pd.DataFrame, viirs: str, modis: str | None, dn: str, months: pd.Index) -> pd.DataFrame:
    v = u[(u.platform == viirs) & (u.daynight == dn) & u.ym.isin(months)]
    X = v.groupby(["cell", "ym", "bin"], observed=True).size().unstack("bin", fill_value=0)
    X = X.reindex(columns=BIN_LABELS, fill_value=0)
    X.columns = list(BIN_LABELS)
    X["pix"] = v.groupby(["cell", "ym"])["n_pix"].sum()
    if modis:
        m = u[(u.platform == modis) & (u.daynight == dn) & u.ym.isin(months)]
        X = X.join(m.groupby(["cell", "ym"]).size().rename("y"), how="outer")
    X = X.fillna(0)
    X["units"] = X[BIN_LABELS].sum(axis=1)
    cells = X.index.get_level_values("cell")
    X["region"] = [h3.cell_to_parent(c, REGION_RES) for c in cells]
    return X


@dataclass
class Fit:
    w: np.ndarray
    c: float
    region_f: dict

    def predict(self, X: np.ndarray, regions=None) -> np.ndarray:
        mu = self.c + X @ self.w
        if regions is not None:
            mu = mu * np.array([self.region_f.get(r, 1.0) for r in regions])
        return mu


def fit_nonneg_poisson(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    k = X.shape[1]

    def nll(p):
        mu = np.maximum(p[-1] + X @ p[:-1], 1e-9)
        g = 1 - y / mu
        return float(np.sum(mu - y * np.log(mu))), np.append(X.T @ g, g.sum())

    p0 = np.full(k + 1, y.sum() / max(X.sum(), 1))
    p0[-1] = 1e-3
    res = minimize(nll, p0, jac=True, method="L-BFGS-B", bounds=[(0, None)] * k + [(1e-6, None)],
                   options={"maxiter": 3000})
    return res.x[:-1], float(res.x[-1])


def fit_dpt(t: pd.DataFrame) -> Fit:
    X, y = t[BIN_LABELS].to_numpy(float), t["y"].to_numpy(float)
    w, c = fit_nonneg_poisson(X, y)
    mu = c + X @ w
    g = pd.DataFrame({"r": t["region"].to_numpy(), "y": y, "mu": mu}).groupby("r").sum()
    region_f = ((g.y + ALPHA) / (g.mu + ALPHA)).to_dict()
    return Fit(w, c, region_f)


def poisson_dev(y: np.ndarray, mu: np.ndarray) -> float:
    mu = np.maximum(mu, 1e-9)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(y > 0, y * np.log(y / mu), 0.0)
    return float(2 * np.sum(t - (y - mu)))


def metrics(df: pd.DataFrame, col: str) -> dict:
    y, mu = df["y"].to_numpy(float), df[col].to_numpy(float)
    nat = df.groupby(level="ym")[["y", col]].sum()
    yr = nat.groupby(nat.index // 12).sum()
    return {
        "cell_month_pseudo_r2": round(1 - poisson_dev(y, mu) / poisson_dev(y, np.full_like(mu, y.mean())), 3),
        "cell_month_r2": round(float(np.corrcoef(y, mu)[0, 1] ** 2), 3),
        "national_month_wape_pct": round(float(np.abs(nat[col] - nat.y).sum() / nat.y.sum() * 100), 1),
        "national_month_r2": round(float(np.corrcoef(nat.y, nat[col])[0, 1] ** 2), 3),
        "total_bias_pct": round(float((mu.sum() / y.sum() - 1) * 100), 1),
        "annual_bias_pct": {int(k): round(float((r[col] / r.y - 1) * 100), 1) for k, r in yr.iterrows()},
    }


def train_and_validate(u: pd.DataFrame, viirs: str, modis: str, n_boot: int = 30) -> dict:
    tr_m, te_m = months_of(TRAIN_YEARS), months_of(TEST_YEARS)
    preds, fits, curves = [], {}, {}
    k_global = None
    tables = {dn: (table(u, viirs, modis, dn, tr_m), table(u, viirs, modis, dn, te_m)) for dn in DN}
    tot_y = sum(tables[dn][0]["y"].sum() for dn in DN)
    k_pix = tot_y / sum(tables[dn][0]["pix"].sum() for dn in DN)
    k_units = tot_y / sum(tables[dn][0]["units"].sum() for dn in DN)
    for dn in DN:
        tr, te = tables[dn]
        f = fit_dpt(tr)
        fits[dn] = f
        Xte = te[BIN_LABELS].to_numpy(float)
        k_dn = tr["y"].sum() / max(tr["units"].sum(), 1)
        preds.append(pd.DataFrame({
            "y": te["y"],
            "B0_raw_pixels_scaled": te["pix"] * k_pix,
            "B1_equal_area_units_scaled": te["units"] * k_units,
            "B2_units_day_night_scaled": te["units"] * k_dn,
            "DPT_global": f.predict(Xte),
            "DPT_regional": f.predict(Xte, te["region"].to_numpy()),
        }, index=te.index))
        # bootstrap over training years -> detection-curve uncertainty
        rng = np.random.default_rng(7)
        yrs = tr.index.get_level_values("ym") // 12
        Xtr, ytr = tr[BIN_LABELS].to_numpy(float), tr["y"].to_numpy(float)
        boots = []
        for _ in range(n_boot):
            pick = rng.choice(list(TRAIN_YEARS), size=len(TRAIN_YEARS), replace=True)
            rows = np.concatenate([np.flatnonzero(yrs == y) for y in pick])
            boots.append(fit_nonneg_poisson(Xtr[rows], ytr[rows])[0])
        boots = np.array(boots)
        curves[dn] = {b: {"w": round(float(f.w[i]), 4), "lo": round(float(np.percentile(boots[:, i], 5)), 4),
                          "hi": round(float(np.percentile(boots[:, i], 95)), 4)} for i, b in enumerate(BIN_LABELS)}
    p = pd.concat(preds).groupby(level=["cell", "ym"]).sum()
    validation = {c: metrics(p, c) for c in p.columns if c != "y"}
    return {"viirs": viirs, "modis": modis, "train_years": list(TRAIN_YEARS), "test_years": list(TEST_YEARS),
            "weights": {dn: dict(zip(BIN_LABELS, map(float, fits[dn].w))) for dn in DN},
            "intercept": {dn: fits[dn].c for dn in DN},
            "region_factor": {dn: fits[dn].region_f for dn in DN},
            "detection_curve": curves, "validation": validation}


def collocated_curve(u: pd.DataFrame, years=TRAIN_YEARS) -> dict:
    """P(Aqua records a unit within 1 ring | S-NPP unit of FRP F), same date and day/night (both ~13:30 pre-drift)."""
    ms = months_of(years)
    s = u[(u.platform == "SNPP") & u.ym.isin(ms)][["h3_r7", "acq_date", "daynight", "frp_sum"]]
    a = u[(u.platform == "Aqua") & u.ym.isin(ms)][["h3_r7", "acq_date", "daynight"]]
    nb = {c: h3.grid_disk(c, 1) for c in a["h3_r7"].unique()}
    a = a.assign(h3_r7=a["h3_r7"].map(nb)).explode("h3_r7").drop_duplicates()
    a["hit"] = 1
    m = s.merge(a, on=["h3_r7", "acq_date", "daynight"], how="left")
    m["hit"] = m["hit"].fillna(0)
    edges = np.array([0, 0.5, 1, 2, 4, 8, 16, 32, 64, 128, 256, np.inf])
    m["fb"] = pd.cut(m["frp_sum"].fillna(0), edges, right=False)
    out = {}
    for dn in DN:
        g = m[m.daynight == dn].groupby("fb", observed=True)["hit"].agg(["mean", "size"])
        mids = np.array([max(iv.left, 0.25) * (2 if np.isfinite(iv.right) else 1.5) ** 0.5 for iv in g.index])
        p, n = g["mean"].to_numpy(), g["size"].to_numpy()
        z = 1.96
        den = 1 + z ** 2 / n
        ctr = (p + z ** 2 / (2 * n)) / den
        half = z * np.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2)) / den

        def logistic(x, pmax, x50, s):
            return pmax / (1 + np.exp(-(np.log2(x) - np.log2(x50)) / s))

        try:
            (pmax, x50, sc), _ = curve_fit(logistic, mids, p, p0=[0.8, 20, 1], sigma=1 / np.sqrt(n + 1),
                                           bounds=([0.05, 0.3, 0.1], [1.0, 500, 10]))
        except Exception:
            pmax = x50 = sc = float("nan")
        out[dn] = {"bins": [str(iv) for iv in g.index], "frp_mid": mids.round(2).tolist(),
                   "p_detect": p.round(4).tolist(), "ci_lo": (ctr - half).round(4).tolist(),
                   "ci_hi": (ctr + half).round(4).tolist(), "n": n.tolist(),
                   "fit": {"pmax": round(float(pmax), 3), "frp50_mw": round(float(x50), 2), "slope": round(float(sc), 3)}}
    return out


def run(aoi: str) -> None:
    u = load_units(aoi)
    out = PROCESSED / aoi
    out.mkdir(parents=True, exist_ok=True)
    models = {}
    for viirs, modis in [("SNPP", "Aqua"), ("SNPP", "Terra")]:
        m = train_and_validate(u, viirs, modis)
        models[f"{viirs}->{modis}"] = m
        print(f"\n=== {viirs} -> {modis}  (train {TRAIN_YEARS.start}-{TRAIN_YEARS.stop - 1}, "
              f"test {TEST_YEARS.start}-{TEST_YEARS.stop - 1}) ===")
        for name, r in m["validation"].items():
            print(f"  {name:28s} pseudoR2={r['cell_month_pseudo_r2']:.3f} cellR2={r['cell_month_r2']:.3f} "
                  f"natWAPE={r['national_month_wape_pct']:.1f}% natR2={r['national_month_r2']:.3f} "
                  f"bias={r['total_bias_pct']:+.1f}% annual={r['annual_bias_pct']}")
        for dn in DN:
            print(f"  w[{dn}]:", {b: v["w"] for b, v in m["detection_curve"][dn].items()})
    col = collocated_curve(u)
    models["collocated_SNPP_Aqua"] = col
    for dn in DN:
        print(f"\ncollocated P(Aqua | S-NPP unit) {dn}: fit={col[dn]['fit']}")
        print("  ", dict(zip(col[dn]["frp_mid"], col[dn]["p_detect"])))
    (out / "dpt_models.json").write_text(json.dumps(models, indent=1), encoding="utf-8")
    print(f"\nsaved {out / 'dpt_models.json'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--aoi", required=True, choices=list(AOIS))
    run(p.parse_args().aoi)
