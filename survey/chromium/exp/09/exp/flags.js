// probes for flagged features in Chromium 153: node flags.js "<blink features>" 
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const fs = require('fs'), path = require('path'), url = require('url');
const feats = process.argv[2] || '';
const P = n => `@property --${n.name}{syntax:'${n.syntax || '<integer>'}';inherits:${n.inherits ? 'true' : 'false'};initial-value:${n.init ?? 0}}`;
const html = (css, body) => `<!doctype html><meta charset="utf-8"><style>${css}</style><body>${body}</body>`;
const prop = (id, n) => getComputedStyle(document.getElementById(id)).getPropertyValue(n).trim();
const W = id => document.getElementById(id).getBoundingClientRect().width;
const only = (process.argv[3]||'').split(',').filter(Boolean);
const pages = {
  ident: [html(P({ name: 'op', syntax: '<number>', init: -99 }) + P({name:'k'}) +
    '.box{position:relative;width:300px;height:40px}.a{height:3px}.r{position:absolute;height:1px}' +
    '#cn{container-name:ident("b" var(--k))}@container b3 style(--q: 1){#cnq{--hit:1}}' ,
    `<i id=lit style='--m3:13;--op:var(ident("--m" 3))'></i>` +
    `<i id=dyn style='--k:3;--m3:13;--op:var(ident("--m" var(--k)))'></i>` +
    `<i id=plain style='--m3:13;--op:var(--m3)'></i>` +
    `<div class=box style='--k:2'><div class=a style='anchor-name:--a1;width:11px'></div><div class=a style='anchor-name:--a2;width:22px'></div><div class=a style='anchor-name:ident("--a" 3);width:33px'></div>` +
    `<div class=r id=asz style='width:anchor-size(ident("--a" var(--k)) width, 7px)'></div><div class=r id=asz3 style='width:anchor-size(--a3 width, 7px)'></div></div>` +
    `<div id=cn style='--k:3;--q:1'><i id=cnq></i></div>`),
    () => ({ lit: prop('lit', '--op'), dyn: prop('dyn', '--op'), plain: prop('plain', '--op'), aszDyn: W('asz'), asz3: W('asz3'), cq: prop('cnq', '--hit') })],
  inherit: [html(P({ name: 'a', init: 0 }) + P({ name: 'b', inherits: true }) + '#p{--a:5}#c{--b:calc(inherit(--a) + 1)}#c2{--b:inherit(--a, 9)}#c3{--u:inherit(--v)}#p{--v:4}',
    '<div id=p><i id=c></i><i id=c2></i><i id=c3></i></div>'),
    () => ({ c: prop('c', '--b'), c2: prop('c2', '--b'), c3: prop('c3', '--u') })],
  mixin: [html('@mixin --m(--w <length>: 5px){width:var(--w);height:1px}#x{@apply --m(17px);}#y{@apply --m;}',
    '<div id=x></div><div id=y></div>'), () => ({ x: W('x'), y: W('y') })],
  custommedia: [html('@custom-media --wide (width > 100px);#x{width:1px;height:1px}@media (--wide){#x{width:9px}}', '<div id=x></div>'), () => ({ x: W('x') })],
  random: [html(P({ name: 'r', syntax: '<number>' }) + P({ name: 's', syntax: '<number>' }) + 'i{--r:random(0, 1000);--s:random(--key, 0, 1000)}', '<i id=a></i><i id=b></i>'),
    () => ({ a: prop('a', '--r'), b: prop('b', '--r'), sa: prop('a', '--s'), sb: prop('b', '--s') })],
  fnrec: [html(P({ name: 'o', syntax: '<number>', init: -1 }) + '@function --f(--n <number>) returns <number> { result: if(style(--n <= 0): 0; else: calc(1 + --f(calc(var(--n) - 1)))); } #x{--o:--f(3)}', '<i id=x></i>'),
    () => ({ o: prop('x', '--o') })],
  stdsq: [html('i{--h:0}@container style(display: flex){i{--h:1}}', '<div style="display:flex"><i id=x></i></div>'), () => ({ h: prop('x', '--h') })],
  ifnum: [html(P({ name: 'o', syntax: '<number>', init: -1 }) + '#x{--v:7;--o:if(style(--v > 5): 1; else: 2)}', '<i id=x></i>'), () => ({ o: prop('x', '--o') })],
};
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', ...(feats ? [`--enable-blink-features=${feats}`] : [])] });
  const dir = fs.mkdtempSync(path.join(__dirname, 'p-'));
  for (const [k, [src, read]] of Object.entries(pages)) { if (only.length && !only.includes(k)) continue;
    const f = path.join(dir, k + '.html'); fs.writeFileSync(f, src);
    const p = await b.newPage(); await p.addInitScript(`window.prop=${prop};window.W=${W}`);
    try { await p.goto(url.pathToFileURL(f).href); await p.waitForTimeout(100); console.log(k.padEnd(12), JSON.stringify(await p.evaluate(read))); } catch (e) { console.log(k, 'ERR', String(e).split('\n')[0]); }
    await p.close();
  }
  await b.close(); fs.rmSync(dir, { recursive: true });
})();
