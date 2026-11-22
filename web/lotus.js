import * as THREE from 'three';

const SHAFT_R = 7;
const DECK_Y = 255;
const DECK_R = 18.5;
const DECK_H = 4.5;
const LOBBY_H = 8;

function lambert(color, extra = {}) {
  return new THREE.MeshLambertMaterial({ color, ...extra });
}

function canvasTexture(w, h, draw) {
  const cv = document.createElement('canvas');
  cv.width = w; cv.height = h;
  draw(cv.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(cv);
  t.colorSpace = THREE.SRGBColorSpace;
  t.magFilter = THREE.NearestFilter;
  return t;
}

function sign(text, w, h, bg = '#2a1f33', fg = '#f5d36b') {
  const tex = canvasTexture(256, 32, (g, W, H) => {
    g.fillStyle = bg; g.fillRect(0, 0, W, H);
    g.fillStyle = fg; g.font = 'bold 16px monospace'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(text, W / 2, H / 2 + 1);
  });
  return new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: tex }));
}

function angDiff(a, b) {
  const d = Math.abs(a - b) % (Math.PI * 2);
  return d > Math.PI ? Math.PI * 2 - d : d;
}

export function buildLotus(f) {
  const cx = f.x, cz = -f.y;
  const R = Math.min(Math.max(f.r * 0.75, 24), 34);
  const thd = Math.atan2(1, -1);
  const dir = new THREE.Vector2(Math.cos(thd), Math.sin(thd));
  const gap = 7 / R;
  const theta0 = Math.atan2(dir.x, dir.y);
  const g = new THREE.Group();
  g.position.set(cx, 0, cz);

  const podiumWall = new THREE.Mesh(
    new THREE.CylinderGeometry(R, R, LOBBY_H, 64, 1, true, theta0 + gap / 2, Math.PI * 2 - gap),
    lambert('#ece4d3', { side: THREE.DoubleSide }));
  podiumWall.position.y = LOBBY_H / 2;
  const lintel = new THREE.Mesh(
    new THREE.CylinderGeometry(R, R, 2, 16, 1, true, theta0 - gap / 2, gap),
    lambert('#ece4d3', { side: THREE.DoubleSide }));
  lintel.position.y = LOBBY_H - 1;
  const podiumRoof = new THREE.Mesh(new THREE.RingGeometry(SHAFT_R, R + 0.5, 64), lambert('#cfc6b4', { side: THREE.DoubleSide }));
  podiumRoof.rotation.x = -Math.PI / 2;
  podiumRoof.position.y = LOBBY_H;
  const tiles = canvasTexture(16, 16, (c) => {
    c.fillStyle = '#e8dcc2'; c.fillRect(0, 0, 16, 16);
    c.fillStyle = '#b4553a'; c.fillRect(0, 0, 8, 8); c.fillRect(8, 8, 8, 8);
  });
  tiles.wrapS = tiles.wrapT = THREE.RepeatWrapping;
  tiles.repeat.set(R / 2, R / 2);
  const floor = new THREE.Mesh(new THREE.CircleGeometry(R, 64), lambert('#ffffff', { map: tiles }));
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = 0.04;

  const petals = new THREE.Group();
  for (let i = 0; i < 16; i++) {
    const a = (i / 16) * Math.PI * 2;
    const p = new THREE.Mesh(new THREE.SphereGeometry(1, 8, 6), lambert(i % 2 ? '#b65a9c' : '#9c4688', { flatShading: true }));
    p.scale.set(2.2, 4.5, 6);
    p.position.set(Math.cos(a) * (R + 1), LOBBY_H + 2.2, Math.sin(a) * (R + 1));
    p.rotation.y = -a;
    p.rotation.z = 0.5;
    petals.add(p);
  }

  const pillars = [];
  for (let i = 0; i < 8; i++) {
    const a = thd + Math.PI / 8 + (i / 8) * Math.PI * 2;
    const r = R * 0.72;
    const pos = new THREE.Vector2(Math.cos(a) * r, Math.sin(a) * r);
    if (angDiff(a, thd) < 0.35) continue;
    const m = new THREE.Mesh(new THREE.CylinderGeometry(0.7, 0.7, LOBBY_H, 10), lambert('#d9cdb5'));
    m.position.set(pos.x, LOBBY_H / 2, pos.y);
    pillars.push(pos);
    g.add(m);
  }

  const ca = thd + 0.75, cr = R * 0.5;
  const counterPos = new THREE.Vector2(Math.cos(ca) * cr, Math.sin(ca) * cr);
  const counter = new THREE.Mesh(new THREE.BoxGeometry(6, 1.1, 1.4), lambert('#7a4a2c'));
  counter.position.set(counterPos.x, 0.55, counterPos.y);
  counter.rotation.y = Math.atan2(counterPos.x, counterPos.y);
  const ticket = sign('TICKETS', 3, 0.6);
  ticket.position.set(counterPos.x * 1.02, 2.4, counterPos.y * 1.02);
  ticket.rotation.y = Math.atan2(-counterPos.x, -counterPos.y);

  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(SHAFT_R - 0.6, SHAFT_R, 228, 32), lambert('#9cc7a4'));
  shaft.position.y = 114;
  const bud = new THREE.Mesh(new THREE.LatheGeometry([
    [SHAFT_R - 0.6, 226], [14, 236], [21, 248], [23, 258], [22, 266], [17, 277], [9, 287], [3, 293], [0.5, 297],
  ].map(([r, y]) => new THREE.Vector2(r, y)), 32), lambert('#a8458e', { flatShading: true }));
  const budPetals = new THREE.Group();
  for (let i = 0; i < 10; i++) {
    const a = (i / 10) * Math.PI * 2;
    const p = new THREE.Mesh(new THREE.SphereGeometry(1, 8, 6), lambert('#c86aa8', { flatShading: true }));
    p.scale.set(3.5, 14, 5);
    p.position.set(Math.cos(a) * 17, 240, Math.sin(a) * 17);
    p.rotation.y = -a;
    p.rotation.z = 0.45;
    budPetals.add(p);
  }
  const antenna = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 1.6, 55, 8), lambert('#dcdcdc'));
  antenna.position.y = 297 + 27.5;

  const deckFloor = new THREE.Mesh(new THREE.RingGeometry(SHAFT_R - 0.6, DECK_R + 0.2, 64), lambert('#3a3040', { side: THREE.DoubleSide }));
  deckFloor.rotation.x = -Math.PI / 2;
  deckFloor.position.y = DECK_Y;
  const deckCeil = deckFloor.clone();
  deckCeil.material = lambert('#6d4a7a', { side: THREE.DoubleSide });
  deckCeil.position.y = DECK_Y + DECK_H;
  const glass = new THREE.Mesh(new THREE.CylinderGeometry(DECK_R, DECK_R, DECK_H, 64, 1, true),
    new THREE.MeshBasicMaterial({ color: '#9fd3ff', transparent: true, opacity: 0.14, side: THREE.DoubleSide, depthWrite: false }));
  glass.position.y = DECK_Y + DECK_H / 2;
  const rail = new THREE.Mesh(new THREE.TorusGeometry(DECK_R - 0.7, 0.06, 4, 64), lambert('#e8e8e8'));
  rail.rotation.x = Math.PI / 2;
  rail.position.y = DECK_Y + 1.05;

  const lift = (y, label) => {
    const door = new THREE.Mesh(new THREE.BoxGeometry(2.6, 3.2, 0.3), lambert('#b8bcc2'));
    door.position.set(dir.x * SHAFT_R, y + 1.6, dir.y * SHAFT_R);
    door.rotation.y = theta0;
    const seam = new THREE.Mesh(new THREE.BoxGeometry(0.06, 3.2, 0.34), lambert('#555a60'));
    seam.position.copy(door.position);
    seam.rotation.y = theta0;
    const s = sign(label, 4.2, 0.6);
    s.position.set(dir.x * (SHAFT_R + 0.2), y + 3.8, dir.y * (SHAFT_R + 0.2));
    s.rotation.y = theta0;
    g.add(door, seam, s);
  };
  lift(0, 'OBSERVATION DECK ▲');
  lift(DECK_Y, 'LOBBY ▼');

  const entrance = sign('LOTUS TOWER', 7, 1.1);
  entrance.position.set(dir.x * (R + 0.15), LOBBY_H - 1, dir.y * (R + 0.15));
  entrance.rotation.y = theta0;

  const lobbyLight = new THREE.PointLight('#ffe2b0', 60, R * 1.6, 1.6);
  lobbyLight.position.y = LOBBY_H - 1.5;
  const deckLight = new THREE.PointLight('#ffd9f0', 40, 30, 1.6);
  deckLight.position.y = DECK_Y + DECK_H - 0.8;

  g.add(podiumWall, lintel, podiumRoof, floor, petals, counter, ticket, shaft, bud, budPetals, antenna,
    deckFloor, deckCeil, glass, rail, entrance, lobbyLight, deckLight);
  g.traverse((o) => { if (o.isMesh && o.material !== glass.material) { o.castShadow = o.receiveShadow = true; } });

  const local = (x, z) => [x - cx, z - cz];
  const liftSpot = (r) => ({ x: cx + dir.x * r, z: cz + dir.y * r });

  return {
    group: g,
    deckY: DECK_Y,
    name: f.name,
    door: { x: cx + dir.x * (R + 7), z: cz + dir.y * (R + 7) },
    center: { x: cx, z: cz },

    contains(x, z) {
      const [dx, dz] = local(x, z);
      return Math.hypot(dx, dz) < R + 0.8;
    },

    blocked(x, z, level) {
      const [dx, dz] = local(x, z);
      const d = Math.hypot(dx, dz);
      if (level === 'deck') return d < SHAFT_R + 0.6 || d > DECK_R - 1.0;
      if (d < SHAFT_R + 0.5) return true;
      if (Math.abs(d - R) < 0.6 && angDiff(Math.atan2(dz, dx), thd) > gap / 2 - 0.03) return true;
      if (pillars.some((p) => Math.hypot(dx - p.x, dz - p.y) < 1.1)) return true;
      const a = Math.atan2(counterPos.x, counterPos.y);
      const ox = dx - counterPos.x, oz = dz - counterPos.y;
      const lx = ox * Math.cos(a) - oz * Math.sin(a), lz = ox * Math.sin(a) + oz * Math.cos(a);
      return Math.abs(lx) < 3.4 && Math.abs(lz) < 1.1;
    },

    prompt(x, z, level) {
      const spot = liftSpot(SHAFT_R + 1.6);
      const near = Math.hypot(x - spot.x, z - spot.z) < 2.6;
      if (level === 'deck') {
        return near ? { text: 'Press E — ride down to the lobby', ride: 'ground' }
          : { text: 'Lotus Tower observation deck · 255 m above Colombo' };
      }
      if (near) return { text: 'Press E — ride up to the observation deck (255 m)', ride: 'deck' };
      const [dx, dz] = local(x, z);
      const d = Math.hypot(dx, dz);
      if (d < R) return { text: 'Lotus Tower lobby' };
      if (d < R + 14 && angDiff(Math.atan2(dz, dx), thd) < 0.6) return { text: 'Lotus Tower · walk in through the entrance' };
      return null;
    },

    ride(to) {
      const s = liftSpot(SHAFT_R + 1.8);
      return { level: to, x: s.x, z: s.z, lookAt: liftSpot(to === 'deck' ? DECK_R : R) };
    },
  };
}
