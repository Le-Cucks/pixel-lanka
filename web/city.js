import * as THREE from 'three';

// Interior mapping: each window cell raycasts into a fake room (back wall, side walls,
// floor, ceiling and one piece of furniture), so every building looks lived-in without geometry.
const INTERIOR_PARS = /* glsl */ `
varying vec3 vWPos;
varying vec3 vWN;
varying vec3 vInfo;

float hash3(vec3 p) {
  p = fract(p * 0.3183099 + 0.1);
  p *= 17.0;
  return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

vec3 buildingSurface(vec3 wall, out vec3 glow) {
  glow = vec3(0.0);
  vec3 n = normalize(vWN);
  float seed = vInfo.x, tall = vInfo.y, top = vInfo.z;
  if (abs(n.y) > 0.5 || top < 5.0) return wall;

  vec2 nh = normalize(n.xz);
  vec2 t = vec2(-nh.y, nh.x);
  float W = tall > 0.5 ? 3.0 : 2.6;
  const float H = 3.2;
  float u = dot(vWPos.xz, t) + seed * 37.0;
  float cu = floor(u / W), cv = floor(vWPos.y / H);
  float pu = u - cu * W, pv = vWPos.y - cv * H;
  if ((cv + 1.0) * H > top - 0.3) return wall;

  bool shop = tall < 0.5 && cv < 0.5 && fract(seed * 7.13) > 0.4;
  vec2 lo = tall > 0.5 ? vec2(0.1, 0.3) : vec2(0.7, 1.0);
  vec2 hi = tall > 0.5 ? vec2(W - 0.1, H - 0.15) : vec2(W - 0.7, 2.4);
  if (shop) { lo = vec2(0.15, 0.1); hi = vec2(W - 0.15, 2.7); }
  if (pu < lo.x - 0.12 || pu > hi.x + 0.12 || pv < lo.y - 0.12 || pv > hi.y + 0.12) return wall;
  if (pu < lo.x || pu > hi.x || pv < lo.y || pv > hi.y) return wall * 0.6;

  vec3 rd = normalize(vWPos - cameraPosition);
  float ru = dot(rd.xz, t), rv = rd.y, rz = max(-dot(rd.xz, nh), 1e-3);
  float D = tall > 0.5 ? 7.0 : 4.5;
  float tb = D / rz;
  float ts = ru > 1e-4 ? (W - pu) / ru : (ru < -1e-4 ? -pu / ru : 1e9);
  float tf = rv > 1e-4 ? (H - pv) / rv : (rv < -1e-4 ? -pv / rv : 1e9);
  float tm = min(tb, min(ts, tf));

  float rs = hash3(vec3(cu, cv, seed * 131.0));
  vec3 tint = mix(vec3(0.96, 0.89, 0.76), vec3(0.78, 0.86, 0.95), step(0.5, fract(rs * 3.7)));
  vec3 c;
  if (tm == tb) {
    vec2 hp = vec2(pu + ru * tm, pv + rv * tm);
    c = tint * 0.9;
    if (abs(hp.x - W * 0.5) < 0.4 && hp.y > 1.2 && hp.y < 1.9)
      c = mix(vec3(0.3, 0.5, 0.4), vec3(0.7, 0.4, 0.3), fract(rs * 11.0));
  } else if (tm == ts) {
    c = tint * 0.72;
  } else if (rv < 0.0) {
    c = fract(rs * 5.3) > 0.5 ? vec3(0.52, 0.36, 0.24) : vec3(0.62, 0.62, 0.64);
  } else {
    c = vec3(0.95, 0.95, 0.92);
  }

  vec3 ro = vec3(pu, pv, 0.0), rdl = vec3(ru, rv, rz);
  vec3 bmin = vec3(W * 0.25, 0.0, D * 0.45), bmax = vec3(W * 0.75, shop ? 1.1 : 0.8, D * 0.8);
  vec3 t0 = (bmin - ro) / rdl, t1 = (bmax - ro) / rdl;
  vec3 tsm = min(t0, t1), tbg = max(t0, t1);
  float tn = max(max(tsm.x, tsm.y), tsm.z), tx = min(min(tbg.x, tbg.y), tbg.z);
  if (tn < tx && tn > 0.0 && tn < tm) {
    c = mix(vec3(0.45, 0.3, 0.22), vec3(0.3, 0.4, 0.6), fract(rs * 17.0));
    tm = tn;
  }

  c *= 1.0 - 0.4 * clamp(tm * rz / D, 0.0, 1.0);
  if (rs < 0.12) c = vec3(0.86, 0.8, 0.62);
  else if (rs > 0.88) c *= 0.3;
  float fres = pow(1.0 - clamp(rz, 0.0, 1.0), 3.0);
  c = mix(c, vec3(0.72, 0.84, 0.93), clamp(0.12 + fres * (tall > 0.5 ? 0.8 : 0.5), 0.0, 0.9));
  glow = c * 0.45;
  return c * 0.55;
}
`;

function wallMaterial() {
  const m = new THREE.MeshLambertMaterial({ vertexColors: true });
  m.onBeforeCompile = (shader) => {
    shader.vertexShader = 'attribute vec3 aInfo;\nvarying vec3 vWPos;\nvarying vec3 vWN;\nvarying vec3 vInfo;\n' +
      shader.vertexShader.replace('#include <begin_vertex>', `#include <begin_vertex>
        vWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;
        vWN = normalize(mat3(modelMatrix) * objectNormal);
        vInfo = aInfo;`);
    shader.fragmentShader = INTERIOR_PARS + shader.fragmentShader.replace('#include <color_fragment>', `
        vec3 glowC;
        diffuseColor.rgb = buildingSurface(vColor.rgb, glowC);
        totalEmissiveRadiance += glowC;`);
  };
  return m;
}

function buildingMeshes(buildings) {
  const wp = [], wn = [], wc = [], wi = [];
  const rp = [], rc = [];
  const col = new THREE.Color();
  for (const b of buildings) {
    const p = b.p, n = p.length / 2, h = b.h;
    col.setStyle(b.w);
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      const e1 = p[2 * i], n1 = p[2 * i + 1], e2 = p[2 * j], n2 = p[2 * j + 1];
      const dx = e2 - e1, dy = n2 - n1, L = Math.hypot(dx, dy);
      if (L < 1e-3) continue;
      const nx = dy / L, nz = dx / L;
      const x1 = e1, z1 = -n1, x2 = e2, z2 = -n2;
      wp.push(x1, 0, z1, x2, 0, z2, x2, h, z2, x1, 0, z1, x2, h, z2, x1, h, z1);
      for (let k = 0; k < 6; k++) {
        wn.push(nx, 0, nz);
        wc.push(col.r, col.g, col.b);
        wi.push(b.s, b.t, h);
      }
    }
    col.setStyle(b.r);
    const contour = [];
    for (let i = 0; i < n; i++) contour.push(new THREE.Vector2(p[2 * i], -p[2 * i + 1]));
    for (const [a, c, d] of THREE.ShapeUtils.triangulateShape(contour, [])) {
      const A = contour[a], B = contour[c], Cc = contour[d];
      const up = (B.y - A.y) * (Cc.x - A.x) - (B.x - A.x) * (Cc.y - A.y) > 0;
      const tri = up ? [A, B, Cc] : [A, Cc, B];
      for (const v of tri) { rp.push(v.x, h, v.y); rc.push(col.r, col.g, col.b); }
    }
  }

  const walls = new THREE.BufferGeometry();
  walls.setAttribute('position', new THREE.Float32BufferAttribute(wp, 3));
  walls.setAttribute('normal', new THREE.Float32BufferAttribute(wn, 3));
  walls.setAttribute('color', new THREE.Float32BufferAttribute(wc, 3));
  walls.setAttribute('aInfo', new THREE.Float32BufferAttribute(wi, 3));
  const roofs = new THREE.BufferGeometry();
  roofs.setAttribute('position', new THREE.Float32BufferAttribute(rp, 3));
  roofs.setAttribute('color', new THREE.Float32BufferAttribute(rc, 3));
  roofs.computeVertexNormals();

  const wallMesh = new THREE.Mesh(walls, wallMaterial());
  const roofMesh = new THREE.Mesh(roofs, new THREE.MeshLambertMaterial({ vertexColors: true }));
  for (const m of [wallMesh, roofMesh]) { m.castShadow = m.receiveShadow = true; }
  return [wallMesh, roofMesh];
}

function treeMeshes(trees) {
  const n = trees.length / 3;
  const canopy = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1, 0),
    new THREE.MeshLambertMaterial({ flatShading: true }), n);
  const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.22, 0.3, 1, 5),
    new THREE.MeshLambertMaterial({ color: '#5a4030' }), n);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), c = new THREE.Color();
  const greens = ['#2f5e2e', '#3d7334', '#44803a', '#558f3f'];
  for (let i = 0; i < n; i++) {
    const x = trees[3 * i], z = -trees[3 * i + 1], r = trees[3 * i + 2];
    q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), i * 2.39);
    m.compose(new THREE.Vector3(x, 2.2 + r * 0.8, z), q, new THREE.Vector3(r, r * 0.85, r));
    canopy.setMatrixAt(i, m);
    canopy.setColorAt(i, c.setStyle(greens[i % greens.length]));
    m.compose(new THREE.Vector3(x, 1.4, z), q, new THREE.Vector3(1, 2.8, 1));
    trunk.setMatrixAt(i, m);
  }
  for (const t of [canopy, trunk]) { t.castShadow = t.receiveShadow = true; }
  return [canopy, trunk];
}

export function groundPlane(bounds, tex, y = 0) {
  const [x0, y0, x1, y1] = bounds;
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.magFilter = THREE.NearestFilter;
  tex.anisotropy = 8;
  const m = new THREE.Mesh(new THREE.PlaneGeometry(x1 - x0, y1 - y0), new THREE.MeshLambertMaterial({ map: tex }));
  m.rotation.x = -Math.PI / 2;
  m.position.set((x0 + x1) / 2, y, -(y0 + y1) / 2);
  m.receiveShadow = true;
  return m;
}

export function buildChunk(data, groundTex) {
  const group = new THREE.Group();
  group.add(groundPlane(data.bounds, groundTex));
  if (data.buildings.length) group.add(...buildingMeshes(data.buildings));
  if (data.trees.length) group.add(...treeMeshes(data.trees));
  return group;
}

function inside(p, e, n) {
  let hit = false;
  for (let i = 0, j = p.length - 2; i < p.length; j = i, i += 2) {
    const xi = p[i], yi = p[i + 1], xj = p[j], yj = p[j + 1];
    if ((yi > n) !== (yj > n) && e < ((xj - xi) * (n - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}

export class Collider {
  constructor(buildings, cell = 25) {
    this.cell = cell;
    this.grid = new Map();
    this.boxes = buildings.map((b, i) => {
      let a = Infinity, c = Infinity, d = -Infinity, e = -Infinity;
      for (let k = 0; k < b.p.length; k += 2) {
        a = Math.min(a, b.p[k]); c = Math.min(c, b.p[k + 1]);
        d = Math.max(d, b.p[k]); e = Math.max(e, b.p[k + 1]);
      }
      for (let gx = Math.floor(a / cell); gx <= Math.floor(d / cell); gx++)
        for (let gy = Math.floor(c / cell); gy <= Math.floor(e / cell); gy++) {
          const key = gx + ',' + gy;
          if (!this.grid.has(key)) this.grid.set(key, []);
          this.grid.get(key).push(i);
        }
      return [a, c, d, e, b.p];
    });
  }

  hit(x, z, r = 0.3) {
    const e = x, n = -z;
    for (const [pe, pn] of [[e, n], [e + r, n], [e - r, n], [e, n + r], [e, n - r]]) {
      const list = this.grid.get(Math.floor(pe / this.cell) + ',' + Math.floor(pn / this.cell));
      if (!list) continue;
      for (const i of list) {
        const [a, c, d, f, p] = this.boxes[i];
        if (pe >= a && pe <= d && pn >= c && pn <= f && inside(p, pe, pn)) return true;
      }
    }
    return false;
  }
}
