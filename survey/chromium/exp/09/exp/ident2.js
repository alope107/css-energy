const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const fs = require('fs'), path = require('path'), url = require('url');
const P = n => `@property --${n.name}{syntax:'${n.syntax || '<integer>'}';inherits:${n.inherits ? 'true' : 'false'};initial-value:${n.init ?? 0}}`;
const html = (css, body) => `<!doctype html><meta charset="utf-8"><style>${css}</style><body>${body}</body>`;
const base = P({ name: 'op', syntax: '<number>', init: -99 }) + '.box{position:relative;width:300px;height:40px}.a{height:3px}.r{position:absolute;height:1px}';
const cases = {
  lit: [`<i id=x style='--m3:13;--op:var(ident("--m" 3))'></i>`, () => getComputedStyle(x).getPropertyValue('--op')],
  dyn: [`<i id=x style='--k:3;--m3:13;--op:var(ident("--m" var(--k)))'></i>`, () => getComputedStyle(x).getPropertyValue('--op')],
  aname: [`<div class=box><div class=a id=x style='anchor-name:ident("--a" 3);width:33px'></div><div class=r id=y style='width:anchor-size(--a3 width, 7px)'></div></div>`, () => y.getBoundingClientRect().width],
  anamedyn: [`<div class=box style='--k:3'><div class=a id=x style='anchor-name:ident("--a" var(--k));width:33px'></div><div class=r id=y style='width:anchor-size(--a3 width, 7px)'></div></div>`, () => y.getBoundingClientRect().width],
  asz: [`<div class=box style='--k:2'><div class=a style='anchor-name:--a2;width:22px'></div><div class=r id=y style='width:anchor-size(ident("--a" 2) width, 7px)'></div></div>`, () => y.getBoundingClientRect().width],
  aszdyn: [`<div class=box style='--k:2'><div class=a style='anchor-name:--a2;width:22px'></div><div class=r id=y style='width:anchor-size(ident("--a" var(--k)) width, 7px)'></div></div>`, () => y.getBoundingClientRect().width],
  cname: [`<style>@container b3 style(--q: 1){#y{--hit:1}}</style><div style='container-name:ident("b" 3);--q:1'><i id=y></i></div>`, () => getComputedStyle(y).getPropertyValue('--hit')],
  cnamedyn: [`<style>@container b3 style(--q: 1){#y{--hit:1}}</style><div style='--k:3;container-name:ident("b" var(--k));--q:1'><i id=y></i></div>`, () => getComputedStyle(y).getPropertyValue('--hit')],
  vtname: [`<style>@keyframes kk{from{--op:0}to{--op:100}}</style><div style='height:100px;overflow:scroll;timeline-scope:--t3'><div style='height:300px'></div><div style='--k:3;view-timeline-name:ident("--t" var(--k));height:10px'></div><div style='height:300px'></div><i id=y style='animation:kk linear both;animation-timeline:--t3'></i></div>`, () => getComputedStyle(y).getPropertyValue('--op')],
};
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', '--enable-blink-features=' + (process.argv[2] || 'CSSIdentFunction')] });
  const dir = fs.mkdtempSync(path.join(__dirname, 'p-'));
  for (const [k, [body, read]] of Object.entries(cases)) {
    const f = path.join(dir, k + '.html'); fs.writeFileSync(f, html(base, body));
    const p = await b.newPage();
    try { await p.goto(url.pathToFileURL(f).href); await p.waitForTimeout(150); console.log(k.padEnd(10), JSON.stringify(await p.evaluate(read))); } catch (e) { console.log(k.padEnd(10), 'ERR', String(e).split('\n')[0]); }
    await p.close().catch(() => {});
  }
  await b.close(); fs.rmSync(dir, { recursive: true });
})();
