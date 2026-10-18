// Plain-JS model of the spheres engine, step for step as the CSS will do it (no browser).
// node model.js [N] [seconds] key=value...   e.g. node model.js 128 8 K=10 RATE=60 IT=1 OMEGA=1
// Slots sorted by x; slot s meets s+1..s+K. Verlet state (x, previous x). One Jacobi projection per iteration.
const A = Object.fromEntries(process.argv.slice(4).map(a => a.split('=')).map(([k, v]) => [k, +v]));
const N = +(process.argv[2] || 128), SEC = +(process.argv[3] || 8);
const P = Object.assign({
  K: 10, RATE: 60, IT: 1, OMEGA: 1.0, WX: 280, WZ: 180, CEIL: 400, RMIN: 13, RMAX: 17, G: 1600,
  DAMP: 0.02, FRIC: 0.3, PFRIC: 0.1, E: 0.4, SHOCK: 0.5, PHASES: 1, SCENE: 0, AVG: 0, SEED: 1,
}, A);
let seed = P.SEED; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const h = 1 / P.RATE, g2 = P.G * h * h;
const r = [], x = [], u = [];
// scene 0: rain (random non-overlapping positions in the upper part, random velocities); 1: block in a corner
for (let i = 0; i < N; i++) {
  const ri = P.RMIN + (P.RMAX - P.RMIN) * rnd();
  let p;
  for (let t = 0; t < 500; t++) {
    p = P.SCENE == 1 ? [-P.WX + ri + (i % 8) * 2 * P.RMAX, -ri - Math.floor(i / 64) * 2 * P.RMAX, -P.WZ + ri + (Math.floor(i / 8) % 8) * 2 * P.RMAX]
      : [-P.WX + ri + rnd() * 2 * (P.WX - ri), -ri - rnd() * (P.CEIL - 2 * ri), -P.WZ + ri + rnd() * 2 * (P.WZ - ri)];
    if (P.SCENE == 1 || x.every((q, j) => Math.hypot(q[0] - p[0], q[1] - p[1], q[2] - p[2]) > ri + r[j] + 1)) break;
  }
  r.push(ri); x.push(p);
  const v = P.SCENE == 1 ? [0, 0, 0] : [(rnd() - 0.5) * 400, (rnd() - 0.5) * 200, (rnd() - 0.5) * 400];
  u.push([p[0] - v[0] * h, p[1] - v[1] * h, p[2] - v[2] * h]);
}
// sort into slots by x
let ord = [...Array(N).keys()].sort((a, b) => x[a][0] - x[b][0]);
let X = ord.map(i => x[i].slice()), U = ord.map(i => u[i].slice()), R = ord.map(i => r[i]);
let step = 0, phase = 0;
function stepOnce() {
  // predict
  const p = X.map((q, s) => [0, 1, 2].map(a => q[a] + (q[a] - U[s][a]) * (1 - P.DAMP) + (a == 1 ? g2 : 0)));
  const cnt = new Array(N).fill(0);
  for (let it = 0; it < P.IT; it++) {
    const d = p.map(() => [0, 0, 0]); cnt.fill(0);
    for (let s = 0; s < N; s++) for (let k = 1; k <= P.K && s + k < N; k++) {
      const t = s + k, dx = p[s][0] - p[t][0], dy = p[s][1] - p[t][1], dz = p[s][2] - p[t][2];
      const dist = Math.max(Math.hypot(dx, dy, dz), 1e-6), D = R[s] + R[t];
      if (dist >= D) continue;
      const c = (D - dist) / dist;
      // shock propagation: the lower sphere (larger y) gets less of the push
      const ny = dy / dist;   // >0: s is lower
      const ws = 0.5 * (1 - P.SHOCK * Math.max(0, ny)) / (1 - 0.5 * P.SHOCK * Math.abs(ny));
      const wt = 1 - ws;
      for (const [a, dd] of [[0, dx], [1, dy], [2, dz]]) { d[s][a] += ws * c * dd; d[t][a] -= wt * c * dd; }
      cnt[s]++; cnt[t]++;
    }
    for (let s = 0; s < N; s++) for (let a = 0; a < 3; a++) p[s][a] += P.OMEGA * d[s][a] / (P.AVG ? Math.max(1, cnt[s]) : 1);
  }
  // walls with restitution (mirror the penetration) and floor friction (damps the tangential move)
  const lo = [-P.WX, -P.CEIL, -P.WZ], hi = [P.WX, 0, P.WZ];
  const nx = p.map((q, s) => {
    const o = q.slice();
    for (let a = 0; a < 3; a++) {
      const l = lo[a] + R[s], hh = hi[a] - R[s];
      if (o[a] < l) o[a] = l + P.E * (l - o[a]);
      if (o[a] > hh) o[a] = hh - P.E * (o[a] - hh);
    }
    if (o[1] >= -R[s] - 0.5) { o[0] = X[s][0] + (o[0] - X[s][0]) * (1 - P.FRIC); o[2] = X[s][2] + (o[2] - X[s][2]) * (1 - P.FRIC); }
    if (cnt[s] > 0) for (const a of [0, 2]) o[a] = X[s][a] + (o[a] - X[s][a]) * (1 - P.PFRIC);
    return o;
  });
  U = X; X = nx;
  // sort: odd-even phases on the new x
  for (let ph = 0; ph < P.PHASES; ph++) {
    for (let s = phase; s + 1 < N; s += 2) if (X[s][0] > X[s + 1][0]) {
      [X[s], X[s + 1]] = [X[s + 1], X[s]]; [U[s], U[s + 1]] = [U[s + 1], U[s]]; [R[s], R[s + 1]] = [R[s + 1], R[s]];
    }
    phase ^= 1;
  }
  step++;
}
function stats() {
  let maxo = 0, sumo = 0, no = 0, miss = 0, missmax = 0, ke = 0, maxpen = 0, unsorted = 0;
  for (let s = 0; s < N; s++) {
    for (let t = s + 1; t < N; t++) {
      const D = R[s] + R[t], dist = Math.hypot(X[s][0] - X[t][0], X[s][1] - X[t][1], X[s][2] - X[t][2]);
      if (dist < D) { const o = D - dist; maxo = Math.max(maxo, o); sumo += o; no++; if (t - s > P.K) { miss++; missmax = Math.max(missmax, o); } }
    }
    const v = [0, 1, 2].map(a => (X[s][a] - U[s][a]) / h); ke += v[0] ** 2 + v[1] ** 2 + v[2] ** 2;
    maxpen = Math.max(maxpen, X[s][1] + R[s]);
    if (s + 1 < N && X[s][0] > X[s + 1][0]) unsorted++;
  }
  return { maxo: maxo.toFixed(2), meano: (sumo / Math.max(1, no)).toFixed(2), contacts: no, miss, missmax: missmax.toFixed(1), vrms: Math.sqrt(ke / N).toFixed(1), floorpen: maxpen.toFixed(2), unsorted };
}
// worst window demand: max over slots of how far (in slots) the farthest x-near sphere is
function demand() {
  let k = 0;
  for (let s = 0; s < N; s++) for (let t = s + 1; t < N; t++) if (X[t][0] - X[s][0] < R[s] + R[t]) k = Math.max(k, t - s);
  return k;
}
const every = Math.round(P.RATE / 2);
let worst = 0, worstmiss = 0;
for (let i = 0; i < SEC * P.RATE; i++) {
  stepOnce();
  const st = i % every == every - 1 ? stats() : null;
  if (st) {
    worst = Math.max(worst, +st.maxo); worstmiss = Math.max(worstmiss, +st.missmax);
    if (!process.env.Q) console.log(`t=${(step * h).toFixed(1)}s`, JSON.stringify(st), 'demand', demand());
  }
}
console.log(`N=${N}`, JSON.stringify(P), `worst overlap ${worst.toFixed(2)} worst miss ${worstmiss.toFixed(1)}`, JSON.stringify(stats()));
