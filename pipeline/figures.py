"""Presentation figures (PNG, 1600x900) for the harmonized MODIS/VIIRS record.

docs/figures/fig_detection_curve.png      collocated P(Aqua detects | S-NPP fire of FRP F) + DPT weights
docs/figures/fig_validation.png           held-out 2017-2020 skill: baselines vs DPT
docs/figures/fig_drift.png                orbit-drift diagnostic (count ratio + overpass time)
docs/figures/fig_naive_vs_harmonized.png  national annual totals: naive splice vs harmonized

python -m pipeline.figures --aoi india
"""
from __future__ import annotations

import argparse
import json
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator  # noqa: E402

from .config import INTERIM, PROCESSED, ROOT  # noqa: E402

OUT = ROOT / "docs" / "figures"

# Okabe-Ito
BLACK, ORANGE, SKY, GREEN = "#000000", "#E69F00", "#56B4E9", "#009E73"
YELLOW, BLUE, VERMILLION, PURPLE = "#F0E442", "#0072B2", "#D55E00", "#CC79A7"
TT = VERMILLION  # Thermal Twins
INK, MUTED = "#1A1A1A", "#555555"
MIN_N = 30  # hide collocation bins with fewer samples

plt.rcParams.update({
    "figure.figsize": (16, 9), "figure.dpi": 100, "savefig.dpi": 100,
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
    "font.size": 14, "axes.titlesize": 16, "axes.labelsize": 16, "xtick.labelsize": 14, "ytick.labelsize": 14,
    "legend.fontsize": 14, "figure.titlesize": 22, "axes.titlelocation": "left", "axes.titlepad": 10,
    "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#444444", "axes.linewidth": 1.1,
    "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
    "legend.frameon": False, "lines.solid_capstyle": "round",
})


def _title(fig, text: str, sub: str | None = None) -> None:
    fig.text(0.045, 0.955, text, fontsize=22, fontweight="bold", ha="left", va="top")
    if sub:
        fig.text(0.045, 0.895, sub, fontsize=16, color=MUTED, ha="left", va="top")


def _note(fig, text: str) -> None:
    fig.text(0.045, 0.018, textwrap.fill(text, 175), fontsize=12, color=MUTED, ha="left", va="bottom",
             linespacing=1.4)


def _save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=100)
    plt.close(fig)
    print(f"[figures] wrote {OUT / name}")


def _hhmm(h: float, _=None) -> str:
    m = int(round(h * 60))
    return f"{m // 60:02d}:{m % 60:02d}"


def _kfmt(v: float, _=None) -> str:
    return f"{v / 1e6:g}M" if v >= 1e6 else f"{v / 1e3:g}k"


def fig_detection_curve(models: dict) -> dict:
    col, dpt = models["collocated_SNPP_Aqua"], models["SNPP->Aqua"]
    yrs = dpt["train_years"]
    fig, (ax, bx) = plt.subplots(1, 2, gridspec_kw={"width_ratios": [1.55, 1]})
    fig.subplots_adjust(left=0.07, right=0.985, top=0.80, bottom=0.15, wspace=0.2)
    _title(fig, "MODIS sees a fraction of what VIIRS sees — and the fraction is physics",
           "The chance Aqua MODIS also catches an S-NPP VIIRS fire rises smoothly with fire power (FRP)")
    style = {"D": (ORANGE, "Day (~13:30)"), "N": (BLUE, "Night (~01:30)")}
    xs = np.geomspace(0.3, 400, 300)
    res = {}
    for dn in ("D", "N"):
        c, (color, lab) = col[dn], style[dn]
        x, p, n = np.array(c["frp_mid"]), np.array(c["p_detect"]), np.array(c["n"])
        lo, hi = np.array(c["ci_lo"]), np.array(c["ci_hi"])
        ok = n >= MIN_N
        ax.fill_between(x[ok], lo[ok] * 100, hi[ok] * 100, color=color, alpha=0.25, lw=0)
        ax.plot(x[ok], p[ok] * 100, "o-", color=color, lw=3, ms=8, label=lab, zorder=4)
        f = c["fit"]
        fit = f["pmax"] / (1 + np.exp(-(np.log2(xs) - np.log2(f["frp50_mw"])) / f["slope"]))
        ax.plot(xs, fit * 100, "--", color=color, lw=1.8, alpha=0.9, zorder=3)
        p50 = f["pmax"] / 2 * 100
        ax.plot([f["frp50_mw"]] * 2, [0, p50], ":", color=color, lw=2.2)
        ax.plot(f["frp50_mw"], p50, "D", color=color, ms=11, mec="white", mew=1.5, zorder=6)
        res[dn] = {**f, "dropped_bins_n": n[~ok].tolist()}
    fd, fn = col["D"]["fit"], col["N"]["fit"]
    ax.annotate(f"Day FRP50 = {fd['frp50_mw']:.0f} MW\n({fd['pmax'] * 50:.0f}% detected)",
                xy=(fd["frp50_mw"], fd["pmax"] * 50), xytext=(150, 20), fontsize=15, color=ORANGE,
                fontweight="bold", ha="center", va="center",
                arrowprops={"arrowstyle": "-|>", "color": ORANGE, "lw": 1.8})
    ax.annotate(f"Night FRP50 = {fn['frp50_mw']:.0f} MW\n(half of {fn['pmax'] * 100:.0f}% plateau)",
                xy=(fn["frp50_mw"], fn["pmax"] * 50), xytext=(3.2, 50), fontsize=15, color=BLUE,
                fontweight="bold", ha="center", va="center",
                arrowprops={"arrowstyle": "-|>", "color": BLUE, "lw": 1.8})
    ax.set_xscale("log", base=2)
    ticks = [0.5, 1, 2, 4, 8, 16, 32, 64, 128, 256]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xlim(0.28, 420)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.grid(axis="y", color="#E5E5E5", lw=1)
    ax.set_axisbelow(True)
    ax.set_xlabel("S-NPP VIIRS fire power, MW per ~5 km² cell (log scale)")
    ax.set_ylabel("Aqua MODIS also detects it")
    ax.set_title(f"Collocated overpasses, {yrs[0]}–{yrs[-1]}", fontsize=16)
    h, _ = ax.get_legend_handles_labels()
    h += [Line2D([], [], color=MUTED, ls="--", lw=1.8), Patch(color=MUTED, alpha=0.25)]
    ax.legend(h, ["Day (~13:30)", "Night (~01:30)", "Logistic fit", "95% Wilson CI"], loc="upper left")

    curve = dpt["detection_curve"]
    bins = list(curve["D"])
    pos = np.arange(len(bins))
    for k, dn in enumerate(("D", "N")):
        w = np.array([curve[dn][b]["w"] for b in bins])
        lo = np.array([curve[dn][b]["lo"] for b in bins])
        hi = np.array([curve[dn][b]["hi"] for b in bins])
        err = np.vstack([np.clip(w - lo, 0, None), np.clip(hi - w, 0, None)])
        bx.bar(pos + (k - 0.5) * 0.4, w, width=0.4, color=style[dn][0], yerr=err, capsize=3,
               error_kw={"elinewidth": 1.4, "ecolor": "#333333"}, label=style[dn][1])
    bx.axhline(1, color=MUTED, ls=":", lw=1.5)
    bx.text(-0.4, 1.02, "1 MODIS unit per VIIRS unit", fontsize=13, color=MUTED, va="bottom")
    bx.set_xticks(pos, [b.replace("-", "–") for b in bins])
    bx.set_ylim(0, 1.35)
    bx.grid(axis="y", color="#E5E5E5", lw=1)
    bx.set_axisbelow(True)
    bx.set_xlabel("FRP bin, MW per cell")
    bx.set_ylabel("Learned weight (MODIS units per VIIRS unit)")
    bx.set_title("Same shape, learned from counts alone (DPT)", fontsize=16)
    bx.legend(loc="upper left", bbox_to_anchor=(0, 0.93))
    _note(fig, f"Collocation: S-NPP fire cells (H3 r7) vs Aqua detections in the same or adjacent cell, same date and "
               f"day/night; bins with n < {MIN_N} hidden. FRP50 = FRP at half the fitted plateau. "
               f"DPT weights: non-negative Poisson fit, bootstrap 5–95% bars.")
    _save(fig, "fig_detection_curve.png")
    return res


METHODS = [("B0_raw_pixels_scaled", "Raw FIRMS points"), ("B1_equal_area_units_scaled", "Equal-area cells"),
           ("B2_units_day_night_scaled", "Cells + day/night"), ("DPT_regional", "Thermal Twins DPT")]
METRICS = [("cell_month_pseudo_r2", "Cell-month pseudo-R²  (higher is better)", "{:.2f}", (-0.4, 1.0)),
           ("national_month_wape_pct", "National monthly error, WAPE  (lower is better)", "{:.1f}%", (0, 40))]


def fig_validation(models: dict) -> dict:
    targets = [("SNPP->Aqua", "Aqua MODIS target"), ("SNPP->Terra", "Terra MODIS target")]
    test = models[targets[0][0]]["test_years"]
    fig, axes = plt.subplots(2, 2, sharey=True)
    fig.subplots_adjust(left=0.165, right=0.975, top=0.76, bottom=0.12, wspace=0.12, hspace=0.42)
    _title(fig, f"Thermal Twins DPT beats every baseline on held-out years {test[0]}–{test[-1]}",
           "Trained on S-NPP VIIRS → MODIS for 2012–2016, scored on years the model never saw")
    colors = ["#CFCFCF", "#A8A8A8", "#7A7A7A", TT]
    y = np.arange(len(METHODS))
    res = {}
    for j, (key, head) in enumerate(targets):
        val = models[key]["validation"]
        fig.text(axes[0, j].get_position().x0, 0.815, head, fontsize=19, fontweight="bold", ha="left")
        for i, (mk, mlab, fmt, lim) in enumerate(METRICS):
            ax = axes[i, j]
            v = [val[m][mk] for m, _ in METHODS]
            res[(key, mk)] = dict(zip([m for m, _ in METHODS], v))
            ax.barh(y, v, color=colors, height=0.7)
            ax.axvline(0, color="#444444", lw=1.1)
            pad = 0.012 * (lim[1] - lim[0])
            for yy, vv, c in zip(y, v, colors):
                bold = c == TT
                ax.text(vv + (pad if vv >= 0 else -pad), yy, fmt.format(vv).replace("-", "−"), va="center",
                        ha="left" if vv >= 0 else "right", fontsize=16 if bold else 14,
                        fontweight="bold" if bold else "normal", color=TT if bold else INK)
            ax.set_xlim(*lim)
            ax.set_title(mlab, fontsize=16)
            ax.spines["left"].set_visible(False)
            ax.tick_params(axis="y", length=0)
            ax.grid(axis="x", color="#EAEAEA", lw=1)
            ax.set_axisbelow(True)
            if mk.endswith("pct"):
                ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    axes[0, 0].set_yticks(y, [lab for _, lab in METHODS])
    axes[0, 0].set_ylim(len(METHODS) - 0.5, -0.5)
    for ax in axes[:, 0]:
        lab = ax.get_yticklabels()[-1]
        lab.set_fontweight("bold")
        lab.set_color(TT)
        for t in ax.get_yticklabels():
            t.set_fontsize(16)
    _note(fig, "Pseudo-R²: Poisson deviance explained per (~250 km² cell, month); negative = worse than a flat mean. "
               "WAPE: weighted absolute % error of national monthly totals. Baselines are scaled to MODIS on the "
               "training years.")
    _save(fig, "fig_validation.png")
    return res


def fig_drift(meta: dict, last_date: pd.Timestamp) -> dict:
    pj = pd.DataFrame(meta["drift"]["focus"]).set_index("year").loc[2013:]
    ind = pd.DataFrame(meta["drift"]["national"]).set_index("year").loc[2013:]
    env, spl = float(meta["envelope"]), int(meta["splice_year"])
    last = int(pj.index.max())
    partial = last == last_date.year and (last_date.month, last_date.day) != (12, 31)
    fig, (ax, bx) = plt.subplots(1, 2, gridspec_kw={"width_ratios": [1.75, 1]})
    fig.subplots_adjust(left=0.065, right=0.975, top=0.80, bottom=0.15, wspace=0.2)
    p26 = pj.aqua_ratio.loc[last]
    _title(fig, "Orbit drift inflates late MODIS counts",
           f"As Aqua drifts into the afternoon it over-counts Punjab fires: {p26:.2f}× the VIIRS-implied level in {last}")
    ax.axhspan(1 - env, 1 + env, color="#E9E9E9", zorder=0, lw=0)
    ax.axhline(1, color=MUTED, lw=1.3, zorder=1)
    outside = ((pj.aqua_ratio - 1).abs() > env).to_numpy()
    bars = ax.bar(pj.index, pj.aqua_ratio - 1, bottom=1, width=0.72,
                  color=np.where(outside, VERMILLION, SKY), zorder=2)
    if partial:
        bars[-1].set_hatch("//")
        bars[-1].set_edgecolor("white")
    ax.plot(ind.index, ind.aqua_ratio, "o-", color=BLACK, lw=2.6, ms=7, zorder=3)
    for yr in pj.index[outside]:
        v = pj.aqua_ratio.loc[yr]
        ax.text(yr, max(v, ind.aqua_ratio.get(yr, v)) + 0.03, f"{v:.2f}", ha="center", va="bottom", fontsize=14, fontweight="bold", color=VERMILLION)
    ax.axvline(spl - 0.5, color="#333333", ls="--", lw=2, zorder=4)
    ax.text(spl - 0.35, 2.12, f"{spl}: switch to\nVIIRS-derived", ha="left", va="top", fontsize=14)
    ax.text(2012.6, 1 + env + 0.012, f"{pj.index.min()}–2020 envelope (±{env:.2f})", fontsize=13, color=MUTED,
            va="bottom")
    ax.set_xlim(2012.4, last + 0.6)
    ax.set_ylim(0.6, 2.15)
    ax.set_xticks(pj.index, [f"{y}*" if (partial and y == last) else str(y) for y in pj.index], rotation=45)
    ax.set_ylabel("Aqua observed ÷ VIIRS-predicted")
    ax.set_title("Aqua MODIS count ratio", fontsize=16)
    ax.legend([Patch(color=SKY), Patch(color=VERMILLION), Line2D([], [], color=BLACK, marker="o", lw=2.6)],
              ["Punjab & Haryana: inside envelope", "Punjab & Haryana: outside", "All India"],
              loc="upper left", bbox_to_anchor=(0, 0.93))

    for col_, color, name in [("aqua_lst", BLUE, "Aqua"), ("terra_lst", GREEN, "Terra")]:
        s = pj[col_]
        bx.plot(s.index, s, "o-", color=color, lw=3, ms=7)
        bx.text(s.index[0] - 0.2, s.iloc[0] + 0.35, f"{name}  {_hhmm(s.iloc[0])}", color=color, fontsize=15,
                fontweight="bold", ha="left", va="bottom")
        bx.text(s.index[-1] + 0.25, s.iloc[-1], _hhmm(s.iloc[-1]), color=color, fontsize=15, fontweight="bold",
                ha="left", va="center")
    bx.axvline(spl - 0.5, color="#333333", ls="--", lw=2)
    bx.yaxis.set_major_formatter(FuncFormatter(_hhmm))
    bx.set_ylim(8.5, 16)
    bx.set_xlim(2012.5, last + 1.6)
    bx.set_xticks([2013, 2016, 2019, 2022, 2025])
    bx.grid(axis="y", color="#E5E5E5", lw=1)
    bx.set_axisbelow(True)
    bx.set_ylabel("Local solar time")
    bx.set_title("Mean daytime overpass time of detections", fontsize=16)
    note = (f"Ratio = MODIS units observed ÷ units predicted from VIIRS by DPT (calibrated 2013–2016). Envelope from "
            f"the national Terra+Aqua ratio, 2013–2020.")
    if partial:
        note += f" *{last} through {last_date:%d %b}."
    _note(fig, note)
    _save(fig, "fig_drift.png")
    return {"punjab_aqua_last": float(p26), "india_aqua_last": float(ind.aqua_ratio.loc[last]),
            "aqua_lst": (float(pj.aqua_lst.iloc[0]), float(pj.aqua_lst.iloc[-1])),
            "terra_lst": (float(pj.terra_lst.iloc[0]), float(pj.terra_lst.iloc[-1])), "envelope": env}


def fig_naive_vs_harmonized(aoi: str, nat: pd.DataFrame, u: pd.DataFrame, meta: dict) -> dict:
    yr = u["acq_date"].dt.year.rename("year")
    g = u.groupby([yr, u["platform"].astype(str)]).n_pix.sum().unstack(fill_value=0)
    viirs_pf = [p for p in ("SNPP", "NOAA20", "NOAA21") if p in g]
    modis_raw, viirs_raw = g[["Terra", "Aqua"]].sum(axis=1), g[viirs_pf].sum(axis=1)
    first_viirs = int(viirs_raw[viirs_raw > 0].index.min())
    naive = modis_raw.where(modis_raw.index < first_viirs, viirs_raw)
    ya = nat.groupby(nat.index // 12).sum()
    last_date = u["acq_date"].max()
    last = int(last_date.year)
    partial = (last_date.month, last_date.day) != (12, 31)
    years = np.arange(2001, last + 1)
    full = years[years < last] if partial else years
    series = [
        (naive.reindex(years), PURPLE, "-", 3, "Naive FIRMS splice (raw points: MODIS, then all VIIRS)"),
        (ya.viirs_units.where(ya.index >= first_viirs).reindex(years), SKY, "-", 3, "Equal-area VIIRS cells (S-NPP)"),
        (ya.modis_units.reindex(years), BLACK, "--", 2.2, "MODIS observed (drifting orbits after 2021)"),
        (ya.meq.reindex(years), TT, "-", 5.5, "Thermal Twins harmonized"),
    ]
    jump = float(naive.loc[first_viirs] / naive.loc[first_viirs - 1])
    fig, ax = plt.subplots()
    fig.subplots_adjust(left=0.085, right=0.975, top=0.80, bottom=0.15)
    _title(fig, f"A naive FIRMS splice fakes a {jump:.1f}× fire surge in {first_viirs}",
           "Thermal Twins keeps one consistent MODIS-equivalent record from 2001 to today")
    order = [3, 2, 1, 0]
    for k in order:
        s, color, ls, lw, lab = series[k]
        sf = s.loc[full]
        z = 5 if k == 3 else (6 if k == 2 else 3)
        ax.plot(sf.index, sf.values, ls=ls, color=color, lw=lw, label=lab, zorder=z, marker="o" if k != 2 else None,
                ms=5 if k != 3 else 0)
        if partial and np.isfinite(s.loc[last]):
            ax.plot([last - 1, last], [s.loc[last - 1], s.loc[last]], ls=":", color=color, lw=min(lw, 2.5), zorder=z)
            ax.plot(last, s.loc[last], "o", mfc="white", mec=color, mew=2.2, ms=9, zorder=z + 1)
    ax.annotate(f"×{jump:.1f} in one year\n(S-NPP VIIRS added)", xy=(first_viirs, naive.loc[first_viirs]),
                xytext=(first_viirs - 4.2, naive.loc[first_viirs] * 1.6), fontsize=16, fontweight="bold", color=PURPLE,
                ha="center", va="center", arrowprops={"arrowstyle": "-|>", "color": PURPLE, "lw": 2})
    steps = {}
    for p, lab in [("Aqua", "+Aqua"), ("NOAA20", "+NOAA-20"), ("NOAA21", "+NOAA-21")]:
        if p not in g:
            continue
        y0 = int(g.index[g[p] > 0].min())
        if y0 in naive.index and y0 - 1 in naive.index:
            steps[p] = (y0, float(naive.loc[y0] / naive.loc[y0 - 1]))
        if p == "Aqua":
            ax.text(y0 + 0.15, 1.55e4, lab, ha="left", va="center", fontsize=14, color=PURPLE)
        else:
            ax.text(y0, naive.loc[y0] * 1.22, lab, ha="center", va="bottom", fontsize=14, color=PURPLE)
    spl = int(meta["splice_year"])
    ax.axvline(spl - 0.5, color="#888888", ls="--", lw=1.4, zorder=1)
    ax.text(spl - 0.35, 1.35e4, f"VIIRS-derived\nfrom {spl}", fontsize=13, color=MUTED, ha="left", va="bottom")
    ax.set_yscale("log")
    ax.set_ylim(1.2e4, 4e6)
    ax.yaxis.set_major_locator(FixedLocator([2e4, 5e4, 1e5, 2e5, 5e5, 1e6, 2e6]))
    ax.yaxis.set_major_formatter(FuncFormatter(_kfmt))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.set_xlim(2000.4, last + 0.6)
    ax.set_xticks(np.arange(2001, last + 1, 2))
    ax.grid(axis="y", color="#E8E8E8", lw=1)
    ax.set_axisbelow(True)
    ax.set_ylabel("Annual fire detections, India (log scale)")
    h, lab = ax.get_legend_handles_labels()
    idx = [lab.index(s[4]) for s in series]
    ax.legend([h[i] for i in idx], [lab[i] for i in idx], loc="upper left", bbox_to_anchor=(0, 1.0))
    note = ("Points = FIRMS fire pixels. Cells = fire-active ~5 km² H3 cells per overpass. Harmonized = Terra+Aqua "
            "MODIS cells (pre-Aqua months gap-filled), VIIRS-derived MODIS-equivalent from "
            f"{spl}.")
    if partial:
        note += f" Open markers: {last} through {last_date:%d %b}."
    _note(fig, note)
    _save(fig, "fig_naive_vs_harmonized.png")
    return {"jump": jump, "naive": naive.reindex(years), "steps": steps, "viirs_platforms": viirs_pf,
            "meq": ya.meq.reindex(years), "modis_units": ya.modis_units.reindex(years)}


def run(aoi: str) -> None:
    src = PROCESSED / aoi
    models = json.loads((src / "dpt_models.json").read_text(encoding="utf-8"))
    meta = json.loads((src / "harmonize_meta.json").read_text(encoding="utf-8"))
    nat = pd.read_csv(src / "national_monthly.csv", index_col="ym")
    u = pd.read_parquet(INTERIM / aoi / "units.parquet", columns=["platform", "acq_date", "n_pix"])
    last_date = u["acq_date"].max()

    det = fig_detection_curve(models)
    for dn, f in det.items():
        print(f"[fig1] {dn}: FRP50={f['frp50_mw']} MW pmax={f['pmax']} slope={f['slope']} "
              f"hidden bins n={f['dropped_bins_n']}")
    val = fig_validation(models)
    for (key, mk), d in val.items():
        print(f"[fig2] {key} {mk}: " + ", ".join(f"{m}={v}" for m, v in d.items()))
    dr = fig_drift(meta, last_date)
    print(f"[fig3] {dr}")
    nv = fig_naive_vs_harmonized(aoi, nat, u, meta)
    print(f"[fig4] naive jump x{nv['jump']:.2f}; steps {nv['steps']}; VIIRS platforms {nv['viirs_platforms']}")
    print(pd.DataFrame({"naive": nv["naive"], "modis_units": nv["modis_units"], "meq": nv["meq"]}).round(0).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", default="india")
    run(ap.parse_args().aoi)
