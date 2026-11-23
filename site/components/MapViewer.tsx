'use client';

import Link from 'next/link';
import OpenSeadragon from 'openseadragon';
import { useCallback, useEffect, useRef, useState } from 'react';
import { baseLayer, formatAt, inBounds, parseAt, placement, toImage, toLonLat, type MapLayer, type World } from '@/lib/geo';
import { LandmarkCard, LandmarkStrip, type Landmark } from './Landmarks';
import Search, { type Place } from './Search';

// Tiles may live on another host (they are too big for most static hosts); fetch() doesn't add basePath itself.
const TILES = process.env.NEXT_PUBLIC_TILES_BASE || `${process.env.NEXT_PUBLIC_BASE_PATH ?? ''}/tiles`;
// With several images open, viewport-level conversions are inaccurate; convert through the base image.
function baseItem(v: OpenSeadragon.Viewer, base: MapLayer) {
  for (let i = 0; i < v.world.getItemCount(); i++) {
    const it = v.world.getItemAt(i);
    if (it.getContentSize().x === base.width) return it;
  }
  return v.world.getItemAt(0);
}

const DETAIL_PIXELS = 1.5; // screen pixels per pixel of the most detailed map covering a place

export default function MapViewer() {
  const el = useRef<HTMLDivElement>(null);
  const viewer = useRef<OpenSeadragon.Viewer | null>(null);
  const pin = useRef<HTMLDivElement | null>(null);
  const [world, setWorld] = useState<World | null>(null);
  const [toast, setToast] = useState('');
  const [landmarks, setLandmarks] = useState<Landmark[]>([]);
  const [selected, setSelected] = useState<Landmark | null>(null);

  useEffect(() => {
    fetch(`${TILES}/landmarks.json`).then((r) => (r.ok ? r.json() : [])).then(setLandmarks).catch(() => {});
  }, []);

  useEffect(() => {
    let v: OpenSeadragon.Viewer | undefined;
    let cancelled = false;
    fetch(`${TILES}/world.json`)
      .then((r) => r.json())
      .then((w: World) => {
        if (cancelled || !el.current) return;
        setWorld(w);
        const base = baseLayer(w);
        const overlays = Object.values(w.maps).filter((m) => m !== base);
        v = OpenSeadragon({
          element: el.current,
          tileSources: [
            { tileSource: `${TILES}/${base.dzi}` },
            ...overlays.map((m) => ({ tileSource: `${TILES}/${m.dzi}`, ...placement(base, m) })),
          ],
          showNavigationControl: false,
          showNavigator: true,
          navigatorPosition: 'BOTTOM_RIGHT',
          navigatorSizeRatio: 0.16,
          drawer: 'canvas', // the WebGL drawer mis-blends transparent overlay tiles
          imageSmoothingEnabled: false,
          maxZoomPixelRatio: 6,
          minZoomImageRatio: 0.9,
          visibilityRatio: 0.4,
          animationTime: 0.9,
          blendTime: 0,
          gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
        } as OpenSeadragon.Options);
        viewer.current = v;
        v.addOnceHandler('open', () => {
          const vp = v!.viewport;
          const img = baseItem(v!, base);
          const at = parseAt(new URLSearchParams(location.search).get('at'));
          const start = Object.values(w.maps).find((m) => m.start)?.start;
          if (at && inBounds(base, at.lon, at.lat)) {
            const p = toImage(w.frame, base, at.lon, at.lat);
            vp.panTo(img.imageToViewportCoordinates(p.x, p.y), true);
            vp.zoomTo(at.zoom, undefined, true);
          } else if (start) {
            const p = toImage(w.frame, base, start.lon, start.lat);
            vp.panTo(img.imageToViewportCoordinates(p.x, p.y), true);
            vp.zoomTo(img.imageToViewportZoom(detailRatio(w, base, start.lon, start.lat) / 3), undefined, true);
          }
        });
        v.addHandler('animation-finish', () => {
          const vp = v!.viewport;
          const c = baseItem(v!, base).viewportToImageCoordinates(vp.getCenter(true));
          const ll = toLonLat(w.frame, base, c.x, c.y);
          history.replaceState(null, '', `?at=${formatAt(ll.lat, ll.lon, vp.getZoom(true))}`);
        });
      });
    return () => {
      cancelled = true;
      v?.destroy();
      viewer.current = null;
    };
  }, []);

  const flyTo = useCallback((lon: number, lat: number) => {
    const v = viewer.current;
    if (!v || !world) return;
    const base = baseLayer(world);
    const vp = v.viewport;
    const p = toImage(world.frame, base, lon, lat);
    const img = baseItem(v, base);
    const point = img.imageToViewportCoordinates(p.x, p.y);
    vp.panTo(point);
    vp.zoomTo(img.imageToViewportZoom(detailRatio(world, base, lon, lat)));
    if (pin.current) v.removeOverlay(pin.current);
    const div = document.createElement('div');
    div.className = 'pin';
    pin.current = div;
    v.addOverlay({ element: div, location: point, placement: OpenSeadragon.Placement.BOTTOM });
  }, [world]);

  const flash = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 2200);
  };

  const onLatLon = (lat: number, lon: number) => {
    if (!world) return;
    if (!inBounds(baseLayer(world), lon, lat)) return flash('That point is outside the map of Sri Lanka');
    flyTo(lon, lat);
  };

  const share = async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      flash('Link copied');
    } catch {
      flash(location.href);
    }
  };

  return (
    <>
      <div ref={el} className="map" role="application" aria-label="Map of Sri Lanka. Drag to move, scroll or pinch to zoom." />
      <header className="brand">
        <Link className="logo chip" href="/" aria-label="Pixel Lanka, whole map"
          onClick={(e) => { e.preventDefault(); viewer.current?.viewport.goHome(); }}>
          <span className="logo-en">Pixel Lanka</span>
          <span className="logo-local"><span lang="si">ශ්‍රී ලංකා</span> · <span lang="ta">இலங்கை</span></span>
        </Link>
      </header>
      <div className="topright">
        <Search
          placesUrls={world ? Object.values(world.maps).map((m) => `${TILES}/${m.places}`) : []}
          extra={landmarks.flatMap((l) => [l.name, ...l.aliases].map((n): Place => [n, 'landmark', l.lon, l.lat, 2]))}
          onPlace={(p: Place) => {
            flyTo(p[2], p[3]);
            setSelected(landmarks.find((l) => l.lon === p[2] && l.lat === p[3]) ?? null);
          }}
          onLatLon={onLatLon}
        />
        <button className="chip share" onClick={share}>Share this view</button>
      </div>
      {selected && <LandmarkCard tiles={TILES} landmark={selected} onClose={() => setSelected(null)} />}
      {landmarks.length > 0 && (
        <LandmarkStrip tiles={TILES} landmarks={landmarks} selected={selected?.id ?? null}
          onPick={(l) => { setSelected(l); flyTo(l.lon, l.lat); }} />
      )}
      <div className="credit chip">
        © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · <a href="https://overturemaps.org">Overture Maps</a> · Google Open Buildings · Microsoft · ESA WorldCover
      </div>
      {toast && <div className="toast chip" role="status">{toast}</div>}
    </>
  );
}

// Zoom (in base-image pixels per screen pixel) that shows the most detailed map at a point crisply.
function detailRatio(w: World, base: MapLayer, lon: number, lat: number) {
  const px = Math.max(...Object.values(w.maps).filter((m) => inBounds(m, lon, lat)).map((m) => m.px), base.px);
  return (DETAIL_PIXELS * px) / base.px;
}
