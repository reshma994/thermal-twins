"""Build the 7-slide demo deck (PDF + per-slide PNG) from pipeline figures and an app screenshot.

python docs/make_deck.py
"""
from pathlib import Path

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parent
FIG, SHOT, OUT = ROOT / "figures", ROOT / "shots", ROOT / "slides"
OUT.mkdir(exist_ok=True)
APP_URL = "LIVE-APP-URL"
REPO_URL = "github.com/reshma994/thermal-twins (branch Nitant)"

INK, MUTED, ACC, ACC2, BG, WARN = "#14161c", "#5b6170", "#e8641b", "#f2a51a", "#ffffff", "#c0392b"
plt.rcParams.update({"font.family": "DejaVu Sans"})


def slide(title: str, kicker: str = ""):
    fig = plt.figure(figsize=(16, 9), dpi=120)
    fig.patch.set_facecolor(BG)
    fig.add_artist(plt.Rectangle((0, 0.965), 1, 0.035, color=ACC, transform=fig.transFigure))
    if kicker:
        fig.text(0.04, 0.905, kicker.upper(), fontsize=13, color=ACC, weight="bold")
    fig.text(0.04, 0.845, title, fontsize=30, color=INK, weight="bold")
    fig.text(0.96, 0.025, "Thermal Twins · NASA Space Apps 2026 · MODIS × VIIRS hot spots", fontsize=10, color=MUTED, ha="right")
    return fig


def image(fig, path, rect):
    ax = fig.add_axes(rect)
    ax.imshow(mpimg.imread(path))
    ax.axis("off")
    return ax


def bullets(fig, items, x, y, size=17, gap=0.075, width=None, color=INK):
    for it in items:
        fig.text(x, y, "▸", fontsize=size, color=ACC, weight="bold", va="top")
        fig.text(x + 0.022, y, it, fontsize=size, color=color, va="top", linespacing=1.35)
        y -= gap
    return y


def card(fig, x, y, w, h, big, small, color=ACC):
    fig.add_artist(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.012",
                                  transform=fig.transFigure, facecolor="#fff6ee", edgecolor=color, linewidth=1.5))
    fig.text(x + 0.015, y + h - 0.065, big, fontsize=30, color=color, weight="bold")
    fig.text(x + 0.015, y + 0.025, small, fontsize=12.5, color=INK)


slides = []

# 1 -- title
f = plt.figure(figsize=(16, 9), dpi=120)
f.patch.set_facecolor("#0b0c10")
f.text(0.06, 0.66, "Thermal Twins", fontsize=64, color="#ffffff", weight="bold")
f.text(0.06, 0.585, "One consistent fire record from two generations of satellites", fontsize=26, color="#ffd166")
f.text(0.06, 0.475, "Sensor-aware harmonization of MODIS and VIIRS active-fire hot spots (NASA FIRMS)\n"
       "into a burning activity calendar — India, Nov 2000 → 14 Nov 2026, any area you draw.",
       fontsize=17, color="#c9ccd6", linespacing=1.6)
f.text(0.06, 0.30, "NASA Space Apps Challenge 2026 · Harmonization of MODIS and VIIRS Hot Spots", fontsize=15, color="#9aa0b0")
f.text(0.06, 0.24, f"Live app: {APP_URL}", fontsize=17, color="#ff8a3d", weight="bold")
f.text(0.06, 0.195, f"Code & data: {REPO_URL}", fontsize=15, color="#c9ccd6")
image(f, SHOT / "app_top.png", [0.60, 0.08, 0.38, 0.40]) if (SHOT / "app_top.png").exists() else None
slides.append(f)

# 2 -- problem
f = slide("A naive MODIS + VIIRS splice invents fires", "The problem")
image(f, FIG / "fig_naive_vs_harmonized.png", [0.02, 0.05, 0.62, 0.74])
bullets(f, ["MODIS (Terra, Aqua) gives 25 years;\nVIIRS gives detail and the future.",
            "Stacking FIRMS points fakes a 7.7×\nnational fire surge in 2012.",
            "More satellites, drifting orbits and\nending missions add more steps.",
            "Managers comparing 'this month vs\nhistory' get the wrong answer."], 0.66, 0.70, size=16, gap=0.14)
slides.append(f)

# 3 -- method
f = slide("Five sensor artifacts, removed with physics", "Our method")
rows = [("1  Resolution", "375 m vs 1 km pixels", "unique H3 cells per overpass"),
        ("2  Sensitivity", "VIIRS sees fires MODIS can't", "learned MODIS detection curve (FRP)"),
        ("3  Constellation", "1 → 5 satellites", "fixed Terra + Aqua reference"),
        ("4  Orbit drift", "Aqua 13:20 → 15:06 LST", "data-driven splice to VIIRS-derived"),
        ("5  Non-fire heat", "flares, kilns, industry", "FIRMS type + persistence mask")]
y = 0.72
for a, b, c in rows:
    f.text(0.04, y, a, fontsize=17, color=ACC, weight="bold")
    f.text(0.205, y, b, fontsize=15, color=MUTED)
    f.text(0.205, y - 0.04, "→ " + c, fontsize=15, color=INK)
    y -= 0.125
image(f, FIG / "fig_detection_curve.png", [0.47, 0.06, 0.52, 0.72])
f.text(0.04, 0.08, "Detection-Physics Transfer: MODIS units = f_region · Σ_b w_b · N_VIIRS,b   (non-negative Poisson fit,\n"
       "trained 2012–16 when Aqua and S-NPP shared the 13:30 orbit; additive, so any area is an exact sum of cells)",
       fontsize=12.5, color=INK, linespacing=1.5)
slides.append(f)

# 4 -- validation
f = slide("Validated on years the model never saw (2017–2020)", "Validity")
image(f, FIG / "fig_validation.png", [0.02, 0.05, 0.64, 0.75])
card(f, 0.68, 0.58, 0.29, 0.18, "0.79 vs 0.50", "share of cell-month variability explained\n(Aqua) — ours vs equal-area cells")
card(f, 0.68, 0.36, 0.29, 0.18, "0.51 vs −0.19", "Terra morning orbit: naive scaling is worse\nthan predicting the average; DPT is not")
card(f, 0.68, 0.14, 0.29, 0.18, "±10%", "held-out national years vs observed MODIS\n(0.98–1.10 after calibration)")
slides.append(f)

# 5 -- the app
f = slide("A burning calendar for any area — no server, opens anywhere", "The app")
image(f, SHOT / "app_top.png", [0.02, 0.05, 0.60, 0.74])
bullets(f, ["Draw a box / polygon, pick a preset,\nor enter lat-lon + radius",
            "Calendar 2000→today: activity,\nvs-median or percentile colours",
            "Situation brief: this month vs the\nsame days in past years, critical months",
            "Season-to-date envelope, trends,\nnaive-vs-harmonized toggle",
            "CSV (with 90% uncertainty), raw\nhotspot CSV (5 satellites), PNG"], 0.645, 0.72, size=14.5, gap=0.125)
slides.append(f)

# 6 -- finding
f = slide("Punjab's burning is moving out of the satellites' view", "Discovery")
image(f, FIG / "fig_drift.png", [0.02, 0.05, 0.58, 0.72])
tab = [("1–14 Nov", "VIIRS", "Aqua*", "Aqua/VIIRS"), ("2021", "36,765", "9,970", "0.27"),
       ("2023", "14,700", "4,113", "0.28"), ("2025", "3,013", "2,194", "0.73"), ("2026", "2,619", "3,963", "1.51")]
y = 0.70
for i, r in enumerate(tab):
    for j, (x, v) in enumerate(zip((0.625, 0.71, 0.795, 0.875), r)):
        f.text(x, y, v, fontsize=14.5, color=(MUTED if i == 0 else (WARN if (i == 4 and j == 3) else INK)), weight="bold" if i in (0, 4) else "normal")
    y -= 0.05
f.text(0.625, 0.445, "VIIRS NOAA-20 at 13:30 · *Aqua MODIS drifting to ≈15:06 · fire units", fontsize=11, color=MUTED)
bullets(f, ["Fire seen at 13:30 fell ~93% since 2021 —\nbut Aqua, now passing ~15:06, sees 5.6×\nmore relative to VIIRS.",
            "Burning is shifting later in the day (cf.\nISRO SAC 2025). The app flags this\nautomatically: an observation-time alert."],
        0.625, 0.39, size=13.5, gap=0.15)
slides.append(f)

# 7 -- impact
f = slide("Impact and what's next", "Why it matters")
bullets(f, ["Emergency & air-quality managers: 'Is this month unusual?' answered on a\nconsistent 26-year baseline, with uncertainty — not a sensor artifact.",
            "Scientists & land managers: trends that survive the MODIS → VIIRS hand-over\n(MODIS ends 2026–27; Suomi NPP ended 2 Nov 2026).",
            "Region-agnostic pipeline: any FIRMS country in one command; static app costs\nnothing to host and keeps working through mission transitions.",
            "Next: geostationary diurnal correction (GOES / Himawari / GK-2A / INSAT-3D),\nLandsat 30 m validation, morning-orbit gap after Terra."], 0.05, 0.70, size=17, gap=0.135)
f.text(0.05, 0.13, f"Live app: {APP_URL}     ·     Code & data: {REPO_URL}", fontsize=15, color=ACC, weight="bold")
f.text(0.05, 0.085, "Data: NASA FIRMS MODIS C6.1 & VIIRS 375 m (S-NPP, NOAA-20, NOAA-21). An AI coding assistant helped draft code; the team reviewed all content.",
       fontsize=11.5, color=MUTED)
slides.append(f)

with PdfPages(ROOT / "Thermal_Twins_demo.pdf") as pdf:
    for i, f in enumerate(slides, 1):
        pdf.savefig(f, facecolor=f.get_facecolor())
        f.savefig(OUT / f"slide_{i}.png", facecolor=f.get_facecolor())
        plt.close(f)
print("wrote", ROOT / "Thermal_Twins_demo.pdf")
