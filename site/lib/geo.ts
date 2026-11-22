export type Meta = {
  dzi: string;
  width: number;
  height: number;
  px: number;
  ox: number;
  oy: number;
  lon0: number;
  lat0: number;
  mx: number;
  my: number;
  bbox: [number, number, number, number];
  start?: { x: number; y: number };
};

const C = Math.SQRT1_2;

// Mirrors render.Iso.xy / tiles.unproject at ground level (z = 0).
export function toImage(m: Meta, lon: number, lat: number) {
  const e = (lon - m.lon0) * m.mx;
  const n = (lat - m.lat0) * m.my;
  return { x: (e - n) * C * m.px - m.ox, y: -(e + n) * C * 0.5 * m.px - m.oy };
}

export function toLonLat(m: Meta, x: number, y: number) {
  const a = (x + m.ox) / (C * m.px);
  const b = -(y + m.oy) / (0.5 * C * m.px);
  return { lon: m.lon0 + (a + b) / 2 / m.mx, lat: m.lat0 + (b - a) / 2 / m.my };
}

export function inBounds(m: Meta, lon: number, lat: number) {
  const [x0, y0, x1, y1] = m.bbox;
  return lon >= x0 && lon <= x1 && lat >= y0 && lat <= y1;
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
