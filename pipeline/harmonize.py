"""Harmonized MODIS-equivalent (MEQ) burning-activity series, 2000-11 -> now.

Per (H3 r5 cell, month, week-of-month):
  * MODIS actual units (Terra+Aqua) where MODIS is trusted,
  * VIIRS-derived MEQ via DPT (S-NPP, then NOAA-20 after S-NPP ends) from the data-chosen splice month,
  * Terra-only months before Aqua (2000-11..2002-06) completed with a regional Aqua/Terra ratio.
Also: orbit-drift diagnostic (actual / VIIRS-predicted per year, national and Punjab).

python -m pipeline.harmonize --aoi india
"""
from __future__ import annotations

import argparse
import json

import h3
import numpy as np
import pandas as pd

from .config import AOIS, INTERIM, PROCESSED
from .dpt import ALPHA, BIN_LABELS, load_units

SNPP_LAST_YM = 2026 * 12 + 9  # Oct 2026: last full S-NPP month (delivery ended 2026-11-02)
AQUA_FIRST_YM = 2002 * 12 + 6  # Jul 2002
VIIRS_FIRST_YM = 2012 * 12 + 0
PUNJAB = AOIS["punjab_haryana"].bbox


def _lookup(model: dict, key: str) -> dict:
    """(dn, bin) -> weight (or lo/hi)."""
    return {(dn, b): v[key] for dn, curve in model["detection_curve"].items() for b, v in curve.items()}


CAL_MONTHS = (2013 * 12, 2016 * 12 + 11)  # calibration window (S-NPP commissioning year 2012 excluded)


def raw_weights(u: pd.DataFrame, model: dict) -> pd.DataFrame:
    keys = list(zip(u["daynight"].to_numpy(), u["bin"].astype(str).to_numpy()))
    out = {}
    for k in ("w", "lo", "hi"):
        lut = _lookup(model, k)
        out[k] = np.fromiter((lut.get(x, 0.0) for x in keys), float, len(keys))
    return pd.DataFrame(out, index=u.index)


def calibrate(v: pd.DataFrame, w0: np.ndarray, modis: pd.DataFrame, platform: str) -> dict:
    """Region x day/night factor so that, over the calibration window, VIIRS-predicted == MODIS actual units
    on the real prediction domain (captures MODIS-only detections + local burn timing). Shrunk by ALPHA."""
    lo, hi = CAL_MONTHS
    sv = v.ym.between(lo, hi).to_numpy()
    pred = pd.DataFrame({"region": v["region"].to_numpy()[sv], "dn": v["daynight"].to_numpy()[sv], "mu": w0[sv]})
    pm = pred.groupby(["dn", "region"])["mu"].sum()
    mm = modis[(modis.platform == platform) & modis.ym.between(lo, hi)].groupby(["daynight", "region"]).size()
    mm.index.names = ["dn", "region"]
    j = pd.concat([pm.rename("mu"), mm.rename("y")], axis=1).fillna(0)
    g = j.groupby(level="dn").sum()
    out = {}
    for dn in ("D", "N"):
        jj = j.loc[dn]
        k_dn = g.loc[dn, "y"] / g.loc[dn, "mu"]  # national prior for this dn
        out[dn] = ((jj.y + ALPHA * k_dn) / (jj.mu + ALPHA)).to_dict()
        out[dn]["__default__"] = float(k_dn)
    return out


def unit_weights(v: pd.DataFrame, raw: pd.DataFrame, rf: dict) -> pd.DataFrame:
    f = np.ones(len(v))
    for dn in ("D", "N"):
        sel = (v["daynight"] == dn).to_numpy()
        f[sel] = v.loc[sel, "region"].map(rf[dn]).fillna(rf[dn]["__default__"]).to_numpy()
    return raw.mul(f, axis=0)


def run(aoi: str) -> None:
    models = json.loads((PROCESSED / aoi / "dpt_models.json").read_text(encoding="utf-8"))
    mA, mT = models["SNPP->Aqua"], models["SNPP->Terra"]
    u = load_units(aoi)
    u = u.assign(day=pd.to_datetime(u["acq_date"]).dt.day.to_numpy())
    u["wk"] = np.minimum((u["day"] - 1) // 7, 3).astype("int8")

    # ---- VIIRS input stream: S-NPP through Oct 2026, NOAA-20 (rescaled to S-NPP) afterwards
    ov = u[u.platform.isin(["SNPP", "NOAA20"]) & u.ym.between(2019 * 12, 2025 * 12 + 11)]
    ratio = ov.groupby(["daynight", "platform"]).size().unstack()
    n20_scale = (ratio["SNPP"] / ratio["NOAA20"]).to_dict()
    print("NOAA-20 -> S-NPP unit scale:", {k: round(v, 3) for k, v in n20_scale.items()})
    v = u[((u.platform == "SNPP") & (u.ym <= SNPP_LAST_YM)) | ((u.platform == "NOAA20") & (u.ym > SNPP_LAST_YM))].copy()
    scale = np.where(v.platform == "NOAA20", v["daynight"].map(n20_scale).to_numpy(), 1.0)
    modis_units = u[u.platform.isin(["Terra", "Aqua"])][["platform", "ym", "daynight", "region"]]
    ra, rt = raw_weights(v, mA), raw_weights(v, mT)
    rf_a = calibrate(v, ra["w"].to_numpy(), modis_units, "Aqua")
    rf_t = calibrate(v, rt["w"].to_numpy(), modis_units, "Terra")
    print("national calibration factors  Aqua:", {d: round(rf_a[d]["__default__"], 3) for d in "DN"},
          " Terra:", {d: round(rf_t[d]["__default__"], 3) for d in "DN"})
    wa, wt = unit_weights(v, ra, rf_a), unit_weights(v, rt, rf_t)
    p = pd.DataFrame({
        "cell": v["cell"].to_numpy(), "ym": v["ym"].to_numpy(), "wk": v["wk"].to_numpy(),
        "pred": (wa["w"] + wt["w"]).to_numpy() * scale,
        "pred_A": wa["w"].to_numpy() * scale, "pred_T": wt["w"].to_numpy() * scale,
        "lo": (wa["lo"] + wt["lo"]).to_numpy() * scale, "hi": (wa["hi"] + wt["hi"]).to_numpy() * scale,
        "viirs_units": scale, "viirs_pix": v["n_pix"].to_numpy() * scale,
    })
    pc = np.clip(p["pred"].to_numpy(), 0, None)
    p["var"] = np.where(pc <= 1, pc * (1 - pc), pc)  # Bernoulli per unit (Poisson if > 1)
    pred = p.groupby(["cell", "ym", "wk"]).sum()

    # ---- MODIS actual
    m = u[u.platform.isin(["Terra", "Aqua"])]
    act = m.groupby(["cell", "ym", "wk", "platform"]).agg(units=("n_pix", "size"), pix=("n_pix", "sum")).unstack("platform", fill_value=0)
    act.columns = [f"{a}_{b}" for a, b in act.columns]
    act = act.reindex(columns=["units_Terra", "units_Aqua", "pix_Terra", "pix_Aqua"], fill_value=0)

    # ---- Orbit-drift diagnostic: actual / VIIRS-predicted per year (national + Punjab)
    lat_lon = {c: h3.cell_to_latlng(c) for c in u["cell"].unique()}
    w_, s_, e_, n_ = PUNJAB
    punjab_cells = {c for c, (la, lo) in lat_lon.items() if s_ <= la <= n_ and w_ <= lo <= e_}
    j = act.join(pred[["pred_A", "pred_T"]], how="outer").fillna(0)
    j = j[j.index.get_level_values("ym") >= VIIRS_FIRST_YM]
    lst = (u[(u.daynight == "D") & u.platform.isin(["Terra", "Aqua", "SNPP", "NOAA20", "NOAA21"])]
           .assign(year=lambda d: d.ym // 12).groupby(["year", "platform"])["lst_hour"].mean().unstack().round(2))
    drift = {}
    for name, sel in [("india", None), ("punjab_haryana", punjab_cells)]:
        jj = j if sel is None else j[j.index.get_level_values("cell").isin(sel)]
        y = jj.groupby(jj.index.get_level_values("ym") // 12).sum()
        d = pd.DataFrame({"aqua_ratio": y.units_Aqua / y.pred_A, "terra_ratio": y.units_Terra / y.pred_T,
                          "modis_ratio": (y.units_Aqua + y.units_Terra) / (y.pred_A + y.pred_T)}).round(3)
        d = d.join(lst[["Terra", "Aqua"]].rename(columns={"Terra": "terra_lst", "Aqua": "aqua_lst"}))
        drift[name] = d
        print(f"\n[drift] {name}: MODIS actual / VIIRS-predicted, with mean daytime local solar time\n{d.to_string()}")

    # ---- Splice month: first year >= 2021 whose national MODIS ratio leaves the 2012-2020 envelope
    nat = drift["india"]["modis_ratio"]
    base = nat.loc[2013:2020]
    thr = max(0.08, 2 * float(base.std()), float((base - 1).abs().max()))
    late = nat.loc[2021:]
    bad = late[(late - 1).abs() > thr]
    splice_year = int(bad.index.min()) if len(bad) else 2021
    splice_ym = splice_year * 12
    print(f"\n[splice] envelope +/-{thr:.3f}; first out-of-envelope year: "
          f"{int(bad.index.min()) if len(bad) else 'none'} -> splice at {splice_year}-01")

    # ---- Pre-Aqua months: Aqua-equivalent from Terra via regional ratio (2003-2011)
    reg = {c: h3.cell_to_parent(c, 3) for c in u["cell"].unique()}
    hist = act[(act.index.get_level_values("ym") >= AQUA_FIRST_YM + 6) & (act.index.get_level_values("ym") < VIIRS_FIRST_YM)]
    hk = hist.reset_index()
    hk["region"], hk["mo"] = hk["cell"].map(reg), hk["ym"] % 12
    r_reg = hk.groupby("region")[["units_Aqua", "units_Terra"]].sum()
    ratio_r = (r_reg.units_Aqua + ALPHA) / (r_reg.units_Terra + ALPHA)
    r_rm = hk.groupby(["region", "mo"])[["units_Aqua", "units_Terra"]].sum()
    prior = ratio_r.reindex(r_rm.index.get_level_values("region")).to_numpy()
    ratio_rm = ((r_rm.units_Aqua.to_numpy() + ALPHA * prior) / (r_rm.units_Terra.to_numpy() + ALPHA))
    ratio_rm = dict(zip(r_rm.index, ratio_rm))  # (region, calendar month) -> Aqua/Terra, shrunk to regional ratio
    ratio_r = ratio_r.to_dict()

    h = act.join(pred, how="outer").fillna(0).reset_index()
    ym = h["ym"].to_numpy()
    modis = (h["units_Terra"] + h["units_Aqua"]).to_numpy(float)
    pre_aqua = ym < AQUA_FIRST_YM
    fill = np.zeros(len(h))
    idx = np.flatnonzero(pre_aqua)
    for i, c, m in zip(idx, h["cell"].to_numpy()[idx], ym[idx]):
        r = reg[c]
        fill[i] = ratio_rm.get((r, m % 12), ratio_r.get(r, 2.0))
    fill *= h["units_Terra"].to_numpy()
    use_pred = ym >= splice_ym
    h["src"] = np.select([use_pred, pre_aqua], [2, 1], 0).astype("int8")
    h["meq"] = np.where(use_pred, h["pred"], np.where(pre_aqua, modis + fill, modis))
    h["meq_lo"] = np.where(use_pred, h["lo"], h["meq"])
    h["meq_hi"] = np.where(use_pred, h["hi"], h["meq"])
    h["meq_var"] = np.where(use_pred, h["var"], np.where(pre_aqua, fill, 0.0))
    h["modis_units"], h["modis_pix"] = modis, (h["pix_Terra"] + h["pix_Aqua"]).to_numpy(float)
    keep = ["cell", "ym", "wk", "src", "meq", "meq_lo", "meq_hi", "meq_var", "modis_units", "modis_pix",
            "pred", "viirs_units", "viirs_pix"]
    h = h[keep].rename(columns={"pred": "viirs_meq"})
    out = PROCESSED / aoi
    h.to_parquet(out / "harmonized_r5_week.parquet", index=False)
    meta = {"splice_ym": splice_ym, "splice_year": splice_year, "envelope": thr, "n20_scale": n20_scale,
            "snpp_last_ym": SNPP_LAST_YM, "aqua_first_ym": AQUA_FIRST_YM, "viirs_first_ym": VIIRS_FIRST_YM,
            "drift": {k: d.reset_index(names="year").to_dict(orient="records") for k, d in drift.items()}}
    (out / "harmonize_meta.json").write_text(json.dumps(meta, indent=1, default=float), encoding="utf-8")
    nat_series = h.groupby("ym")[["meq", "modis_units", "viirs_units", "viirs_meq", "modis_pix", "viirs_pix"]].sum()
    nat_series.to_csv(out / "national_monthly.csv")
    yr = nat_series.groupby(nat_series.index // 12).sum().round(0).astype(int)
    print(f"\n[harmonize] {len(h):,} rows -> {out / 'harmonized_r5_week.parquet'}\n{yr.to_string()}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--aoi", required=True, choices=list(AOIS))
    run(p.parse_args().aoi)
