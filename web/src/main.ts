import "./style.css";
import { latLngToCell, polygonToCells } from "h3-js";
import { aggregate, Dataset, loadDataset, MONTHS, Series, srcOf, ymLabel } from "./data";
import { bboxRing, circleRing, FireMap, FIRE_RAMP, Ring } from "./map";
import {
  annual, annualOption, baselineMonth, calendarOption, CalMode, climOption, criticalPeriod, Ctx, curveOption, driftOption,
  legendText, makeChart, seasonOption, yearOf,
} from "./charts";
import { fmt, fmtPct, median, percentileRank } from "./stats";
import { hotspotsCsv, isoToDay } from "./hotspots";

const BASE = "./data/india";
const CELL_KM2 = 252.9;
const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

interface Aoi { id: string; name: string; ring: Ring | null; cells: Set<string>; mask: Uint8Array; nCells: number }

const state = { naive: false, cmode: "count" as CalMode, showNums: false, b0: 2003, b1: 2022, from: 0, to: 0 };
let ds: Dataset, s: Series, aoi: Aoi, fmap: FireMap;
const charts: Record<string, ReturnType<typeof makeChart>> = {};

function ctx(): Ctx { return { ds, s, naive: state.naive, b0: state.b0, b1: state.b1, aoiName: aoi.name }; }

function makeAoi(id: string, name: string, ring: Ring | null): Aoi {
  const mask = new Uint8Array(ds.meta.cells.length);
  let cells: Set<string>;
  if (!ring) { mask.fill(1); cells = new Set(ds.meta.cells); }
  else {
    let list = polygonToCells([ring], 5, true);
    if (!list.length) {
      const lon = ring.reduce((a, p) => a + p[0], 0) / ring.length, lat = ring.reduce((a, p) => a + p[1], 0) / ring.length;
      list = [latLngToCell(lat, lon, 5)];
    }
    cells = new Set(list);
    for (const c of list) { const i = ds.cellIndex.get(c); if (i !== undefined) mask[i] = 1; }
  }
  return { id, name, ring, cells, mask, nCells: cells.size };
}

function setAoi(a: Aoi, fit = true) {
  aoi = a;
  s = aggregate(ds, aoi.mask);
  if (a.ring) fmap.setAoi(a.ring, fit); else { fmap.setAoi(null); if (fit) fmap.fitIndia(); }
  $("aoi-info").textContent = `${a.name} · ${fmt(a.nCells)} cells ≈ ${fmt(a.nCells * CELL_KM2)} km²`;
  writeHash();
  renderAll();
}

/* ------------------------------ rendering ------------------------------ */
function renderAll() {
  renderMap(); renderCalendar(); renderSeason(); renderClim(); renderAnnual(); renderBrief();
}

function periodMonths(): [number, number] { return [Math.max(state.from, ds.meta.modis_first_ym), Math.min(state.to, ds.lastM)]; }

async function renderMap() {
  const [m0, m1] = periodMonths();
  const c = ds.col, n = ds.meta.n, vals = new Float64Array(ds.meta.cells.length);
  const vf = ds.meta.viirs_first_ym;
  for (let i = 0; i < n; i++) {
    const m = c.ym[i];
    if (m < m0 || m > m1) continue;
    vals[c.cell[i]] += state.naive ? (m < vf ? c.mp[i] : c.vp[i]) : (c.w0[i] + c.w1[i] + c.w2[i] + c.w3[i]) / 10;
  }
  const max = await fmap.setValues(vals);
  $("map-legend").innerHTML = `<div>${state.naive ? "Naive FIRMS points" : "Harmonized fire units"} · ${ymLabel(m0)} – ${ymLabel(m1)}</div>
    <div class="bar" style="background:linear-gradient(90deg,${FIRE_RAMP.join(",")})"></div>
    <div class="ticks"><span>0</span><span>${fmt(Math.sqrt(max))}</span><span>${fmt(max)} / cell</span></div>`;
}

function renderCalendar() {
  const c = ctx();
  charts.cal.setOption(calendarOption(c, state.cmode, state.showNums), true);
  const sy = yearOf(ds.meta.splice_ym);
  $("cal-sub").textContent = state.naive ? "NAIVE: FIRMS MODIS points until 2011, VIIRS points after" : `Harmonized MODIS-equivalent fire units · ${aoi.name}`;
  $("cal-foot").textContent = `${legendText(state.cmode, c)} Hatched = no satellite record. ◇ = years from ${sy} derived from VIIRS through the detection-physics transfer (MODIS orbits drifting). Last month runs to ${ds.endDay} ${MONTHS[ds.lastM % 12]}.`;
}

function renderSeason() {
  charts.std.setOption(seasonOption(ctx()), true);
  $("std-sub").textContent = `cumulative, weekly · baseline ${state.b0}–${state.b1}`;
}

function renderClim() {
  const c = ctx(), cp = criticalPeriod(c);
  charts.clim.setOption(climOption(c, cp), true);
  $("clim-sub").textContent = cp.months.length ? `critical months ${cp.label} · peak ${MONTHS[cp.peak]} · baseline ${state.b0}–${state.b1}` : "";
}

let ann: ReturnType<typeof annual>;
function renderAnnual() {
  ann = annual(ctx());
  charts.annual.setOption(annualOption(ctx(), ann), true);
  const t = ann.trend, nt = ann.naiveTrend;
  $("ann-sub").innerHTML = `Harmonized trend <b>${fmtPct(t.pct)}/yr</b> (Mann–Kendall p=${t.p.toFixed(2)}) · naive splice would claim <b style="color:#ff6b6b">${fmtPct(nt.pct)}/yr</b> (p=${nt.p.toFixed(3)})`;
}

function renderBrief() {
  const c = ctx(), L = ds.lastM, curY = yearOf(L), mo = L % 12;
  const wk = ds.wkDone;
  // current month to date vs same days in baseline years
  const partSum = (m: number) => { let v = 0; for (let w = 0; w < wk; w++) v += s.wk[m * 4 + w]; return v; };
  const cur = partSum(L);
  const baseVals: number[] = [], allVals: number[] = [];
  for (let y = 2001; y < curY; y++) { const m = (y - 2000) * 12 + mo; if (srcOf(ds, m) < 0) continue; const v = partSum(m); allVals.push(v); if (y >= state.b0 && y <= state.b1) baseVals.push(v); }
  const med = median(baseVals);
  const rank = allVals.filter((v) => v > cur).length + 1;
  const pctDiff = med > 0 ? (cur / med - 1) * 100 : NaN;
  // year to date
  let ytd = 0; for (let m = (curY - 2000) * 12; m < L; m++) ytd += s.meq[m]; ytd += cur;
  const ytdBase: number[] = [];
  for (let y = state.b0; y <= state.b1; y++) { let v = 0; for (let k = 0; k < mo; k++) v += s.meq[(y - 2000) * 12 + k]; v += partSum((y - 2000) * 12 + mo); ytdBase.push(v); }
  const ytdMed = median(ytdBase);
  const cp = criticalPeriod(c);
  let critTxt = "";
  if (cp.months.length) {
    if (cp.months.includes(mo)) critTxt = `You are <b>inside</b> a critical burning period. Critical months here: <b>${cp.label}</b> (peak ${MONTHS[cp.peak]}).`;
    else {
      const [yy, mm, dd] = ds.meta.data_end.split("-").map(Number);
      let k = 1; while (k < 12 && !cp.months.includes((mo + k) % 12)) k++;
      const next = (mo + k) % 12, ty = yy + Math.floor((mm - 1 + k) / 12);
      const days = Math.round((Date.UTC(ty, next, 1) - Date.UTC(yy, mm - 1, dd)) / 86400000);
      critTxt = `Next critical period starts in about <b>${days} days</b> (${MONTHS[next]}). Critical months here: <b>${cp.label}</b>.`;
    }
  }
  // observation-time alert: is a later-afternoon sensor now seeing far more fire than 13:30 VIIRS (vs history)?
  let bm = 0, bv = 0;
  for (let y = 2013; y <= 2020; y++) { const m = (y - 2000) * 12 + mo; bm += s.mu[m]; bv += s.vu[m]; }
  const rBase = bv > 0 ? bm / bv : NaN, rNow = s.vu[L] > 0 ? s.mu[L] / s.vu[L] : NaN;
  const timingK = rNow / rBase;
  const timingTxt = s.vu[L] >= 30 && Number.isFinite(timingK) && timingK >= 1.5
    ? `<div class="flag"><b>Observation-time alert.</b> MODIS on drifting Aqua (now passing ≈15:00 local) records <b>${timingK.toFixed(1)}×</b> more fire relative to 13:30 VIIRS than it did in ${MONTHS[mo]} 2013–2020. Burning appears to be shifting later in the day, outside the classic overpass window — so a 13:30-equivalent count (like any polar-orbit count) likely understates total burning.</div>`
    : "";
  // record month / year
  let recM = 0; for (let m = 0; m <= L; m++) if (s.meq[m] > s.meq[recM]) recM = m;
  const fullYears = ann.years.filter((y) => y < curY);
  const recYi = fullYears.reduce((bi, _, i) => (ann.harm[i] > ann.harm[bi] ? i : bi), 0);
  // naive inflation and drift
  const ratio = (a: number, b: number, f: (m: number) => number, g: (m: number) => number) => { let x = 0, y = 0; for (let m = a; m <= b; m++) { x += f(m); y += g(m); } return y > 0 ? x / y : NaN; };
  const naiveK = ratio(13 * 12, 20 * 12 + 11, (m) => s.naive[m], (m) => s.meq[m]) / ratio(3 * 12, 11 * 12 + 11, (m) => s.naive[m], (m) => s.meq[m]);
  const driftPct = (ratio(25 * 12, L, (m) => s.mu[m], (m) => s.meq[m]) - 1) * 100;
  const dir = pctDiff > 0 ? "up" : "down";
  $("brief").innerHTML = `
    <div class="kicker">Situation brief · ${aoi.name}</div>
    <div class="headline">1–${ds.endDay} ${MONTHS[mo]} ${curY}: <span class="${dir}">${fmt(cur)}</span> fire units,
      <span class="${dir}">${Number.isFinite(pctDiff) ? fmtPct(pctDiff) : "n/a"}</span> vs the ${state.b0}–${state.b1} median for the same days
      (rank ${rank} of ${allVals.length + 1} years).</div>
    <div class="stats">
      <div class="stat"><div class="v">${fmt(ytd)}</div><div class="k">${curY} to date · median ${fmt(ytdMed)} (${fmtPct((ytd / (ytdMed || 1) - 1) * 100)})</div></div>
      <div class="stat"><div class="v">${MONTHS[cp.peak] ?? "–"}</div><div class="k">typical peak month · ${Math.round((cp.share[cp.peak] ?? 0) * 100)}% of a year's fires</div></div>
      <div class="stat"><div class="v">${ymLabel(recM)}</div><div class="k">busiest month on record · ${fmt(s.meq[recM])} units</div></div>
      <div class="stat"><div class="v">${fullYears[recYi] ?? "–"}</div><div class="k">busiest full year · ${fmt(ann.harm[recYi])} units</div></div>
    </div>
    <div class="flag info">${critTxt}</div>
    ${timingTxt}
    ${Number.isFinite(naiveK) ? `<div class="flag">Naive FIRMS splice makes 2012+ look <b>${naiveK.toFixed(1)}×</b> busier here — a sensor artifact, not fire.</div>` : ""}
    ${Number.isFinite(driftPct) && Math.abs(driftPct) > 5 ? `<div class="flag">Raw MODIS reads <b>${fmtPct(driftPct)}</b> vs harmonized in 2025–26 here: Terra/Aqua orbit drift changed when they look.</div>` : ""}`;
}

/* ------------------------------ trust section ------------------------------ */
function renderTrust() {
  const v = ds.meta.validation;
  const rows: [string, string][] = [
    ["B0_raw_pixels_scaled", "Raw FIRMS points × constant"],
    ["B1_equal_area_units_scaled", "Equal-area cells × constant"],
    ["B2_units_day_night_scaled", "Cells + day/night factors"],
    ["DPT_regional", "Thermal Twins DPT"],
  ];
  const A = v["SNPP->Aqua"], T = v["SNPP->Terra"];
  $("val-table").innerHTML = `<table class="val"><thead><tr><th>Method</th><th>Aqua R²ₚ</th><th>Aqua WAPE</th><th>Terra R²ₚ</th><th>Terra WAPE</th></tr></thead><tbody>${rows
    .map(([k, label]) => `<tr class="${k.startsWith("DPT") ? "ours" : ""}"><td>${label}</td><td>${A[k].cell_month_pseudo_r2.toFixed(2)}</td><td>${A[k].national_month_wape_pct.toFixed(1)}%</td><td>${T[k].cell_month_pseudo_r2.toFixed(2)}</td><td>${T[k].national_month_wape_pct.toFixed(1)}%</td></tr>`)
    .join("")}</tbody></table>`;
  charts.curve.setOption(curveOption(ds.meta));
  charts.drift.setOption(driftOption(ds.meta));
  const span = (a: number, b: number) => `left:${((a - 2000) / 27) * 100}%;width:${((b - a) / 27) * 100}%`;
  const tl: [string, number, number, string, number?][] = [
    ["Terra", 2000.15, 2026.9, "#ffd166", 2021], ["Aqua", 2002.5, 2026.9, "#ff8a3d", 2021],
    ["S-NPP", 2012.05, 2026.84, "#7fb3ff"], ["NOAA-20", 2018.25, 2026.9, "#9f8fd0"], ["NOAA-21", 2023.17, 2026.9, "#7bd389"],
  ];
  $("timeline").innerHTML =
    tl.map(([n, a, b, col, drift]) => `<div class="tl-row"><span>${n}</span><div class="tl-track"><div class="tl-bar" style="${span(a, b)};background:${col}"></div>${drift ? `<div class="tl-bar" style="${span(drift, b)};background:repeating-linear-gradient(45deg,${col},${col} 3px,#0e1016 3px,#0e1016 6px)" title="orbit drifting"></div>` : ""}</div></div>`).join("") +
    `<div class="tl-axis"><span></span><div><span>2000</span><span>2006</span><span>2013</span><span>2020</span><span>2027</span></div></div>
     <p class="foot">Striped = orbit drifting. MODIS ends 2026–27; Suomi NPP delivery ended 2 Nov 2026.</p>`;
  $("splice-y").textContent = String(yearOf(ds.meta.splice_ym));
}

/* ------------------------------ downloads ------------------------------ */
function download(name: string, text: string, type = "text/csv") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
const slug = () => aoi.name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");

function calendarCsv() {
  const c = ctx();
  const head = "aoi,year,month,partial_month,source,harmonized_modis_eq_units,ci90_low,ci90_high,baseline_median,ratio_to_median,percentile_vs_baseline,modis_units_observed,modis_points,viirs_units,viirs_points,viirs_derived_modis_eq,naive_firms_points";
  const lines = [head];
  for (let m = 0; m <= ds.lastM; m++) {
    const src = s.src[m];
    if (src < 0) continue;
    const bv = baselineMonth({ ...c, naive: false }, m % 12), med = median(bv);
    lines.push([`"${aoi.name}"`, yearOf(m), m % 12 + 1, m === ds.lastM ? `to day ${ds.endDay}` : "", `"${ds.meta.src_codes[String(src)]}"`,
      s.meq[m].toFixed(2), s.ciLo[m].toFixed(2), s.ciHi[m].toFixed(2), med.toFixed(2), med > 0 ? (s.meq[m] / med).toFixed(3) : "",
      percentileRank(bv, s.meq[m]).toFixed(1), s.mu[m], s.mp[m], m >= ds.meta.viirs_first_ym ? s.vu[m] : "", m >= ds.meta.viirs_first_ym ? s.vp[m] : "",
      m >= ds.meta.viirs_first_ym ? s.vmeq[m].toFixed(2) : "", s.naive[m]].join(","));
  }
  download(`thermal_twins_calendar_${slug()}.csv`, lines.join("\n"));
}

async function hotCsv() {
  const st = $("dl-status");
  const [m0, m1] = periodMonths();
  const d0 = isoToDay(`${2000 + Math.floor(m0 / 12)}-${String((m0 % 12) + 1).padStart(2, "0")}-01`);
  const endM = new Date(Date.UTC(2000 + Math.floor(m1 / 12), (m1 % 12) + 1, 0)).toISOString().slice(0, 10);
  const d1 = isoToDay(endM);
  try {
    const r = await hotspotsCsv(BASE, aoi.cells, d0, d1, (msg) => (st.textContent = msg));
    download(`thermal_twins_hotspots_${slug()}_${ymLabel(m0).replace(" ", "")}_${ymLabel(m1).replace(" ", "")}.csv`, r.csv);
    st.textContent = `${fmt(r.rows)} hotspots exported${r.truncated ? " (capped at 1.5M rows — narrow the period)" : ""}.`;
  } catch (e) { st.textContent = `Hotspot export failed: ${(e as Error).message}`; }
}

/* ------------------------------ URL state ------------------------------ */
function writeHash() {
  const p = new URLSearchParams();
  if (aoi.id.startsWith("preset:")) p.set("aoi", aoi.id.slice(7));
  else if (aoi.ring) p.set("poly", aoi.ring.map(([x, y]) => `${x.toFixed(3)},${y.toFixed(3)}`).join(";"));
  if (state.naive) p.set("mode", "naive");
  if (state.cmode !== "count") p.set("c", state.cmode);
  history.replaceState(null, "", `#${p.toString()}`);
}

function aoiFromHash(): Aoi | null {
  const p = new URLSearchParams(location.hash.slice(1));
  state.naive = p.get("mode") === "naive";
  const cm = p.get("c"); if (cm === "anom" || cm === "pct") state.cmode = cm;
  const id = p.get("aoi");
  if (id) { const pr = ds.meta.presets.find((x) => x.id === id); if (pr) return makeAoi(`preset:${pr.id}`, pr.name, pr.bbox ? bboxRing(pr.bbox) : null); }
  const poly = p.get("poly");
  if (poly) { const ring = poly.split(";").map((t) => t.split(",").map(Number) as [number, number]); if (ring.length >= 4) return makeAoi("custom", "Custom area", ring); }
  return null;
}

/* ------------------------------ boot ------------------------------ */
async function boot() {
  ds = await loadDataset(BASE);
  $("hdr-end").textContent = new Date(ds.meta.data_end + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  fmap = new FireMap($("map"), ds.meta.cells);
  for (const id of ["cal", "std", "clim", "annual", "curve", "drift"]) charts[id] = makeChart($(id));
  state.to = ds.lastM; state.from = (yearOf(ds.lastM) - 2000) * 12;
  const toIso = (m: number) => `${2000 + Math.floor(m / 12)}-${String((m % 12) + 1).padStart(2, "0")}`;
  const fromIso = (v: string) => { const [y, mm] = v.split("-").map(Number); return (y - 2000) * 12 + mm - 1; };
  const pf = $<HTMLInputElement>("p-from"), pt = $<HTMLInputElement>("p-to");
  pf.value = toIso(state.from); pt.value = toIso(state.to);
  pf.min = pt.min = "2000-11"; pf.max = pt.max = toIso(ds.lastM);
  pf.onchange = () => { state.from = fromIso(pf.value); renderMap(); };
  pt.onchange = () => { state.to = fromIso(pt.value); renderMap(); };
  const bf = $<HTMLInputElement>("b-from"), bt = $<HTMLInputElement>("b-to");
  const onBase = () => { state.b0 = Math.min(+bf.value, +bt.value); state.b1 = Math.max(+bf.value, +bt.value); renderCalendar(); renderSeason(); renderClim(); renderBrief(); };
  bf.onchange = onBase; bt.onchange = onBase;

  const sel = $<HTMLSelectElement>("preset");
  sel.innerHTML = ds.meta.presets.map((p) => `<option value="${p.id}">${p.name}</option>`).join("") + `<option value="__custom" disabled>Custom area</option>`;
  sel.onchange = () => { const p = ds.meta.presets.find((x) => x.id === sel.value)!; setAoi(makeAoi(`preset:${p.id}`, p.name, p.bbox ? bboxRing(p.bbox) : null)); };

  const bR = $("draw-rect"), bP = $("draw-poly");
  bR.onclick = () => fmap.setMode(bR.getAttribute("aria-pressed") === "true" ? "none" : "rect");
  bP.onclick = () => fmap.setMode(bP.getAttribute("aria-pressed") === "true" ? "none" : "poly");
  fmap.onModeChange = (m) => { bR.setAttribute("aria-pressed", String(m === "rect")); bP.setAttribute("aria-pressed", String(m === "poly")); };
  fmap.onAoi = (ring) => { sel.value = "__custom"; setAoi(makeAoi("custom", "Custom area", ring), false); };
  $("pt-go").onclick = () => {
    const lat = +$<HTMLInputElement>("pt-lat").value, lon = +$<HTMLInputElement>("pt-lon").value, r = +$<HTMLInputElement>("pt-r").value;
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || !(r > 0)) return;
    sel.value = "__custom";
    setAoi(makeAoi("custom", `${lat.toFixed(2)}°, ${lon.toFixed(2)}° ± ${r} km`, circleRing(lat, lon, r)));
  };

  const setMode = (naive: boolean) => {
    state.naive = naive;
    $("mode-harm").classList.toggle("on", !naive); $("mode-naive").classList.toggle("on", naive);
    $("mode-harm").setAttribute("aria-pressed", String(!naive)); $("mode-naive").setAttribute("aria-pressed", String(naive));
    writeHash(); renderMap(); renderCalendar(); renderAnnual();
  };
  $("mode-harm").onclick = () => setMode(false);
  $("mode-naive").onclick = () => setMode(true);
  document.querySelectorAll<HTMLInputElement>('input[name="cmode"]').forEach((r) => (r.onchange = () => { state.cmode = r.value as CalMode; writeHash(); renderCalendar(); }));
  $<HTMLInputElement>("show-nums").onchange = (e) => { state.showNums = (e.target as HTMLInputElement).checked; renderCalendar(); };
  $("dl-cal").onclick = calendarCsv;
  $("dl-hot").onclick = hotCsv;
  $("dl-png").onclick = () => {
    const url = charts.cal.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#0b0c10" });
    const a = document.createElement("a"); a.href = url; a.download = `thermal_twins_calendar_${slug()}.png`; a.click();
  };

  renderTrust();
  const fromHash = aoiFromHash();
  const def = ds.meta.presets.find((p) => p.id === "punjab_haryana") ?? ds.meta.presets[0];
  const start = fromHash ?? makeAoi(`preset:${def.id}`, def.name, def.bbox ? bboxRing(def.bbox) : null);
  sel.value = start.id.startsWith("preset:") ? start.id.slice(7) : "__custom";
  document.querySelectorAll<HTMLInputElement>('input[name="cmode"]').forEach((r) => (r.checked = r.value === state.cmode));
  $("mode-harm").classList.toggle("on", !state.naive); $("mode-naive").classList.toggle("on", state.naive);
  setAoi(start);
  $("loading").classList.add("hide");
}

boot().catch((e) => {
  console.error(e);
  $("loading").innerHTML = `<p>Failed to load data: ${(e as Error).message}</p>`;
});
