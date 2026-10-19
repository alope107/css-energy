const http = require('http');
const log = [];
http.createServer((q, r) => {
  const p = new URL(q.url, 'http://x').pathname;
  if (p === '/log') { r.setHeader('content-type', 'application/json'); return r.end(JSON.stringify(log)); }
  log.push(p);
  if (p === '/') {
    r.setHeader('Speculation-Rules', '"/rules.json"'); r.setHeader('content-type', 'text/html'); r.setHeader('cache-control', 'no-store');
    let a = '', b = '';
    for (let i = 0; i < 60; i++) { a += `<a class=w href="/d/a${i}">a${i}</a> `; b += `<a class=w href="/d/b${i}">b${i}</a> `; }
    return r.end(`<!doctype html><style>.B{display:none} #t:checked ~ .A{display:none} #t:checked ~ .B{display:block}</style><input type=checkbox id=t><div class=A>${a}</div><div class=B>${b}</div>`);
  }
  if (p === '/rules.json') { r.setHeader('content-type', 'application/speculationrules+json');
    return r.end(JSON.stringify({ prefetch: [{ source: 'document', where: { selector_matches: '.w' }, eagerness: 'immediate' }] })); }
  if (p.startsWith('/d/')) { r.setHeader('Use-As-Dictionary', 'match="/r/*"'); r.setHeader('Cache-Control', 'public, max-age=31536000'); r.setHeader('Vary', '*'); return r.end('dict' + p); }
  r.statusCode = 404; r.end();
}).listen(+process.argv[2], '127.0.0.1');
