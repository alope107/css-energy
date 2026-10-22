// e2e.js — end-to-end test of the paint site with real mouse input, in headless Chromium (~1.5 min).
//
//   node tools/e2e.js [seed] [site]          (site defaults to paint/site)
//
// Starts serve.js, opens a fresh persistent profile, and checks the canvas the user sees (each cell's .px: the
// colour painted in this page, else the colour read, else blank) after: clicks, drags, fast strokes that jump cells
// between frames (each must paint the whole line), 40 changes of one cell (more than one writer document holds), a
// palette change, reload, repainting cells read back, a repaint followed by a reload, and a browser restart. Before
// each reload it waits until every painted cell's writer has finished its current write (what the spinner shows).
// Prints one line per check and exits non-zero on any mismatch.
const path = require('path');
const { PAINT, serve, profileDir, sleep, pendingWrites } = require('./lib.js');

const N = 480, W = 24, CELL = 22;
const seed = +(process.argv[2] || 7);
const site = process.argv[3] || path.join(PAINT, 'site');
let rnd = seed >>> 0 || 1;                                      // xorshift32: reproducible cells and colours
const rand = n => { rnd ^= rnd << 13; rnd >>>= 0; rnd ^= rnd >>> 17; rnd ^= rnd << 5; rnd >>>= 0; return rnd % n; };

// The colour index each cell shows (-1: blank, the checkerboard).
const PALETTE_INDEX = `(sel) => {
  const pal = [...Array(16)].map((_, v) => { const d = document.createElement('div'); d.style.background = 'var(--p' + v + ')';
    document.body.append(d); const c = getComputedStyle(d).backgroundColor; d.remove(); return c; });
  return [...document.querySelectorAll(sel)].map(e => { const bg = getComputedStyle(e).backgroundColor;
    const i = pal.indexOf(bg); return i >= 0 ? i : bg === 'rgba(0, 0, 0, 0)' ? -1 : -8; });
}`;
const state = pg => pg.evaluate(`(${PALETTE_INDEX})('.c .px')`);

let failures = 0;
async function check(pg, want, label, tmax = 90) {
  const t0 = Date.now();
  for (;;) {
    const got = await state(pg);
    const bad = [...Array(N).keys()].filter(k => got[k] !== want[k]);
    if (!bad.length || Date.now() - t0 > tmax * 1000) {
      if (bad.length) failures++;
      console.log(`${bad.length ? 'FAIL' : 'ok  '} ${label}: mismatches ${bad.length}` +
        (bad.length ? ` (cell ${bad[0]}: got ${got[bad[0]]}, want ${want[bad[0]]})` : ''));
      return;
    }
    await sleep(1000);
  }
}

const centre = (pg, k) => pg.evaluate(k => { const b = document.querySelectorAll('.c')[k].getBoundingClientRect();
  return [b.x + b.width / 2, b.y + b.height / 2]; }, k);
const pick = (pg, col) => pg.click(`label[for=pc${col}]`);

async function paint(pg, k, col) {
  await pick(pg, col);
  const [x, y] = await centre(pg, k);
  await pg.mouse.click(x, y);
}

// One stroke through the centres of cells ks, in order, with the button held.
async function drag(pg, ks, col) {
  await pick(pg, col);
  const [x, y] = await centre(pg, ks[0]);
  await pg.mouse.move(x, y); await pg.mouse.down();
  for (const k of ks.slice(1)) { const [a, b] = await centre(pg, k); await pg.mouse.move(a, b, { steps: 3 }); }
  await pg.mouse.up(); await pg.mouse.move(2, 2);
}

// A fast stroke: the button held through samples (row, column) one frame or more apart, so the pointer jumps cells
// between frames. Returns the cells the page should paint: the line between consecutive samples, one cell per step
// along the major axis, the nearest (rounding half up, as CSS round() does).
async function fastStroke(pg, pts, col) {
  await pick(pg, col);
  const P = []; for (const [r, q] of pts) P.push(await centre(pg, r * W + q));
  await pg.mouse.move(...P[0]); await pg.mouse.down(); await sleep(40);
  for (const p of P.slice(1)) { await pg.mouse.move(...p); await sleep(40); }
  await pg.mouse.up(); await pg.mouse.move(2, 2);
  const cells = new Set([pts[0][0] * W + pts[0][1]]);
  for (let i = 1; i < pts.length; i++) {
    const [sy, sx] = pts[i - 1], [qy, qx] = pts[i], dx = qx - sx, dy = qy - sy;
    if (Math.abs(dx) >= Math.abs(dy)) for (let c = Math.min(sx, qx); c <= Math.max(sx, qx); c++) cells.add(Math.round(sy + (c - sx) * dy / (dx || 1)) * W + c);
    else for (let r = Math.min(sy, qy); r <= Math.max(sy, qy); r++) cells.add(r * W + Math.round(sx + (r - sy) * dx / dy));
  }
  return cells;
}

// A pending write: the cell's latch and slot in the page, and each of its writers' size and loads.
async function explain(pg, k) {
  const u = await pg.evaluate(k => { const s = getComputedStyle(document.querySelectorAll('.u')[k]);
    return ['L', 'W', 'g', 'ws', 'wj'].map(n => `${n}=${s.getPropertyValue('--' + n)}`).join(' '); }, k);
  console.log(`     cell ${k}: ${u}`);
  for (const f of pg.mainFrame().childFrames()) {
    if (f.isDetached() || !f.url().endsWith(`/c/${k}/w`)) continue;
    const vis = await (await f.frameElement()).isVisible();
    const r = await f.evaluate(() => [innerWidth, innerHeight, performance.getEntriesByType('resource')
      .map(e => `${e.name.replace(/.*\/d\//, '')}:${e.responseEnd ? Math.round(e.responseEnd) : 'open'}`).join(' ')]);
    console.log(`     writer ${vis ? 'shown' : 'hidden'} ${r[0]}x${r[1]}: ${r[2] || 'no loads'}`);
  }
}
async function saved(pg, cells, label, tmax = 60) {
  const t0 = Date.now();
  for (;;) {
    const pending = await pendingWrites(pg, cells, CELL);
    if (!pending.length || Date.now() - t0 > tmax * 1000) {
      if (pending.length) failures++;
      console.log(`${pending.length ? 'FAIL' : 'ok  '} ${label}: ${cells.size} writes done in ${((Date.now() - t0) / 1000).toFixed(1)} s` +
        (pending.length ? `, ${pending.length} pending (cell ${pending[0]})` : ''));
      for (const k of pending.slice(0, 3)) await explain(pg, k);
      return;
    }
    await sleep(250);
  }
}

(async () => {
  const srv = await serve(site);
  const prof = await profileDir();
  const viewport = { width: 700, height: 760 };
  try {
    let c = await prof.ctx({ viewport }), pg = c.pages()[0] || await c.newPage();
    const U = srv.base + '/';
    let t = Date.now(); await pg.goto(U, { timeout: 300000 });
    console.log(`page loaded in ${((Date.now() - t) / 1000).toFixed(1)} s, ${pg.mainFrame().childFrames().length} frames`);
    const want = Array(N).fill(-1);
    await check(pg, want, 'fresh profile: every cell blank');

    let painted = new Set();
    const cells = new Set(); while (cells.size < 40) cells.add(rand(N));
    for (const k of cells) { const col = rand(16); await paint(pg, k, col); want[k] = col; painted.add(k); }
    for (let i = 0; i < 40; i++) { const col = (i * 7) % 16; await paint(pg, 123, col); want[123] = col; }
    painted.add(123);
    const row = [...Array(13).keys()].map(i => 5 * W + 3 + i), col = [...Array(8).keys()].map(i => (8 + i) * W + 20);
    await drag(pg, row, 12); for (const k of row) { want[k] = 12; painted.add(k); }
    await drag(pg, col.slice().reverse(), 2); for (const k of col) { want[k] = 2; painted.add(k); }
    for (const [pts, col] of [[[[0, 1], [0, 7], [0, 13], [0, 19]], 6],                     // 6 cells per frame
      [[[17, 0], [12, 5], [7, 10]], 9],                                                        // diagonal
      [[[1, 22], [4, 16], [7, 22], [10, 16]], 13]])                                             // slope 1/2 zigzag
      for (const k of await fastStroke(pg, pts, col)) { want[k] = col; painted.add(k); }
    await pg.mouse.move(2, 2); await sleep(500);
    await check(pg, want, '40 clicks, cell 123 changed 40 times, two drags, three fast strokes (shown at once)', 5);
    const wj = await pg.evaluate(() => getComputedStyle(document.querySelectorAll('.u')[123]).getPropertyValue('--wj'));
    console.log(`${+wj >= 1 ? 'ok  ' : 'FAIL'} cell 123 moved on to writer ${wj} after 40 changes`); if (+wj < 1) failures++;
    await pick(pg, 3); await sleep(500); await check(pg, want, 'palette change repaints nothing', 5);
    await saved(pg, painted, 'every painted cell written');
    await pg.reload({ timeout: 300000 }); await check(pg, want, 'reload: read back from the dictionaries');

    // Cells that were read back, repainted (one with the colour it already holds) and one changed twice.
    painted = new Set();
    const [a, b, c1] = [...Array(N).keys()].filter(k => want[k] >= 0);
    const ca = want[a] !== 11 ? 11 : 10;
    await paint(pg, a, ca); want[a] = ca;
    await paint(pg, b, want[b]);
    const u = want[c1] !== 3 ? 3 : 5, w = u !== 4 ? 4 : 6;
    await paint(pg, c1, u); await paint(pg, c1, w); want[c1] = w;
    for (const k of [a, b, c1]) painted.add(k);
    await check(pg, want, 'repaint cells read back', 5);
    await saved(pg, painted, 'repaints written');
    await pg.reload({ timeout: 300000 }); await check(pg, want, 'repaints persisted: reload');

    // A cell changed twice, then a reload as soon as the writes are done.
    const fast = [...Array(N).keys()].find(k => want[k] === -1);
    await paint(pg, fast, 9); await paint(pg, fast, 2); want[fast] = 2;
    await saved(pg, new Set([fast]), 'fast repaint written');
    await pg.reload({ timeout: 300000 }); await check(pg, want, 'fast repaint, immediate reload');

    await c.close(); c = await prof.ctx({ viewport }); pg = c.pages()[0] || await c.newPage();
    await pg.goto(U, { timeout: 300000 }); await check(pg, want, 'browser restart');
    await c.close();
  } finally { srv.stop(); prof.remove(); }
  console.log(failures ? `${failures} check(s) failed` : 'all checks passed');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
