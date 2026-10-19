const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
function build(c) {
  let h = `<div id="f" style="display:flex;width:max-content;--seed:0">`;
  for (let i = 0; i < c.N; i++) h += `<div class="it" style="--i:${i};${c.order ? `order: calc(mod(var(--i) * 7919 + var(--seed), ${c.N}))` : ''};width:${(i%5)+1}px;height:2px${c.anchor ? `;anchor-name:--b${i}` : ''}"></div>`;
  h += '</div>';
  let r = '';
  if (c.readers) for (let i = 0; i < c.N; i++) r += `<div style="position:fixed;top:0;height:1px;left:anchor(--b${i} left);width:1px"></div>`;
  document.body.innerHTML = h + r;
  document.body.offsetWidth;
}
function run(iters) {
  const f = document.getElementById('f'); const t = [];
  for (let i = 0; i < iters; i++) {
    const t0 = performance.now();
    f.style.setProperty('--seed', String(i * 13 % 997));
    document.body.offsetWidth;
    t.push(performance.now() - t0);
  }
  t.sort((a, b) => a - b); return t[t.length >> 1];
}
(async () => {
  const browser = await chromium.launch({executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox']});
  const cases = {
    'N1000 no order': {N:1000}, 'N1000 order': {N:1000, order:true},
    'N1000 order+anchors': {N:1000, order:true, anchor:true}, 'N1000 order+anchors+readers': {N:1000, order:true, anchor:true, readers:true},
    'N10000 no order': {N:10000}, 'N10000 order': {N:10000, order:true}};
  for (const [n, c] of Object.entries(cases)) {
    const page = await browser.newPage();
    await page.setContent('<!doctype html><body></body>');
    await page.evaluate(build, c); await page.evaluate(run, 20);
    const m = await page.evaluate(run, 100);
    // check: the reader of item i sits at the prefix sum of widths before it in sorted order
    console.log(n.padEnd(30), m.toFixed(2), 'ms/pass');
    await page.close();
  }
  await browser.close();
})();
