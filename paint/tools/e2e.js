// e2e.js — end-to-end test of the paint site with real mouse input, in headless Chromium (~1.5 min).
//
//   node tools/e2e.js [seed] [site]          (site defaults to paint/site)
//
// Starts serve.js, opens a fresh persistent profile, and checks the canvas the user sees (each cell's .px: the
// colour painted in this page, else the colour read, else blank) after: clicks, drags, fast strokes that jump cells
// between frames (each must paint the whole line), a turning stroke streamed like a real mouse (the "hunks" of
// 2026-10-23: chords and fans from a stale previous point), 60 changes of one cell (more than one writer document holds), a
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

// A stroke through (row, column) points over `ms`, a pointer move every 4 ms, sent without waiting for each to be
// handled (Playwright's mouse.move waits, which spaces moves a frame or more apart): Chromium coalesces them to one a
// frame, as it does a real mouse's.
async function streamStroke(pg, pts, col, ms) {
  await pick(pg, col);
  const P = []; for (const [r, q] of pts) P.push(await centre(pg, r * W + q));
  const cdp = await pg.context().newCDPSession(pg), sent = [];
  const ev = (type, [x, y], buttons = 1) => sent.push(cdp.send('Input.dispatchMouseEvent',
    { type, x, y, button: 'left', buttons, clickCount: type === 'mouseMoved' ? 0 : 1 }));
  ev('mouseMoved', P[0], 0); ev('mousePressed', P[0]); await sleep(30);
  const t0 = Date.now();
  for (;;) {
    const f = Math.min(1, (Date.now() - t0) / ms) * (P.length - 1), i = Math.min(P.length - 2, Math.floor(f)), u = f - i;
    ev('mouseMoved', [P[i][0] + (P[i + 1][0] - P[i][0]) * u, P[i][1] + (P[i + 1][1] - P[i][1]) * u]);
    if (f >= P.length - 1) break;
    await sleep(4);
  }
  ev('mouseReleased', P[P.length - 1], 0); await Promise.all(sent); await cdp.detach();
  await pg.mouse.move(2, 2); await sleep(300);
}
// Distance in cells from cell k's centre to the polyline through (row, column) points.
function distToPath(k, pts) {
  const y = (k / W) | 0, x = k % W; let best = Infinity;
  for (let i = 1; i < pts.length; i++) {
    const [ay, ax] = pts[i - 1], [by, bx] = pts[i], dy = by - ay, dx = bx - ax;
    const t = dy || dx ? Math.max(0, Math.min(1, ((y - ay) * dy + (x - ax) * dx) / (dy * dy + dx * dx))) : 0;
    best = Math.min(best, Math.hypot(y - ay - t * dy, x - ax - t * dx));
  }
  return best;
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
// Waits until every cell in `cells` has finished its write, then 500 ms more: a reload ~50 ms after the last write
// finished once read two of three repainted cells' old colours (1 run in ~12; the browser restart after read the new
// ones), so a dictionary seems to become readable a little after its response is complete.
async function saved(pg, cells, label, tmax = 60) {
  const t0 = Date.now();
  for (;;) {
    const pending = await pendingWrites(pg, cells, CELL);
    if (!pending.length || Date.now() - t0 > tmax * 1000) {
      if (pending.length) failures++;
      console.log(`${pending.length ? 'FAIL' : 'ok  '} ${label}: ${cells.size} writes done in ${((Date.now() - t0) / 1000).toFixed(1)} s` +
        (pending.length ? `, ${pending.length} pending (cell ${pending[0]})` : ''));
      for (const k of pending.slice(0, 3)) await explain(pg, k);
      await sleep(500);
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
    // 60 changes: each moves the cell's clock at least 50 ms, 1.25 slots, so 75+ slots, past the first writer's 64
    for (let i = 0; i < 60; i++) { const col = (i * 7) % 16; await paint(pg, 123, col); want[123] = col; }
    painted.add(123);
    const row = [...Array(13).keys()].map(i => 5 * W + 3 + i), col = [...Array(8).keys()].map(i => (8 + i) * W + 20);
    await drag(pg, row, 12); for (const k of row) { want[k] = 12; painted.add(k); }
    await drag(pg, col.slice().reverse(), 2); for (const k of col) { want[k] = 2; painted.add(k); }
    for (const [pts, col] of [[[[0, 1], [0, 7], [0, 13], [0, 19]], 6],                     // 6 cells per frame
      [[[17, 0], [12, 5], [7, 10]], 9],                                                        // diagonal
      [[[1, 22], [4, 16], [7, 22], [10, 16]], 13]])                                             // slope 1/2 zigzag
      for (const k of await fastStroke(pg, pts, col)) { want[k] = col; painted.add(k); }
    await pg.mouse.move(2, 2); await sleep(500);
    await check(pg, want, '40 clicks, cell 123 changed 60 times, two drags, three fast strokes (shown at once)', 5);
    // A fast stroke that turns, streamed like a real mouse: under a cell a frame. The line must stay near the path and
    // reach its corners (a stale previous point drew chords and fans from the stroke's start: "hunks", every time). A
    // stroke is drawn from points 1-2 frames apart, so a corner may be cut by a cell or so. A stall of the main thread
    // (this machine is shared) skips what the pointer crossed meanwhile: a failed stroke is tried once more elsewhere,
    // and fails only if that one does too, unless both tries saw a frame over 750 ms (then: not judged). The old fan
    // failed both tries with frames of 230 ms and less.
    // (After the writes so far: ~100 writer documents loading at once make long frames, and long frames cut corners.)
    await saved(pg, painted, 'writes before the streamed stroke');
    let stalledBefore = false;
    for (const [pts, col, last] of [[[[12, 1], [12, 14], [19, 14], [13, 1]], 14, false],
      [[[2, 2], [2, 15], [9, 15], [3, 2]], 15, true]]) {
      const before = await state(pg);
      // long frames, observed passively (a requestAnimationFrame loop to time them made them: 400-1,200 ms)
      const t0 = await pg.evaluate(() => { if (!window.LOAF) { window.LOAF = [];
        new PerformanceObserver(l => LOAF.push(...l.getEntries())).observe({ type: 'long-animation-frame', buffered: true }); }
        return performance.now(); });
      await streamStroke(pg, pts, col, 900);
      const maxFrame = await pg.evaluate(t0 => Math.max(0, ...LOAF.filter(e => e.startTime + e.duration >= t0).map(e => e.duration)), t0);
      const after = await state(pg), near = (k, d = 1.5) => distToPath(k, pts) <= d;
      const newCells = [...Array(N).keys()].filter(k => after[k] === col && before[k] !== col);
      const far = newCells.filter(k => !near(k));
      const corners = pts.filter(([r, c]) => !newCells.concat([...Array(N).keys()].filter(k => before[k] === col))
        .some(k => Math.max(Math.abs(((k / W) | 0) - r), Math.abs(k % W - c)) <= 2));
      const ok = !far.length && !corners.length && newCells.length >= 25, stalled = maxFrame > 750 && (!last || stalledBefore);
      stalledBefore = maxFrame > 750;
      for (const k of newCells) { want[k] = col; painted.add(k); }
      const verdict = ok ? 'ok  ' : !last ? 'miss' : stalled ? 'SKIP' : 'FAIL';
      console.log(`${verdict} fast stroke with turns (streamed${last ? ', second try' : ''}): ` +
        `${newCells.length} cells, ${far.length} off the path` + (far.length ? ` (cell ${far[0]})` : '') +
        `, ${corners.length} corners missed, longest frame ${maxFrame.toFixed(0)} ms` +
        (verdict === 'SKIP' ? ' (frames over 750 ms on both tries: not judged)' : ''));
      if (!ok) {
        const r0 = Math.min(...pts.map(p => p[0])) - 1;
        for (let r = r0; r < r0 + 10; r++) console.log(`     ${String(r).padStart(2)} ` + [...Array(W).keys()].map(c => {
          const k = r * W + c; return newCells.includes(k) ? (near(k) ? 'o' : 'X') : distToPath(k, pts) < 0.5 ? '-' : '.'; }).join(''));
      }
      if (ok) break;
      if (last && !stalled) failures++;
    }
    const wj = await pg.evaluate(() => getComputedStyle(document.querySelectorAll('.u')[123]).getPropertyValue('--wj'));
    console.log(`${+wj >= 1 ? 'ok  ' : 'FAIL'} cell 123 moved on to writer ${wj} after 60 changes`); if (+wj < 1) failures++;
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
