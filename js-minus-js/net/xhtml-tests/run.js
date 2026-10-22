// run.js — the two xhtml-tests on this repo's launcher (their run.py needs Python Playwright, which isn't installed here).
//   node net/xhtml-tests/run.js [quirks|readback]
// Serves each test's www/ and its "third-party" API on the ports the pages hard-code (srv.py's behaviour), then
// performs run.py's checks. Values the readback API serves come from readback/v.txt, as in srv.py.
const fs = require('fs'), path = require('path'), http = require('http');
const { launch } = require('../../tools/browser.js');
const HERE = __dirname;
const sleep = ms => new Promise(r => setTimeout(r, ms));

function srv(root, port, api) {
  const s = http.createServer((req, res) => {
    const p = req.url.split('?')[0];
    const h = { 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store' };
    if (p === '/api') { const [ct, body] = api(); res.writeHead(200, { ...h, 'Content-Type': ct }); return res.end(body); }
    const f = path.join(root, p.replace(/^\/+/, ''));
    if (!fs.existsSync(f) || !fs.statSync(f).isFile()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { ...h, 'Content-Type': f.endsWith('.xhtml') ? 'application/xhtml+xml' : 'text/html' });
    res.end(fs.readFileSync(f));
  });
  return new Promise(ok => s.listen(port, '127.0.0.1', () => ok(s)));
}

async function quirks(b) {
  const www = path.join(HERE, 'quirks', 'www');
  const a = await srv(www, 9471, () => ['text/plain', '*{--t:"42"} #m{width:42px;height:17px}']);
  const c = await srv(www, 9472, () => ['text/plain', '*{--t:"42"} #m{width:42px;height:17px}']);
  const pg = await b.newPage();
  await pg.goto('http://127.0.0.1:9471/parent.xhtml', { waitUntil: 'networkidle' }); await sleep(500);
  console.log('quirks: parent', await pg.evaluate(() => [document.contentType, document.compatMode, document.documentElement.namespaceURI]));
  for (const fid of ['oq', 'os', 'iq', 'dq', 'ds']) {
    const r = await pg.evaluate(id => { const e = document.getElementById(id); let d;
      try { d = e.contentDocument; } catch (x) { return 'no access: ' + x.message; }
      if (!d) return 'no contentDocument (opaque origin?)';
      const m = d.getElementById('m'); const cs = m && d.defaultView.getComputedStyle(m);
      return { mode: d.compatMode, type: d.contentType, w: cs && cs.width, t: cs && cs.getPropertyValue('--t') }; }, fid);
    // dq / ds are data: children: Playwright can still read them through their frame
    const fr = pg.frames().find(f => f.url().startsWith('data:') && (fid === 'dq' ? !f.url().includes('doctype') : f.url().includes('doctype')));
    const r2 = (fid === 'dq' || fid === 'ds') && fr ? await fr.evaluate(() => { const m = document.getElementById('m'); const cs = getComputedStyle(m);
      return { mode: document.compatMode, w: cs.width, t: cs.getPropertyValue('--t') }; }) : null;
    console.log('  ', fid, JSON.stringify(r), r2 ? 'via frame: ' + JSON.stringify(r2) : '');
  }
  await pg.close(); a.close(); c.close();
}

async function readback(b) {
  const D = path.join(HERE, 'readback'), www = path.join(D, 'www');
  const setv = v => fs.writeFileSync(path.join(D, 'v.txt'), String(v));
  const log = [];
  const a = await srv(www, 9481, () => ['text/plain', '']);
  const c = await srv(www, 9482, () => { const v = fs.readFileSync(path.join(D, 'v.txt'), 'utf8').trim(); log.push(v); return ['text/plain', `.v{width:${v}px}`]; });
  for (const url of ['http://127.0.0.1:9481/p.html', 'http://127.0.0.1:9481/p.xhtml']) {
    setv(1234); const pg = await b.newPage(); await pg.goto(url); const t0 = Date.now(); const seen = [];
    for (const [vNext, at] of [[57, 3.0], [2999, 7.0], [0, 11.0], [null, 15.0]]) {
      while (Date.now() - t0 < at * 1000) {
        const r = await pg.evaluate(() => [document.contentType, document.querySelector('.slot').scrollLeft, getComputedStyle(document.querySelector('.out')).getPropertyValue('--r').trim()]);
        if (!seen.length || JSON.stringify(seen[seen.length - 1].slice(1)) !== JSON.stringify(r)) seen.push([+((Date.now() - t0) / 1000).toFixed(1), ...r]);
        await sleep(100);
      }
      if (vNext !== null) setv(vNext);
    }
    console.log('readback:', url);
    for (const s of seen) console.log('   ', JSON.stringify(s));
    console.log('    rendered:', JSON.stringify(await pg.evaluate(() => getComputedStyle(document.querySelector('.out'), '::after').content)));
    await pg.close();
  }
  console.log('    API served values:', log.join(' '));
  a.close(); c.close();
}

(async () => {
  const which = process.argv[2];
  const b = await launch();
  console.log('browser', b.version());
  if (!which || which === 'quirks') await quirks(b);
  if (!which || which === 'readback') await readback(b);
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
