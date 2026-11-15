export function quantile(values: number[], q: number): number {
  const a = values.filter((v) => Number.isFinite(v)).sort((x, y) => x - y);
  if (!a.length) return NaN;
  const p = (a.length - 1) * q, lo = Math.floor(p), hi = Math.ceil(p);
  return a[lo] + (a[hi] - a[lo]) * (p - lo);
}
export const median = (v: number[]) => quantile(v, 0.5);

export function percentileRank(values: number[], x: number): number {
  const a = values.filter((v) => Number.isFinite(v));
  if (!a.length) return NaN;
  let below = 0, eq = 0;
  for (const v of a) { if (v < x) below++; else if (v === x) eq++; }
  return ((below + 0.5 * eq) / a.length) * 100;
}

export function theilSen(xs: number[], ys: number[]): { slope: number; intercept: number } {
  const slopes: number[] = [];
  for (let i = 0; i < xs.length; i++) for (let j = i + 1; j < xs.length; j++) if (xs[j] !== xs[i]) slopes.push((ys[j] - ys[i]) / (xs[j] - xs[i]));
  const slope = median(slopes);
  const intercept = median(xs.map((x, i) => ys[i] - slope * x));
  return { slope, intercept };
}

function erf(x: number): number {
  const t = 1 / (1 + 0.3275911 * Math.abs(x));
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
  return x >= 0 ? y : -y;
}
const normCdf = (z: number) => 0.5 * (1 + erf(z / Math.SQRT2));

export function mannKendall(ys: number[]): { S: number; z: number; p: number } {
  const n = ys.length;
  let S = 0;
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) S += Math.sign(ys[j] - ys[i]);
  const varS = (n * (n - 1) * (2 * n + 5)) / 18;
  const z = S > 0 ? (S - 1) / Math.sqrt(varS) : S < 0 ? (S + 1) / Math.sqrt(varS) : 0;
  return { S, z, p: 2 * (1 - normCdf(Math.abs(z))) };
}

export const fmt = (v: number, d = 0) =>
  !Number.isFinite(v) ? "–" : v.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
export const fmtPct = (v: number) => (!Number.isFinite(v) ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(0)}%`);
