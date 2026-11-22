'use client';

import dynamic from 'next/dynamic';

const MapViewer = dynamic(() => import('./MapViewer'), {
  ssr: false,
  loading: () => <div className="loading">Drawing Colombo…</div>,
});

export default function MapClient() {
  return <MapViewer />;
}
