const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
function build(c) {
  let h = `<style>#st{position:fixed;top:0;left:0;white-space:pre;font:16px monospace;width:${c.width}} #st>span::before{content:counter(c)} #st>span{counter-reset:c var(--v)}</style><div id="st">`;
  for (let i = 0; i < c.N; i++) h += `<span style="--v:${1000 + i}"></span>`;
  h += '</div><div id="drv" style="width:10px;height:1px"></div>';
  document.body.innerHTML = h; document.body.offsetWidth;
}
function run(a) {
  const [iters, mode] = a; const sp = document.querySelectorAll('#st>span'); const drv = document.getElementById('drv'); const t = [];
  for (let i = 0; i < iters; i++) {
    const t0 = performance.now();
    if (mode === 'one') sp[i % sp.length].style.setProperty('--v', String(1000 + (i & 7)));
    else drv.style.width = (10 + (i & 1)) + 'px';
    document.body.offsetWidth; t.push(performance.now() - t0);
  }
  t.sort((a, b) => a - b); return t[t.length >> 1];
}
(async () => {
  const browser = await chromium.launch({executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox']});
  for (const N of [150, 1274]) for (const width of ['max-content', '100000px']) for (const mode of ['none', 'one']) {
    const page = await browser.newPage(); await page.setContent('<!doctype html><body></body>');
    await page.evaluate(build, {N, width}); await page.evaluate(run, [20, mode]);
    const m = await page.evaluate(run, [150, mode]);
    console.log(`N=${N} width=${width} change=${mode}: ${m.toFixed(2)} ms/pass`); await page.close();
  }
  await browser.close();
})();
