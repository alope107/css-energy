const http = require('http'), crypto = require('crypto');
const log = []; const body = v => Buffer.from(('dict-' + v + '-').repeat(8));
const H = v => ':' + crypto.createHash('sha256').update(body(v)).digest('base64') + ':';
http.createServer((q, r) => {
  const u = new URL(q.url, 'http://x'), p = u.pathname;
  if (p === '/log') { r.setHeader('content-type', 'application/json'); return r.end(JSON.stringify(log)); }
  log.push({ p, ad: q.headers['available-dictionary'] || '', t: Date.now() });
  if (p.startsWith('/page')) {
    const ms = u.searchParams.get('ms'), k = u.searchParams.get('k'), mode = u.searchParams.get('mode');
    const css = { anim_hidden: `.w{display:none;visibility:hidden} #t:checked ~ .w{animation:pulse ${ms}ms}`,
                  anim_vis: `.w{display:none} #t:checked ~ .w{animation:pulse ${ms}ms}`,
                  toggle_hidden: `.w{display:none;visibility:hidden} #t:checked ~ .w{display:block}`,
                  toggle_opacity: `.w{display:none;opacity:0} #t:checked ~ .w{display:block}`,
                  anim_forwards: `.w{display:none} #t:checked ~ .w{animation:pulse ${ms}ms forwards}` }[mode];
    r.setHeader('Speculation-Rules', '"/rules.json"'); r.setHeader('content-type', 'text/html'); r.setHeader('cache-control', 'no-store');
    return r.end(`<!doctype html><style>
@keyframes pulse { from, to { display: block } }
${css}
</style><input type=checkbox id=t><a class=w href="/${k}/d/${k}">w</a>`);
  }
  if (p === '/rules.json') { r.setHeader('content-type', 'application/speculationrules+json');
    return r.end(JSON.stringify({ prefetch: [{ source: 'document', where: { selector_matches: '.w' }, eagerness: 'immediate' }] })); }
  if (/^\/\w+\/d\//.test(p)) { const k = p.split('/')[1];
    setTimeout(() => { r.setHeader('Use-As-Dictionary', 'match="/' + k + '/r/*"'); r.setHeader('Cache-Control', 'public, max-age=31536000'); r.setHeader('Vary', '*'); r.end(body(k)); }, 400); return; }
  if (/^\/\w+\/r\//.test(p)) { r.setHeader('cache-control', 'no-store'); return r.end('ok'); }
  if (p === '/probe') { r.setHeader('content-type', 'text/html'); return r.end(`<!doctype html>${['anim_hidden','anim_vis','toggle_hidden','toggle_opacity','anim_forwards'].map(m=>'<img src=/'+m+'/r/x>').join('')}`); }
  if (p === '/hash') { r.setHeader('content-type', 'application/json'); return r.end(JSON.stringify(Object.fromEntries(['anim_hidden','anim_vis','toggle_hidden','toggle_opacity','anim_forwards'].map(m=>[m,H(m)])))); }
  r.statusCode = 404; r.end();
}).listen(+process.argv[2], '127.0.0.1');
