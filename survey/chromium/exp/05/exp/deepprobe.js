const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
function build(c) {
  const b = document.body; b.innerHTML = '';
  const T = document.createElement('div'); T.style.cssText = 'contain:strict;position:relative;height:0;width:500px'; b.appendChild(T);
  let parent = T;
  for (let d = 0; d < c.depth; d++) { const x = document.createElement('div'); x.style.display = 'contents'; parent.appendChild(x); parent = x; }
  let h = '<b style="display:block;height:0;width:7px;anchor-name:--lab"></b>';
  for (let i = 0; i < c.M; i++) {
    const w = c.read ? 'calc(5px + anchor-size(--lab width, 0px))' : '5px';
    h += `<b style="position:fixed;top:0;left:0;height:1px;visibility:hidden;display:block;width:${w}${c.name ? `;anchor-name:--c${i}` : ''}"></b>`;
  }
  const tmp = document.createElement('div'); tmp.innerHTML = h; while (tmp.firstChild) parent.appendChild(tmp.firstChild);
  const drv = document.createElement('div'); drv.id = 'drv'; drv.style.cssText = 'width:10px;height:1px'; parent.appendChild(drv);
  document.body.offsetWidth;
}
function run(iters) {
  const drv = document.getElementById('drv'); const t = [];
  for (let i = 0; i < iters; i++) { const t0 = performance.now(); drv.style.width = (10 + (i & 1)) + 'px'; document.body.offsetWidth; t.push(performance.now() - t0); }
  t.sort((a, b) => a - b); return t[t.length >> 1];
}
(async () => {
  const browser = await chromium.launch({executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox']});
  const cases = {};
  for (const depth of [0, 2000]) for (const [k, v] of Object.entries({plain: {}, named: {name: true}, read: {read: true}, 'named+read': {name: true, read: true}})) cases[`d${depth} ${k}`] = {depth, M: 500, ...v};
  for (let r = 0; r < 2; r++) for (const [n, c] of Object.entries(cases)) {
    const page = await browser.newPage();
    await page.setContent('<!doctype html><body></body>');
    await page.evaluate(build, c); await page.evaluate(run, 20);
    const m = await page.evaluate(run, 150);
    console.log(r, n.padEnd(20), m.toFixed(2), 'ms/pass');
    await page.close();
  }
  await browser.close();
})();
