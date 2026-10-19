const http = require('http'), crypto = require('crypto');
const log = [];
const dict = v => Buffer.from(`dictionary-body-${v}-`.repeat(4));
http.createServer((q, r) => {
  const u = new URL(q.url, 'http://x'), p = u.pathname;
  const entry = { p: q.url, purpose: q.headers['sec-purpose'] || '', ad: q.headers['available-dictionary'] || '', dest: q.headers['sec-fetch-dest'] || '' };
  if (p !== '/log') log.push(entry);
  if (p === '/log') { r.setHeader('content-type', 'application/json'); return r.end(JSON.stringify({ log, hashes: Object.fromEntries([1,2,3,4,5,6].map(v => [v, ':' + crypto.createHash('sha256').update(dict(v)).digest('base64') + ':'])) })); }
  if (p === '/') {
    r.setHeader('Speculation-Rules', '"/rules.json"'); r.setHeader('content-type', 'text/html'); r.setHeader('cache-control', 'no-store');
    return r.end(`<!doctype html><style>.h{display:none} #t:checked ~ .h{display:block}</style>
<input type=checkbox id=t><a class=w href="/d/1">one</a><div class=h><a class=w href="/d/2">two</a></div>
<p><a class=m href="/d/3" id=m3 style="display:inline-block;width:80px;height:30px">h3</a><a class=m href="/d/4" id=m4 style="display:inline-block;width:80px;height:30px">h4</a><a class=m href="/d/5" id=m5 style="display:inline-block;width:80px;height:30px">h5</a></p><a class=w href="/d/6">six</a><a class=w href="/d/6">six again</a>`);
  }
  if (p === '/rules.json') { r.setHeader('content-type', 'application/speculationrules+json');
    return r.end(JSON.stringify({ prefetch: [{ source: 'document', where: { selector_matches: '.w' }, eagerness: 'immediate' }, { source: 'document', where: { selector_matches: '.m' }, eagerness: 'moderate' }] })); }
  if (p.startsWith('/d/')) { const v = p.slice(3);
    r.setHeader('Use-As-Dictionary', 'match="/r/*"'); r.setHeader('Cache-Control', 'public, max-age=31536000'); r.setHeader('Vary', '*'); r.setHeader('content-type', 'text/html');
    return r.end(dict(v)); }
  if (p.startsWith('/r/')) { r.setHeader('cache-control', 'no-store'); r.setHeader('content-type', 'text/plain'); return r.end('ok'); }
  if (p === '/probe') { r.setHeader('content-type', 'text/html'); r.setHeader('cache-control', 'no-store'); return r.end(`<!doctype html><img src="/r/x?${u.searchParams.get('n')}">`); }
  r.statusCode = 404; r.end();
}).listen(+process.argv[2], '127.0.0.1');
