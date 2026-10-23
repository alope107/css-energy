// probe1.js — which requests can CSS fire, and what of a response reaches the page (harness only; exploratory).
//   node net/probe/probe1.js [--flags "..."]
const fs = require('fs'), path = require('path');
const B = require('../../tools/browser.js');
const { serve } = require('../server.js');
const ROOT = path.join(__dirname, '..', '..', 'build', 'netprobe');
fs.mkdirSync(ROOT, { recursive: true });
const X = (body, head = '') => `<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/>${head}</head><body>${body}</body></html>`;
const enc = encodeURIComponent;
const svg = (w, h) => enc(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"/>`);

const pages = {
  // A: an <object> under a display:none parent; the harness shows / hides the parent (#a.on)
  'a.xhtml': X(`
    <div id="a" class="off">
      <object id="o1" data="/r/o-html?ct=text/html&amp;body=hi">fb</object>
      <object id="o2" data="/r/o-svg?ct=image/svg+xml&amp;body=${svg(37, 5)}">fb</object>
      <object id="o3" data="/r/o-404?status=404&amp;ct=text/html"><span id="fb3">fallback</span></object>
      <object id="o4" data="/r/o-json?ct=application/json&amp;body=%7B%7D">fb</object>
      <object id="o5" data="/r/o-none?ct=none&amp;body=hello">fb</object>
      <iframe id="i1" src="/r/i-html?ct=text/html&amp;body=hi"></iframe>
      <iframe id="i2" loading="lazy" src="/r/i-lazy?ct=text/html&amp;body=hi"></iframe>
      <div style="font-family: f1">x</div>
    </div>`, `<style>
      .off { display: none } object, iframe { border: 0 }
      @font-face { font-family: f1; src: url(/r/font1?ct=font/woff2) }
    </style>`),
  // D: stylesheets in the XHTML page with various content types
  'd.xhtml': X(`<p id="p1">1</p><p id="p2">2</p><p id="p3">3</p><p id="p4">4</p>`, `
    <link rel="stylesheet" href="/r/css-none?ct=none&amp;body=${enc('#p1{width:11px}')}"/>
    <link rel="stylesheet" href="/r/css-json?ct=application/json&amp;body=${enc('#p2{width:12px}')}"/>
    <link rel="stylesheet" href="/r/css-css?ct=text/css&amp;body=${enc('#p3{width:13px}')}"/>
    <link rel="stylesheet" href="/r/css-plain?ct=text/plain&amp;body=${enc('#p4{width:14px}')}"/>`),
  // E: a quirks-mode HTML child (no doctype) loading non-CSS responses as stylesheets
  'e-child.html': `<html><head>
    <link rel="stylesheet" href="/r/q-json?ct=application/json&amp;body=${enc('#p1{width:21px}')}">
    <link rel="stylesheet" href="/r/q-plain?ct=text/plain&amp;body=${enc('#p2{width:22px}')}">
    <link rel="stylesheet" href="/r/q-html?ct=text/html&amp;body=${enc('#p3{width:23px}')}">
    <link rel="stylesheet" href="/r/q-nosniff?ct=application/json&amp;nosniff=1&amp;body=${enc('#p4{width:24px}')}">
    <link rel="stylesheet" href="/r/q-png?ct=image/png&amp;body=${enc('#p5{width:25px}')}">
    </head><body><p id="p1">1</p><p id="p2">2</p><p id="p3">3</p><p id="p4">4</p><p id="p5">5</p></body></html>`,
  'e.xhtml': X(`<iframe id="c" src="e-child.html"></iframe>`),
  // F: responsive iframe: a quirks child that opts in; its content height comes from a JSON-typed "stylesheet"
  'f-child.html': `<html><head><meta name="responsive-embedded-sizing" content="'self'">
    <link rel="stylesheet" href="/r/f-json?ct=application/json&amp;body=${enc('#v{height:345px}')}">
    <style>html,body{margin:0}</style></head><body><div id="v"></div></body></html>`,
  'f.xhtml': X(`<iframe id="c" src="f-child.html" style="frame-sizing: content-height; border: 0; width: 50px"></iframe>`),
};
for (const [n, s] of Object.entries(pages)) fs.writeFileSync(path.join(ROOT, n), s);

const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const srv = await serve(ROOT, 0), port = srv.address().port, base = `http://127.0.0.1:${port}/`;
  const extra = process.argv.includes('--flags') ? process.argv[process.argv.indexOf('--flags') + 1].split(' ') : [];
  const b = await B.launch({ extraArgs: extra });
  console.log('chrome', b.version(), extra.join(' '));
  const hits = async () => (await (await fetch(base + 'hits')).json()).map(h => h.name);
  const reset = () => fetch(base + 'reset');
  const p = await b.newPage();

  // A
  await reset(); await p.goto(base + 'a.xhtml'); await sleep(500);
  console.log('A hidden at load:', await hits());
  const show = async on => { await p.evaluate(on => document.getElementById('a').className = on ? '' : 'off', on); await sleep(500); };
  const sizes = () => p.evaluate(() => ['o1', 'o2', 'o3', 'o4', 'o5', 'fb3'].map(i => { const r = document.getElementById(i).getBoundingClientRect(); return `${i}:${r.width}x${r.height}`; }).join(' '));
  for (const [i, on] of [[1, true], [2, false], [3, true], [4, false], [5, true]].entries()) {
    await reset(); await show(on[1]); console.log(`A step ${on[0]} ${on[1] ? 'show' : 'hide'}:`, await hits(), on[1] ? await sizes() : '');
  }

  // D
  await reset(); await p.goto(base + 'd.xhtml'); await sleep(300);
  console.log('D XHTML stylesheets:', await p.evaluate(() => [1, 2, 3, 4].map(i => getComputedStyle(document.getElementById('p' + i)).width).join(' ')), await hits());

  // E
  await reset(); await p.goto(base + 'e.xhtml'); await sleep(500);
  const fr = p.frames()[1];
  console.log('E quirks child:', await fr.evaluate(() => document.compatMode + ' ' + [1, 2, 3, 4, 5].map(i => getComputedStyle(document.getElementById('p' + i)).width).join(' ')));

  // F
  await reset(); await p.goto(base + 'f.xhtml'); await sleep(800);
  console.log('F responsive iframe height:', await p.evaluate(() => document.getElementById('c').getBoundingClientRect().height));
  await b.close(); srv.close();
})().catch(e => { console.error(e); process.exit(1); });
