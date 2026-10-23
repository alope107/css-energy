// touch.js — painting with a finger on a phone-sized touch screen, in headless Chromium (~40 s).
//
//   node tools/touch.js [site]               (site defaults to paint/site)
//
// Real touch gestures (CDP Input.dispatchTouchEvent goes through Chromium's gesture recognizer: touch slop, scroll
// latching, flings), as tools/touchcheck.js does in css-physics. Each stroke must paint a continuous line (8-connected)
// from the cell it started on, of about the path's length, within a cell of the path, and leave every handle back at
// rest and the page unscrolled:
//   drag    touch, rest 150 ms (show-press), drag 6 cells right, hold, lift
//   quick   touch and drag 5 cells down at once, lift while moving (no :hover ever arrives; may fling)
//   back    drag 4 cells right and back again
//   fast    a diagonal in jumps of 4 cells, one per two frames
//   tap     one cell
// then reloads and reads the strokes back. A stroke trails the finger by the touch slop (here ~15 px, about a cell),
// so it may end a cell short, or sit a cell off the path, in the stroke's first direction.
const path = require('path');
const { PAINT, serve, profileDir, sleep, pendingWrites } = require('./lib.js');

const N = 480, W = 24;
const site = process.argv[2] || path.join(PAINT, 'site');
const VIEW = { viewport: { width: 412, height: 915 }, deviceScaleFactor: 2.625, isMobile: true, hasTouch: true };
const PALETTE_INDEX = `(() => {
  const pal = [...Array(16)].map((_, v) => { const d = document.createElement('div'); d.style.background = 'var(--p' + v + ')';
    document.body.append(d); const c = getComputedStyle(d).backgroundColor; d.remove(); return c; });
  return [...document.querySelectorAll('.c .px')].map(e => { const bg = getComputedStyle(e).backgroundColor;
    const i = pal.indexOf(bg); return i >= 0 ? i : bg === 'rgba(0, 0, 0, 0)' ? -1 : -8; }); })()`;

let failures = 0;
const note = (ok, msg) => { console.log(`${ok ? 'ok  ' : 'FAIL'} ${msg}`); if (!ok) failures++; };

(async () => {
  const srv = await serve(site);
  const prof = await profileDir();
  try {
    let c = await prof.ctx(VIEW), pg = c.pages()[0] || await c.newPage();
    await pg.goto(srv.base + '/', { timeout: 300000 });
    const cdp = await c.newCDPSession(pg);
    const T = (type, x, y) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchEnd' ? [] : [{ x, y }] });
    const box = k => pg.evaluate(k => { const b = document.querySelectorAll('.c')[k].getBoundingClientRect();
      return [b.x + b.width / 2, b.y + b.height / 2, b.width]; }, k);
    const [, , cw] = await box(0);
    note(await pg.evaluate(() => getComputedStyle(document.querySelector('.hd')).display === 'block'),
      `touch handles on a coarse pointer (cells ${cw.toFixed(1)} px on screen)`);

    let shown = await pg.evaluate(PALETTE_INDEX);
    const want = shown.slice();
    // touch cell k, rest `pre` ms, then visit the cells `pts` ([row, column] offsets from k), `gap` ms apart; rest, lift
    async function gesture(label, k, col, pts, pre, post, gap = 16) {
      await pg.locator(`label[for=pc${col}]`).tap(); await sleep(200);
      const [x, y] = await box(k);
      const s0 = await pg.evaluate(() => scrollY);
      await T('touchStart', x, y); await sleep(pre);
      for (const [r, q] of pts) { await T('touchMove', x + q * cw, y + r * cw); await sleep(gap); }
      await sleep(post); await T('touchEnd'); await sleep(600);
      const now = await pg.evaluate(PALETTE_INDEX);
      const changed = new Set([...Array(N).keys()].filter(i => now[i] !== shown[i]));
      // the path: the cells on the lines between the samples, from the start cell
      const ideal = new Set([k]); let [pr, pq] = [0, 0];
      for (const [r, q] of pts.map(([r, q]) => [Math.round(r), Math.round(q)])) {
        const n = Math.max(Math.abs(r - pr), Math.abs(q - pq));
        for (let i = 1; i <= n; i++) ideal.add(k + Math.round(pr + (r - pr) * i / n) * W + Math.round(pq + (q - pq) * i / n));
        [pr, pq] = [r, q];
      }
      const near = i => [...ideal].some(j => Math.abs(((i / W) | 0) - ((j / W) | 0)) <= 1 && Math.abs(i % W - j % W) <= 1);
      const seen = new Set([k]), todo = [k];                      // the 8-connected component of the start cell
      while (todo.length) { const i = todo.pop();
        for (const j of changed) if (!seen.has(j) && Math.abs(((i / W) | 0) - ((j / W) | 0)) <= 1 && Math.abs(i % W - j % W) <= 1) { seen.add(j); todo.push(j); } }
      const far = [...changed].filter(i => !near(i)), apart = [...changed].filter(i => !seen.has(i));
      const ok = now[k] === col && [...changed].every(i => now[i] === col) && !far.length && !apart.length && changed.size >= ideal.size - 1;
      note(ok, `${label}: ${changed.size} cells painted for a path of ${ideal.size}, start ${now[k] === col ? 'painted' : 'NOT painted'}, ` +
        `${far.length} off the path, ${apart.length} not connected` + (far.length ? ` (cell ${far[0]})` : apart.length ? ` (cell ${apart[0]})` : ''));
      const rest = await pg.evaluate(() => [[...document.querySelectorAll('.hd')].filter(h => h.scrollLeft !== 3000 || h.scrollTop !== 3000).length,
        getComputedStyle(document.querySelector('.grid')).getPropertyValue('--held'), scrollY]);
      note(rest[0] === 0 && rest[1] === '0' && rest[2] === s0, `${label}: handles off rest ${rest[0]}, held ${rest[1]}, page scroll ${s0} -> ${rest[2]}`);
      for (const i of changed) want[i] = now[i];
      shown = now;
    }
    const line = (r, q, n) => [...Array(n).keys()].map(i => [r * (i + 1) / n, q * (i + 1) / n]);
    await gesture('drag', 3 * W + 2, 5, line(0, 6, 14), 150, 300);
    await gesture('quick', 8 * W + 4, 9, line(5, 0, 10), 0, 0);
    await gesture('back', 12 * W + 10, 11, [...line(0, 4, 10), ...line(0, 4, 10).reverse().slice(1), [0, 0]], 100, 100);
    await gesture('fast', 5 * W + 14, 3, [[4, 4], [8, 8], [12, 8]], 120, 100, 34);
    await pg.locator('label[for=pc14]').tap(); await sleep(200);
    const tk = 16 * W + 20, [tx, ty] = await box(tk); await pg.touchscreen.tap(tx, ty); await sleep(600);
    const now = await pg.evaluate(PALETTE_INDEX);
    const changed = [...Array(N).keys()].filter(i => now[i] !== shown[i]);
    note(changed.length === 1 && now[tk] === 14, `tap: ${changed.length} cell(s) changed` + (now[tk] === 14 ? '' : `, tapped cell shows ${now[tk]}`));
    want[tk] = now[tk];

    const painted = [...Array(N).keys()].filter(i => want[i] >= 0), t1 = Date.now();
    let pending; do { pending = await pendingWrites(pg, painted); if (pending.length) await sleep(250); }
    while (pending.length && Date.now() - t1 < 60000);
    note(!pending.length, `${painted.length} writes done in ${((Date.now() - t1) / 1000).toFixed(1)} s` + (pending.length ? `, ${pending.length} pending (cell ${pending[0]})` : ''));
    await pg.reload({ timeout: 300000 });
    const t0 = Date.now(); let got;
    do { await sleep(1000); got = await pg.evaluate(PALETTE_INDEX); } while (got.some((v, i) => v !== want[i]) && Date.now() - t0 < 90000);
    const bad = [...Array(N).keys()].filter(i => got[i] !== want[i]);
    note(!bad.length, `reload: the strokes read back (${want.filter(v => v >= 0).length} cells), mismatches ${bad.length}`);
    await c.close();
  } finally { srv.stop(); prof.remove(); }
  console.log(failures ? `${failures} check(s) failed` : 'all checks passed');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
