import * as THREE from 'three';
import { buildChunk, Collider } from './city.js';

const MAX_INFLIGHT = 4;

function dispose(group) {
  group.traverse((o) => {
    o.geometry?.dispose();
    if (o.material) {
      o.material.map?.dispose();
      o.material.dispose();
    }
  });
}

export class ChunkManager {
  constructor(scene, base, manifest) {
    this.scene = scene;
    this.base = base;
    this.size = manifest.chunk;
    [this.x0, this.y0] = manifest.bounds;
    this.available = manifest.chunks.map(([i, j]) => ({
      key: `${i}_${j}`,
      x: this.x0 + (i + 0.5) * this.size,
      z: -(this.y0 + (j + 0.5) * this.size),
    }));
    this.live = new Map();
    this.inflight = 0;
    this.loader = new THREE.TextureLoader();
  }

  update(fx, fz, radius) {
    const wanted = this.available
      .map((c) => [Math.hypot(c.x - fx, c.z - fz), c])
      .filter(([d]) => d < radius)
      .sort((a, b) => a[0] - b[0]);
    for (const [, c] of wanted) {
      if (this.inflight >= MAX_INFLIGHT) break;
      if (!this.live.has(c.key)) this.load(c.key);
    }
    const keep = radius * 1.4 + this.size;
    for (const c of this.available) {
      const e = this.live.get(c.key);
      if (e?.group && Math.hypot(c.x - fx, c.z - fz) > keep) this.unload(c.key);
    }
  }

  async load(key) {
    const entry = {};
    this.live.set(key, entry);
    this.inflight++;
    try {
      const [data, tex] = await Promise.all([
        fetch(`${this.base}/chunks/${key}.json`).then((r) => r.json()),
        this.loader.loadAsync(`${this.base}/chunks/${key}.png`),
      ]);
      if (this.live.get(key) !== entry) { tex.dispose(); return; }
      entry.group = buildChunk(data, tex);
      entry.collider = new Collider(data.buildings);
      this.scene.add(entry.group);
    } catch (err) {
      console.error(`chunk ${key}`, err);
      this.live.delete(key);
    } finally {
      this.inflight--;
    }
  }

  unload(key) {
    const e = this.live.get(key);
    this.live.delete(key);
    if (e?.group) {
      this.scene.remove(e.group);
      dispose(e.group);
    }
  }

  hit(x, z) {
    const ci = Math.floor((x - this.x0) / this.size), cj = Math.floor((-z - this.y0) / this.size);
    for (let di = -1; di <= 1; di++)
      for (let dj = -1; dj <= 1; dj++)
        if (this.live.get(`${ci + di}_${cj + dj}`)?.collider?.hit(x, z)) return true;
    return false;
  }

  get stats() {
    let ready = 0;
    for (const e of this.live.values()) if (e.group) ready++;
    return { ready, loading: this.inflight, total: this.available.length };
  }
}
