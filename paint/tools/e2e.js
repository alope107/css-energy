// e2e.js — end-to-end test of the paint site with real clicks, in headless Chromium (~1.5 min).
//
//   node tools/e2e.js [seed] [site]          (site defaults to paint/site)
//
// Starts serve.js, opens a fresh persistent profile, and checks the canvas the user sees against the expected
// colours after: painting, a palette change, reload, Back/Forward (undo/redo, live and after reload), an undo
// between two paints of one cell, a fast repaint followed by an immediate reload, and a browser restart.
// Prints one line per check and exits non-zero on any mismatch.
const path = require('path');
const { PAINT, serve, profileDir, sleep } = require('./lib.js');

const N = 480;
const seed = +(process.argv[2] || 7);
const site = process.argv[3] || path.join(PAINT, 'site');
let rnd = seed >>> 0 || 1;                                      // xorshift32: reproducible cells and colours
const rand = n => { rnd ^= rnd << 13; rnd >>>= 0; rnd ^= rnd >>> 17; rnd ^= rnd << 5; rnd >>>= 0; return rnd % n; };

// The colour index a document shows: the page's .px (boot read) or a painted cell document's .px.
const PALETTE_INDEX = `(sel) => {
  const pal = [...Array(16)].map((_, v) => { const d = document.createElement('div'); d.style.background = 'var(--p' + v + ')';
    document.body.append(d); const c = getComputedStyle(d).backgroundColor; d.remove(); return c; });
  return [...document.querySelectorAll(sel)].map(e => { const bg = getComputedStyle(e).backgroundColor;
    const i = pal.indexOf(bg); return i >= 0 ? i : bg === 'rgba(0, 0, 0, 0)' ? -1 : -8; });
}`;

async function state(pg) {
  const out = await pg.evaluate(`(${PALETTE_INDEX})('.c .w > .px')`);       // what the page read
  for (const f of pg.mainFrame().childFrames()) {                               // cells showing a painted document
    const m = /\/c\/(\d+)\/p\//.exec(f.url());
    if (!m || f.isDetached()) continue;
    const el = await f.frameElement();
    if (!(await el.isVisible())) continue;
    try { out[+m[1]] = (await f.evaluate(`(${PALETTE_INDEX})('.px')`))[0]; } catch { out[+m[1]] = -9; }
  }
  return out;
}

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

async function paint(pg, k, col) {
  await pg.click(`label[for=pc${col}]`);
  const r = await pg.evaluate(k => { const b = document.querySelectorAll('.c')[k].getBoundingClientRect();
    return [b.x + b.width / 2, b.y + b.height / 2]; }, k);
  let frame;
  for (const f of pg.mainFrame().childFrames())
    if (f.url().includes(`/c/${k}/`) && !f.isDetached() && await (await f.frameElement()).isVisible()) frame = f;
  await Promise.all([frame.waitForNavigation(), pg.mouse.click(r[0], r[1])]);
}

// The toolbar's Back/Forward: Playwright's goBack() waits for a top-level navigation, which an undo isn't.
async function history(pg, delta) {
  const cdp = await pg.context().newCDPSession(pg);
  const h = await cdp.send('Page.getNavigationHistory');
  await cdp.send('Page.navigateToHistoryEntry', { entryId: h.entries[h.currentIndex + delta].id });
  await cdp.detach(); await sleep(1500);
}

(async () => {
  const srv = await serve(site);
  const prof = await profileDir();
  const viewport = { width: 700, height: 760 };
  try {
    let c = await prof.ctx({ viewport }), pg = c.pages()[0] || await c.newPage();
    const U = srv.base + '/';
    let t = Date.now(); await pg.goto(U, { timeout: 300000 });
    console.log(`page + 480 cell documents loaded in ${((Date.now() - t) / 1000).toFixed(1)} s`);
    const want = Array(N).fill(-1);
    await check(pg, want, 'fresh profile: every cell blank');

    const cells = new Set(); while (cells.size < 40) cells.add(rand(N));
    for (const k of cells) { const col = rand(16); await paint(pg, k, col); want[k] = col; }
    for (let i = 0; i < 25; i++) { const col = (i * 7) % 16; await paint(pg, 123, col); want[123] = col; }
    await sleep(1000); await check(pg, want, '65 paints (cell 123 painted 25 times)', 10);
    await pg.click('label[for=pc3]'); await sleep(500); await check(pg, want, 'palette change repaints nothing', 5);
    await pg.reload({ timeout: 300000 }); await check(pg, want, 'reload: read back from the dictionaries');

    // Undo/redo. Painting a cell its current colour is a same-URL navigation, which replaces the history entry
    // instead of adding one, so always paint a different colour here.
    const [a, b, c1] = [...Array(N).keys()].filter(k => want[k] >= 0);
    const [pa, pb] = [want[a], want[b]];
    const ca = want[a] !== 11 ? 11 : 10, cb = want[b] !== 12 ? 12 : 13;
    await paint(pg, a, ca); await paint(pg, b, cb); want[a] = ca; want[b] = cb;
    await history(pg, -1); await history(pg, -1); want[a] = pa; want[b] = pb;
    await check(pg, want, 'Back x2 (undo to the page-load colours), live', 10);
    await history(pg, +1); want[a] = ca;
    await check(pg, want, 'Forward (redo), live', 10);
    await pg.reload({ timeout: 300000 }); await check(pg, want, 'undo/redo persisted: reload');

    const u = want[c1] !== 3 ? 3 : 5, w = u !== 4 ? 4 : 6;
    await paint(pg, c1, u); await paint(pg, c1, w); await history(pg, -1); want[c1] = u;
    await check(pg, want, 'paint, paint, Back (page-to-page undo), live', 10);
    await pg.reload({ timeout: 300000 }); await check(pg, want, 'page-to-page undo persisted: reload');

    // A paint followed at once by a reload: the CSS write must not wait for the network to go idle.
    const fast = [...Array(N).keys()].find(k => want[k] === -1);
    await paint(pg, fast, 9); await paint(pg, fast, 2); want[fast] = 2;
    await pg.reload({ timeout: 300000 }); await check(pg, want, 'fast repaint, immediate reload');

    await c.close(); c = await prof.ctx({ viewport }); pg = c.pages()[0] || await c.newPage();
    await pg.goto(U, { timeout: 300000 }); await check(pg, want, 'browser restart');
    await c.close();
  } finally { srv.stop(); prof.remove(); }
  console.log(failures ? `${failures} check(s) failed` : 'all checks passed');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
