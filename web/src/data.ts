export interface Column { name: string; dtype: "uint16" | "uint8"; offset: number; length: number; scale: number }
export interface Preset { id: string; name: string; bbox: [number, number, number, number] | null }
export interface Meta {
  aoi: string; name: string; data_end: string; ym0: number; n: number; h3_res: number; cells: string[];
  columns: Column[]; splice_ym: number; snpp_last_ym: number; aqua_first_ym: number; viirs_first_ym: number;
  modis_first_ym: number; presets: Preset[]; src_codes: Record<string, string>;
  drift: Record<string, Array<Record<string, number>>>;
  validation: Record<string, Record<string, any>>;
  collocated: Record<string, { frp_mid: number[]; p_detect: number[]; ci_lo: number[]; ci_hi: number[]; n: number[]; fit: { pmax: number; frp50_mw: number; slope: number } }>;
}

export interface Dataset {
  meta: Meta;
  col: Record<string, Uint16Array | Uint8Array>;
  nM: number; // months 0..nM-1 (0 = Jan 2000)
  lastM: number; // last month with data (partial)
  wkDone: number; // complete week buckets in last month
  endDay: number;
  cellIndex: Map<string, number>;
}

async function gunzipIfNeeded(buf: ArrayBuffer): Promise<ArrayBuffer> {
  const b = new Uint8Array(buf, 0, 2);
  if (b[0] !== 0x1f || b[1] !== 0x8b) return buf;
  const stream = new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"));
  return await new Response(stream).arrayBuffer();
}

export async function fetchBinary(url: string): Promise<ArrayBuffer> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return gunzipIfNeeded(await r.arrayBuffer());
}

export async function loadDataset(base: string): Promise<Dataset> {
  const meta: Meta = await (await fetch(`${base}/meta.json`)).json();
  const buf = await fetchBinary(`${base}/monthly.bin.gz`);
  const col: Record<string, Uint16Array | Uint8Array> = {};
  for (const c of meta.columns) {
    col[c.name] = c.dtype === "uint16" ? new Uint16Array(buf, c.offset, c.length) : new Uint8Array(buf, c.offset, c.length);
  }
  const [y, m, d] = meta.data_end.split("-").map(Number);
  const lastM = (y - 2000) * 12 + (m - 1);
  const cellIndex = new Map(meta.cells.map((c, i) => [c, i] as [string, number]));
  return { meta, col, nM: lastM + 1, lastM, wkDone: Math.min(4, Math.floor(d / 7)), endDay: d, cellIndex };
}

export interface Series {
  meq: Float64Array; wk: Float64Array; lo: Float64Array; hi: Float64Array; vr: Float64Array;
  mu: Float64Array; mp: Float64Array; vu: Float64Array; vp: Float64Array; vmeq: Float64Array;
  src: Int8Array; // -1 no data, 0 MODIS observed, 1 Terra + modeled Aqua, 2 VIIRS-derived
  ciLo: Float64Array; ciHi: Float64Array; naive: Float64Array;
}

export function srcOf(ds: Dataset, m: number): number {
  const M = ds.meta;
  if (m < M.modis_first_ym || m > ds.lastM) return -1;
  if (m >= M.splice_ym) return 2;
  if (m < M.aqua_first_ym) return 1;
  return 0;
}

export function aggregate(ds: Dataset, mask: Uint8Array): Series {
  const nM = ds.nM, c = ds.col, n = ds.meta.n;
  const z = () => new Float64Array(nM);
  const s: Series = {
    meq: z(), wk: new Float64Array(nM * 4), lo: z(), hi: z(), vr: z(), mu: z(), mp: z(), vu: z(), vp: z(), vmeq: z(),
    src: new Int8Array(nM), ciLo: z(), ciHi: z(), naive: z(),
  };
  const cell = c.cell, ym = c.ym, w0 = c.w0, w1 = c.w1, w2 = c.w2, w3 = c.w3;
  for (let i = 0; i < n; i++) {
    if (!mask[cell[i]]) continue;
    const m = ym[i];
    if (m >= nM) continue;
    const a = w0[i] / 10, b = w1[i] / 10, cc = w2[i] / 10, d = w3[i] / 10;
    const k = m * 4;
    s.wk[k] += a; s.wk[k + 1] += b; s.wk[k + 2] += cc; s.wk[k + 3] += d;
    s.meq[m] += a + b + cc + d;
    s.lo[m] += c.lo[i] / 10; s.hi[m] += c.hi[i] / 10; s.vr[m] += c.var[i] / 10;
    s.mu[m] += c.mu[i]; s.mp[m] += c.mp[i]; s.vu[m] += c.vu[i]; s.vp[m] += c.vp[i]; s.vmeq[m] += c.vmeq[i] / 10;
  }
  const Z = 1.645;
  for (let m = 0; m < nM; m++) {
    const src = srcOf(ds, m);
    s.src[m] = src;
    const sd = Math.sqrt(s.vr[m]);
    if (src === 2) { s.ciLo[m] = Math.max(0, Math.min(s.lo[m], s.meq[m]) - Z * sd); s.ciHi[m] = Math.max(s.hi[m], s.meq[m]) + Z * sd; }
    else if (src === 1) { s.ciLo[m] = Math.max(0, s.meq[m] - Z * sd); s.ciHi[m] = s.meq[m] + Z * sd; }
    else { s.ciLo[m] = s.meq[m]; s.ciHi[m] = s.meq[m]; }
    s.naive[m] = m < ds.meta.viirs_first_ym ? s.mp[m] : s.vp[m];
  }
  return s;
}

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const ymLabel = (m: number) => `${MONTHS[m % 12]} ${2000 + Math.floor(m / 12)}`;
