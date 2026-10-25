// safari.js — the real Safari on the Mac host, through safaridriver (WebDriver), behind the part of Playwright's
// Browser/Page API the evaluate-based tools use: newPage, goto, evaluate, waitForTimeout, mouse, click,
// locator().boundingBox(), screenshot, setViewportSize, close, version.
//
//   const S = require('../../shared/js/safari.js');
//   const b = await S.launch();  const p = await b.newPage({viewport: {width: 1000, height: 900}});
//   await p.goto(S.fileUrl('out/p16.html'));  await p.evaluate(() => innerWidth);
//
// Setup (shared/README.md#safari): on the Mac, Safari's Develop menu > Allow Remote Automation, `safaridriver --enable`
// once, then `safaridriver -p 4444`. The container reaches it at host.docker.internal (IPv4: its IPv6 address is
// unreachable); safaridriver refuses any request whose Host header isn't localhost, so every request says so.
// SAFARIDRIVER=http://host:port overrides the address.
// Safari loads pages from the repo-root server (python3 -m http.server 8765 --bind 127.0.0.1 --directory <main checkout>)
// through VS Code's forwarding of port 8765; a file:// URL or path under the main checkout (a worktree's included)
// becomes http://localhost:8765/<path>. SERVE=url overrides the base. Pages outside it can't be loaded.
// One session at a time (safaridriver's limit): newPage opens the session, a second concurrent page is an error.
// No CDP: no tracing, no virtual time, no console logs. Screenshots are the window at the Mac's device pixel ratio.
const fs = require('fs'), path = require('path'), url = require('url'), http = require('http'), dns = require('dns');
// the directory the repo-root server serves: the main checkout, which holds this worktree's files too (under
// .claude/worktrees/<name>/); SERVE_ROOT overrides it
const ROOT = process.env.SERVE_ROOT || (() => {
  const here = path.join(__dirname, '..', '..');
  try { return path.dirname(require('child_process').execFileSync('git', ['rev-parse', '--path-format=absolute', '--git-common-dir'],
    { cwd: here, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()); } catch (e) { return here; }
})();
const SERVE = (process.env.SERVE || 'http://localhost:8765').replace(/\/$/, '');

let base;  // resolved driver address {host, port}
async function driver() {
  if (base) return base;
  const u = new URL(process.env.SAFARIDRIVER || 'http://host.docker.internal:4444');
  const { address } = await dns.promises.lookup(u.hostname, { family: 4 });
  return (base = { host: address, port: +u.port || 4444 });
}

// one WebDriver command; resolves with `value`, rejects with the driver's error message
async function wd(method, p, body) {
  const { host, port } = await driver();
  const data = body === undefined ? undefined : JSON.stringify(body);
  return new Promise((resolve, reject) => {
    const req = http.request({ host, port, method, path: p,
      headers: { Host: `localhost:${port}`, 'Content-Type': 'application/json', ...(data ? { 'Content-Length': Buffer.byteLength(data) } : {}) } },
      res => { let s = ''; res.setEncoding('utf8'); res.on('data', c => s += c); res.on('end', () => {
        let j; try { j = JSON.parse(s); } catch (e) { return reject(new Error(`safaridriver ${method} ${p}: ${res.statusCode} ${s.slice(0, 200)}`)); }
        if (j.value && j.value.error) return reject(new Error(`safaridriver ${method} ${p}: ${j.value.error}: ${j.value.message}`));
        resolve(j.value); }); });
    req.on('error', e => reject(new Error(`safaridriver at ${host}:${port} unreachable (${e.code || e.message}): is \`safaridriver -p ${port}\` running on the Mac?`)));
    if (data) req.write(data);
    req.end();
  });
}

// a file path or file:// URL under the repo root -> its URL on the repo-root server; other URLs unchanged
function toUrl(u) {
  const f = u.startsWith('file:') ? url.fileURLToPath(u) : /^[a-z]+:/i.test(u) ? null : path.resolve(u);
  if (f === null) return u;
  const rel = path.relative(ROOT, f);
  if (rel.startsWith('..') || path.isAbsolute(rel)) throw new Error(`safari.js: ${f} is outside the repo root; Safari loads pages from ${SERVE}`);
  return `${SERVE}/${rel.split(path.sep).map(encodeURIComponent).join('/')}`;
}
const fileUrl = f => toUrl(path.resolve(f));

// the repo-root server must answer here, or Safari has nothing to load
async function checkServer() {
  await new Promise((resolve, reject) => http.get('http://127.0.0.1:8765/', r => { r.resume(); resolve(); })
    .on('error', () => reject(new Error('safari.js: nothing serves the repo root on :8765; start python3 -m http.server 8765 --bind 127.0.0.1 --directory ' + ROOT))));
}

let open = null;  // the one session's page

// A session left open (a tool that crashed or was killed before close) pairs Safari with it and every later session is
// refused; safaridriver can't list sessions, so the open one's id is kept in a file until a DELETE of it succeeds.
// safaridriver answers a session's commands in order: a DELETE waits for a running script, so a tool killed inside
// evaluate leaves the session until the script times out (SCRIPT_MS; SAFARI_SCRIPT_MS overrides, for longer evaluates).
// At exit, however the process exits, a detached child sends that DELETE and waits for it; the next session waits
// for it too.
const SESSION_FILE = path.join(require('os').tmpdir(), 'css-energy-safari.session');
const SCRIPT_MS = +process.env.SAFARI_SCRIPT_MS || 120000;
const staleId = () => { try { return fs.readFileSync(SESSION_FILE, 'utf8').trim(); } catch (e) { return null; } };
const forget = sid => { if (staleId() === sid) try { fs.unlinkSync(SESSION_FILE); } catch (e) {} };
// (a gone session is closed too: invalid session id)
const del = sid => wd('DELETE', `/session/${sid}`).then(() => forget(sid),
  e => { if (/invalid session id/.test(e.message)) forget(sid); else throw e; });
function closeAtExit() {
  if (!open) return;
  const { host, port } = base, sid = open.sid;
  require('child_process').spawn(process.execPath, ['-e', `
    const fs = require('fs'), f = ${JSON.stringify(SESSION_FILE)}, sid = ${JSON.stringify(sid)};
    const forget = () => { try { if (fs.readFileSync(f, 'utf8').trim() === sid) fs.unlinkSync(f); } catch (e) {} };
    require('http').request({ host: ${JSON.stringify(host)}, port: ${port}, method: 'DELETE', path: '/session/' + sid,
      headers: { Host: 'localhost:${port}' } }, r => { r.resume(); r.on('end', forget); }).on('error', () => {}).end();
    setTimeout(() => process.exit(), ${SCRIPT_MS + 60000});`], { detached: true, stdio: 'ignore' }).unref();
}
process.on('exit', closeAtExit);
for (const s of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(s, () => process.exit(128 + require('os').constants.signals[s]));

// a new session; while an earlier one this harness opened is still closing, wait for it (up to SCRIPT_MS and a minute)
async function newSession() {
  const until = Date.now() + SCRIPT_MS + 60000;
  for (let said = false; ; ) {
    const sid = staleId();
    if (sid) await del(sid).catch(() => {});
    try { return await wd('POST', '/session', { capabilities: { alwaysMatch: { browserName: 'safari' } } }); }
    catch (e) {
      if (!/already paired/.test(e.message)) throw e;
      if (!staleId() || Date.now() > until) throw new Error(`${e.message}\nsafari.js: a session this harness doesn't know of holds Safari; restart safaridriver on the Mac`);
      if (!said) { console.error(`safari.js: waiting for session ${staleId()} to close (a killed tool's script runs out within ${SCRIPT_MS / 1000} s)`); said = true; }
      await new Promise(r => setTimeout(r, 2000));
    }
  }
}

async function launch() {
  await wd('GET', '/status');
  if (!process.env.SERVE) await checkServer();
  let version = '';
  return {
    version: () => version,
    async newPage(opts = {}) {
      if (open) throw new Error('safari.js: safaridriver runs one session at a time; close the other page first');
      const caps = await newSession();
      fs.writeFileSync(SESSION_FILE, caps.sessionId);
      version = caps.capabilities.browserVersion;
      open = page(caps.sessionId);
      // (evaluate runs as long as the tool's script does: smoke.js watches the page for MS, 12 s by default)
      await wd('POST', `/session/${caps.sessionId}/timeouts`, { script: SCRIPT_MS });
      if (opts.viewport) await open.setViewportSize(opts.viewport);
      return open;
    },
    async close() { if (open) await open.close(); },
  };
}

function page(sid) {
  const S = `/session/${sid}`;
  const cmd = (m, p, b) => wd(m, S + p, b);
  // Playwright's evaluate: a function (called with arg) or an expression string; promises are awaited by the driver
  const evaluate = (fn, arg) => cmd('POST', '/execute/sync', typeof fn === 'function'
    ? { script: `return (${fn}).apply(null, arguments)`, args: arg === undefined ? [] : [arg] }
    : { script: `return (${fn})`, args: [] });
  // pointer state (position, pressed buttons) persists across perform-actions calls within the session
  let at = { x: 0, y: 0 };
  const pointer = acts => cmd('POST', '/actions', { actions: [{ type: 'pointer', id: 'mouse', parameters: { pointerType: 'mouse' }, actions: acts }] });
  // whether Safari draws frames: it stops when the Mac's display sleeps or the window is hidden, and then nothing that
  // waits for requestAnimationFrame (or, sometimes, a load) finishes
  const frames = () => evaluate(() => new Promise(res => { let n = 0; const t = performance.now();
    (function f() { if (++n < 30 && performance.now() - t < 1000) requestAnimationFrame(f); else res(n); })(); }))
    .then(n => `${n} frames drawn in the next second${n < 5 ? ': is the Mac\'s display asleep or the Safari window hidden?' : ''}`);
  const P = {
    sid,
    frames,
    url: () => cmd('GET', '/url'),
    // As Playwright's goto, until the load event: safaridriver's navigate can return while a large page still loads.
    // A load that makes no progress for 10 s is started again (up to 4 tries): the page comes through VS Code's port
    // forwarding, which now and then stalls in the middle of a large page (the server sent it all; Safari's parser
    // stopped at a few hundred elements and waited for the rest for minutes).
    async goto(u) {
      const state = () => evaluate(() => ({ readyState: document.readyState, href: location.href, elements: document.getElementsByTagName('*').length,
        resources: performance.getEntriesByType('resource').map(e => `${e.name.split('/').pop()} ${Math.round(e.duration)} ms`) }));
      for (let attempt = 1; ; attempt++) {
        await cmd('POST', '/url', { url: toUrl(u) });
        let st, last = -1, since = Date.now();
        for (;;) { st = await state(); if (st.readyState === 'complete') return;
          if (st.elements !== last) { last = st.elements; since = Date.now(); }
          if (Date.now() - since > 10000) break;
          await new Promise(r => setTimeout(r, 50)); }
        if (attempt === 4) throw new Error(`safari.js: ${u} didn't finish loading in 4 tries: ${JSON.stringify(st)}; ${await frames()}`);
        console.error(`safari.js: loading ${u} stalled at ${st.elements} elements (${st.readyState}); loading it again`);
      }
    },
    evaluate,
    waitForTimeout: ms => new Promise(r => setTimeout(r, ms)),
    async setViewportSize({ width, height }) {
      const [iw, ih, ow, oh] = await evaluate(() => [innerWidth, innerHeight, outerWidth, outerHeight]);
      await cmd('POST', '/window/rect', { width: width + ow - iw, height: height + oh - ih });
    },
    viewportSize: () => evaluate(() => ({ width: innerWidth, height: innerHeight })),
    mouse: {
      // steps as in Playwright: intermediate moves, here over steps × 16 ms
      async move(x, y, o = {}) { const n = o.steps || 1, acts = [];
        for (let i = 1; i <= n; i++) acts.push({ type: 'pointerMove', origin: 'viewport', duration: n > 1 ? 16 : 0,
          x: Math.round(at.x + (x - at.x) * i / n), y: Math.round(at.y + (y - at.y) * i / n) });
        at = { x, y }; await pointer(acts); },
      down: () => pointer([{ type: 'pointerDown', button: 0 }]),
      up: () => pointer([{ type: 'pointerUp', button: 0 }]),
    },
    async click(sel) {
      const el = await cmd('POST', '/element', { using: 'css selector', value: sel });
      await cmd('POST', `/element/${Object.values(el)[0]}/click`, {});
    },
    locator: sel => ({ boundingBox: () => evaluate(s => { const e = document.querySelector(s); if (!e) return null;
      const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; }, sel) }),
    async screenshot(o = {}) {
      const png = Buffer.from(await cmd('GET', '/screenshot'), 'base64');
      if (o.path) fs.writeFileSync(o.path, png);
      return png;
    },
    async close() { if (open === P) open = null; await del(sid); },
  };
  return P;
}

module.exports = { launch, fileUrl, toUrl, wd };
