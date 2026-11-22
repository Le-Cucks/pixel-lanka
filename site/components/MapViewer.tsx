'use client';

import Link from 'next/link';
import OpenSeadragon from 'openseadragon';
import { useCallback, useEffect, useRef, useState } from 'react';
import { formatAt, inBounds, parseAt, toImage, toLonLat, type Meta } from '@/lib/geo';
import Search, { type Place } from './Search';

const TILES = `${process.env.NEXT_PUBLIC_TILES_BASE ?? '/tiles'}/colombo`;
const PLACE_ZOOM = 1.5; // screen pixels per image pixel when jumping to a place

export default function MapViewer() {
  const el = useRef<HTMLDivElement>(null);
  const viewer = useRef<OpenSeadragon.Viewer | null>(null);
  const pin = useRef<HTMLDivElement | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [toast, setToast] = useState('');

  useEffect(() => {
    let v: OpenSeadragon.Viewer | undefined;
    let cancelled = false;
    fetch(`${TILES}/meta.json`)
      .then((r) => r.json())
      .then((m: Meta) => {
        if (cancelled || !el.current) return;
        setMeta(m);
        v = OpenSeadragon({
          element: el.current,
          tileSources: `${TILES}/${m.dzi}`,
          showNavigationControl: false,
          showNavigator: true,
          navigatorPosition: 'BOTTOM_RIGHT',
          navigatorSizeRatio: 0.16,
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
          const at = parseAt(new URLSearchParams(location.search).get('at'));
          if (at && inBounds(m, at.lon, at.lat)) {
            const p = toImage(m, at.lon, at.lat);
            vp.panTo(vp.imageToViewportCoordinates(p.x, p.y), true);
            vp.zoomTo(at.zoom, undefined, true);
          } else if (m.start) {
            vp.panTo(vp.imageToViewportCoordinates(m.start.x, m.start.y), true);
            vp.zoomTo(vp.imageToViewportZoom(0.5), undefined, true);
          }
        });
        v.addHandler('animation-finish', () => {
          const vp = v!.viewport;
          const c = vp.viewportToImageCoordinates(vp.getCenter(true));
          const ll = toLonLat(m, c.x, c.y);
          history.replaceState(null, '', `?at=${formatAt(ll.lat, ll.lon, vp.getZoom(true))}`);
        });
      });
    return () => {
      cancelled = true;
      v?.destroy();
      viewer.current = null;
    };
  }, []);

  const flyTo = useCallback((x: number, y: number) => {
    const v = viewer.current;
    if (!v) return;
    const vp = v.viewport;
    const point = vp.imageToViewportCoordinates(x, y);
    vp.panTo(point);
    vp.zoomTo(vp.imageToViewportZoom(PLACE_ZOOM));
    if (pin.current) v.removeOverlay(pin.current);
    const div = document.createElement('div');
    div.className = 'pin';
    pin.current = div;
    v.addOverlay({ element: div, location: point, placement: OpenSeadragon.Placement.BOTTOM });
  }, []);

  const flash = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 2200);
  };

  const onLatLon = (lat: number, lon: number) => {
    if (!meta) return;
    if (!inBounds(meta, lon, lat)) return flash('That point is outside the map (Colombo city only, for now)');
    const p = toImage(meta, lon, lat);
    flyTo(p.x, p.y);
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
      <div ref={el} className="map" role="application" aria-label="Map of Colombo. Drag to move, scroll or pinch to zoom." />
      <header className="brand">
        <Link className="logo chip" href="/" aria-label="Pixel Lanka, whole map"
          onClick={(e) => { e.preventDefault(); viewer.current?.viewport.goHome(); }}>
          <span className="logo-en">Pixel Lanka</span>
          <span className="logo-local"><span lang="si">කොළඹ</span> · <span lang="ta">கொழும்பு</span></span>
        </Link>
      </header>
      <div className="topright">
        <Search placesUrl={`${TILES}/places.json`} onPlace={(p: Place) => flyTo(p[2], p[3])} onLatLon={onLatLon} />
        <button className="chip share" onClick={share}>Share this view</button>
      </div>
      <div className="credit chip">
        © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · <a href="https://overturemaps.org">Overture Maps</a> · Google Open Buildings · Microsoft
      </div>
      {toast && <div className="toast chip" role="status">{toast}</div>}
    </>
  );
}
