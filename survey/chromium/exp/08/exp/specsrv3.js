const http = require('http'), crypto = require('crypto');
const log = []; const body = v => Buffer.from(('dict-' + v + '-').repeat(8));
const H = v => ':' + crypto.createHash('sha256').update(body(v)).digest('base64') + ':';
http.createServer((q, r) => {
  const u = new URL(q.url, 'http://x'), p = u.pathname;
  if (p === '/log') { r.setHeader('content-type', 'application/json'); return r.end(JSON.stringify(log)); }
  log.push({ p, ad: q.headers['available-dictionary'] || '', t: Date.now() });
  if (p.startsWith('/page')) {
    const ms = u.searchParams.get('ms'), k = u.searchParams.get('k');
    r.setHeader('Speculation-Rules', '"/rules.json"'); r.setHeader('content-type', 'text/html'); r.setHeader('cache-control', 'no-store');
    return r.end(`<!doctype html><style>
@keyframes pulse { from, to { display: block } }
.w { display: none; visibility: hidden }
#t:checked ~ .w { animation: pulse ${ms}ms }
</style><input type=checkbox id=t><a class=w href="/${k}/d/${k}">w</a>`);
  }
  if (p === '/rules.json') { r.setHeader('content-type', 'application/speculationrules+json');
    return r.end(JSON.stringify({ prefetch: [{ source: 'document', where: { selector_matches: '.w' }, eagerness: 'immediate' }] })); }
  if (/^\/\w+\/d\//.test(p)) { const k = p.split('/')[1];
    setTimeout(() => { r.setHeader('Use-As-Dictionary', 'match="/' + k + '/r/*"'); r.setHeader('Cache-Control', 'public, max-age=31536000'); r.setHeader('Vary', '*'); r.end(body(k)); }, 400); return; }
  if (/^\/\w+\/r\//.test(p)) { r.setHeader('cache-control', 'no-store'); return r.end('ok'); }
  if (p === '/probe') { r.setHeader('content-type', 'text/html'); return r.end(`<!doctype html><img src="/short/r/x"><img src="/long/r/x">`); }
  if (p === '/hash') { r.setHeader('content-type', 'application/json'); return r.end(JSON.stringify({ short: H('short'), long: H('long') })); }
  r.statusCode = 404; r.end();
}).listen(+process.argv[2], '127.0.0.1');
