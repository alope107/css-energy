// server.js — the page's web server and its network gateway (harness and local use; the page itself runs no script).
//
//   node net/server.js <root> [port]      serves <root> with the gateway under /net/; prints `listening <port>`
//
// The page has no script, so the NET instruction (machine/uarch.py) talks to this gateway through P "modems" (layout.json
// net_parts): iframes (machine/gen_css.py) whose documents reload themselves all the time, alternating /net/…/m0.html#t
// and m1.html#t (a refresh to the same URL doesn't reload). Each load:
//   - reads the request K from its own height (the page makes every modem 1 + K px tall: K = 1 + the word while NET
//     waits, else 0), and sends it as six CSS-chosen requests d/<i>/<nonce>/<v>: five hex digits of K and their sum mod
//     16 (`background-image: if(...)`). A resize restyles the document at once, so a new K goes out without a reload;
//   - loads `rx` as a stylesheet. It is served as application/json, which a stylesheet may be only in quirks mode (the
//     modem has no doctype): `:root { --nn: <nonce>; --rx: <R> }`, R = valid + 2 seq + 4 (this part's answer), seq the
//     word's bit 0 (the lib alternates it);
//   - lays out a span R px wide, then #t, and the load scrolls to #t: the scroll reaches the page's 100 px wide
//     `overflow: hidden` slot around the iframe, whose scrollLeft is then R (a scroll timeline reads it on the page).
//     Fragment scrolls cross documents of one origin only, so the modems are in the page's process.
// A load's request counts if every digit came in once, with a matching check digit: a load that saw its height change
// sends a second value for the digits that changed.
//
// The page's modems are a group: as it serves a page, the server writes a group id into their URLs (/net/m0.html?g=…&part=j
// &n=P); each modem's first request is redirected to its own session, /net/s/<id>/m0.html (the fragment carries over), and
// its documents' URLs are relative to that. The group computes the answers to a word once, when a part's request changes
// to it (a part still finishing a load with the last word changes nothing; a word repeated two words later is new again,
// since every part has seen the word between). It resolves relative URLs against the page (the first referrer).
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
const SLOT = 100;                          // the page's slot width = #t's width

// a modem document: quirks mode (no doctype); reloads itself as `next` (m0 <-> m1) after `refresh` seconds
function modemHtml(next, refresh, show = false) {
  const prop = n => `@property --${n} { syntax: "<integer>"; inherits: true; initial-value: 0; }`;
  const dig = [...Array(ND - 1).keys()].map(i => `--d${i}: mod(round(down, var(--k) / ${16 ** i}), 16);`).join(' ');
  const req = [...Array(ND).keys()].map(i => `#q${i} { --x: calc(var(--nn) * 16 + var(--d${i})); background-image: if(` +
    [...Array(32).keys()].map(x => `style(--x: ${x}): url(d/${i}/${x >> 4}/${x & 15})`).join('; ') + `); }`).join('\n');
  const plain = !show;      // (a demo page's modem, /net/m0.html?show, paints a ruler and #t)
  return `<html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="${refresh}; url=${next}#t">
<link rel="stylesheet" href="rx">
<style>
${['k', 'x', 'nn', ...[...Array(ND).keys()].map(i => 'd' + i)].map(prop).join('\n')}
html, body { margin: 0; overflow: hidden; } body { white-space: nowrap; height: ${plain ? 1 : 40}px; font-size: 0; }
:root { --k: max(0, calc(100vh / 1px - 1)); ${dig} --d${ND - 1}: mod(calc(${[...Array(ND - 1).keys()].map(i => `var(--d${i})`).join(' + ')}), 16); }
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

// a group: one page's modems, and the protocol's state
function group(port, base, n, log) {
  let k = -1, ans = null, url = [], body = Buffer.alloc(0), pos = 0;
  async function get(u) {
    try {
      const r = await fetch(new URL(u, base || `http://127.0.0.1:${port}/`), { redirect: 'follow' });
      return [Math.min(511, r.status), Buffer.from(await r.arrayBuffer())];
    } catch (e) { return [-1, Buffer.alloc(0)]; }
  }
  function act(K) {                        // the answers to word K - 1, one per part (null while a GET is out)
    k = K; const p = (K - 1) >> 1, op = p & 3, arg = p >> 2, z = new Array(n).fill(0);
    log('req', op, arg);
    if (op === 0) { url.push(...[arg & 255, arg >> 8].filter(b => b)); ans = z; return; }
    if (op === 1) {
      const u = Buffer.from(url).toString('latin1'); url = []; ans = null;
      get(u).then(([st, b]) => { body = b; pos = 0; log('get', u, st, b.length); if (k === K) { ans = z.slice(); ans[0] = st < 0 ? 0 : st + 1; } });
      return;
    }
    if (op === 2) {
      ans = z.map((_, j) => { const bs = body.subarray(pos + 2 * j, Math.min(body.length, pos + 2 * j + 2)); return (bs[0] || 0) + 256 * (bs[1] || 0) + 65536 * bs.length; });
      pos = Math.min(body.length, pos + 2 * n); return;
    }
    ans = z;
  }
  return { n, act, cur: () => k, answer: (K, j) => (K === k && ans ? ans[j] : null), lastReq: 0 };
}

// a session: one modem (part j of group g) over its loads
function session(g, j, show) {
  let nonce = 0, digits = [], pk = 0;      // pk: the request this part last reported
  function finish() {                      // the last load is complete (its onload led here): its request, if whole and checked
    const d = digits; digits = [];
    for (let i = 0; i < ND; i++) if (!d[i] || d[i].size !== 1) return;
    const v = d.map(x => [...x][0]);
    if (v.slice(0, ND - 1).reduce((a, b) => a + b, 0) % 16 !== v[ND - 1]) return;
    const K = v.slice(0, ND - 1).reduce((a, x, i) => a + x * 16 ** i, 0);
    if (K) g.lastReq = Date.now();
    if (K !== pk) { pk = K; if (K && K !== g.cur()) g.act(K); }
  }
  return (req, res, file) => {
    if (file === 'm0.html' || file === 'm1.html') {
      finish();
      const idle = Date.now() - g.lastReq > 3000;
      res.writeHead(200, { 'Content-Type': 'text/html', ...NOSTORE });
      return res.end(modemHtml(file === 'm0.html' ? 'm1.html' : 'm0.html', idle ? 1 : 0, show));
    }
    if (file === 'rx') {
      nonce ^= 1; digits = [];
      const a = pk ? g.answer(pk, j) : null, R = a === null ? 0 : 1 + 2 * ((pk - 1) & 1) + 4 * a;
      res.writeHead(200, { 'Content-Type': 'application/json', ...NOSTORE });
      return res.end(`:root { --nn: ${nonce}; --rx: ${R}; }\n`);
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
  const sessions = new Map(), groups = new Map(); let next = 0;
  const open = (req, res, u) => {          // a modem's first request: its session (and its page's group)
    const q = u.searchParams, gid = q.get('g') || `solo${next + 1}`;
    if (!groups.has(gid)) groups.set(gid, group(port, req.headers.referer || null, +(q.get('n') || 1), log));
    const id = ++next; sessions.set(id, session(groups.get(gid), +(q.get('part') || 0), q.has('show')));
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
  let hits = [];
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x'), q = Object.fromEntries(u.searchParams);
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

module.exports = { serve, modemHtml, SLOT };

if (require.main === module) {
  const [root = '.', port = '0'] = process.argv.slice(2);
  serve(path.resolve(root), +port, {}, { log: process.env.NETLOG ? (...a) => console.log(...a) : undefined })
    .then(s => console.log('listening', s.address().port));
}
