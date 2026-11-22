import * as THREE from 'three';
import { MapControls } from 'three/addons/controls/MapControls.js';
import { PointerLockControls } from 'three/addons/controls/PointerLockControls.js';
import { buildCity, Collider } from './city.js';
import { buildLotus } from './lotus.js';

const AREA = new URLSearchParams(location.search).get('area') || 'colombo-fort';
const EYE = 1.7;
const PIXEL_SIZES = [1, 2, 3, 4];
const $ = (id) => document.getElementById(id);

const [data, groundTex] = await Promise.all([
  fetch(`data/${AREA}/scene.json`).then((r) => r.json()),
  new THREE.TextureLoader().loadAsync(`data/${AREA}/ground.png`),
]);

const renderer = new THREE.WebGLRenderer({ antialias: false, logarithmicDepthBuffer: true });
renderer.shadowMap.enabled = true;
document.body.prepend(renderer.domElement);

const scene = new THREE.Scene();
const SKY = new THREE.Color('#bcd9ec');
scene.background = SKY;
scene.fog = new THREE.Fog(SKY, 2500, 9000);
const camera = new THREE.PerspectiveCamera(45, 1, 0.3, 30000);

scene.add(new THREE.HemisphereLight('#dfeeff', '#8a7f6a', 1.6));
const sun = new THREE.DirectionalLight('#fff2da', 2.6);
sun.castShadow = true;
sun.shadow.mapSize.set(4096, 4096);
scene.add(sun, sun.target);
const SUN_DIR = new THREE.Vector3(0.75, 1.0, -0.35).normalize();

scene.add(buildCity(data, groundTex));
const collider = new Collider(data);
const lotus = buildLotus(data.featured.find((f) => f.kind === 'lotus'));
scene.add(lotus.group);

const controls = new MapControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI * 0.47;
controls.minDistance = 15;
controls.maxDistance = 6000;
controls.target.set(0, 0, 0);
camera.position.set(-900, 1000, 900);

const look = new PointerLockControls(camera, document.body);
let mode = 'fly';
let level = 'ground';
let pixel = 3;
const player = { x: 0, z: 0 };
const keys = new Set();

function resize() {
  renderer.setPixelRatio(1 / pixel);
  renderer.setSize(innerWidth, innerHeight);
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
}
addEventListener('resize', resize);
resize();

function blocked(x, z) {
  if (level === 'deck' || lotus.contains(x, z)) return lotus.blocked(x, z, level);
  return collider.hit(x, z);
}

function findFree(x, z) {
  for (let r = 0; r < 80; r += 1.5) {
    for (let a = 0; a < Math.PI * 2; a += 0.4) {
      const px = x + Math.cos(a) * r, pz = z + Math.sin(a) * r;
      if (!blocked(px, pz)) return { x: px, z: pz };
      if (r === 0) break;
    }
  }
  return { x, z };
}

function floorY() {
  return level === 'deck' ? lotus.deckY : 0;
}

function placePlayer(x, z, lookAt) {
  player.x = x;
  player.z = z;
  camera.position.set(x, floorY() + EYE, z);
  if (lookAt) camera.lookAt(lookAt.x, floorY() + EYE, lookAt.z);
}

function enterWalk(x, z, lookAt) {
  const yaw = new THREE.Vector3().subVectors(controls.target, camera.position).setY(0).normalize();
  mode = 'walk';
  level = 'ground';
  controls.enabled = false;
  const spot = findFree(x, z);
  placePlayer(spot.x, spot.z, lookAt || { x: spot.x + yaw.x, z: spot.z + yaw.z });
  scene.fog.near = 400;
  scene.fog.far = 2600;
  pixel = 2;
  resize();
  $('help-fly').hidden = true;
  $('help-walk').hidden = false;
  $('cross').hidden = false;
  look.lock();
}

function enterFly() {
  mode = 'fly';
  look.unlock();
  controls.enabled = true;
  controls.target.set(player.x, 0, player.z);
  camera.position.set(player.x - 140, 170, player.z + 140);
  level = 'ground';
  scene.fog.near = 2500;
  scene.fog.far = 9000;
  pixel = 3;
  resize();
  $('help-fly').hidden = false;
  $('help-walk').hidden = true;
  $('cross').hidden = true;
  $('prompt').hidden = true;
}

let current = null;
function updatePrompt() {
  current = mode === 'walk' ? lotus.prompt(player.x, player.z, level) : null;
  $('prompt').hidden = !current;
  if (current) $('prompt').textContent = current.text;
}

function act() {
  if (!current?.ride) return;
  const r = lotus.ride(current.ride);
  level = r.level;
  placePlayer(r.x, r.z, r.lookAt);
  scene.fog.near = level === 'deck' ? 1500 : 400;
  scene.fog.far = level === 'deck' ? 7000 : 2600;
}

addEventListener('keydown', (e) => {
  keys.add(e.code);
  if (e.code === 'KeyF') mode === 'fly' ? enterWalk(controls.target.x, controls.target.z) : enterFly();
  if (e.code === 'KeyP') { pixel = PIXEL_SIZES[(PIXEL_SIZES.indexOf(pixel) + 1) % PIXEL_SIZES.length]; resize(); }
  if (e.code === 'KeyE' && mode === 'walk') act();
});
addEventListener('keyup', (e) => keys.delete(e.code));
renderer.domElement.addEventListener('click', () => { if (mode === 'walk' && !look.isLocked) look.lock(); });
look.addEventListener('lock', () => { $('paused').hidden = true; });
look.addEventListener('unlock', () => { $('paused').hidden = mode !== 'walk'; });
$('walk').onclick = () => enterWalk(controls.target.x, controls.target.z);
$('lotus').onclick = () => enterWalk(lotus.door.x, lotus.door.z, lotus.center);

const fwd = new THREE.Vector3();
function walkStep(dt) {
  if (!look.isLocked) return;
  camera.getWorldDirection(fwd);
  fwd.y = 0;
  fwd.normalize();
  let mx = 0, mz = 0;
  if (keys.has('KeyW')) { mx += fwd.x; mz += fwd.z; }
  if (keys.has('KeyS')) { mx -= fwd.x; mz -= fwd.z; }
  if (keys.has('KeyD')) { mx -= fwd.z; mz += fwd.x; }
  if (keys.has('KeyA')) { mx += fwd.z; mz -= fwd.x; }
  const len = Math.hypot(mx, mz);
  if (!len) return;
  const step = ((keys.has('ShiftLeft') || keys.has('ShiftRight')) ? 14 : 4.5) * dt / len;
  if (!blocked(player.x + mx * step, player.z)) player.x += mx * step;
  if (!blocked(player.x, player.z + mz * step)) player.z += mz * step;
  camera.position.set(player.x, floorY() + EYE, player.z);
}

const focus = new THREE.Vector3();
function updateSun() {
  let size;
  if (mode === 'walk') {
    focus.set(player.x, 0, player.z);
    size = level === 'deck' ? 700 : 90;
  } else {
    focus.copy(controls.target);
    size = THREE.MathUtils.clamp(camera.position.distanceTo(controls.target) * 0.8, 60, 1600);
  }
  sun.target.position.copy(focus);
  sun.position.copy(focus).addScaledVector(SUN_DIR, 2000);
  const c = sun.shadow.camera;
  c.left = c.bottom = -size;
  c.right = c.top = size;
  c.near = 10;
  c.far = 4500;
  c.updateProjectionMatrix();
  sun.shadow.normalBias = (size / 4096) * 2;
  sun.shadow.bias = -0.0002;
}

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.05);
  if (mode === 'fly') controls.update();
  else walkStep(dt);
  updateSun();
  updatePrompt();
  renderer.render(scene, camera);
  $('loading').hidden = true;
});

window.pixelLanka = { camera, controls, enterWalk, enterFly, lotus, act, player, get mode() { return mode; }, get level() { return level; } };
