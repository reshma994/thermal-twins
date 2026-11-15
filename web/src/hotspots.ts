import { cellToParent, latLngToCell } from "h3-js";
import { fetchBinary } from "./data";

interface HotIndex { res: number; epoch: string; platforms: string[]; confidence: string[]; files: Record<string, { n: number; bytes: number; day_min: number; day_max: number }> }
const SAT = ["Terra", "Aqua", "Suomi NPP", "NOAA-20", "NOAA-21"];
const INSTR = ["MODIS", "MODIS", "VIIRS", "VIIRS", "VIIRS"];
const CONF = ["low", "nominal", "high"];
const EPOCH = Date.UTC(2000, 0, 1);
let index: HotIndex | null = null;
let hotBase = "";
// Raw-hotspot packs (~120 MB) are served from the public repo when the host doesn't carry them.
const REPO_PACKS: string =
  import.meta.env.VITE_HOTSPOT_BASE ?? "https://raw.githubusercontent.com/reshma994/thermal-twins/Nitant/web/public/data/india/hotspots";

async function loadIndex(base: string): Promise<HotIndex> {
  try {
    const r = await fetch(`${base}/hotspots/index.json`);
    if (r.ok && (r.headers.get("content-type") || "").includes("json")) { hotBase = `${base}/hotspots`; return await r.json(); }
  } catch { /* fall through to repo-hosted packs */ }
  hotBase = REPO_PACKS;
  const r = await fetch(`${REPO_PACKS}/index.json`);
  if (!r.ok) throw new Error(`hotspot index unavailable (HTTP ${r.status})`);
  return await r.json();
}

const dayToIso = (d: number) => new Date(EPOCH + d * 86400000).toISOString().slice(0, 10);

function lowerBound(a: Uint16Array, x: number) { let lo = 0, hi = a.length; while (lo < hi) { const mid = (lo + hi) >> 1; if (a[mid] < x) lo = mid + 1; else hi = mid; } return lo; }

/** Raw FIRMS hotspots inside the AOI cells (H3 r5) and day range -> CSV text. */
export async function hotspotsCsv(
  base: string, cells: Set<string>, day0: number, day1: number, onProgress: (msg: string) => void, maxRows = 1_500_000,
): Promise<{ csv: string; rows: number; truncated: boolean }> {
  if (!index) index = await loadIndex(base);
  const parents = new Set<string>();
  cells.forEach((c) => parents.add(cellToParent(c, index!.res)));
  const files = [...parents].filter((p) => index!.files[p] && index!.files[p].day_max >= day0 && index!.files[p].day_min <= day1);
  const out: string[] = ["latitude,longitude,acq_date,acq_time_utc,satellite,instrument,confidence,frp_mw,daynight,static_source,local_solar_hour,h3_r5"];
  let rows = 0, truncated = false;
  for (let fi = 0; fi < files.length && !truncated; fi++) {
    const f = files[fi];
    onProgress(`Reading pack ${fi + 1}/${files.length} (${(index!.files[f].bytes / 1e6).toFixed(1)} MB)…`);
    const buf = await fetchBinary(`${hotBase}/${f}.bin.gz`);
    const n = index!.files[f].n;
    const lat = new Int32Array(buf, 0, n), lon = new Int32Array(buf, 4 * n, n);
    const day = new Uint16Array(buf, 8 * n, n), hhmm = new Uint16Array(buf, 10 * n, n), frp = new Uint16Array(buf, 12 * n, n), code = new Uint8Array(buf, 14 * n, n);
    for (let i = lowerBound(day, day0); i < n && day[i] <= day1; i++) {
      const la = lat[i] / 1e5, lo = lon[i] / 1e5;
      const cell = latLngToCell(la, lo, 5);
      if (!cells.has(cell)) continue;
      const cd = code[i], p = cd & 7, cf = (cd >> 3) & 3, night = (cd >> 5) & 1, st = (cd >> 6) & 1;
      const t = hhmm[i], hh = Math.floor(t / 100), mm = t % 100;
      const lst = (((hh + mm / 60 + lo / 15) % 24) + 24) % 24;
      out.push(`${la.toFixed(5)},${lo.toFixed(5)},${dayToIso(day[i])},${String(t).padStart(4, "0")},${SAT[p]},${INSTR[p]},${CONF[cf]},${(frp[i] / 10).toFixed(1)},${night ? "N" : "D"},${st},${lst.toFixed(2)},${cell}`);
      if (++rows >= maxRows) { truncated = true; break; }
    }
  }
  return { csv: out.join("\n"), rows, truncated };
}

export const isoToDay = (iso: string) => Math.round((Date.parse(iso + "T00:00:00Z") - EPOCH) / 86400000);
