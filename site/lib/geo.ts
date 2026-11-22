export type Frame = { lon0: number; lat0: number; mx: number; my: number };

export type MapLayer = {
  dzi: string;
  places: string;
  width: number;
  height: number;
  px: number;
  ox: number;
  oy: number;
  overlay: boolean;
  bbox: [number, number, number, number];
  start?: { lon: number; lat: number };
};

export type World = { frame: Frame; maps: Record<string, MapLayer> };

const C = Math.SQRT1_2;

// Mirrors render.Iso.xy / tiles.unproject at ground level (z = 0).
export function toImage(f: Frame, m: MapLayer, lon: number, lat: number) {
  const e = (lon - f.lon0) * f.mx;
  const n = (lat - f.lat0) * f.my;
  return { x: (e - n) * C * m.px - m.ox, y: -(e + n) * C * 0.5 * m.px - m.oy };
}

export function toLonLat(f: Frame, m: MapLayer, x: number, y: number) {
  const a = (x + m.ox) / (C * m.px);
  const b = -(y + m.oy) / (0.5 * C * m.px);
  return { lon: f.lon0 + (a + b) / 2 / f.mx, lat: f.lat0 + (b - a) / 2 / f.my };
}

export function inBounds(m: MapLayer, lon: number, lat: number) {
  const [x0, y0, x1, y1] = m.bbox;
  return lon >= x0 && lon <= x1 && lat >= y0 && lat <= y1;
}

// The base map is the one that is not an overlay; overlays are scaled sub-rectangles of it.
export function baseLayer(w: World) {
  return Object.values(w.maps).find((m) => !m.overlay) ?? Object.values(w.maps)[0];
}

// Where an overlay sits, in OpenSeadragon viewport units (base image width = 1).
export function placement(base: MapLayer, m: MapLayer) {
  const k = base.px / m.px;
  return { x: (m.ox * k - base.ox) / base.width, y: (m.oy * k - base.oy) / base.width, width: (m.width * k) / base.width };
}

export function parseLatLon(s: string) {
  const g = s.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
  return g ? { lat: Number(g[1]), lon: Number(g[2]) } : null;
}

export function parseAt(s: string | null) {
  const parts = s?.split(',').map(Number);
  if (!parts || parts.length !== 3 || parts.some(Number.isNaN)) return null;
  return { lat: parts[0], lon: parts[1], zoom: parts[2] };
}

export function formatAt(lat: number, lon: number, zoom: number) {
  return `${lat.toFixed(5)},${lon.toFixed(5)},${zoom.toFixed(2)}`;
}
