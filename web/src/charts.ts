import * as echarts from "echarts";
import type { Dataset, Series } from "./data";
import { MONTHS } from "./data";
import { fmt, fmtPct, mannKendall, median, percentileRank, quantile, theilSen } from "./stats";
import { FIRE_RAMP } from "./map";

export type CalMode = "count" | "anom" | "pct";
const TXT = "#e8e9ee", MUTED = "#9aa0b0", LINE = "#262a36", ACC = "#ff8a3d", ACC2 = "#ffd166", WARN = "#ff6b6b", BLUE = "#7fb3ff";
const DIVERGE = ["#5e3c99", "#9f8fd0", "#3a3d48", "#f6a25a", "#e66101"];
const base = { backgroundColor: "transparent", textStyle: { color: TXT, fontFamily: "Inter, system-ui, sans-serif" }, animationDuration: 300 };
const axisStyle = { axisLine: { lineStyle: { color: LINE } }, axisLabel: { color: MUTED }, splitLine: { lineStyle: { color: LINE } } };

export interface Ctx { ds: Dataset; s: Series; naive: boolean; b0: number; b1: number; aoiName: string }

export const yearOf = (m: number) => 2000 + Math.floor(m / 12);
export const valueOf = (c: Ctx, m: number) => (c.naive ? c.s.naive[m] : c.s.meq[m]);

/** Values of month-of-year `mo` for baseline years (complete months with data only). */
export function baselineMonth(c: Ctx, mo: number): number[] {
  const out: number[] = [];
  for (let y = c.b0; y <= c.b1; y++) {
    const m = (y - 2000) * 12 + mo;
    if (m < c.ds.lastM && c.s.src[m] >= 0) out.push(valueOf(c, m));
  }
  return out;
}

export function calendarOption(c: Ctx, mode: CalMode, showNums: boolean) {
  const { ds, s } = c;
  const years = Array.from({ length: yearOf(ds.lastM) - 2000 + 1 }, (_, i) => 2000 + i);
  const data: any[] = [], nodata: any[] = [];
  const stats = MONTHS.map((_, mo) => { const v = baselineMonth(c, mo); return { v, med: median(v) }; });
  let vmax = 0;
  for (let m = 0; m <= ds.lastM; m++) if (s.src[m] >= 0) vmax = Math.max(vmax, valueOf(c, m));
  for (let yi = 0; yi < years.length; yi++) {
    for (let mo = 0; mo < 12; mo++) {
      const m = yi * 12 + mo;
      if (m > ds.lastM || s.src[m] < 0) { nodata.push([mo, yi, 0]); continue; }
      const v = valueOf(c, m);
      const st = stats[mo];
      let cv: number;
      if (mode === "count") cv = Math.log1p(v) / Math.log1p(vmax || 1);
      else if (mode === "anom") cv = st.med > 0 ? Math.max(-2, Math.min(2, Math.log2(Math.max(v, 0.25) / st.med))) : v > 0 ? 2 : 0;
      else cv = percentileRank(st.v, v);
      data.push({ value: [mo, yi, cv], raw: v, m });
    }
  }
  const visualMap =
    mode === "count"
      ? { type: "continuous", min: 0, max: 1, inRange: { color: FIRE_RAMP }, show: false, seriesIndex: 0 }
      : mode === "anom"
        ? { type: "continuous", min: -2, max: 2, inRange: { color: DIVERGE }, show: false, seriesIndex: 0 }
        : { type: "continuous", min: 0, max: 100, inRange: { color: ["#1b2a4a", "#3a4f7a", "#3a3d48", "#c26a3a", "#ff8a3d"] }, show: false, seriesIndex: 0 };
  const spliceYear = yearOf(ds.meta.splice_ym);
  return {
    ...base,
    grid: { left: 64, right: 16, top: 30, bottom: 26 },
    tooltip: {
      backgroundColor: "#0f1117", borderColor: LINE, textStyle: { color: TXT },
      formatter: (p: any) => {
        if (p.seriesIndex === 1) return `${MONTHS[p.value[0]]} ${years[p.value[1]]}: no satellite record`;
        const m = p.data.m as number, st = stats[m % 12];
        const src = s.src[m];
        const partial = m === ds.lastM ? ` <span style="color:${ACC2}">(to ${ds.endDay} ${MONTHS[m % 12]})</span>` : "";
        const ci = src === 0 ? "observed" : `90% CI ${fmt(s.ciLo[m])}–${fmt(s.ciHi[m])}`;
        return [
          `<b>${MONTHS[m % 12]} ${yearOf(m)}</b>${partial}`,
          `Harmonized: <b>${fmt(s.meq[m], 1)}</b> MODIS-eq. units <span style="color:${MUTED}">(${ci})</span>`,
          `vs ${c.b0}–${c.b1} median ${fmt(st.med, 1)}: <b>${st.med > 0 ? fmtPct((s.meq[m] / st.med - 1) * 100) : "–"}</b> · percentile ${fmt(percentileRank(st.v, valueOf(c, m)))}`,
          `<span style="color:${MUTED}">MODIS observed: ${fmt(s.mu[m])} units (${fmt(s.mp[m])} pts) · VIIRS: ${m >= ds.meta.viirs_first_ym ? `${fmt(s.vu[m])} units (${fmt(s.vp[m])} pts)` : "not yet launched"}</span>`,
          `<span style="color:${MUTED}">Naive FIRMS splice: ${fmt(s.naive[m])} points</span>`,
          `<span style="color:${MUTED}">Source: ${ds.meta.src_codes[String(src)]}</span>`,
        ].join("<br/>");
      },
    },
    xAxis: { type: "category", data: MONTHS, position: "top", ...axisStyle, splitLine: { show: false }, axisTick: { show: false } },
    yAxis: {
      type: "category", data: years, inverse: true, ...axisStyle, splitLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: MUTED, formatter: (y: string) => (Number(y) >= spliceYear ? `${y} ◇` : y) },
    },
    visualMap: [visualMap, { type: "continuous", min: 0, max: 1, inRange: { color: ["#14161d", "#14161d"] }, show: false, seriesIndex: 1 }],
    series: [
      {
        type: "heatmap", data, itemStyle: { borderColor: "#0b0c10", borderWidth: 1.5, borderRadius: 3 },
        label: { show: showNums, color: "#0b0c10", fontSize: 9.5, formatter: (p: any) => (p.data.raw >= 1 ? fmt(p.data.raw) : "") },
        emphasis: { itemStyle: { borderColor: ACC2, borderWidth: 2 } },
      },
      { type: "heatmap", data: nodata, itemStyle: { color: "#14161d", borderColor: "#0b0c10", borderWidth: 1.5, decal: { symbol: "rect", dashArrayX: [1, 0], dashArrayY: [2, 4], rotation: -0.8, color: "#232634" } }, silent: false },
    ],
  };
}

export function legendText(mode: CalMode, c: Ctx): string {
  if (mode === "count") return "Colour: activity (log scale), dark = none → yellow = highest month on record.";
  if (mode === "anom") return `Colour: ratio to the ${c.b0}–${c.b1} median for that month — purple ¼× … grey 1× … orange 4×.`;
  return `Colour: percentile among ${c.b0}–${c.b1} for that month — blue low, orange high.`;
}

/** Cumulative-by-week season-to-date curves (harmonized). */
export function seasonOption(c: Ctx) {
  const { ds, s } = c;
  const cum = (y: number) => {
    const out: number[] = [];
    let acc = 0;
    for (let k = 0; k < 48; k++) {
      const m = (y - 2000) * 12 + Math.floor(k / 4), w = k % 4;
      if (m > ds.lastM || (m === ds.lastM && w >= ds.wkDone)) break;
      acc += s.wk[m * 4 + w];
      out.push(acc);
    }
    return out;
  };
  const curY = yearOf(ds.lastM);
  const base: number[][] = [];
  for (let y = Math.max(c.b0, 2001); y <= c.b1; y++) base.push(cum(y));
  const med = [], p10 = [], band = [];
  for (let k = 0; k < 48; k++) {
    const v = base.map((b) => b[k]).filter((x) => x !== undefined);
    const lo = quantile(v, 0.1), hi = quantile(v, 0.9);
    med.push(median(v)); p10.push(lo); band.push(hi - lo);
  }
  const xs = Array.from({ length: 48 }, (_, k) => (k % 4 === 0 ? MONTHS[k / 4] : ""));
  const cur = cum(curY), prev = cum(curY - 1);
  return {
    ...base_(),
    grid: { left: 56, right: 70, top: 40, bottom: 30 },
    legend: { top: 0, right: 0, textStyle: { color: MUTED }, data: [`${curY}`, `${curY - 1}`, "Median", "10–90% range"] },
    tooltip: { trigger: "axis", backgroundColor: "#0f1117", borderColor: LINE, textStyle: { color: TXT }, valueFormatter: (v: number) => fmt(v) },
    xAxis: { type: "category", data: xs, boundaryGap: false, ...axisStyle, splitLine: { show: false }, axisLabel: { color: MUTED, interval: 0 } },
    yAxis: { type: "value", ...axisStyle },
    series: [
      { name: "p10", type: "line", data: p10, stack: "band", lineStyle: { opacity: 0 }, symbol: "none", tooltip: { show: false } },
      { name: "10–90% range", type: "line", color: "rgba(127,179,255,0.35)", data: band, stack: "band", lineStyle: { opacity: 0 }, symbol: "none", areaStyle: { color: "rgba(127,179,255,0.15)" } },
      { name: "Median", type: "line", color: BLUE, data: med, symbol: "none", lineStyle: { color: BLUE, width: 2, type: "dashed" } },
      { name: `${curY - 1}`, type: "line", color: MUTED, data: prev, symbol: "none", lineStyle: { color: MUTED, width: 1.5 } },
      { name: `${curY}`, type: "line", color: ACC, data: cur, symbol: "none", lineStyle: { color: ACC, width: 3 }, endLabel: { show: true, color: ACC, formatter: () => "so far" } },
    ],
  };
}
const base_ = () => base;

export interface Critical { months: number[]; peak: number; share: number[]; label: string }
/** Critical months = the fewest months that together hold >= 75% of a typical year's activity (may be several seasons). */
export function criticalPeriod(c: Ctx): Critical {
  const med = MONTHS.map((_, mo) => median(baselineMonth({ ...c, naive: false }, mo)) || 0);
  const tot = med.reduce((a, b) => a + b, 0) || 1;
  const share = med.map((v) => v / tot);
  const order = share.map((v, i) => [v, i]).sort((a, b) => b[0] - a[0]);
  const months: number[] = [];
  let acc = 0;
  for (const [v, i] of order) { if (acc >= 0.75 || v <= 0) break; months.push(i); acc += v; }
  months.sort((a, b) => a - b);
  // group consecutive months (circular) into seasons for the label
  const set = new Set(months), seasons: string[] = [], seen = new Set<number>();
  for (const m of months) {
    if (seen.has(m)) continue;
    let a = m; while (set.has((a + 11) % 12) && !seen.has((a + 11) % 12) && (a + 11) % 12 !== m) a = (a + 11) % 12;
    let b = a; const run = [a]; while (set.has((b + 1) % 12) && (b + 1) % 12 !== a) { b = (b + 1) % 12; run.push(b); }
    run.forEach((x) => seen.add(x));
    seasons.push(a === b ? MONTHS[a] : `${MONTHS[a]}–${MONTHS[b]}`);
  }
  return { months, peak: share.indexOf(Math.max(...share)), share, label: seasons.join(" & ") };
}

export function climOption(c: Ctx, cp: Critical) {
  const { ds, s } = c;
  const curY = yearOf(ds.lastM);
  const rows = MONTHS.map((_, mo) => {
    const v = baselineMonth({ ...c, naive: false }, mo);
    return { med: median(v), q1: quantile(v, 0.25), q3: quantile(v, 0.75), max: Math.max(...v) };
  });
  const cur = MONTHS.map((_, mo) => { const m = (curY - 2000) * 12 + mo; return m < ds.lastM ? s.meq[m] : m === ds.lastM ? s.meq[m] : null; });
  const inCrit = (mo: number) => cp.months.includes(mo);
  return {
    ...base,
    grid: { left: 56, right: 16, top: 40, bottom: 30 },
    legend: { top: 0, right: 0, textStyle: { color: MUTED }, data: ["Median month (critical = orange)", "Interquartile range", `${curY}`] },
    tooltip: { trigger: "axis", backgroundColor: "#0f1117", borderColor: LINE, textStyle: { color: TXT }, valueFormatter: (v: number) => fmt(v, 1) },
    xAxis: { type: "category", data: MONTHS, ...axisStyle, splitLine: { show: false } },
    yAxis: { type: "value", ...axisStyle },
    series: [
      {
        name: "Median month (critical = orange)", type: "bar", color: ACC, data: rows.map((r, mo) => ({ value: r.med, itemStyle: { color: inCrit(mo) ? ACC : "#5a4a3e" } })), barWidth: "55%",
      },
      { name: "Interquartile range", type: "custom", color: TXT, renderItem: (_p: any, api: any) => {
          const x = api.coord([api.value(0), 0])[0], y1 = api.coord([0, api.value(1)])[1], y2 = api.coord([0, api.value(2)])[1];
          return { type: "group", children: [
            { type: "line", shape: { x1: x, y1, x2: x, y2 }, style: { stroke: TXT, lineWidth: 1.2 } },
            { type: "line", shape: { x1: x - 5, y1, x2: x + 5, y2: y1 }, style: { stroke: TXT, lineWidth: 1.2 } },
            { type: "line", shape: { x1: x - 5, y1: y2, x2: x + 5, y2 }, style: { stroke: TXT, lineWidth: 1.2 } } ] };
        }, data: rows.map((r, mo) => [mo, r.q1, r.q3]), z: 5 },
      { name: `${curY}`, type: "scatter", color: ACC2, data: cur, symbolSize: 9, itemStyle: { color: ACC2, borderColor: "#0b0c10" }, z: 6 },
    ],
  };
}

export interface Annual { years: number[]; harm: number[]; naive: number[]; modis: number[]; trend: { slope: number; intercept: number; p: number; pct: number }; naiveTrend: { pct: number; p: number } }
export function annual(c: Ctx): Annual {
  const { ds, s } = c;
  const lastFull = yearOf(ds.lastM) - (ds.lastM % 12 === 11 && ds.wkDone === 4 ? 0 : 1);
  const years: number[] = [], harm: number[] = [], naive: number[] = [], modis: number[] = [];
  for (let y = 2001; y <= yearOf(ds.lastM); y++) {
    let h = 0, n = 0, mo = 0;
    for (let k = 0; k < 12; k++) { const m = (y - 2000) * 12 + k; if (m > ds.lastM) break; h += s.meq[m]; n += s.naive[m]; mo += s.mu[m]; }
    years.push(y); harm.push(h); naive.push(n); modis.push(mo);
  }
  const fy = years.filter((y) => y <= lastFull);
  const fh = harm.slice(0, fy.length), fn = naive.slice(0, fy.length);
  const ts = theilSen(fy, fh), mk = mannKendall(fh);
  const tn = theilSen(fy, fn), mkn = mannKendall(fn);
  return {
    years, harm, naive, modis,
    trend: { ...ts, p: mk.p, pct: (ts.slope / (median(fh) || 1)) * 100 },
    naiveTrend: { pct: (tn.slope / (median(fn) || 1)) * 100, p: mkn.p },
  };
}

export function annualOption(c: Ctx, a: Annual) {
  const { ds } = c;
  const curY = yearOf(ds.lastM);
  const lastFull = a.years.filter((y) => y < curY);
  const trendLine = lastFull.map((y) => a.trend.intercept + a.trend.slope * y);
  return {
    ...base,
    grid: { left: 64, right: 64, top: 40, bottom: 30 },
    legend: { top: 0, textStyle: { color: MUTED }, data: ["Harmonized (MODIS-eq. units)", "MODIS observed (units)", "Trend (Theil–Sen)", "Naive FIRMS splice (points, right axis)"] },
    tooltip: { trigger: "axis", backgroundColor: "#0f1117", borderColor: LINE, textStyle: { color: TXT }, valueFormatter: (v: number) => fmt(v) },
    xAxis: { type: "category", data: a.years, ...axisStyle, splitLine: { show: false } },
    yAxis: [
      { type: "value", ...axisStyle, name: "units / year", nameTextStyle: { color: MUTED } },
      { type: "value", ...axisStyle, splitLine: { show: false }, name: "points / year", nameTextStyle: { color: WARN }, axisLabel: { color: WARN } },
    ],
    series: [
      { name: "Harmonized (MODIS-eq. units)", type: "bar", color: ACC, data: a.harm.map((v, i) => ({ value: v, itemStyle: { color: a.years[i] === curY ? "rgba(255,138,61,0.45)" : ACC } })), barWidth: "60%" },
      { name: "MODIS observed (units)", type: "line", color: ACC2, data: a.modis, symbol: "circle", symbolSize: 4, lineStyle: { color: ACC2, width: 1.5, type: "dashed" }, itemStyle: { color: ACC2 } },
      { name: "Trend (Theil–Sen)", type: "line", color: TXT, data: trendLine, symbol: "none", lineStyle: { color: TXT, width: 2 } },
      { name: "Naive FIRMS splice (points, right axis)", type: "line", color: WARN, yAxisIndex: 1, data: a.naive, symbol: "none", lineStyle: { color: WARN, width: 2 }, step: "middle" },
    ],
  };
}

export function curveOption(meta: Dataset["meta"]) {
  const col = meta.collocated;
  const mk = (dn: "D" | "N", color: string, name: string) => {
    const d = col[dn];
    const pts = d.frp_mid.map((x, i) => [x, d.p_detect[i] * 100, d.n[i]]).filter((p) => p[2] >= 30);
    return { name, type: "line", data: pts, symbolSize: 6, lineStyle: { color, width: 2.5 }, itemStyle: { color } };
  };
  return {
    ...base,
    grid: { left: 48, right: 16, top: 32, bottom: 40 },
    legend: { top: 0, textStyle: { color: MUTED } },
    tooltip: { trigger: "axis", backgroundColor: "#0f1117", borderColor: LINE, textStyle: { color: TXT }, valueFormatter: (v: number) => `${fmt(v, 1)}%` },
    xAxis: { type: "log", logBase: 2, name: "VIIRS fire power (MW)", nameLocation: "middle", nameGap: 26, nameTextStyle: { color: MUTED }, ...axisStyle, min: 0.25, max: 512 },
    yAxis: { type: "value", max: 100, name: "% also seen by MODIS", nameTextStyle: { color: MUTED }, ...axisStyle },
    series: [mk("D", ACC, "Day"), mk("N", BLUE, "Night")],
  };
}

export function driftOption(meta: Dataset["meta"]) {
  const pj = meta.drift["punjab_haryana"], ind = meta.drift["india"];
  const yrs = pj.map((r) => r.year).filter((y) => y >= 2013);
  const pick = (rows: any[], k: string) => rows.filter((r) => r.year >= 2013).map((r) => r[k]);
  const splice = meta.splice_ym / 12 + 2000;
  return {
    ...base,
    grid: { left: 48, right: 52, top: 32, bottom: 28 },
    legend: { top: 0, textStyle: { color: MUTED } },
    tooltip: { trigger: "axis", backgroundColor: "#0f1117", borderColor: LINE, textStyle: { color: TXT } },
    xAxis: { type: "category", data: yrs, ...axisStyle, splitLine: { show: false } },
    yAxis: [
      { type: "value", min: 0.6, max: 2.2, name: "MODIS ÷ VIIRS-expected", nameTextStyle: { color: MUTED }, ...axisStyle },
      { type: "value", min: 8, max: 16, name: "overpass (LST h)", nameTextStyle: { color: MUTED }, ...axisStyle, splitLine: { show: false } },
    ],
    series: [
      { name: "Punjab & Haryana (Aqua)", type: "line", data: pick(pj, "aqua_ratio"), lineStyle: { color: WARN, width: 2.5 }, itemStyle: { color: WARN },
        markLine: { silent: true, symbol: "none", lineStyle: { color: MUTED, type: "dashed" }, label: { color: MUTED }, data: [{ yAxis: 1, label: { formatter: "no bias" } }, { xAxis: String(splice), label: { formatter: "switch to VIIRS-derived" } }] } },
      { name: "India (Aqua)", type: "line", data: pick(ind, "aqua_ratio"), lineStyle: { color: ACC, width: 2 }, itemStyle: { color: ACC } },
      { name: "Aqua overpass", type: "line", yAxisIndex: 1, data: pick(ind, "aqua_lst"), lineStyle: { color: BLUE, type: "dotted" }, itemStyle: { color: BLUE }, symbol: "none" },
      { name: "Terra overpass", type: "line", yAxisIndex: 1, data: pick(ind, "terra_lst"), lineStyle: { color: "#9f8fd0", type: "dotted" }, itemStyle: { color: "#9f8fd0" }, symbol: "none" },
    ],
  };
}

export function makeChart(el: HTMLElement) {
  const ch = echarts.init(el, undefined, { renderer: "canvas" });
  new ResizeObserver(() => ch.resize()).observe(el);
  return ch;
}
