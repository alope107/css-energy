// harness server: /f?n= serves a frame with n hanging images; /img/* never answers
const http = require('http');
let seen = 0;
const srv = http.createServer((q, r) => {
  const u = new URL(q.url, 'http://x');
  if (u.pathname === '/img') { seen++; return; }          // hang forever
  if (u.pathname === '/seen') { r.end(String(seen)); return; }
  if (u.pathname === '/f') {
    const n = +u.searchParams.get('n'), id = u.searchParams.get('id');
    let h = '<!doctype html><body>';
    for (let i = 0; i < n; i++) h += `<img src="/img?f=${id}&i=${i}" width=1 height=1>`;
    r.setHeader('content-type', 'text/html'); r.end(h); return;
  }
  if (u.pathname === '/') {
    const k = +u.searchParams.get('k'), n = +u.searchParams.get('n');
    let h = '<!doctype html><body>';
    for (let j = 0; j < k; j++) h += `<iframe src="/f?n=${n}&id=${j}" width=10 height=10></iframe>`;
    r.setHeader('content-type', 'text/html'); r.end(h); return;
  }
  r.statusCode = 404; r.end();
});
srv.keepAliveTimeout = 0;
srv.listen(+process.argv[2], '127.0.0.1');
