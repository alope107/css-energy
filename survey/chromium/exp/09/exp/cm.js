const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const fs = require('fs'), path = require('path'), url = require('url');
const css = {
  cm1: '@custom-media --wide (min-width: 100px);#x{width:1px;height:1px}@media (--wide){#x{width:9px}}',
  cm2: '@custom-media --wide screen;#x{width:1px;height:1px}@media (--wide){#x{width:9px}}',
  cm3: '@custom-media --t true;#x{width:1px;height:1px}@media (--t){#x{width:9px}}',
  mx1: '@mixin --m{width:9px;height:1px}#x{@apply --m;}',
  mx2: '@mixin --m(){width:9px;height:1px}#x{@apply --m();}',
  mx3: '@mixin --m{@result{width:9px;height:1px}}#x{@apply --m;}',
  mx4: '@mixin --m(--w){@result{width:var(--w);height:1px}}#x{@apply --m(9px);}',
  mx5: '@mixin --m(--w <length>: 9px){@result{width:var(--w);height:1px}}#x{@apply --m;}',
  mx6: '@mixin --m(--w){width:var(--w);height:1px}#x{@apply --m(9px);}',
  mx7: '@mixin --m{&{width:9px;height:1px}}#x{@apply --m;}',
};
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', '--enable-blink-features=CSSCustomMedia,CSSMixins'] });
  const dir = fs.mkdtempSync(path.join(__dirname, 'p-'));
  for (const [k, c] of Object.entries(css)) {
    const f = path.join(dir, k + '.html'); fs.writeFileSync(f, `<!doctype html><style>${c}</style><div id=x></div>`);
    const p = await b.newPage();
    try { await p.goto(url.pathToFileURL(f).href); console.log(k, await p.evaluate(() => x.getBoundingClientRect().width), await p.evaluate(() => [...document.styleSheets[0].cssRules].map(r => r.constructor.name + ':' + r.cssText.slice(0, 60)).join(' | '))); } catch (e) { console.log(k, 'ERR', String(e).split('\n')[0]); }
    await p.close();
  }
  await b.close(); fs.rmSync(dir, { recursive: true });
})();
