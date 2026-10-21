// server.js — the page's web server and its network gateway (harness and local use; the page itself runs no script).
//
//   node net/server.js <root> [port]      serves <root> with the gateway under /net/; prints `listening <port>`
//
// The page has no script, so the NET instruction (machine/uarch.py) talks to this gateway through a "modem": an iframe
// (machine/gen_css.py) whose document reloads itself all the time, alternating /net/…/m0.html#t and m1.html#t (a refresh
// to the same URL doesn't reload). Each load:
//   - reads the request K from its own height (the page makes the iframe 1 + K px tall: K = 1 + (word mod 8192) while NET
//     waits, else 0), and sends it as five CSS-chosen requests d/<i>/<nonce>/<v>: four hex digits of K and their sum mod
//     16 (`background-image: if(...)`). A resize restyles the document at once, so a new K goes out without a reload;
//   - loads `rx` as a stylesheet. It is served as application/json, which a stylesheet may be only in quirks mode (the
//     modem has no doctype): `:root { --nn: <nonce>; --rx: <R> }`, R = valid + 2 seq + 4 (answer mod 2^18), seq the
//     word's bit 12 (the lib alternates it);
//   - lays out a span R px wide, then #t, and the load scrolls to #t: the scroll reaches the page's 100 px wide
//     `overflow: hidden` slot around the iframe, whose scrollLeft is then R (a scroll timeline reads it on the page).
//     Fragment scrolls cross documents of one origin only, so the modem is in the page's process.
// A load's request counts if every digit came in once, with a matching check digit: a load that saw its height change
// sends a second value for the digits that changed. The gateway acts on each K once.
//
// Each modem has its own session: its first request (/net/m0.html#t, the page's iframe) is redirected to
// /net/s/<id>/m0.html (the fragment carries over), and its documents' URLs are relative to that. The session remembers
// the page's URL (the first request's referrer) for relative URLs.
//
// The words (net/device.py has the same protocol for the tests): 256 + b appends byte b to the URL; 512 GETs it (a path
// relative to the page, or an absolute http(s) URL) and answers the status (> 511 reads 511), -1 if it failed; 768
// answers the body's next byte, -1 past its end. Bit 12 of the word is the sequence bit only.
//
// Other routes, for the probes: /r/<name>?ct=&status=&body=&delay= answers `status` (200) with `body` as `ct` (`none`:
// no Content-Type) and logs a hit; /hits lists the hits as JSON, /reset clears them.
const http = require('http'), fs = require('fs'), path = require('path');

const TYPES = { '.html': 'text/html', '.xhtml': 'application/xhtml+xml', '.svg': 'image/svg+xml', '.css': 'text/css',
  '.js': 'text/javascript', '.json': 'application/json', '.txt': 'text/plain', '.woff2': 'font/woff2', '.png': 'image/png' };
const NOSTORE = { 'Cache-Control': 'no-store' };
const ND = 5;                              // request digits: 4 hex digits of K, then their sum mod 16
const SLOT = 100;                          // the page's slot width = #t's width

// a modem document: quirks mode (no doctype); reloads itself as `next` (m0 <-> m1) after `refresh` seconds
function modemHtml(next, refresh, show = false) {
  const prop = n => `@property --${n} { syntax: "<integer>"; inherits: true; initial-value: 0; }`;
  const dig = [...Array(4).keys()].map(i => `--d${i}: mod(round(down, var(--k) / ${16 ** i}), 16);`).join(' ');
  const req = [...Array(ND).keys()].map(i => `#q${i} { --x: calc(var(--nn) * 16 + var(--d${i})); background-image: if(` +
    [...Array(32).keys()].map(x => `style(--x: ${x}): url(d/${i}/${x >> 4}/${x & 15})`).join('; ') + `); }`).join('\n');
  const plain = !show;      // (a demo page's modem, /net/m0.html?show, paints a ruler and #t)
  return `<html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="${refresh}; url=${next}#t">
<link rel="stylesheet" href="rx">
<style>
${['k', 'd0', 'd1', 'd2', 'd3', 'd4', 'x', 'nn'].map(prop).join('\n')}
html, body { margin: 0; overflow: hidden; } body { white-space: nowrap; height: ${plain ? 1 : 40}px; font-size: 0; }
:root { --k: max(0, calc(100vh / 1px - 1)); ${dig} --d4: mod(calc(var(--d0) + var(--d1) + var(--d2) + var(--d3)), 16); }
i { position: absolute; left: 0; top: 0; width: 1px; height: 1px; }
${req}
span { display: inline-block; height: ${plain ? 1 : 40}px; } .v { width: calc(var(--rx, 0) * 1px); } #t { width: ${SLOT}px; }
${plain ? '' : `/* what shows on a demo page (gen_css.py NETSHOW=1, whose iframe asks for /net/m0.html?show): a ruler, 10 px ticks and
   100 px marks, up to #t, which is orange */
.v { background: repeating-linear-gradient(90deg, #17212b 0 2px, transparent 2px 100px) 0 0 / auto 40px no-repeat,
  repeating-linear-gradient(90deg, #8a96a3 0 1px, transparent 1px 10px) 0 24px / auto 16px no-repeat, #eef4ff; }
#t { background: #e8590c; }`}
</style></head><body>${[...Array(ND).keys()].map(i => `<i id="q${i}"></i>`).join('')}<span class="v"></span><span id="t"></span></body></html>
`;
}

// a gateway session: the protocol above over one modem's loads
function session(port, base, log, show) {
  let nonce = 0, digits = [], done = -1, lastReq = 0, resp = 0;     // resp: R
  let url = [], body = Buffer.alloc(0), pos = 0;
  const answer = (s, v) => { resp = 1 + 2 * s + 4 * (((v % (1 << 18)) + (1 << 18)) % (1 << 18)); };
  async function get(u) {
    try {
      const r = await fetch(new URL(u, base || `http://127.0.0.1:${port}/`), { redirect: 'follow' });
      return [Math.min(511, r.status), Buffer.from(await r.arrayBuffer())];
    } catch (e) { return [-1, Buffer.alloc(0)]; }
  }
  function act(K) {
    if (K === 0) { resp = 0; return; }     // idle: no valid answer until the next request
    const p = (K - 1) % 4096, s = ((K - 1) >> 12) & 1;
    log('req', p, s);
    if (p > 256 && p < 512) { url.push(p - 256); return answer(s, 0); }
    if (p === 512) {
      const u = Buffer.from(url).toString('latin1'); url = []; resp = 0;
      get(u).then(([st, b]) => { body = b; pos = 0; log('get', u, st, b.length); answer(s, st); });
      return;
    }
    if (p === 768) return answer(s, pos < body.length ? body[pos++] : -1);
    answer(s, 0);
  }
  function finish() {                      // the last load is complete (its onload led here): its request, if whole and checked
    const d = digits; digits = [];
    for (let i = 0; i < ND; i++) if (!d[i] || d[i].size !== 1) return;
    const [d0, d1, d2, d3, d4] = d.map(x => [...x][0]);
    if ((d0 + d1 + d2 + d3) % 16 !== d4) return;
    const K = d0 + 16 * d1 + 256 * d2 + 4096 * d3;
    if (K) lastReq = Date.now();
    if (K !== done) { done = K; act(K); }
  }
  return (req, res, file) => {
    if (file === 'm0.html' || file === 'm1.html') {
      finish();
      const idle = Date.now() - lastReq > 3000;
      res.writeHead(200, { 'Content-Type': 'text/html', ...NOSTORE });
      return res.end(modemHtml(file === 'm0.html' ? 'm1.html' : 'm0.html', idle ? 1 : 0, show));
    }
    if (file === 'rx') {
      nonce ^= 1; digits = [];
      res.writeHead(200, { 'Content-Type': 'application/json', ...NOSTORE });
      return res.end(`:root { --nn: ${nonce}; --rx: ${resp}; }\n`);
    }
    if (file.startsWith('d/')) {
      const [i, n, v] = file.split('/').slice(1).map(Number);
      if (n === nonce && i < ND) (digits[i] = digits[i] || new Set()).add(v);
      res.writeHead(204, NOSTORE); return res.end();
    }
    res.writeHead(404, NOSTORE); res.end();
  };
}

function gateway(port, log = () => {}) {
  const sessions = new Map(); let next = 0;
  const open = (req, res, u) => {          // a modem's first request: its session
    const id = ++next; sessions.set(id, session(port, req.headers.referer || null, log, u.searchParams.has('show')));
    if (sessions.size > 32) sessions.delete(sessions.keys().next().value);
    res.writeHead(302, { Location: `/net/s/${id}/${path.basename(u.pathname)}`, ...NOSTORE }); res.end();
  };
  return {
    '/net/m0.html': open, '/net/m1.html': open,
    '/net/s/': (req, res, u) => {
      const [, , , id, ...rest] = u.pathname.split('/'), s = sessions.get(+id);
      if (!s) { res.writeHead(404, NOSTORE); return res.end(); }
      s(req, res, rest.join('/'));
    },
  };
}

function serve(root, port, routes = {}, opts = {}) {
  const t0 = Date.now();
  let hits = [];
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x'), q = Object.fromEntries(u.searchParams);
    if (u.pathname === '/hits') { res.writeHead(200, { 'Content-Type': 'application/json', ...NOSTORE }); return res.end(JSON.stringify(hits)); }
    if (u.pathname === '/reset') { hits = []; res.writeHead(204, NOSTORE); return res.end(); }
    const all = { ...(opts.net === false ? {} : gw), ...routes };
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
      res.writeHead(200, { 'Content-Type': TYPES[path.extname(f)] || 'application/octet-stream', ...NOSTORE });
      fs.createReadStream(f).pipe(res);
    });
  });
  let gw = {};
  return new Promise(ok => srv.listen(port, opts.host || '127.0.0.1', () => { gw = gateway(srv.address().port, opts.log); ok(srv); }));
}

module.exports = { serve, modemHtml, SLOT };

if (require.main === module) {
  const [root = '.', port = '0'] = process.argv.slice(2);
  serve(path.resolve(root), +port, {}, { log: process.env.NETLOG ? (...a) => console.log(...a) : undefined })
    .then(s => console.log('listening', s.address().port));
}
