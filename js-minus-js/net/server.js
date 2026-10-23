// server.js — the page's web server and its network gateway (harness and local use; the page itself runs no script).
//
//   node net/server.js <root> [port]      serves <root> with the gateway under /net/; prints `listening <port>`
//
// The page has no script, so the NET instruction (machine/uarch.py) talks to this gateway through modems: iframes
// (machine/gen_css.py), one per two of the P parts of an answer (layout.json net_parts), whose documents this gateway
// serves one per word, alternating /net/…/m0.html#t and m1.html#t (a refresh to the same URL doesn't reload):
//   - the request: the page makes every modem NW + K px tall (K = 1 + the word while NET waits, else 0). Modem 0's
//     documents read K (100vh - NW) and send it as six CSS-chosen requests d/<doc>/<i>/<x>, x = 16 tag + digit: five hex
//     digits of K and their sum mod 16 (`background-image: if(...)`). A resize restyles the document at once, so a new
//     word goes out as soon as the page's frame lays it out. tag is 1 + the word's seq bit (the lib alternates it), and
//     0 (nothing sent) for K = 0 and for the word the document was served for: every new word changes all six URLs, so
//     the gateway acts as soon as all six have come for one tag (a document fetches a URL once);
//   - the answer: modem i's document puts #t (SLOT x SLOT) at x, y = the answers of parts 2i and 2i + 1, R = valid +
//     2 seq + 4 (the part's answer), and its load scrolls to #t. The scroll reaches the page's SLOT x SLOT `overflow:
//     hidden` slot around the iframe (which a NW x NW box clips), whose scrollLeft and scrollTop are then the two Rs
//     (scroll timelines read them on the page). Fragment scrolls cross documents of one origin only, so the modems are in
//     the page's process;
//   - the loads are held: a document refreshes as soon as it has loaded (0 s), and the gateway answers that navigation
//     only once there are new answers for it (or after HOLD ms, with none), so a modem loads once per word, and the old
//     document, still showing, sends the next request (ENGINE_NOTES 62). Each load costs the page two forced style
//     updates (ENGINE_NOTES 63), so two answers per document halve them. A held load holds a connection, and Chrome
//     opens 6 per host: past MAXHELD held loads in one browser (a cookie tells browsers apart) the others poll,
//     refreshing every second.
//
// The page's modems are a group: as it serves a page, the server writes a group id into their URLs (/net/m0.html?g=…&part=i
// &n=P); each modem's first request is redirected to its own session, /net/s/<id>/m0.html (the fragment carries over), and
// its documents' URLs are relative to that. The group computes the answers to a word once, when a request differs from
// the current word, and gives each modem's next load its answers once (later loads carry none: R = 0, so an answer can't
// come back for a later word with the same seq). It resolves relative URLs against the page (the first referrer).
//
// The words (net/device.py has the same protocol for the tests): word = 2 p + seq, p = 4 arg + op. Op 0: arg =
// b0 + 256 b1, URL bytes (b1 unless 0), answers 0. Op 1: GET the URL (relative to the page, or an absolute http(s) URL):
// part 0 answers the status + 1 (> 511 reads 511; 0 if it failed). Op 2: READ the body's next 2 P bytes: part j answers
// bytes 2j and 2j + 1 as b0 + 256 b1 + 65536 n (n of them there).
//
// Other routes, for the probes: /r/<name>?ct=&status=&body=&delay= answers `status` (200) with `body` as `ct` (`none`:
// no Content-Type) and logs a hit; /hits lists the hits as JSON, /reset clears them.
const http = require('http'), fs = require('fs'), path = require('path');

const TYPES = { '.html': 'text/html', '.xhtml': 'application/xhtml+xml', '.svg': 'image/svg+xml', '.css': 'text/css',
  '.js': 'text/javascript', '.json': 'application/json', '.txt': 'text/plain', '.woff2': 'font/woff2', '.png': 'image/png' };
const NOSTORE = { 'Cache-Control': 'no-store' };
const ND = 6;                              // request digits: 5 hex digits of K, then their sum mod 16
const SLOT = 100;                          // the page's slot: SLOT x SLOT px, as #t (machine/net_slot.py)
const NW = (1 << 20) + SLOT;               // the modem iframe's width, and its height without the request
const HOLD = 20000;                        // a held load is answered after this long anyway (with no answer)
const MAXHELD = 4;                         // held loads at once (Chrome opens 6 connections per host; the digits need some)

// a modem document: reloads itself as `next` (m0 <-> m1) after `refresh` seconds; puts #t at x, y = R (two answers).
// With `req` = { doc, kn } (its id, the request it was served for) it also sends the request its height carries (the
// height beyond NW), unless that is still kn
function modemHtml(next, [rx, ry], { req = null, refresh = 0, show = false } = {}) {
  const prop = n => `@property --${n} { syntax: "<integer>"; inherits: true; initial-value: 0; }`;
  const plain = !show;      // (a demo page's modem, /net/m0.html?show, paints a grid and #t)
  let css = '', els = '';
  if (req) {
    const dig = [...Array(ND - 1).keys()].map(i => `--d${i}: mod(round(down, var(--k) / ${16 ** i}), 16);`).join(' ');
    css = [...['k', 'tg', 'x', ...[...Array(ND).keys()].map(i => 'd' + i)].map(prop),
      // tg: 0 (send nothing) for K = 0 and K = kn, else 1 + the word's seq bit, which every new word flips
      `:root { --k: max(0, calc(100vh / 1px - ${NW})); --tg: calc(min(1, var(--k)) * min(1, max(var(--k) - ${req.kn}, ${req.kn} - var(--k))) * (1 + mod(var(--k) - 1, 2)));`,
      `  ${dig} --d${ND - 1}: mod(calc(${[...Array(ND - 1).keys()].map(i => `var(--d${i})`).join(' + ')}), 16); }`,
      'i { position: absolute; left: 0; top: 0; width: 1px; height: 1px; }',
      ...[...Array(ND).keys()].map(i => `#q${i} { --x: calc(var(--tg) * 16 + var(--d${i})); background-image: if(` +
        [...Array(32).keys()].map(x => `style(--x: ${16 + x}): url(d/${req.doc}/${i}/${16 + x})`).join('; ') + '); }')].join('\n');
    els = [...Array(ND).keys()].map(i => `<i id="q${i}"></i>`).join('');
  }
  return `<!DOCTYPE html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="${refresh}; url=${next}#t">
<style>
${css}
html, body { margin: 0; overflow: hidden; }
#t { position: absolute; left: ${rx}px; top: ${ry}px; width: ${SLOT}px; height: ${SLOT}px; }
${plain ? '' : `/* what shows on a demo page (gen_css.py NETSHOW=1, whose iframe asks for /net/m0.html?show): a grid, 10 px and
   100 px lines, and #t, orange, with the answers it stands at */
html { background: repeating-linear-gradient(90deg, #17212b 0 2px, transparent 2px 100px), repeating-linear-gradient(#17212b 0 2px, transparent 2px 100px),
  repeating-linear-gradient(90deg, #c9d1d9 0 1px, transparent 1px 10px), repeating-linear-gradient(#c9d1d9 0 1px, transparent 1px 10px), #eef4ff; }
#t { background: #e8590c; } #t::before { content: "x ${rx}\\A y ${ry}"; white-space: pre; display: block; padding: 6px;
  font: 12px/1.4 ui-monospace, monospace; color: #fff; }`}
</style></head><body>${els}<div id="t"></div></body></html>
`;
}

// a group: one page's modems, and the protocol's state
function group(port, base, n, log) {
  let k = -1, ans = null, url = [], body = Buffer.alloc(0), pos = 0;
  const docs = (n + 1) >> 1;               // modem i answers parts 2i (x) and 2i + 1 (y)
  const served = new Array(docs).fill(-1), waiting = new Map();   // the word whose answers modem i has had; held loads
  async function get(u) {
    try {
      const r = await fetch(new URL(u, base || `http://127.0.0.1:${port}/`), { redirect: 'follow' });
      return [Math.min(511, r.status), Buffer.from(await r.arrayBuffer())];
    } catch (e) { return [-1, Buffer.alloc(0)]; }
  }
  const ready = i => k > 0 && ans !== null && served[i] !== k;
  function release() { for (const [i, w] of [...waiting]) if (ready(i)) { waiting.delete(i); w(); } }
  function act(K) {                        // the answers to word K - 1, one per part (null while a GET is out)
    k = K; const p = (K - 1) >> 1, op = p & 3, arg = p >> 2, z = new Array(n).fill(0);
    log('req', op, arg);
    if (op === 0) { url.push(...[arg & 255, arg >> 8].filter(b => b)); ans = z; return release(); }
    if (op === 1) {
      const u = Buffer.from(url).toString('latin1'); url = []; ans = null;
      get(u).then(([st, b]) => { body = b; pos = 0; log('get', u, st, b.length); if (k === K) { ans = z.slice(); ans[0] = st < 0 ? 0 : st + 1; release(); } });
      return;
    }
    if (op === 2) {
      ans = z.map((_, j) => { const bs = body.subarray(pos + 2 * j, Math.min(body.length, pos + 2 * j + 2)); return (bs[0] || 0) + 256 * (bs[1] || 0) + 65536 * bs.length; });
      pos = Math.min(body.length, pos + 2 * n); return release();
    }
    ans = z; release();
  }
  // the R (x, y) a load of modem i carries: its answers to the current word the first time, else 0 (no answer)
  function take(i) {
    if (!ready(i)) return [0, 0];
    served[i] = k; return [2 * i, 2 * i + 1].map(j => j < n ? 1 + 2 * ((k - 1) & 1) + 4 * ans[j] : 0);
  }
  return { n, log, act, cur: () => k, ready, take, wait: (i, w) => { waiting.set(i, w); return () => waiting.delete(i); } };
}

// a session: one modem (i of group g) over its loads; modem 0 sends the requests
function session(g, i, show, holding) {
  let docs = 0, first = true;
  const sets = new Map();                  // `doc/tag` -> the digits that came per position (true once complete)
  function digit(doc, q, x) {
    const key = `${doc}/${x >> 4}`; let d = sets.get(key);
    if (d === true) return;
    if (!d) { g.log('digit', i, doc); sets.set(key, d = []); for (const k of sets.keys()) if (+k.split('/')[0] < doc - 3) sets.delete(k); }
    (d[q] = d[q] || new Set()).add(x & 15);
    for (let q = 0; q < ND; q++) if (!d[q] || d[q].size !== 1) return;
    sets.set(key, true);
    const v = d.map(s => [...s][0]);
    if (v.slice(0, ND - 1).reduce((a, b) => a + b, 0) % 16 !== v[ND - 1]) return;
    const K = v.slice(0, ND - 1).reduce((a, x, e) => a + x * 16 ** e, 0);
    if (K && K !== g.cur()) g.act(K);
  }
  function load(res, next, refresh) {
    const kn = g.cur(), R = g.take(i);
    g.log('load', i, ...R);
    res.writeHead(200, { 'Content-Type': 'text/html', ...NOSTORE });
    res.end(modemHtml(next, R, { req: i === 0 ? { doc: ++docs, kn } : null, refresh, show }));
  }
  return (req, res, file) => {
    if (file === 'm0.html' || file === 'm1.html') {
      const next = file === 'm0.html' ? 'm1.html' : 'm0.html';
      if (first || g.ready(i)) { first = false; return load(res, next, 0); }
      const holds = holding(req);
      if (holds.n >= MAXHELD) return load(res, next, 1);     // (more modems than connections: they poll)
      // hold the load until this modem has answers (or HOLD ms): the old document stays, and modem 0's sends requests
      holds.n++;
      let done = false;
      const fin = () => { if (done) return false; done = true; holds.n--; clearTimeout(t); un(); return true; };
      const un = g.wait(i, () => { if (fin()) load(res, next, 0); });
      const t = setTimeout(() => { if (fin()) load(res, next, 0); }, HOLD);
      res.on('close', () => { if (!res.writableEnded) fin(); });
      return;
    }
    if (file.startsWith('d/')) {
      const [doc, q, x] = file.split('/').slice(1).map(Number);
      if (q < ND && x >= 16 && x < 48) digit(doc, q, x);
      res.writeHead(204, NOSTORE); return res.end();
    }
    res.writeHead(404, NOSTORE); res.end();
  };
}

function gateway(port, log = () => {}) {
  const sessions = new Map(), groups = new Map(), held = new Map(); let next = 0;
  const holding = req => {                 // a browser's held loads (the connection limit is per browser): its cookie
    const b = (/(?:^|;\s*)netb=(\w+)/.exec(req.headers.cookie || '') || [, ''])[1];
    if (!held.has(b)) held.set(b, { n: 0 });
    return held.get(b);
  };
  const open = (req, res, u) => {          // a modem's first request: its session (and its page's group)
    const q = u.searchParams, gid = q.get('g') || `solo${next + 1}`;
    if (!groups.has(gid)) groups.set(gid, group(port, req.headers.referer || null, +(q.get('n') || 1), log));
    const id = ++next; sessions.set(id, session(groups.get(gid), +(q.get('part') || 0), q.has('show'), holding));
    for (const m of [sessions, groups]) if (m.size > 64) m.delete(m.keys().next().value);
    res.writeHead(302, { Location: `/net/s/${id}/${path.basename(u.pathname)}`, ...NOSTORE }); res.end();
  };
  let gids = 0;
  return {
    '/net/m0.html': open, '/net/m1.html': open,
    '/net/s/': (req, res, u) => {
      const [, , , id, ...rest] = u.pathname.split('/'), s = sessions.get(+id);
      if (!s) { res.writeHead(404, NOSTORE); return res.end(); }
      s(req, res, rest.join('/'));
    },
    gid: () => `p${++gids}`,
  };
}

function serve(root, port, routes = {}, opts = {}) {
  const t0 = Date.now();
  let hits = [], browsers = 0;
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x'), q = Object.fromEntries(u.searchParams);
    if (!/(?:^|;\s*)netb=/.test(req.headers.cookie || '')) res.setHeader('Set-Cookie', `netb=${t0.toString(36)}_${++browsers}; Path=/; SameSite=Lax`);
    if (u.pathname === '/hits') { res.writeHead(200, { 'Content-Type': 'application/json', ...NOSTORE }); return res.end(JSON.stringify(hits)); }
    if (u.pathname === '/reset') { hits = []; res.writeHead(204, NOSTORE); return res.end(); }
    const all = { ...(opts.net === false ? {} : gw), ...routes }; delete all.gid;
    for (const [prefix, fn] of Object.entries(all)) if (prefix.endsWith('/') ? u.pathname.startsWith(prefix) : u.pathname === prefix) {
      if (!prefix.startsWith('/net/')) hits.push({ name: u.pathname, q, t: Date.now() - t0 });
      return fn(req, res, u);
    }
    if (u.pathname.startsWith('/r/')) {
      hits.push({ name: u.pathname.slice(3), q, t: Date.now() - t0 });
      const h = { ...NOSTORE };
      if (q.ct !== 'none') h['Content-Type'] = q.ct || 'text/plain';
      if (q.nosniff) h['X-Content-Type-Options'] = 'nosniff';
      const send = () => { res.writeHead(+(q.status || 200), h); res.end(q.body || ''); };
      return q.delay ? setTimeout(send, +q.delay) : send();
    }
    const f = path.join(root, path.normalize(decodeURIComponent(u.pathname)).replace(/^(\.\.[/\\])+/, ''));
    fs.stat(f, (e, st) => {
      if (e || !st.isFile()) { res.writeHead(404, NOSTORE); return res.end(); }   // (an empty body, as net/device.py's)
      const type = TYPES[path.extname(f)] || 'application/octet-stream';
      res.writeHead(200, { 'Content-Type': type, ...NOSTORE });
      if (opts.net === false || !/html/.test(type)) return fs.createReadStream(f).pipe(res);
      fs.readFile(f, 'utf8', (e2, text) => {       // a page with modems: their group id (a new one per page load)
        if (text.includes('src="/net/m0.html?')) { const g = gw.gid(); text = text.split('src="/net/m0.html?').join(`src="/net/m0.html?g=${g}&amp;`); }
        res.end(text);
      });
    });
  });
  let gw = {};
  return new Promise(ok => srv.listen(port, opts.host || '127.0.0.1', () => { gw = gateway(srv.address().port, opts.log); ok(srv); }));
}

module.exports = { serve, modemHtml, SLOT, NW };

if (require.main === module) {
  const [root = '.', port = '0'] = process.argv.slice(2);
  serve(path.resolve(root), +port, {}, { log: process.env.NETLOG ? (...a) => console.log(...a) : undefined })
    .then(s => console.log('listening', s.address().port));
}
