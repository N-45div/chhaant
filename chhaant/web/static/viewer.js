// The 3D cell: MuJoCo body poses streamed by the server, drawn with three.js.
// The arm, turntable and bins are simulated; the photos the agent decides on are real.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const box = document.getElementById("viewer");
const note = document.getElementById("viewer-note");
let renderer, scene, camera, controls, root = null, meshes = null;
let runId = null, cursor = 0, frames = [], captions = [], fps = 12.5, playhead = 0, moving = [], bodies = new Map();
let poller = null, idlePolls = 0, lastT = 0;
let seek = Number(new URLSearchParams(location.hash.slice(1)).get("frame")) || 0; // #frame=N jumps there, for filming

const SPEED = 3; // the simulated arm moves at a careful pace; three times real time reads better
const toQuat = (q) => new THREE.Quaternion(q[1], q[2], q[3], q[0]); // MuJoCo (w, x, y, z)
const setNote = (t) => { note.textContent = t; };

function decode(b64, Type) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Type(bytes.buffer);
}

function shape(g) {
  const [sx, sy, sz] = g.size;
  let geo;
  if (g.type === "box") geo = new THREE.BoxGeometry(2 * sx, 2 * sy, 2 * sz);
  else if (g.type === "sphere") geo = new THREE.SphereGeometry(sx, 28, 18);
  else if (g.type === "ellipsoid") { geo = new THREE.SphereGeometry(1, 28, 18); geo.scale(sx, sy, sz); }
  else if (g.type === "cylinder") { geo = new THREE.CylinderGeometry(sx, sx, 2 * sy, 40); geo.rotateX(Math.PI / 2); }
  else if (g.type === "capsule") { geo = new THREE.CapsuleGeometry(sx, 2 * sy, 8, 16); geo.rotateX(Math.PI / 2); }
  else if (g.type === "plane") geo = new THREE.PlaneGeometry(2 * (sx || 1), 2 * (sy || 1));
  else if (g.type === "mesh" && meshes[String(g.mesh)]) {
    const m = meshes[String(g.mesh)];
    geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(decode(m.v, Float32Array), 3));
    geo.setIndex(new THREE.BufferAttribute(decode(m.f, Uint32Array), 1));
    geo.computeVertexNormals();
  } else return null;
  const [r, gr, b, a] = g.rgba;
  const mat = new THREE.MeshStandardMaterial({ roughness: 0.65, metalness: 0.05, transparent: a < 1, opacity: a });
  mat.color.setRGB(r, gr, b, THREE.SRGBColorSpace);
  const obj = new THREE.Mesh(geo, mat);
  obj.castShadow = g.type !== "plane";
  obj.receiveShadow = true;
  obj.position.set(...g.pos);
  obj.quaternion.copy(toQuat(g.quat));
  return obj;
}

function init() {
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  box.appendChild(renderer.domElement);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(38, 1, 0.01, 20);
  camera.up.set(0, 0, 1); // MuJoCo is z-up
  camera.position.set(0.52, -0.46, 0.42);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0.1, 0.02, 0.06);
  controls.enableDamping = true;
  controls.minDistance = 0.2;
  controls.maxDistance = 1.6;
  controls.maxPolarAngle = Math.PI * 0.48; // stay above the floor
  controls.update();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8c8a80, 1.2));
  const sun = new THREE.DirectionalLight(0xffffff, 1.7);
  sun.position.set(0.5, -0.4, 1.3);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -0.45, right: 0.45, top: 0.45, bottom: -0.45, near: 0.5, far: 2.5 });
  sun.shadow.bias = -0.0004;
  scene.add(sun);
  const bg = getComputedStyle(document.documentElement).getPropertyValue("--chip").trim() || "#f0efe9";
  scene.background = new THREE.Color(bg);
  scene.fog = new THREE.Fog(bg, 1.0, 2.0); // the floor fades out instead of ending in a hard edge
  const grid = new THREE.GridHelper(2, 40, 0x9a978c, 0xbdbab0);
  grid.rotateX(Math.PI / 2);
  grid.position.z = 0.0004;
  grid.material.transparent = true;
  grid.material.opacity = 0.35;
  scene.add(grid);
  const fit = () => {
    const w = box.clientWidth, h = box.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(fit).observe(box);
  fit();
  renderer.setAnimationLoop(tick);
}

async function load(id) {
  runId = id; cursor = 0; frames = []; captions = []; playhead = 0; idlePolls = 0;
  if (root) scene.remove(root);
  const res = await fetch(`/api/runs/${id}/sim/scene`);
  if (!res.ok) { setNote("The 3D cell runs where MuJoCo is installed (the deployed server)."); return; }
  if (!meshes) meshes = await (await fetch("/api/sim/meshes")).json();
  const sc = await res.json();
  fps = sc.fps; moving = sc.moving;
  root = new THREE.Group();
  bodies = new Map();
  sc.body_poses.forEach((p, b) => {
    const grp = new THREE.Group();
    grp.position.set(p[0], p[1], p[2]);
    grp.quaternion.copy(toQuat(p.slice(3)));
    root.add(grp);
    bodies.set(b, grp);
  });
  sc.geoms.forEach((g) => { const o = shape(g); if (o) bodies.get(g.body).add(o); });
  scene.add(root);
  setNote("waiting for the arm");
  clearInterval(poller);
  poller = setInterval(poll, 800);
  poll();
}

async function poll() {
  if (!runId) return;
  const res = await fetch(`/api/runs/${runId}/sim?after=${cursor}`);
  if (!res.ok) return;
  const d = await res.json();
  frames.push(...d.frames);
  captions.push(...d.captions);
  if (seek && frames.length > seek) { playhead = seek; seek = 0; }
  cursor = d.next;
  idlePolls = d.frames.length ? 0 : idlePolls + 1;
  if (idlePolls > 40) clearInterval(poller); // the run has been quiet for half a minute
}

function apply(i) {
  const f = frames[i];
  if (!f) return;
  moving.forEach((b, k) => {
    const o = k * 7, g = bodies.get(b);
    g.position.set(f[o], f[o + 1], f[o + 2]);
    g.quaternion.set(f[o + 4], f[o + 5], f[o + 6], f[o + 3]);
  });
}

function tick(t) {
  const dt = Math.min(0.1, (t - lastT) / 1000 || 0);
  lastT = t;
  if (frames.length) {
    const behind = (frames.length - 1 - playhead) / fps; // seconds of motion not yet shown
    playhead = Math.min(frames.length - 1, playhead + dt * fps * SPEED * (behind > 30 ? 3 : behind > 10 ? 1.5 : 1));
    apply(Math.floor(playhead));
    let cap = null;
    for (const c of captions) if (c[0] <= playhead) cap = c[1];
    setNote(cap || "waiting for the arm");
  }
  controls.update();
  renderer.render(scene, camera);
}

document.getElementById("replay").addEventListener("click", () => { playhead = 0; });
window.addEventListener("chhaant:watch", (e) => load(e.detail));
init();
if (window.chhaantRun) load(window.chhaantRun); // app.js may have picked a run before this module loaded
