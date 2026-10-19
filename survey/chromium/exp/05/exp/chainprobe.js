const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
function build(c) {
  const st = document.createElement('style');
  st.textContent = `@property --v { syntax: "<number>"; inherits: true; initial-value: 0; } .l { display: contents; } .k { display: block; height: 0; } .l, .k { --w: calc(var(--v) + 1); }`;
  document.head.appendChild(st);
  const root = document.createElement('div'); root.id = 'root'; document.body.appendChild(root);
  let p = root;
  for (let d = 0; d < c.D; d++) { const x = document.createElement('div'); x.className = (c.K && d % c.K === c.K - 1) ? 'k' : 'l'; p.appendChild(x); p = x; }
  p.appendChild(document.createElement('i'));
  document.body.offsetWidth;
}
function run(iters) {
  const r = document.getElementById('root'); const t = [];
  for (let i = 0; i < iters; i++) { const t0 = performance.now(); r.style.setProperty('--v', String(i)); document.body.offsetWidth; t.push(performance.now() - t0); }
  t.sort((a, b) => a - b); return t[t.length >> 1];
}
(async () => {
  const browser = await chromium.launch({executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox']});
  for (let r = 0; r < 2; r++) for (const [n, c] of Object.entries({'D1561 all contents': {D: 1561}, 'D1561 block every 64': {D: 1561, K: 64}, 'D1561 block every 8': {D: 1561, K: 8}, 'D400 all contents': {D: 400}})) {
    const page = await browser.newPage(); await page.setContent('<!doctype html><html><head></head><body></body></html>');
    await page.evaluate(build, c); await page.evaluate(run, 10);
    const m = await page.evaluate(run, 60);
    console.log(r, n.padEnd(24), m.toFixed(2), 'ms per full-chain restyle'); await page.close();
  }
  await browser.close();
})();
