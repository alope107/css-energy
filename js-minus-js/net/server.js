// server.js — the page's web server and its network gateway (harness and local use; the page itself runs no script).
//
//   node net/server.js <root> [port]      serves <root> with the gateway under /net/; prints `listening <port>`
//
// The page has no script, so the NET instruction (machine/uarch.py) talks to this gateway through a "modem": an
// iframe (machine/gen_fvm4.py) whose document, /net/modem.html, reloads itself all the time. Each load:
//   - reads the request word from its own width (the page sets the iframe's width: 1 + K, K = 2 Q + s, Q = 0 idle or
//     1 + the word, s the page's sequence bit), and sends it as five CSS-chosen requests /net/d/<i>/<nonce>/<v>: four
//     hex digits of K and their sum mod 16 (`background-image: if(...)`, fired by the load's own style);
//   - loads /net/rx as a stylesheet. It is served as application/json, which a stylesheet may be only in quirks mode
//     (the modem has no doctype): `:root { --nn: <nonce>; --rx: <R> }`, R = valid + 2 s + 4 (answer mod 1024);
//   - reports R as its content height through responsive iframes (`frame-sizing: content-height` on the page, a
//     `responsive-embedded-sizing` meta here). The height is measured with the viewport the load started with, which
//     is the iframe's height then: it can't shrink, so the modem grows it by less than 4096 px to the next value that is
//     R mod 4096, and the page reads it mod 4096. Past 2^24 px a load says so (/net/h/1) and the next one goes through
//     /net/reset.html, which isn't opted in: the iframe falls back to 150 px (even: no valid answer).
// A load's request counts if every digit came in once, with a matching check digit: a load that saw the width change after
// its style was computed restyles, and sends a second value for the digits that changed. The answer to K is valid with
// sequence bit s: the page waits for that.
//
// The words (net/device.py has the same protocol for the tests): 256 + b appends byte b to the URL; 512 GETs it (a path
// relative to the page, which the modem's first request names as its referrer, or an absolute http(s) URL), and
// answers the status (> 511 reads 511), -1 if it failed; 768 answers the body's next byte, -1 past its end.
//
// Other routes, for the probes: /r/<name>?ct=&status=&body=&delay= answers `status` (200) with `body` as `ct` (`none`:
// no Content-Type) and logs a hit; /hits lists the hits as JSON, /reset clears them.
const http = require('http'), fs = require('fs'), path = require('path');

const TYPES = { '.html': 'text/html', '.xhtml': 'application/xhtml+xml', '.svg': 'image/svg+xml', '.css': 'text/css',
  '.js': 'text/javascript', '.json': 'application/json', '.txt': 'text/plain', '.woff2': 'font/woff2', '.png': 'image/png' };
const NOSTORE = { 'Cache-Control': 'no-store' };
const HMAX = 1 << 24;                      // modem heights past this get a reset
const ND = 5;                              // request digits: 4 hex digits of K, then their sum mod 16

// the modem document: quirks mode (no doctype), opted in to responsive sizing (Chrome 153 reads the meta's content as
// the allowed origins, 155+ as `allow-origins=…`: each ignores the other's), reloads itself after `refresh` seconds
function modemHtml(refresh) {
  const prop = n => `@property --${n} { syntax: "<integer>"; inherits: true; initial-value: 0; }`;
  const dig = [...Array(4).keys()].map(i => `--d${i}: mod(round(down, var(--k) / ${16 ** i}), 16);`).join(' ');
  const req = [...Array(ND).keys()].map(i => `#q${i} { --x: calc(var(--nn) * 16 + var(--d${i})); background-image: if(` +
    [...Array(32).keys()].map(x => `style(--x: ${x}): url(/net/d/${i}/${x >> 4}/${x & 15})`).join('; ') + `); }`).join('\n');
  return `<html><head>
<meta name="responsive-embedded-sizing" content="*">
<meta name="responsive-embedded-sizing" content="allow-origins=*">
<meta http-equiv="refresh" content="${refresh}">
<link rel="stylesheet" href="/net/rx">
<style>
${['k', 'd0', 'd1', 'd2', 'd3', 'd4', 'x', 'nn', 'hb'].map(prop).join('\n')}
html, body { margin: 0; }
:root { --k: calc(100vw / 1px - 1); ${dig} --d4: mod(calc(var(--d0) + var(--d1) + var(--d2) + var(--d3)), 16);
  --hb: clamp(0, round(down, 100vh / ${HMAX}px), 1); }
i { position: absolute; left: 0; top: 0; width: 1px; height: 1px; }
${req}
#h { background-image: if(style(--hb: 1): url(/net/h/1); else: url(/net/h/0)); }
#v { height: calc(100vh + mod(var(--rx, 0) * 1px - 100vh, 4096px)); }   /* (the fallback: the DOMContentLoaded report, which
   can come before /net/rx applies, is invalid; reporting the viewport instead could show an answer two words old) */
</style></head><body>${[...Array(ND).keys()].map(i => `<i id="q${i}"></i>`).join('')}<i id="h"></i><div id="v"></div></body></html>
`;
}
const RESET = `<html><head><meta http-equiv="refresh" content="0; url=/net/modem.html"></head><body></body></html>\n`;

// the gateway: the protocol above over a modem's loads
function gateway(port, log = () => {}) {
  let base = null;                         // the page's URL, for relative URLs (the modem's first referrer, or setBase)
  let nonce = 0, digits = [], hb = 0, done = -1, lastReq = 0;
  let resp = 0;                            // R
  let url = [], body = Buffer.alloc(0), pos = 0;
  const answer = (s, v) => { resp = 1 + 2 * s + 4 * (((v % 1024) + 1024) % 1024); };
  async function get(u) {
    try {
      const r = await fetch(new URL(u, base || `http://127.0.0.1:${port}/`), { redirect: 'follow' });
      return [Math.min(511, r.status), Buffer.from(await r.arrayBuffer())];
    } catch (e) { return [-1, Buffer.alloc(0)]; }
  }
  function act(K) {
    const Q = K >> 1, s = K & 1;
    if (Q === 0) { resp = 0; return; }     // idle: no valid answer until the next request
    const p = (Q - 1) % 4096;
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
    if (K >> 1) lastReq = Date.now();
    if (K !== done) { done = K; act(K); }
  }
  return {
    setBase: u => { base = u; },
    '/net/modem.html': (req, res) => {
      const ref = req.headers.referer;
      if (ref && !/\/net\/(modem|reset)\.html/.test(ref)) base = ref;
      finish();
      const idle = Date.now() - lastReq > 3000;
      res.writeHead(200, { 'Content-Type': 'text/html', ...NOSTORE });
      res.end(hb ? RESET : modemHtml(idle ? 1 : 0)); hb = 0;
    },
    '/net/reset.html': (req, res) => { res.writeHead(200, { 'Content-Type': 'text/html', ...NOSTORE }); res.end(RESET); },
    '/net/rx': (req, res) => {
      nonce ^= 1; digits = [];
      res.writeHead(200, { 'Content-Type': 'application/json', ...NOSTORE });
      res.end(`:root { --nn: ${nonce}; --rx: ${resp}; }\n`);
    },
    '/net/d/': (req, res, u) => {
      const [i, n, v] = u.pathname.split('/').slice(3).map(Number);
      if (n === nonce && i < ND) (digits[i] = digits[i] || new Set()).add(v);
      res.writeHead(204, NOSTORE); res.end();
    },
    '/net/h/': (req, res, u) => { if (u.pathname.endsWith('/1')) hb = 1; res.writeHead(204, NOSTORE); res.end(); },
  };
}

function serve(root, port, routes = {}, opts = {}) {
  const t0 = Date.now();
  let hits = [];
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x'), q = Object.fromEntries(u.searchParams);
    if (u.pathname === '/hits') { res.writeHead(200, { 'Content-Type': 'application/json', ...NOSTORE }); return res.end(JSON.stringify(hits)); }
    if (u.pathname === '/reset') { hits = []; res.writeHead(204, NOSTORE); return res.end(); }
    const all = { ...(opts.net === false ? {} : gw), ...routes }; delete all.setBase;
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
      // a page with the modem, opened at 127.0.0.1: the modem goes to localhost, a different site, so Chrome runs it in
      // its own process (site isolation) instead of between the page's frames on its main thread (ENGINE_NOTES 55). Only
      // then: through a port forward, localhost may be all that reaches the server. The gateway resolves the page's
      // relative URLs against this URL (a cross-site modem's referrer is only the origin)
      fs.readFile(f, 'utf8', (e2, text) => {
        const host = (req.headers.host || '').split(':')[0];
        if (text.includes('src="/net/modem.html"')) {
          gw.setBase(`http://${req.headers.host}${u.pathname}`);
          if (opts.oopif !== false && host === '127.0.0.1') text = text.replace('src="/net/modem.html"', `src="http://localhost:${srv.address().port}/net/modem.html"`);
        }
        res.end(text);
      });
    });
  });
  let gw = {};
  return new Promise(ok => srv.listen(port, opts.host || '127.0.0.1', () => { gw = gateway(srv.address().port, opts.log); ok(srv); }));
}

module.exports = { serve, modemHtml };

if (require.main === module) {
  const [root = '.', port = '0'] = process.argv.slice(2);
  serve(path.resolve(root), +port, {}, { log: process.env.NETLOG ? (...a) => console.log(...a) : undefined })
    .then(s => console.log('listening', s.address().port));
}
