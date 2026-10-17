#!/usr/bin/env node
// Local static server for the dictionary-RAM sites. Zero dependencies (Node 18+).
// Applies the site's Cloudflare-Pages-style _headers and _redirects (200 rewrites) and nothing else:
// responses never depend on request headers, exactly like a static host.
//
//   node serve.js SITE_DIR [PORT]                           plain HTTP on localhost (default 8080)
//   node serve.js SITE_DIR [PORT] --cert C.pem --key K.pem   HTTP/2 over TLS (much faster probes)
//
// Use http://localhost:PORT/ (localhost is a secure context, so dictionaries work).
// For HTTPS the cert must be TRUSTED (e.g. `mkcert localhost`): with a self-signed cert Chrome
// refuses to cache responses, so no dictionary ever registers.
// Flags: --log          print every request with its Available-Dictionary hash (first 8 chars).
//        --delay MS     add latency to every response.
//        --fault NAME   simulate a host that gets one thing wrong, to check selftest/ catches it:
//                       target  match _headers on the rewrite target instead of the request path
//                       strip   drop Use-As-Dictionary (Cloudflare's Shared dictionaries "disabled")
//                       vary    drop `Vary: *`
'use strict';
const fs = require('fs'), path = require('path'), http = require('http'), http2 = require('http2');

const args = process.argv.slice(2);
const flag = n => { const i = args.indexOf(n); return i >= 0 ? args.splice(i, 2)[1] : null; };
const LOG = args.includes('--log'); if (LOG) args.splice(args.indexOf('--log'), 1);
const CERT = flag('--cert'), KEY = flag('--key'), DELAY = +(flag('--delay') || 0), FAULT = flag('--fault');
if (FAULT && !['target', 'strip', 'vary'].includes(FAULT)) throw new Error('--fault: target, strip or vary');
const ROOT = path.resolve(args[0] || '.'), PORT = +(args[1] || (CERT ? 8443 : 8080));

// ---- Cloudflare Pages pattern syntax: :name matches one path segment, * matches anything
function compile(pat) {
  const rx = pat.replace(/[.+^${}()|[\]\\?]/g, '\\$&').replace(/\*/g, '(?<splat>.*)').replace(/:(\w+)/g, '(?<$1>[^/]+)');
  return new RegExp('^' + rx + '$');
}
const sub = (v, groups) => { for (const [k, x] of Object.entries(groups || {})) v = v.split(':' + k).join(x); return v; };

const headerRules = []; let cur = null;
const hp = path.join(ROOT, '_headers');
if (fs.existsSync(hp)) for (const line of fs.readFileSync(hp, 'utf8').split('\n')) {
  if (!line.trim() || line.trim().startsWith('#')) continue;
  if (!/^\s/.test(line)) headerRules.push(cur = { rx: compile(line.trim()), h: [] });
  else { const i = line.indexOf(':'); cur.h.push([line.slice(0, i).trim().toLowerCase(), line.slice(i + 1).trim()]); }
}
const rewrites = [];
const rp = path.join(ROOT, '_redirects');
if (fs.existsSync(rp)) for (const line of fs.readFileSync(rp, 'utf8').split('\n')) {
  const [src, dst, code] = line.trim().split(/\s+/);
  if (!src || src.startsWith('#')) continue;
  if (code !== '200') { console.warn('skipping non-200 rule:', line.trim()); continue; }
  rewrites.push({ rx: compile(src), dst });
}

const TYPES = { '.html': 'text/html; charset=utf-8', '.png': 'image/png', '.css': 'text/css',
  '.js': 'text/javascript', '.svg': 'image/svg+xml', '.json': 'application/json', '.woff2': 'font/woff2' };
const cache = new Map();

function rewrite(urlPath) {
  for (const r of rewrites) { const m = urlPath.match(r.rx); if (m) return sub(r.dst, m.groups); }
  return urlPath;
}

function resolve(urlPath) {
  const file = rewrite(urlPath);
  let fp = path.normalize(path.join(ROOT, decodeURIComponent(file)));
  if (fp !== ROOT && !fp.startsWith(ROOT + path.sep)) return null;              // no escaping the site
  if (file.endsWith('/')) fp = path.join(fp, 'index.html');
  else if (!fs.existsSync(fp) && fs.existsSync(fp + '.html')) fp += '.html';  // pretty URLs, like Pages
  return fp;
}

function respond(method, urlPath, reqHeaders, send) {
  if (DELAY) return setTimeout(() => respond0(method, urlPath, reqHeaders, send), DELAY);
  respond0(method, urlPath, reqHeaders, send);
}
function respond0(method, urlPath, reqHeaders, send) {
  const fp = resolve(urlPath);
  let body = fp && cache.get(fp);
  if (body === undefined) {
    try { body = fs.statSync(fp).isFile() ? fs.readFileSync(fp) : null; } catch { body = null; }
    if (fp && !fp.endsWith('.html')) cache.set(fp, body);                    // data files are immutable
  }
  if (LOG) console.log(Date.now() % 100000, urlPath, 'ad=' + (reqHeaders['available-dictionary'] || '-').slice(1, 9), body ? 200 : 404);
  if (!body) return send(404, { 'content-type': 'text/plain' }, Buffer.from('not found\n'));
  const h = { 'content-type': TYPES[path.extname(fp)] || 'application/octet-stream' };
  const hpath = FAULT === 'target' ? rewrite(urlPath) : urlPath; // matched on the REQUEST path, as Pages does
  for (const r of headerRules) {                         // a header set by two rules is joined with ", ", as Pages does
    const m = hpath.match(r.rx);
    if (m) for (const [k, v] of r.h) h[k] = h[k] && k !== 'content-type' ? h[k] + ', ' + sub(v, m.groups) : sub(v, m.groups);
  }
  if (FAULT === 'strip') delete h['use-as-dictionary'];
  if (FAULT === 'vary' && h.vary === '*') delete h.vary;
  send(200, h, method === 'HEAD' ? null : body, body.length);
}

if (CERT) {
  const srv = http2.createSecureServer({ cert: fs.readFileSync(CERT), key: fs.readFileSync(KEY), allowHTTP1: true,
    settings: { maxConcurrentStreams: 1000 } });
  srv.on('stream', (st, h) => {
    st.on('error', () => {});
    respond(h[':method'], h[':path'].split('?')[0], h, (status, hdrs, body, len) => {
      st.respond({ ':status': status, ...hdrs, 'content-length': len ?? body.length }, { endStream: !body });
      if (body) st.end(body);
    });
  });
  srv.on('sessionError', () => {});
  srv.listen(PORT, () => console.log(`serving ${ROOT} on https://localhost:${PORT}/ (HTTP/2)`));
} else {
  const srv = http.createServer((req, res) => {
    respond(req.method, req.url.split('?')[0], req.headers, (status, hdrs, body, len) => {
      res.writeHead(status, { ...hdrs, 'content-length': len ?? body.length }); res.end(body || undefined);
    });
  });
  srv.keepAliveTimeout = 60000;
  srv.listen(PORT, 'localhost', () => console.log(`serving ${ROOT} on http://localhost:${PORT}/` + (FAULT ? ` (fault: ${FAULT})` : '')));
}
