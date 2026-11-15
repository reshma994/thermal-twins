import maplibregl, { GeoJSONSource, Map as MlMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { cellToBoundary } from "h3-js";

export type Ring = [number, number][]; // [lng, lat], closed

export const FIRE_RAMP = ["#1b1030", "#4a1170", "#8c2981", "#d3436e", "#f8765c", "#fdb96b", "#fcfdbf"];

export class FireMap {
  map: MlMap;
  private cells: string[];
  private ready: Promise<void>;
  private mode: "none" | "rect" | "poly" = "none";
  private start: [number, number] | null = null;
  private pts: [number, number][] = [];
  onAoi: (ring: Ring) => void = () => {};
  onModeChange: (m: "none" | "rect" | "poly") => void = () => {};

  constructor(el: HTMLElement, cells: string[]) {
    this.cells = cells;
    this.map = new maplibregl.Map({
      container: el,
      style: {
        version: 8,
        sources: {
          esri: {
            type: "raster", tileSize: 256, maxzoom: 17,
            tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
            attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
          },
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#0b0c10" } },
          { id: "esri", type: "raster", source: "esri", paint: { "raster-brightness-max": 0.5, "raster-saturation": -0.5, "raster-contrast": 0.05 } },
        ],
      },
      center: [80, 22.5], zoom: 3.7, attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false,
    });
    this.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    this.ready = new Promise((res) => this.map.on("load", () => { this.init(); res(); }));
  }

  private init() {
    const features = this.cells.map((c, i) => {
      const ring = cellToBoundary(c, true) as [number, number][];
      if (ring[0][0] !== ring[ring.length - 1][0] || ring[0][1] !== ring[ring.length - 1][1]) ring.push(ring[0]);
      return { type: "Feature" as const, id: i, properties: { v: 0, lv: 0 }, geometry: { type: "Polygon" as const, coordinates: [ring] } };
    });
    this.map.addSource("hex", { type: "geojson", data: { type: "FeatureCollection", features } });
    this.map.addLayer({
      id: "hex", type: "fill", source: "hex",
      paint: {
        "fill-color": ["interpolate", ["linear"], ["get", "lv"], 0, FIRE_RAMP[0], 0.17, FIRE_RAMP[1], 0.33, FIRE_RAMP[2], 0.5, FIRE_RAMP[3], 0.67, FIRE_RAMP[4], 0.83, FIRE_RAMP[5], 1, FIRE_RAMP[6]],
        "fill-opacity": ["case", [">", ["get", "v"], 0], 0.88, 0.08],
      },
    });
    this.map.addSource("aoi", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    this.map.addLayer({ id: "aoi-fill", type: "fill", source: "aoi", paint: { "fill-color": "#ffd166", "fill-opacity": 0.06 } });
    this.map.addLayer({ id: "aoi-line", type: "line", source: "aoi", paint: { "line-color": "#ffd166", "line-width": 2.2, "line-dasharray": [2, 1] } });
    this.map.addSource("draft", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    this.map.addLayer({ id: "draft", type: "line", source: "draft", paint: { "line-color": "#ffffff", "line-width": 1.6 } });
    this.map.addLayer({ id: "draft-pts", type: "circle", source: "draft", paint: { "circle-radius": 4, "circle-color": "#ffd166" } });
    this.bindDraw();
  }

  async setValues(values: Float64Array) {
    await this.ready;
    let max = 0;
    for (const v of values) if (v > max) max = v;
    const lmax = Math.log1p(max) || 1;
    const src = this.map.getSource("hex") as GeoJSONSource;
    const data = (src as any)._data as GeoJSON.FeatureCollection;
    data.features.forEach((f, i) => { const v = values[i] || 0; f.properties = { v, lv: Math.log1p(v) / lmax }; });
    src.setData(data);
    return max;
  }

  async setAoi(ring: Ring | null, fit = true) {
    await this.ready;
    const src = this.map.getSource("aoi") as GeoJSONSource;
    src.setData({ type: "FeatureCollection", features: ring ? [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [ring] } }] : [] });
    if (ring && fit) {
      const lons = ring.map((p) => p[0]), lats = ring.map((p) => p[1]);
      this.map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 40, duration: 600, maxZoom: 8 });
    }
  }

  fitIndia() { this.map.fitBounds([[67.5, 6.5], [97.8, 37.3]], { padding: 20, duration: 600 }); }

  setMode(m: "none" | "rect" | "poly") {
    this.mode = m; this.start = null; this.pts = [];
    this.setDraft([]);
    m === "none" ? this.map.dragPan.enable() : this.map.dragPan.disable();
    this.map.doubleClickZoom[m === "poly" ? "disable" : "enable"]();
    this.map.getCanvas().style.cursor = m === "none" ? "" : "crosshair";
    this.onModeChange(m);
  }

  private setDraft(coords: [number, number][], closed = false) {
    const src = this.map.getSource("draft") as GeoJSONSource | undefined;
    if (!src) return;
    const line = closed && coords.length ? [...coords, coords[0]] : coords;
    src.setData({
      type: "FeatureCollection",
      features: [
        ...(line.length > 1 ? [{ type: "Feature" as const, properties: {}, geometry: { type: "LineString" as const, coordinates: line } }] : []),
        ...coords.map((c) => ({ type: "Feature" as const, properties: {}, geometry: { type: "Point" as const, coordinates: c } })),
      ],
    });
  }

  private bindDraw() {
    const m = this.map;
    const rectRing = (a: [number, number], b: [number, number]): Ring => [[a[0], a[1]], [b[0], a[1]], [b[0], b[1]], [a[0], b[1]], [a[0], a[1]]];
    m.on("mousedown", (e) => { if (this.mode === "rect") { this.start = [e.lngLat.lng, e.lngLat.lat]; } });
    m.on("mousemove", (e) => {
      if (this.mode === "rect" && this.start) this.setDraft(rectRing(this.start, [e.lngLat.lng, e.lngLat.lat]).slice(0, 4), true);
      if (this.mode === "poly" && this.pts.length) this.setDraft([...this.pts, [e.lngLat.lng, e.lngLat.lat]]);
    });
    m.on("mouseup", (e) => {
      if (this.mode !== "rect" || !this.start) return;
      const b: [number, number] = [e.lngLat.lng, e.lngLat.lat];
      if (Math.abs(b[0] - this.start[0]) < 0.05 || Math.abs(b[1] - this.start[1]) < 0.05) { this.start = null; return; }
      const ring = rectRing(this.start, b);
      this.setMode("none");
      this.onAoi(ring);
    });
    m.on("click", (e) => { if (this.mode === "poly") { this.pts.push([e.lngLat.lng, e.lngLat.lat]); this.setDraft(this.pts); } });
    m.on("dblclick", (e) => {
      if (this.mode !== "poly") return;
      e.preventDefault();
      const pts = this.pts.slice();
      if (pts.length >= 3) { this.setMode("none"); this.onAoi([...pts, pts[0]]); }
    });
  }
}

export function circleRing(lat: number, lon: number, km: number, n = 64): Ring {
  const ring: Ring = [];
  const dLat = km / 110.574;
  const dLon = km / (111.32 * Math.cos((lat * Math.PI) / 180));
  for (let i = 0; i <= n; i++) {
    const t = (2 * Math.PI * i) / n;
    ring.push([lon + dLon * Math.cos(t), lat + dLat * Math.sin(t)]);
  }
  return ring;
}

export const bboxRing = (b: [number, number, number, number]): Ring => [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]];
