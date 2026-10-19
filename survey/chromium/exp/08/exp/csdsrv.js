const http = require('http');
const log = [];
const png = Buffer.from('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a1d40000000049454e44ae426082', 'hex');
http.createServer((q, r) => {
  const p = new URL(q.url, 'http://x').pathname;
  if (p === '/log') { r.setHeader('content-type', 'application/json'); return r.end(JSON.stringify(log)); }
  log.push(p + ' ' + (q.headers['available-dictionary'] ? 'AD' : '-'));
  r.setHeader('content-type', 'text/html'); r.setHeader('cache-control', 'no-store');
  if (p === '/write') return r.end('<!doctype html><div style="width:1px;height:1px;mask-image:url(/d/1.png)"></div>');
  if (p === '/d/1.png') { r.setHeader('content-type', 'image/png'); r.setHeader('Use-As-Dictionary', 'match="/r/*"'); r.setHeader('Cache-Control', 'public, max-age=31536000'); r.setHeader('Vary', '*'); return r.end(png); }
  if (p.startsWith('/r/')) return r.end('x');
  if (p === '/probe') return r.end('<!doctype html><img src="/r/' + Math.random() + '">');
  if (p === '/reset') return r.end('<!doctype html><div style="width:1px;height:1px;mask-image:url(/reset.png)"></div>');
  if (p === '/reset.png') { r.setHeader('content-type', 'image/png'); r.setHeader('Clear-Site-Data', '"cache"'); return r.end(png); }
  r.statusCode = 404; r.end();
}).listen(+process.argv[2], '127.0.0.1');
