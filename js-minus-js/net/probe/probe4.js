// probe4.js — what a data: child document can read from other origins, and whether it can report back (harness only).
//   node net/probe/probe4.js
// 1. A data:text/html document (quirks mode, opaque origin) in an iframe loads cross-origin responses as stylesheets:
//    which Content-Types apply, with and without CORS; an <object>'s 404 fallback; a cross-origin font as a data carrier.
// 2. The same child opts in to responsive sizing: does its content height reach the page's iframe?
// 3. The data: URL navigation cap: the longest inert document an iframe still loads.
const path = require('path');
const B = require('../../tools/browser.js');
const { serve } = require('../server.js');
const ROOT = path.join(__dirname, '..', '..', 'build', 'netprobe');

(async () => {
  const page = await serve(ROOT, 0, {}, { net: false }), pbase = `http://127.0.0.1:${page.address().port}/`;
  // the "API": another origin (another port), answering CSS text under several types, with or without CORS headers
  const api = await serve(ROOT, 0, {
    '/a/': (req, res, u) => {
      const [, , kind, k] = u.pathname.split('/'), q = Object.fromEntries(u.searchParams);
      const h = { 'Cache-Control': 'no-store' };
      if (q.cors) h['Access-Control-Allow-Origin'] = '*';
      if (kind === '404') { res.writeHead(404, h); return res.end(); }
      h['Content-Type'] = { css: 'text/css', json: 'application/json', txt: 'text/plain', html: 'text/html', none: undefined }[kind];
      if (!h['Content-Type']) delete h['Content-Type'];
      res.writeHead(200, h); res.end(`#z{--k:${k}}`);
    },
  }, { net: false });
  const abase = `http://localhost:${api.address().port}/a/`;
  const b = await B.launch({ extraArgs: ['--enable-blink-features=ResponsiveIframes'] });
  const p = await b.newPage({ viewport: { width: 1000, height: 800 } });
  const doc = body => 'data:text/html,' + encodeURIComponent(body);
  const child = async body => {
    await p.setContent(`<!doctype html><style>iframe{border:0;width:300px;frame-sizing:content-height}</style><iframe id=f src="${doc(body)}"></iframe>`);
    await p.waitForTimeout(1500);
    return p.frames()[1];
  };

  // 1. response channels: each <link> in its own child (one origin, one request each)
  console.log('1. cross-origin stylesheets in a data: child (quirks)');
  for (const [label, kind, attrs, cors] of [
    ['text/css, no CORS', 'css', '', 0], ['application/json, no CORS', 'json', '', 0],
    ['application/json + ACAO, crossorigin', 'json', 'crossorigin', 1], ['application/json + ACAO, no crossorigin attr', 'json', '', 1],
    ['application/json, crossorigin attr, no ACAO', 'json', 'crossorigin', 0],
    ['text/plain + ACAO, crossorigin', 'txt', 'crossorigin', 1], ['text/html + ACAO, crossorigin', 'html', 'crossorigin', 1],
    ['no Content-Type, no CORS', 'none', '', 0], ['no Content-Type + ACAO, crossorigin', 'none', 'crossorigin', 1]]) {
    const f = await child(`<link rel=stylesheet ${attrs} href="${abase}${kind}/7?cors=${cors}"><i id=z></i>`);
    const k = await f.evaluate(() => [document.compatMode, getComputedStyle(document.getElementById('z')).getPropertyValue('--k').trim()]);
    console.log(`  ${k[1] === '7' ? 'APPLIED' : 'not applied'}  ${label}  (${k[0]})`);
  }
  // the same two in a standards-mode child, for contrast
  for (const [label, kind, attrs, cors] of [['standards mode: application/json + ACAO, crossorigin', 'json', 'crossorigin', 1], ['standards mode: text/css', 'css', '', 0]]) {
    const f = await child(`<!doctype html><link rel=stylesheet ${attrs} href="${abase}${kind}/7?cors=${cors}"><i id=z></i>`);
    const k = await f.evaluate(() => [document.compatMode, getComputedStyle(document.getElementById('z')).getPropertyValue('--k').trim()]);
    console.log(`  ${k[1] === '7' ? 'APPLIED' : 'not applied'}  ${label}  (${k[0]})`);
  }
  // an <object>'s fallback shows on a 404: one bit about any URL
  {
    const f = await child(`<object data="${abase}404/0" style="display:block;width:50px;height:20px"><i id=fb>fb</i></object><object data="${abase}txt/1" style="display:block;width:50px;height:20px"><i id=fb2>fb</i></object>`);
    const r = await f.evaluate(() => [document.getElementById('fb').getClientRects().length > 0, document.getElementById('fb2').getClientRects().length > 0]);
    console.log(`  <object> fallback shown: 404 ${r[0]}, 200 text ${r[1]}`);
  }

  // 2. the return channel: an opted-in data: child's content height on the page's iframe
  console.log('2. responsive height from a data: child');
  for (const [label, meta] of [['content="*" (153 syntax)', '<meta name=responsive-embedded-sizing content="*">'],
    ['both metas', '<meta name=responsive-embedded-sizing content="*"><meta name=responsive-embedded-sizing content="allow-origins=*">'],
    ['no meta', '']]) {
    await child(`${meta}<style>html,body{margin:0}</style><div style="height:345px"></div>`);
    const h = await p.evaluate(() => document.getElementById('f').getBoundingClientRect().height);
    console.log(`  height ${h} (345 = reported; 150 = not)  ${label}`);
  }
  // and from a data: child reached by a form submission (GET, target the iframe), which is how the program would get there
  {
    await p.setContent(`<!doctype html><style>iframe{border:0;width:300px;frame-sizing:content-height}</style>
      <form method=get action="data:text/html,${encodeURIComponent('<meta name=responsive-embedded-sizing content="*"><style>html,body{margin:0}</style><div style="height:345px"></div><p>')}" target=ch>
      <input type=hidden name=q value="tail"><button id=go>go</button></form><iframe id=f name=ch></iframe>`);
    await p.waitForTimeout(500); await p.click('#go'); await p.waitForTimeout(1500);
    const h = await p.evaluate(() => document.getElementById('f').getBoundingClientRect().height);
    const u = p.frames()[1] && p.frames()[1].url();
    console.log(`  after a form GET into the iframe: height ${h}; child URL ${u && u.slice(0, 40)}… (query appended: ${u && u.includes('?q=tail')})`);
  }

  // 3. the data: URL cap: an inert document padded with a comment
  console.log('3. data: URL navigation cap');
  for (const kb of [1000, 1900, 2000, 2030, 2050, 2100]) {
    const body = `<i id=z></i><!--${'x'.repeat(kb * 1024)}-->`;
    await p.setContent(`<!doctype html><iframe id=f src="data:text/html,${body}"></iframe>`);
    await p.waitForTimeout(800);
    const ok = await p.frames()[1].evaluate(() => !!document.getElementById('z')).catch(() => false);
    console.log(`  ${kb} KB: ${ok ? 'loaded' : 'did not load'}`);
  }
  await b.close(); page.close(); api.close();
})().catch(e => { console.error(e); process.exit(1); });
// Results (2026-10-20, Chromium 153.0.8010.12, --enable-blink-features=ResponsiveIframes; the parent page served over
// http: a parent at about:blank (page.setContent) is not allowed by any source list, and every child then reads 150):
// 1. In a quirks-mode data: child a cross-origin stylesheet applies when it is text/css or has no Content-Type (no CORS
//    needed), or when the <link> has `crossorigin` and the response Access-Control-Allow-Origin (then any type: JSON,
//    text/plain, text/html). Without the header a CORS request fails even for text/css. Standards mode: text/css only.
//    An <object>'s fallback shows on a 404 and not on a 200. Memory-cache trap: the same URL fetched again in another
//    mode reuses the first response; give each test its own URL.
// 2. A data: or srcdoc child that opts in (content="*" in 153; allow-origins=* in 155+) reports its content height to
//    the page's frame-sizing iframe, also when it got there by a form GET. Each navigation resets the iframe to its
//    150 px default first (document_loader.cc, FrameResponsiveSizing::kHeight), so a smaller answer follows a larger
//    one; answers below 150 px read 150. The appended `?name=value` renders as a text line (+18 px) unless the action's
//    body ends with `<!--`.
// 3. End to end (form GET -> data: child -> <link crossorigin> to another origin answering JSON `#v{height:Npx}` ->
//    iframe height): N reaches the page 50-70 ms after the click.
// 4. data: URL navigation: 2,030 KB loads, 2,050 KB doesn't.
