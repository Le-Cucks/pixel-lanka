'use client';

/* eslint-disable @next/next/no-img-element -- thumbnails are pre-rendered pixel art served next to the tiles */

export type Landmark = {
  id: string;
  name: string;
  si: string;
  ta: string;
  blurb: string;
  aliases: string[];
  lon: number;
  lat: number;
  thumb: string;
};

type StripProps = { tiles: string; landmarks: Landmark[]; selected: string | null; onPick: (l: Landmark) => void };

export function LandmarkStrip({ tiles, landmarks, selected, onPick }: StripProps) {
  return (
    <nav className="landmarks" aria-label="Landmarks">
      <ul>
        {landmarks.map((l) => (
          <li key={l.id}>
            <button className={`card chip${l.id === selected ? ' selected' : ''}`} onClick={() => onPick(l)}
              aria-pressed={l.id === selected}>
              <img src={`${tiles}/${l.thumb}`} alt="" width={150} height={95} loading="lazy" />
              <span className="card-name">{l.name}</span>
              <span className="card-local" lang="si">{l.si}</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

type CardProps = { tiles: string; landmark: Landmark; onClose: () => void };

export function LandmarkCard({ tiles, landmark: l, onClose }: CardProps) {
  return (
    <aside className="detail chip" aria-label={l.name}>
      <button className="close" onClick={onClose} aria-label="Close">×</button>
      <img src={`${tiles}/${l.thumb}`} alt={`Pixel-art view of ${l.name}`} width={300} height={190} />
      <h2>{l.name}</h2>
      <p className="local"><span lang="si">{l.si}</span> · <span lang="ta">{l.ta}</span></p>
      <p>{l.blurb}</p>
    </aside>
  );
}
