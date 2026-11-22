'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { parseLatLon } from '@/lib/geo';

export type Place = [name: string, category: string, lon: number, lat: number, score: number];

type Props = {
  placesUrls: string[];
  onPlace: (p: Place) => void;
  onLatLon: (lat: number, lon: number) => void;
};

export default function Search({ placesUrls, onPlace, onLatLon }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [places, setPlaces] = useState<Place[] | null>(null);
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement !== input.current) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    addEventListener('keydown', onKey);
    return () => removeEventListener('keydown', onKey);
  }, []);

  const load = () => {
    if (places) return;
    Promise.all(placesUrls.map((u) => fetch(u).then((r) => r.json() as Promise<Place[]>))).then((lists) => {
      const seen = new Set<string>();
      const merged: Place[] = [];
      for (const p of lists.flat().sort((a, b) => b[4] - a[4])) {
        const key = `${p[0].toLowerCase()}|${p[2].toFixed(3)}|${p[3].toFixed(3)}`;
        if (!seen.has(key)) { seen.add(key); merged.push(p); }
      }
      setPlaces(merged);
    });
  };

  const latLon = parseLatLon(q);
  const results = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!places || s.length < 2 || latLon) return [];
    const starts: Place[] = [], contains: Place[] = [];
    // places.json is sorted by score, so the first matches are the most reliable ones
    for (const p of places) {
      const name = p[0].toLowerCase();
      if (name.startsWith(s) || name.includes(` ${s}`)) starts.push(p);
      else if (contains.length < 8 && name.includes(s)) contains.push(p);
      if (starts.length >= 8) break;
    }
    return [...starts, ...contains].slice(0, 8);
  }, [places, q, latLon]);

  const pick = (p: Place) => {
    onPlace(p);
    setQ(p[0]);
    setOpen(false);
    input.current?.blur();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === 'Escape') { setOpen(false); input.current?.blur(); }
    else if (e.key === 'Enter') {
      if (latLon) { onLatLon(latLon.lat, latLon.lon); input.current?.blur(); }
      else if (results[active]) pick(results[active]);
    }
  };

  return (
    <div className="search-wrap">
      <form className="search chip" role="search" onSubmit={(e) => e.preventDefault()}>
        <svg className="icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        <input
          ref={input}
          type="search"
          placeholder="A place, a street or lat, long"
          aria-label="Search the map"
          value={q}
          onFocus={() => { load(); setOpen(true); }}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onChange={(e) => { setQ(e.target.value); setActive(0); setOpen(true); }}
          onKeyDown={onKeyDown}
        />
        <kbd aria-hidden="true">/</kbd>
      </form>
      {open && (results.length > 0 || latLon || (q.length >= 2 && places)) && (
        <ul className="results chip" role="listbox">
          {latLon && (
            <li role="option" aria-selected className="active" onMouseDown={() => onLatLon(latLon.lat, latLon.lon)}>
              Go to {latLon.lat}, {latLon.lon}
            </li>
          )}
          {results.map((p, i) => (
            <li key={`${p[0]}-${p[2]}-${p[3]}`} role="option" aria-selected={i === active}
              className={i === active ? 'active' : ''} onMouseEnter={() => setActive(i)} onMouseDown={() => pick(p)}>
              <span>{p[0]}</span>
              {p[1] && <small>{p[1]}</small>}
            </li>
          ))}
          {!latLon && results.length === 0 && <li className="empty">No places match “{q}”</li>}
        </ul>
      )}
    </div>
  );
}
